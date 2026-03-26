import json
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from backend.services.conversation_service import update_semantic_memory
from backend.services.tts_service import TTSService
from backend.routes.voice_routes import process_text_stream
from backend.validators.input_validator import InputValidator


class _StubIntentService:
    async def detect_async(self, text, debug=False, timings=None):
        return {"intent": "scheme_query", "confidence": 0.92}


class _StubConversationService:
    def process(self, session_id, user_input, language, debug=False):
        return {
            "session_id": session_id,
            "response_text": "Here is the response.",
            "voice_text": "Here is the response.",
            "field_name": None,
            "validation_passed": True,
            "validation_error": None,
            "session_complete": False,
            "mode": "info",
            "action": "ask_to_apply_or_more_info",
            "steps_done": 0,
            "steps_total": 0,
            "completed_fields": [],
            "scheme_details": None,
            "recommended_schemes": [],
            "user_profile": {},
            "quick_actions": [],
            "primary_intent": "scheme_query",
            "secondary_intents": [],
            "intent_debug": {"confidence": 0.92},
        }


class _FailingConversationService:
    def process(self, session_id, user_input, language, debug=False):
        raise RuntimeError("conversation_failed")


class _StubTtsService:
    async def synthesize_async(self, text, language, timings=None):
        return "ZHVtbXk="


def _build_request() -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/process-text-stream",
        "headers": [],
        "client": ("127.0.0.1", 5001),
    }
    request = Request(scope)
    request.state.request_id = "test-stream-1"
    request.state.timings = {}
    return request


def _build_container(conversation_service):
    return SimpleNamespace(
        settings=SimpleNamespace(max_session_id_chars=64, response_tone="assistant-like"),
        intent_service=_StubIntentService(),
        conversation_service=conversation_service,
        tts_service=_StubTtsService(),
        input_validator=InputValidator(max_chars=500),
    )


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_streaming_tts_stops_on_interrupt(monkeypatch):
    monkeypatch.setattr("backend.services.tts_service.generate_tts_bytes", lambda text, language: f"chunk:{text}".encode("utf-8"))

    service = TTSService()
    calls = {"count": 0}

    def interrupted() -> bool:
        calls["count"] += 1
        return calls["count"] > 1

    data = []
    async for chunk in service.stream_synthesize_async(
        "First sentence. Second sentence. Third sentence.",
        "en",
        interrupted=interrupted,
        timings={},
    ):
        data.append(chunk)

    assert len(data) == 1
    assert data[0].startswith(b"chunk:")


def test_semantic_memory_records_intents_and_entities():
    session = {}
    response = {
        "response_text": "PM Kisan eligibility requires income criteria.",
        "voice_text": "PM Kisan eligibility shared.",
    }

    update_semantic_memory(
        session,
        "Tell me PM Kisan for aadhaar 123412341234",
        response,
        "scheme_query",
    )

    memory = session.get("semantic_memory", [])
    assert len(memory) == 1
    assert memory[0]["intent"] == "scheme_query"
    assert "pm kisan" in memory[0]["entities"]["schemes"]
    assert "123412341234" in memory[0]["entities"]["numbers"]


def test_semantic_memory_keeps_recent_window():
    session = {}
    for idx in range(20):
        update_semantic_memory(
            session,
            f"Need scheme info {idx}",
            {"response_text": f"response {idx}", "voice_text": f"voice {idx}"},
            "scheme_query",
        )

    memory = session.get("semantic_memory", [])
    assert len(memory) <= 12
    assert memory[-1]["assistant_summary"].startswith("voice 19")


@pytest.mark.anyio
async def test_process_text_stream_emits_meta_audio_done():
    request = _build_request()
    container = _build_container(_StubConversationService())

    response = await process_text_stream(
        request,
        text="Need information",
        user_id="",
        session_id="stream-1",
        language="en",
        x_language=None,
        debug=False,
        container=container,
    )

    lines = []
    async for chunk in response.body_iterator:
        lines.extend([line for line in chunk.decode("utf-8").splitlines() if line.strip()])

    types = [json.loads(line).get("type") for line in lines]
    assert types[0] == "meta"
    assert "audio_chunk" in types
    assert types[-1] == "done"


@pytest.mark.anyio
async def test_process_text_stream_emits_done_on_failure():
    request = _build_request()
    container = _build_container(_FailingConversationService())

    response = await process_text_stream(
        request,
        text="Need information",
        user_id="",
        session_id="stream-2",
        language="en",
        x_language=None,
        debug=False,
        container=container,
    )

    lines = []
    async for chunk in response.body_iterator:
        lines.extend([line for line in chunk.decode("utf-8").splitlines() if line.strip()])

    types = [json.loads(line).get("type") for line in lines]
    assert types[0] == "meta"
    assert types[-1] == "done"
