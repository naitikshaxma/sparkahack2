import subprocess
import sys
import time
from pathlib import Path

import requests


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


def run_pipeline_test() -> None:
    backend_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(BACKEND_PORT)],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        health = wait_for_backend()
        if health.get("status") != "ok":
            raise RuntimeError(f"Unexpected health status: {health}")

        if not health.get("whisper", {}).get("model_loaded"):
            raise RuntimeError("Whisper did not load correctly.")

        intent_model = health.get("intent_model")
        if isinstance(intent_model, dict):
            intent_model_status = str(intent_model.get("status") or "").strip().lower()
        else:
            intent_model_status = str(intent_model or "").strip().lower()

        if intent_model_status not in {"loaded", "fallback"}:
            raise RuntimeError(f"Unexpected intent_model status: {intent_model}")

        if int(health.get("rag", {}).get("total_schemes", 0)) != 500:
            raise RuntimeError("RAG dataset did not load with 500 schemes.")

        process_response = requests.post(
            f"{BACKEND_URL}/api/process-text",
            data={"session_id": "local-audit-user", "language": "hi", "text": "मुझे जानकारी चाहिए"},
            timeout=120,
        )
        process_response.raise_for_status()
        payload = process_response.json()

        required_top_level = {"session_id", "response_text", "mode", "quick_actions", "audio_base64"}
        missing_top_level = required_top_level - set(payload.keys())
        if missing_top_level:
            raise RuntimeError(f"Missing response fields: {sorted(missing_top_level)}")

        response_text = payload["response_text"]
        if not isinstance(response_text, str) or not response_text.strip():
            raise RuntimeError("response_text must be a non-empty string.")

        quick_actions = payload.get("quick_actions", [])
        if quick_actions and not all(isinstance(item, dict) and "label" in item and "value" in item for item in quick_actions):
            raise RuntimeError("quick_actions must contain objects with label/value.")

        audio_base64 = payload.get("audio_base64")
        if audio_base64 is not None:
            if not isinstance(audio_base64, str) or not audio_base64.startswith("data:audio/mp3;base64,"):
                raise RuntimeError("audio_base64 is missing expected mp3 base64 data URI.")
        else:
            print("audio_base64 missing; TTS fallback likely used.")

        intent_response = requests.post(
            f"{BACKEND_URL}/api/intent",
            json={"text": "check my application status"},
            timeout=30,
        )
        intent_response.raise_for_status()
        intent_payload = intent_response.json()
        if "intent" not in intent_payload or "confidence" not in intent_payload:
            raise RuntimeError("Intent endpoint response missing intent/confidence fields.")

        print("Local pipeline test passed.")
        print(f"Session ID: {payload['session_id']}")
        print(f"Mode: {payload.get('mode')}")
        safe_response_text = response_text.encode("unicode_escape").decode("ascii")
        print(f"Response text (unicode-escaped): {safe_response_text}")
    finally:
        backend_process.terminate()
        try:
            backend_process.wait(timeout=10)
        except Exception:  # noqa: BLE001
            backend_process.kill()


if __name__ == "__main__":
    run_pipeline_test()
