import argparse
import subprocess
import sys
import time
from pathlib import Path

import requests


def wait_for_health(base_url: str, timeout_seconds: int = 60) -> dict:
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        try:
            response = requests.get(f"{base_url}/health", timeout=5)
            if response.status_code == 200:
                return response.json()
            last_error = f"Unexpected status {response.status_code}"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(1)
    raise RuntimeError(f"Backend health check failed: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Backend smoke test")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8012)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "backend.main:app",
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]

    process = subprocess.Popen(
        cmd,
        cwd=str(root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    base_url = f"http://{args.host}:{args.port}"

    try:
        health = wait_for_health(base_url)
        if health.get("status") != "ok":
            raise RuntimeError(f"Health status is not ok: {health}")

        intent_response = requests.post(
            f"{base_url}/api/intent",
            json={"text": "check application status"},
            timeout=15,
        )
        intent_response.raise_for_status()
        intent_payload = intent_response.json()
        if "intent" not in intent_payload or "confidence" not in intent_payload:
            raise RuntimeError(f"Invalid /api/intent response: {intent_payload}")

        flow_response = requests.post(
            f"{base_url}/api/process-text",
            data={"session_id": "smoke-1", "language": "en", "text": "Need information"},
            timeout=30,
        )
        flow_response.raise_for_status()
        flow_payload = flow_response.json()
        if not isinstance(flow_payload.get("response_text"), str):
            raise RuntimeError(f"Invalid /api/process-text response: {flow_payload}")

        print("SMOKE_TEST_OK")
        print(f"Health status: {health.get('status')}")
        print(f"Intent: {intent_payload.get('intent')}")
        print(f"Flow mode: {flow_payload.get('mode')}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"SMOKE_TEST_FAILED: {exc}")
        return 1
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except Exception:  # noqa: BLE001
            process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
