import json
import logging
import os
import threading
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import redis

from ..config import get_settings
from .form_schema import LOAN_FIELDS
from .privacy import sanitize_session_payload

SETTINGS = get_settings()

REDIS_URL = SETTINGS.redis_url
SESSION_TTL_SECONDS = SETTINGS.session_ttl_seconds
SESSION_STORE_BACKEND = (os.getenv("SESSION_STORE_BACKEND") or "auto").strip().lower()

logger = logging.getLogger(__name__)

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


def _build_store() -> SessionStore:
    if SESSION_STORE_BACKEND == "memory":
        logger.info("Session store backend forced to memory")
        return MemorySessionStore(SESSION_TTL_SECONDS)

    if SESSION_STORE_BACKEND == "redis":
        return RedisSessionStore(REDIS_URL, SESSION_TTL_SECONDS)

    try:
        return RedisSessionStore(REDIS_URL, SESSION_TTL_SECONDS)
    except Exception:
        logger.warning("Redis unavailable, using in-memory session store")
        return MemorySessionStore(SESSION_TTL_SECONDS)


_store: SessionStore = _build_store()


def _default_session(session_id: str) -> Dict[str, Any]:
    first_field = LOAN_FIELDS[0] if LOAN_FIELDS else None
    return {
        "session_id": session_id,
        "form_type": "loan_application",
        "language": "en",
        "user_profile": {},
        "field_completion": {field: False for field in LOAN_FIELDS},
        "next_field": first_field,
        "conversation_history": [],
        "last_completed_field_index": -1,
        "confirmation_done": False,
        "confirmation_state": "pending",
        "session_complete": False,
        "created_at": time.time(),
        "updated_at": time.time(),
    }


def create_session(session_id: str) -> Dict[str, Any]:
    session = _default_session(session_id)
    _store.set(session_id, session)
    logger.info("Session created: %s", session_id)
    return session


def get_session(session_id: str) -> Dict[str, Any]:
    session = _store.get(session_id)
    if not session:
        return create_session(session_id)
    return session


def update_session(session_id: str, session_data: Dict[str, Any]) -> Dict[str, Any]:
    session_data = sanitize_session_payload(session_data)
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
