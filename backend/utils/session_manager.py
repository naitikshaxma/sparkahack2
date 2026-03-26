import asyncio
import json
import logging
import os
import threading
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, Optional

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    redis = None

from ..config import get_settings
from ..db import db_session_scope
from ..models.db_models import ConversationHistory, Session as DBSession
from ..auth import get_current_user_id
from sqlalchemy import text
from .form_schema import DEFAULT_SCHEME_NAME, get_fields_for_scheme, resolve_scheme_name
from .privacy import sanitize_session_payload

SETTINGS = get_settings()

REDIS_URL = SETTINGS.redis_url
SESSION_TTL_SECONDS = SETTINGS.session_ttl_seconds
SESSION_STORE_BACKEND = (os.getenv("SESSION_STORE_BACKEND") or "auto").strip().lower()

logger = logging.getLogger(__name__)

_ASYNC_LOCKS: Dict[tuple[int, str], asyncio.Lock] = {}
_ASYNC_LOCK_LAST_USED: Dict[tuple[int, str], float] = {}
_ASYNC_LOCK_GUARD = threading.Lock()
_MAX_ASYNC_LOCKS = max(100, int((os.getenv("MAX_ASYNC_LOCKS") or "4000").strip() or "4000"))


def _session_key(session_id: str) -> str:
    return (session_id or "").strip() or "anonymous"


def get_async_session_lock(session_id: str) -> asyncio.Lock:
    key = _session_key(session_id)
    loop_id = id(asyncio.get_running_loop())
    lock_key = (loop_id, key)
    with _ASYNC_LOCK_GUARD:
        lock = _ASYNC_LOCKS.get(lock_key)
        if lock is None:
            lock = asyncio.Lock()
            _ASYNC_LOCKS[lock_key] = lock
        _ASYNC_LOCK_LAST_USED[lock_key] = time.time()

        if len(_ASYNC_LOCKS) > _MAX_ASYNC_LOCKS:
            # Drop unlocked, least-recently-used locks.
            candidates = sorted(_ASYNC_LOCK_LAST_USED.items(), key=lambda item: item[1])
            for candidate_key, _ in candidates:
                candidate = _ASYNC_LOCKS.get(candidate_key)
                if candidate is None:
                    _ASYNC_LOCK_LAST_USED.pop(candidate_key, None)
                    continue
                if candidate.locked():
                    continue
                _ASYNC_LOCKS.pop(candidate_key, None)
                _ASYNC_LOCK_LAST_USED.pop(candidate_key, None)
                if len(_ASYNC_LOCKS) <= _MAX_ASYNC_LOCKS:
                    break
    return lock

class SessionStore(ABC):
    @abstractmethod
    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def set(self, session_id: str, session_data: Dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, session_id: str) -> None:
        raise NotImplementedError

    @property
    @abstractmethod
    def status(self) -> str:
        raise NotImplementedError


class MemorySessionStore(SessionStore):
    def __init__(self, ttl_seconds: int) -> None:
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._expires_at: Dict[str, float] = {}
        self._ttl_seconds = max(1, int(ttl_seconds))
        self._lock = threading.RLock()

    def _cleanup_expired_locked(self) -> None:
        now = time.time()
        expired_ids = [session_id for session_id, expiry in self._expires_at.items() if expiry <= now]
        for session_id in expired_ids:
            self._sessions.pop(session_id, None)
            self._expires_at.pop(session_id, None)

    def cleanup_expired(self) -> int:
        with self._lock:
            before = len(self._sessions)
            self._cleanup_expired_locked()
            return max(0, before - len(self._sessions))

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            self._cleanup_expired_locked()
            return self._sessions.get(session_id)

    def set(self, session_id: str, session_data: Dict[str, Any]) -> None:
        with self._lock:
            self._cleanup_expired_locked()
            self._sessions[session_id] = session_data
            self._expires_at[session_id] = time.time() + self._ttl_seconds

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)
            self._expires_at.pop(session_id, None)

    @property
    def status(self) -> str:
        return "memory"


class RedisSessionStore(SessionStore):
    def __init__(self, redis_url: str, ttl_seconds: int) -> None:
        if redis is None:
            raise RuntimeError("redis package is not installed")
        self._ttl = ttl_seconds
        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._client.ping()

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        raw = self._client.get(f"session:{session_id}")
        if not raw:
            return None
        return json.loads(raw)

    def set(self, session_id: str, session_data: Dict[str, Any]) -> None:
        self._client.setex(f"session:{session_id}", self._ttl, json.dumps(session_data))

    def delete(self, session_id: str) -> None:
        self._client.delete(f"session:{session_id}")

    @property
    def status(self) -> str:
        return "redis"


