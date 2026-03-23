import pytest

from backend.services.conversation_service import update_semantic_memory
from backend.services.tts_service import TTSService


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
