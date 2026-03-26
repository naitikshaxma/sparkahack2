import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterator

import pytest
import requests


ROOT = Path(__file__).resolve().parent.parent
TEST_PORT = 8124
BASE_URL = f"http://127.0.0.1:{TEST_PORT}"


def wait_for_backend(timeout_seconds: int = 120) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            response = requests.get(f"{BASE_URL}/health", timeout=5)
            if response.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError("Backend did not become healthy in time")


@pytest.fixture(scope="module", autouse=True)
def backend_server() -> Iterator[None]:
    env = dict(os.environ)
    env["ENABLE_API_KEY_AUTH"] = "false"

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(TEST_PORT),
        ],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        wait_for_backend()
        yield
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except Exception:
            process.kill()


def _parse_stream_lines(response):
    records = []
    for line in response.iter_lines(decode_unicode=True):
        if not line:
            continue
        records.append(json.loads(line))
    return records


def test_health_endpoint_valid() -> None:
    response = requests.get(f"{BASE_URL}/health", timeout=10)
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("status") == "ok"


def test_process_text_valid_request() -> None:
    response = requests.post(
        f"{BASE_URL}/api/process-text",
        data={"session_id": "api-test-1", "language": "en", "text": "Need information"},
        timeout=30,
    )
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload.get("response_text"), str)
    assert payload.get("mode") in {"info", "action", "clarify"}


def test_process_text_invalid_input() -> None:
    response = requests.post(
        f"{BASE_URL}/api/process-text",
        data={"session_id": "api-test-2", "language": "en", "text": ""},
        timeout=15,
    )
    assert response.status_code in {400, 422}


def test_process_text_stream_event_sequence() -> None:
    with requests.post(
        f"{BASE_URL}/api/process-text-stream",
        data={"session_id": "stream-api-1", "language": "en", "text": "Need info"},
        timeout=45,
        stream=True,
    ) as response:
        assert response.status_code == 200
        events = _parse_stream_lines(response)

    event_types = [item.get("type") for item in events]
    assert event_types[0] == "meta"
    assert "audio_chunk" in event_types
    assert event_types[-1] == "done"


def test_tts_valid_request() -> None:
    response = requests.post(
        f"{BASE_URL}/api/tts",
        json={"text": "Hello", "language": "en"},
        timeout=20,
    )
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload.get("audio_base64"), str)


def test_intent_valid_and_invalid_json() -> None:
    valid = requests.post(f"{BASE_URL}/api/intent", json={"text": "loan eligibility"}, timeout=15)
    assert valid.status_code == 200
    assert isinstance(valid.json().get("intent"), str)

    invalid = requests.post(
        f"{BASE_URL}/api/intent",
        data="{bad json",
        headers={"content-type": "application/json"},
        timeout=15,
    )
    assert invalid.status_code >= 400


def test_edge_cases_long_input_and_rapid_requests() -> None:
    very_long = "a" * 5000
    long_response = requests.post(
        f"{BASE_URL}/api/process-text",
        data={"session_id": "edge-long-1", "language": "en", "text": very_long},
        timeout=30,
    )
    assert long_response.status_code in {400, 413}

    statuses = []
    for idx in range(8):
        response = requests.post(
            f"{BASE_URL}/api/process-text",
            data={"session_id": "edge-rapid-1", "language": "en", "text": f"Need help {idx}"},
            timeout=20,
        )
        statuses.append(response.status_code)

    assert any(code == 200 for code in statuses)
    assert all(code < 500 for code in statuses)
