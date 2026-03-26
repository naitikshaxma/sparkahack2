import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterator

import pytest
import requests


ROOT = Path(__file__).resolve().parent.parent
TEST_PORT = 8126
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


def test_multi_turn_flow_keeps_state() -> None:
    session_id = "conv-flow-1"

    first = requests.post(
        f"{BASE_URL}/api/process-text",
        data={"session_id": session_id, "language": "en", "text": "I want to apply"},
        timeout=30,
    )
    second = requests.post(
        f"{BASE_URL}/api/process-text",
        data={"session_id": session_id, "language": "en", "text": "yes"},
        timeout=30,
    )

    assert first.status_code == 200
    assert second.status_code == 200

    p1 = first.json()
    p2 = second.json()

    assert p1.get("session_id") == session_id
    assert p2.get("session_id") == session_id
    assert isinstance(p1.get("response_text"), str)
    assert isinstance(p2.get("response_text"), str)


def test_correction_then_submission_path() -> None:
    session_id = "conv-flow-2"

    start = requests.post(
        f"{BASE_URL}/api/process-text",
        data={"session_id": session_id, "language": "en", "text": "apply scheme"},
        timeout=30,
    )
    correction = requests.post(
        f"{BASE_URL}/api/process-text",
        data={"session_id": session_id, "language": "en", "text": "not sure"},
        timeout=30,
    )
    final = requests.post(
        f"{BASE_URL}/api/process-text",
        data={"session_id": session_id, "language": "en", "text": "continue"},
        timeout=30,
    )

    assert start.status_code == 200
    assert correction.status_code == 200
    assert final.status_code == 200

    p2 = correction.json()
    p3 = final.json()

    assert isinstance(p2.get("validation_passed"), bool)
    assert isinstance(p3.get("session_complete"), bool)
    assert isinstance(p3.get("steps_done"), int)


def test_session_reset_clears_flow_state() -> None:
    session_id = "conv-flow-reset"

    requests.post(
        f"{BASE_URL}/api/process-text",
        data={"session_id": session_id, "language": "en", "text": "start"},
        timeout=30,
    )

    reset = requests.post(
        f"{BASE_URL}/api/reset-session",
        json={"session_id": session_id},
        timeout=15,
    )
    assert reset.status_code == 200

    post_reset = requests.post(
        f"{BASE_URL}/api/process-text",
        data={"session_id": session_id, "language": "en", "text": "start"},
        timeout=30,
    )
    assert post_reset.status_code == 200
    payload = post_reset.json()
    assert payload.get("session_id") == session_id
