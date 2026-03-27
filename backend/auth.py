from __future__ import annotations

import base64
import hashlib
import hmac
import json
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, Request

from backend.infrastructure.database.connection import db_session_scope
from .models.db_models import User

_CURRENT_USER_ID: ContextVar[str] = ContextVar("current_user_id", default="")


def set_current_user_id(user_id: str) -> None:
    _CURRENT_USER_ID.set((user_id or "").strip())


def get_current_user_id() -> str:
    return (_CURRENT_USER_ID.get() or "").strip()


def clear_current_user_id() -> None:
    _CURRENT_USER_ID.set("")


def extract_bearer_token(authorization_header: str) -> str:
    value = (authorization_header or "").strip()
    if not value.lower().startswith("bearer "):
        return ""
    return value[7:].strip()


def create_access_token(subject: str, email: str, secret_key: str, algorithm: str, expires_minutes: int) -> str:
    if algorithm.upper() != "HS256":
        raise HTTPException(status_code=500, detail="Unsupported JWT algorithm")

    expiry = datetime.now(timezone.utc) + timedelta(minutes=max(1, expires_minutes))
    payload = {
        "sub": str(subject),
        "email": (email or "").strip().lower(),
        "exp": int(expiry.timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
    }
    header = {"alg": "HS256", "typ": "JWT"}

    def _b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")

    encoded_header = _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    encoded_payload = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{encoded_header}.{encoded_payload}".encode("utf-8")
    signature = hmac.new(secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    encoded_signature = _b64url(signature)
    return f"{encoded_header}.{encoded_payload}.{encoded_signature}"


def decode_access_token(token: str, secret_key: str, algorithm: str) -> dict[str, Any]:
    if algorithm.upper() != "HS256":
        raise HTTPException(status_code=500, detail="Unsupported JWT algorithm")

    parts = (token or "").split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    header_b64, payload_b64, signature_b64 = parts

    def _b64url_decode(value: str) -> bytes:
        padded = value + "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(padded.encode("utf-8"))

    try:
        header = json.loads(_b64url_decode(header_b64).decode("utf-8"))
        decoded = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        provided_signature = _b64url_decode(signature_b64)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    if header.get("alg") != "HS256":
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    expected_signature = hmac.new(secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(provided_signature, expected_signature):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    exp = int(decoded.get("exp") or 0)
    now_ts = int(datetime.now(timezone.utc).timestamp())
    if exp and now_ts >= exp:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    subject = str(decoded.get("sub") or "").strip()
    if not subject:
        raise HTTPException(status_code=401, detail="Invalid token subject")
    return decoded


def get_authenticated_user(request: Request) -> User:
    user_id = str(getattr(request.state, "user_id", "") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    with db_session_scope() as db:
        user = db.get(User, int(user_id)) if user_id.isdigit() else None
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        return user
