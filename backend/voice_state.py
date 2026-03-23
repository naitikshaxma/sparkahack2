from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass
class SessionVoiceState:
    state: str = "idle"
    interrupted: bool = False


_LOCK = threading.RLock()
_STATE: dict[str, SessionVoiceState] = {}


def _get_or_create(session_id: str) -> SessionVoiceState:
    key = (session_id or "").strip() or "anonymous"
    with _LOCK:
        value = _STATE.get(key)
        if value is None:
            value = SessionVoiceState()
            _STATE[key] = value
        return value


def set_voice_state(session_id: str, state: str) -> None:
    with _LOCK:
        current = _get_or_create(session_id)
        current.state = state
        if state != "interrupted":
            current.interrupted = False


def interrupt_voice(session_id: str) -> None:
    with _LOCK:
        current = _get_or_create(session_id)
        current.interrupted = True
        current.state = "interrupted"


def clear_interrupt(session_id: str) -> None:
    with _LOCK:
        current = _get_or_create(session_id)
        current.interrupted = False
        if current.state == "interrupted":
            current.state = "idle"


def is_interrupted(session_id: str) -> bool:
    with _LOCK:
        current = _get_or_create(session_id)
        return bool(current.interrupted)


def get_voice_state(session_id: str) -> dict:
    with _LOCK:
        current = _get_or_create(session_id)
        return {
            "state": current.state,
            "interrupted": current.interrupted,
        }