class SqlAlchemySessionStore(SessionStore):
    def __init__(self) -> None:
        with db_session_scope() as db:
            db.execute(text("SELECT 1"))

    def _utcnow(self) -> datetime:
        return datetime.now(timezone.utc)

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        with db_session_scope() as db:
            record = db.get(DBSession, session_id)
            if record is None:
                return None

            state = record.state_json if isinstance(record.state_json, dict) else {}
            state = dict(state)
            state["session_id"] = session_id
            if record.user_id is not None:
                state["user_id"] = str(record.user_id)

            history_rows = (
                db.query(ConversationHistory)
                .filter(ConversationHistory.session_id == session_id)
                .order_by(ConversationHistory.timestamp.asc())
                .all()
            )
            if history_rows:
                state["conversation_history"] = [
                    {
                        "role": row.role,
                        "content": row.message,
                    }
                    for row in history_rows
                ][-10:]

            return state

    def set(self, session_id: str, session_data: Dict[str, Any]) -> None:
        payload = dict(session_data)
        history_items = list(payload.get("conversation_history") or [])

        with db_session_scope() as db:
            record = db.get(DBSession, session_id)
            if record is None:
                record = DBSession(
                    session_id=session_id,
                    state_json=payload,
                    updated_at=self._utcnow(),
                )
                db.add(record)
            else:
                record.state_json = payload
                record.updated_at = self._utcnow()

            user_id = str(payload.get("user_id") or "").strip()
            if user_id.isdigit():
                record.user_id = int(user_id)

            db.flush()

            db.query(ConversationHistory).filter(ConversationHistory.session_id == session_id).delete(synchronize_session=False)
            for item in history_items[-50:]:
                role = str(item.get("role") or "assistant").strip()[:32]
                message = str(item.get("content") or item.get("message") or "").strip()
                if not message:
                    continue
                db.add(
                    ConversationHistory(
                        session_id=session_id,
                        role=role,
                        message=message,
                        timestamp=self._utcnow(),
                    )
                )

    def delete(self, session_id: str) -> None:
        with db_session_scope() as db:
            db.query(ConversationHistory).filter(ConversationHistory.session_id == session_id).delete(synchronize_session=False)
            record = db.get(DBSession, session_id)
            if record is not None:
                db.delete(record)

    @property
    def status(self) -> str:
        return "postgresql"


def _build_store() -> SessionStore:
    if SESSION_STORE_BACKEND in {"postgres", "postgresql", "sqlalchemy", "db"}:
        logger.info("Session store backend forced to postgresql")
        return SqlAlchemySessionStore()

    if SESSION_STORE_BACKEND == "memory":
        logger.info("Session store backend forced to memory")
        return MemorySessionStore(SESSION_TTL_SECONDS)

    if SESSION_STORE_BACKEND == "redis":
        return RedisSessionStore(REDIS_URL, SESSION_TTL_SECONDS)

    try:
        return SqlAlchemySessionStore()
    except Exception:
        logger.warning("PostgreSQL unavailable, trying redis session store")

    try:
        return RedisSessionStore(REDIS_URL, SESSION_TTL_SECONDS)
    except Exception:
        logger.warning("Redis unavailable, using in-memory session store")
        return MemorySessionStore(SESSION_TTL_SECONDS)


_store: SessionStore = _build_store()


def _default_session(session_id: str) -> Dict[str, Any]:
    selected_scheme = resolve_scheme_name(DEFAULT_SCHEME_NAME)
    dynamic_fields = get_fields_for_scheme(selected_scheme)
    first_field = dynamic_fields[0] if dynamic_fields else None
    return {
        "session_id": session_id,
        "form_type": "loan_application",
        "selected_scheme": selected_scheme,
        "language": "en",
        "user_profile": {},
        "user_need_profile": {
            "user_type": None,
            "income_range": None,
            "need_category": None,
        },
        "field_completion": {field: False for field in dynamic_fields},
        "next_field": first_field,
        "conversation_history": [],
        "history_summary": "",
        "onboarding_done": False,
        "past_need_confidence": None,
        "rejected_schemes": [],
        "accepted_scheme": None,
        "last_recommendation_reason": None,
        "learning_profile": {
            "rejected_counts": {},
            "accepted_counts": {},
        },
        "last_completed_field_index": -1,
        "confirmation_done": False,
        "confirmation_state": "pending",
        "session_complete": False,
        "user_id": None,
        "created_at": time.time(),
        "updated_at": time.time(),
    }


def _attach_user_context(session_data: Dict[str, Any]) -> Dict[str, Any]:
    current_user_id = get_current_user_id()
    if current_user_id and str(session_data.get("user_id") or "").strip() != current_user_id:
        session_data["user_id"] = current_user_id
    return session_data


def create_session(session_id: str) -> Dict[str, Any]:
    session = _attach_user_context(_default_session(session_id))
    _store.set(session_id, session)
    logger.info("Session created: %s", session_id)
    return session


def get_session(session_id: str) -> Dict[str, Any]:
    session = _store.get(session_id)
    if not session:
        return create_session(session_id)
    before_user = str(session.get("user_id") or "").strip()
    session = _attach_user_context(session)
    after_user = str(session.get("user_id") or "").strip()
    if after_user != before_user:
        _store.set(session_id, session)
    return session


def update_session(session_id: str, session_data: Dict[str, Any]) -> Dict[str, Any]:
    session_data = _attach_user_context(sanitize_session_payload(session_data))
    session_data["updated_at"] = time.time()
    _store.set(session_id, session_data)
    return session_data


def delete_session(session_id: str) -> None:
    _store.delete(session_id)


def get_session_store_status() -> str:
    return _store.status


def cleanup_expired_sessions() -> int:
    if isinstance(_store, MemorySessionStore):
        return _store.cleanup_expired()
    return 0
