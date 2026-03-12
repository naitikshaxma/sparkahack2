import base64
import re
import subprocess
import sys
import time
from io import BytesIO
from pathlib import Path

import requests
from gtts import gTTS


ROOT = Path(__file__).resolve().parent.parent
BACKEND_PORT = 8011
BACKEND_URL = f"http://127.0.0.1:{BACKEND_PORT}"


def wait_for_backend(timeout_seconds: int = 120) -> dict:
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        try:
            response = requests.get(f"{BACKEND_URL}/health", timeout=5)
            if response.status_code == 200:
                return response.json()
            last_error = f"Unexpected status: {response.status_code}"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(1)
    raise RuntimeError(f"Backend did not become healthy in time. Last error: {last_error}")


def build_hindi_test_audio(text: str) -> bytes:
    buffer = BytesIO()
    tts = gTTS(text=text, lang="hi")
    tts.write_to_fp(buffer)
    return buffer.getvalue()


def run_pipeline_test() -> None:
    backend_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(BACKEND_PORT)],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        health = wait_for_backend()
        if not health.get("whisper", {}).get("model_loaded"):
            raise RuntimeError("Whisper did not load correctly.")
        if not health.get("intent_model", {}).get("loaded"):
            raise RuntimeError("BERT model did not load correctly.")
        if int(health.get("rag", {}).get("total_schemes", 0)) != 500:
            raise RuntimeError("RAG dataset did not load with 500 schemes.")

        query = "pm kisan scheme kya hai"
        payload = None
        last_transcript = ""

        for _ in range(5):
            audio_bytes = build_hindi_test_audio(query)
            response = requests.post(
                f"{BACKEND_URL}/api/process-audio",
                files={"audio": ("query.mp3", audio_bytes, "audio/mpeg")},
                data={"user_id": "local-audit-user", "language": "hi"},
                timeout=300,
            )
            response.raise_for_status()
            payload = response.json()

            response_text_probe = payload.get("response_text", {})
            joined_probe = (
                str(response_text_probe.get("confirmation", "")).lower()
                + " "
                + str(response_text_probe.get("explanation", "")).lower()
            )
            last_transcript = str(payload.get("transcript", ""))
            if "pm kisan" in joined_probe:
                break
        else:
            raise RuntimeError(
                "Expected PM Kisan scheme response, but PM Kisan was not detected in response text. "
                f"Last transcript: {last_transcript.encode('unicode_escape').decode('ascii')}"
            )

        required_top_level = {"transcript", "intent", "confidence", "response_text", "audio_base64"}
        missing_top_level = required_top_level - set(payload.keys())
        if missing_top_level:
            raise RuntimeError(f"Missing response fields: {sorted(missing_top_level)}")

        response_text = payload["response_text"]
        required_response_fields = {"confirmation", "explanation", "next_step"}
        missing_response_fields = required_response_fields - set(response_text.keys())
        if missing_response_fields:
            raise RuntimeError(f"Missing response_text fields: {sorted(missing_response_fields)}")

        if not isinstance(payload["audio_base64"], str) or not payload["audio_base64"].startswith("data:audio/mp3;base64,"):
            raise RuntimeError("audio_base64 is missing expected mp3 base64 data URI.")

        b64_part = payload["audio_base64"].split(",", 1)[1]
        base64.b64decode(b64_part)

        hindi_text = " ".join([response_text["confirmation"], response_text["explanation"], response_text["next_step"]])
        if not re.search(r"[\u0900-\u097F]", hindi_text):
            raise RuntimeError("Expected Hindi response text for Hindi query, but Hindi characters were not found.")
        print("Local pipeline test passed.")
        print(f"Transcript: {payload['transcript']}")
        print(f"Intent: {payload['intent']}")
        print(f"Confidence: {payload['confidence']}")
        safe_confirmation = response_text["confirmation"].encode("unicode_escape").decode("ascii")
        print(f"Hindi response (unicode-escaped): {safe_confirmation}")
    finally:
        backend_process.terminate()
        try:
            backend_process.wait(timeout=10)
        except Exception:  # noqa: BLE001
            backend_process.kill()


if __name__ == "__main__":
    run_pipeline_test()
