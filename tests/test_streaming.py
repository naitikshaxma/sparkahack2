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
TEST_PORT = 8125
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


def _stream_events(response):
    events = []
    for line in response.iter_lines(decode_unicode=True):
        if not line:
            continue
        events.append(json.loads(line))
    return events


def test_streaming_event_order() -> None:
    with requests.post(
        f"{BASE_URL}/api/process-text-stream",
        data={"session_id": "stream-flow-1", "language": "en", "text": "show schemes"},
        timeout=45,
        stream=True,
    ) as response:
        assert response.status_code == 200
        events = _stream_events(response)

    types = [evt.get("type") for evt in events]
    assert types[0] == "meta"
    assert "audio_chunk" in types
    assert types[-1] == "done"


def test_streaming_no_premature_termination() -> None:
    with requests.post(
        f"{BASE_URL}/api/process-text-stream",
        data={"session_id": "stream-flow-2", "language": "en", "text": "Need a farming scheme recommendation"},
        timeout=45,
        stream=True,
    ) as response:
        events = _stream_events(response)

    assert len(events) >= 2
    assert events[-1].get("type") == "done"


def test_streaming_interrupt_behavior() -> None:
    session_id = "stream-flow-3"
    with requests.post(
        f"{BASE_URL}/api/process-text-stream",
        data={"session_id": session_id, "language": "en", "text": "Read details slowly"},
        timeout=45,
        stream=True,
    ) as response:
        first_lines = []
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            first_lines.append(json.loads(line))
            if len(first_lines) >= 2:
                requests.post(
                    f"{BASE_URL}/api/tts-interrupt",
                    data={"session_id": session_id},
                    timeout=10,
                )
                break

        remaining = _stream_events(response)

    all_events = first_lines + remaining
    types = [evt.get("type") for evt in all_events]
    assert "meta" in types
    assert "done" in types
    assert "interrupted" in types or "audio_chunk" in types
