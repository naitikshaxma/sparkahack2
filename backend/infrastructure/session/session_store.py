from __future__ import annotations

import asyncio
from typing import Any, Dict

from ...utils import session_manager as legacy_session_manager


def get_async_session_lock(session_id: str) -> asyncio.Lock:
    return legacy_session_manager.get_async_session_lock(session_id)


def create_session(session_id: str) -> Dict[str, Any]:
    return legacy_session_manager.create_session(session_id)


def get_session(session_id: str) -> Dict[str, Any]:
    return legacy_session_manager.get_session(session_id)


def update_session(session_id: str, session_data: Dict[str, Any]) -> Dict[str, Any]:
    return legacy_session_manager.update_session(session_id, session_data)


def delete_session(session_id: str) -> None:
    return legacy_session_manager.delete_session(session_id)


def get_session_store_status() -> str:
    return legacy_session_manager.get_session_store_status()


def cleanup_expired_sessions() -> int:
    return legacy_session_manager.cleanup_expired_sessions()
