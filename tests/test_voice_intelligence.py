import uuid

from backend.tts_service import split_tts_chunks
from backend.utils.language import detect_input_language
from backend.utils.personality import apply_tone, normalize_tone
from backend.voice_state import clear_interrupt, get_voice_state, interrupt_voice, is_interrupted, set_voice_state
from backend.routes.voice_routes import tts_interrupt


def test_detect_input_language_handles_hinglish_tokens():
    assert detect_input_language("kya loan scheme hai") == "hi"
    assert detect_input_language("what is the pension scheme") == "hi"


def test_detect_input_language_handles_english_text():
    assert detect_input_language("please help me apply") == "en"


def test_personality_tone_normalization_and_application():
    assert normalize_tone("friendly") == "friendly"
    assert normalize_tone("unknown") == "assistant-like"
    assert apply_tone("Your form is ready", "formal", "en").startswith("Kindly note: ")
    assert apply_tone("Aapka form ready hai", "assistant-like", "hi").startswith("सहायक: ")


def test_voice_state_interruption_cycle():
    session_id = f"test-session-{uuid.uuid4().hex}"

    set_voice_state(session_id, "processing")
    current = get_voice_state(session_id)
    assert current["state"] == "processing"
    assert current["interrupted"] is False

    interrupt_voice(session_id)
    assert is_interrupted(session_id) is True
    interrupted = get_voice_state(session_id)
    assert interrupted["state"] == "interrupted"

    clear_interrupt(session_id)
    cleared = get_voice_state(session_id)
    assert cleared["state"] == "idle"
    assert cleared["interrupted"] is False


def test_tts_interrupt_marks_state():
    session_id = f"interrupt-route-{uuid.uuid4().hex}"
    response = tts_interrupt(session_id=session_id)
    assert response.get("interrupted") is True
    state = get_voice_state(session_id)
    assert state["state"] == "interrupted"


def test_tts_chunking_splits_long_text():
    text = " ".join(["This is a sentence."] * 30)
    chunks = split_tts_chunks(text, max_chars=80)

    assert len(chunks) > 1
    assert all(len(chunk) <= 80 for chunk in chunks)
