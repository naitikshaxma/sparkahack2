import pytest

from backend.core.config import Settings
from backend.container import get_container


def test_di_container_is_singleton() -> None:
    first = get_container()
    second = get_container()
    assert first is second
    assert first.intent_service is not None
    assert first.conversation_service is not None
    assert first.ocr_service is not None
    assert first.tts_service is not None
    assert first.stt_service is not None


def test_config_validation_rejects_placeholder_openai_key() -> None:
    settings = Settings(
        openai_api_key="replace-with-your-openai-key",
        openai_chat_model="gpt-4o-mini",
        redis_url="redis://localhost:6379/0",
        session_ttl_seconds=60,
        model_path=get_container().settings.model_path,
        hf_intent_model_id="",
        whisper_model_size="base",
        response_tone="assistant-like",
        max_text_input_chars=500,
        max_session_id_chars=64,
        api_rate_limit_window_seconds=60,
        api_rate_limit_max_requests=100,
        api_key_rate_limit_max_requests=120,
        max_request_size_bytes=1048576,
        trust_proxy_headers=False,
        enable_api_key_auth=False,
        api_auth_key="",
        database_url="postgresql://localhost:5432/testdb",
        jwt_secret_key="dev-jwt-secret-change-me",
        jwt_algorithm="HS256",
        jwt_expiration_minutes=60,
        jwt_required_for_protected_routes=False,
        jwt_protected_prefixes=("/api/private", "/api/v1/private"),
        frontend_dev_origin="http://127.0.0.1:5173",
        frontend_production_origin="https://voice-os-bharat.com",
        cors_allow_origins=("http://127.0.0.1:5173", "https://voice-os-bharat.com"),
    )

    with pytest.raises(RuntimeError):
        settings.validate_runtime()
