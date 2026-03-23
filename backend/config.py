from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


# Load .env once for all backend modules.
load_dotenv()


_PLACEHOLDER_VALUES = {
    "",
    "replace-with-your-openai-key",
    "replace-with-strong-random-token",
    "change-me",
    "changeme",
    "default",
    "your-api-key",
}


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _as_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a valid integer.") from exc


def _is_placeholder(secret_value: str) -> bool:
    value = (secret_value or "").strip().lower()
    if value in _PLACEHOLDER_VALUES:
        return True

    return (
        "replace" in value
        or "example" in value
        or "dummy" in value
        or "test-key" in value
    )


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_chat_model: str
    redis_url: str
    session_ttl_seconds: int
    model_path: Path
    hf_intent_model_id: str
    whisper_model_size: str
    response_tone: str
    max_text_input_chars: int
    max_session_id_chars: int
    api_rate_limit_window_seconds: int
    api_rate_limit_max_requests: int
    api_key_rate_limit_max_requests: int
    max_request_size_bytes: int
    trust_proxy_headers: bool
    enable_api_key_auth: bool
    api_auth_key: str

    def validate_runtime(self) -> None:
        if not self.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for startup.")
        if _is_placeholder(self.openai_api_key):
            raise RuntimeError("OPENAI_API_KEY uses a placeholder/default value. Refusing startup.")

        parsed = urlparse(self.redis_url)
        if parsed.scheme not in {"redis", "rediss"}:
            raise RuntimeError("REDIS_URL must use redis:// or rediss:// scheme.")

        if self.session_ttl_seconds <= 0:
            raise RuntimeError("SESSION_TTL_SECONDS must be > 0.")
        if self.max_text_input_chars < 64:
            raise RuntimeError("MAX_TEXT_INPUT_CHARS must be >= 64.")
        if self.max_session_id_chars < 8:
            raise RuntimeError("MAX_SESSION_ID_CHARS must be >= 8.")
        if self.api_rate_limit_window_seconds <= 0:
            raise RuntimeError("API_RATE_LIMIT_WINDOW_SECONDS must be > 0.")
        if self.api_rate_limit_max_requests <= 0:
            raise RuntimeError("API_RATE_LIMIT_MAX_REQUESTS must be > 0.")
        if self.api_key_rate_limit_max_requests <= 0:
            raise RuntimeError("API_KEY_RATE_LIMIT_MAX_REQUESTS must be > 0.")
        if self.max_request_size_bytes <= 0:
            raise RuntimeError("MAX_REQUEST_SIZE_BYTES must be > 0.")

        if self.enable_api_key_auth:
            if not self.api_auth_key:
                raise RuntimeError("API_AUTH_KEY is required when ENABLE_API_KEY_AUTH=true.")
            if _is_placeholder(self.api_auth_key):
                raise RuntimeError("API_AUTH_KEY uses a placeholder/default value. Refusing startup.")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        openai_api_key=(os.getenv("OPENAI_API_KEY") or "").strip(),
        openai_chat_model=(os.getenv("OPENAI_CHAT_MODEL") or "gpt-4o-mini").strip(),
        redis_url=(os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip(),
        session_ttl_seconds=_as_int("SESSION_TTL_SECONDS", 86400),
        model_path=Path(os.getenv("MODEL_PATH", "./models/intent")).resolve(),
        hf_intent_model_id=(os.getenv("HF_INTENT_MODEL_ID") or "").strip(),
        whisper_model_size=(os.getenv("WHISPER_MODEL_SIZE") or "base").strip(),
        response_tone=(os.getenv("RESPONSE_TONE") or "assistant-like").strip().lower(),
        max_text_input_chars=_as_int("MAX_TEXT_INPUT_CHARS", 500),
        max_session_id_chars=_as_int("MAX_SESSION_ID_CHARS", 64),
        api_rate_limit_window_seconds=_as_int("API_RATE_LIMIT_WINDOW_SECONDS", 60),
        api_rate_limit_max_requests=_as_int("API_RATE_LIMIT_MAX_REQUESTS", 80),
        api_key_rate_limit_max_requests=_as_int("API_KEY_RATE_LIMIT_MAX_REQUESTS", 120),
        max_request_size_bytes=_as_int("MAX_REQUEST_SIZE_BYTES", 1048576),
        trust_proxy_headers=_as_bool(os.getenv("TRUST_PROXY_HEADERS"), False),
        enable_api_key_auth=_as_bool(os.getenv("ENABLE_API_KEY_AUTH"), False),
        api_auth_key=(os.getenv("API_AUTH_KEY") or "").strip(),
    )
