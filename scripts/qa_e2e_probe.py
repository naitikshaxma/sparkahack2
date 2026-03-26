import json
import time
from dataclasses import dataclass

import requests

BASE_URL = "http://127.0.0.1:8099"


@dataclass
class CheckResult:
    name: str
    ok: bool
    details: dict


def _collect_stream_events(session_id: str, text: str, timeout_seconds: float = 90.0):
    response = requests.post(
        f"{BASE_URL}/api/process-text-stream",
        data={"text": text, "session_id": session_id, "language": "en"},
        stream=True,
        timeout=120,
    )
    response.raise_for_status()

    started = time.time()
    parsed = []
    for raw_line in response.iter_lines(decode_unicode=True):
        if not raw_line:
            continue
        line = raw_line if isinstance(raw_line, str) else raw_line.decode("utf-8", errors="ignore")
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError:
            parsed.append({"_raw": line})
        if isinstance(parsed[-1], dict) and parsed[-1].get("type") == "done":
            break
        if time.time() - started > timeout_seconds:
            break
    return parsed


def run_checks() -> list[CheckResult]:
    results: list[CheckResult] = []

    # 1) Health endpoint
    health = requests.get(f"{BASE_URL}/health", timeout=30)
    results.append(
        CheckResult(
            name="health",
            ok=health.status_code == 200,
            details={"status": health.status_code, "sample": health.text[:220]},
        )
    )

    # 2) process-text contract
    process = requests.post(
        f"{BASE_URL}/api/process-text",
        data={"text": "I need PM Kisan information", "session_id": "qa-probe-pt", "language": "en"},
        timeout=90,
    )
    process_json = process.json() if process.headers.get("content-type", "").startswith("application/json") else {}
    required_fields = [
        "success",
        "data",
        "error",
        "session_id",
        "response_text",
        "mode",
        "action",
        "steps_done",
        "steps_total",
        "quick_actions",
        "voice_text",
    ]
    missing = [field for field in required_fields if field not in process_json]
    results.append(
        CheckResult(
            name="process_text_valid",
            ok=process.status_code == 200 and not missing,
            details={
                "status": process.status_code,
                "missing": missing,
                "mode": process_json.get("mode"),
                "action": process_json.get("action"),
                "has_audio_base64": bool(process_json.get("audio_base64")),
            },
        )
    )

    # 3) process-text-stream order: meta -> audio_chunk -> done
    events = _collect_stream_events("qa-probe-stream", "Tell me PM Kisan eligibility details")
    event_types = [event.get("type") for event in events if isinstance(event, dict)]
    meta_idx = event_types.index("meta") if "meta" in event_types else -1
    audio_idx = event_types.index("audio_chunk") if "audio_chunk" in event_types else -1
    done_idx = event_types.index("done") if "done" in event_types else -1
    in_order = meta_idx != -1 and audio_idx != -1 and done_idx != -1 and meta_idx < audio_idx < done_idx
    done_last = done_idx == len(event_types) - 1 if done_idx != -1 else False
    results.append(
        CheckResult(
            name="process_text_stream_order",
            ok=in_order and done_last,
            details={
                "event_types": event_types,
                "meta_idx": meta_idx,
                "audio_idx": audio_idx,
                "done_idx": done_idx,
                "done_last": done_last,
            },
        )
    )

    # 4) Interrupt behavior: no extra audio_chunk after interrupted
    sid = "qa-probe-interrupt"
    stream_response = requests.post(
        f"{BASE_URL}/api/process-text-stream",
        data={"text": "Explain PM Kisan in very detailed points " * 10, "session_id": sid, "language": "en"},
        stream=True,
        timeout=120,
    )
    stream_response.raise_for_status()

    interrupt_sent = False
    interrupt_status = None
    interrupt_events = []
    started = time.time()
    for raw_line in stream_response.iter_lines(decode_unicode=True):
        if not raw_line:
            continue
        line = raw_line if isinstance(raw_line, str) else raw_line.decode("utf-8", errors="ignore")
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            obj = {"_raw": line}
        interrupt_events.append(obj)

        if obj.get("type") == "audio_chunk" and not interrupt_sent:
            intr = requests.post(f"{BASE_URL}/api/tts-interrupt", data={"session_id": sid}, timeout=30)
            interrupt_sent = True
            interrupt_status = intr.status_code

        if obj.get("type") in {"interrupted", "done"}:
            break
        if time.time() - started > 90:
            break

    i_types = [item.get("type") for item in interrupt_events if isinstance(item, dict)]
    if interrupt_sent:
        # We trigger interrupt after the first audio chunk; stream must not emit
        # any later audio chunks even if terminal event is done instead of interrupted.
        post_interrupt_types = i_types[2:] if len(i_types) > 2 else []
        extra_chunks = [t for t in post_interrupt_types if t == "audio_chunk"]
        no_extra_after_interrupt = len(extra_chunks) == 0
    else:
        post_interrupt_types = []
        no_extra_after_interrupt = False

    results.append(
        CheckResult(
            name="interrupt_stops_stream",
            ok=interrupt_sent and interrupt_status == 200 and no_extra_after_interrupt,
            details={
                "interrupt_sent": interrupt_sent,
                "interrupt_status": interrupt_status,
                "event_types": i_types,
                "post_interrupt_types": post_interrupt_types,
                "no_extra_after_interrupt": no_extra_after_interrupt,
            },
        )
    )

    # 5) Error handling: empty input + invalid input + client-side network failure
    empty = requests.post(
        f"{BASE_URL}/api/process-text",
        data={"text": "", "session_id": "qa-probe-empty", "language": "en"},
        timeout=30,
    )
    invalid = requests.post(
        f"{BASE_URL}/api/process-text",
        data={"text": "x" * 30000, "session_id": "qa-probe-invalid", "language": "en"},
        timeout=30,
    )
    net_fail_ok = False
    net_fail_error = ""
    try:
        requests.get("http://127.0.0.1:65530/health", timeout=2)
    except Exception as exc:  # noqa: BLE001
        net_fail_ok = True
        net_fail_error = str(exc)

    results.append(
        CheckResult(
            name="error_handling",
            ok=empty.status_code >= 400 and invalid.status_code >= 400 and net_fail_ok,
            details={
                "empty_status": empty.status_code,
                "invalid_status": invalid.status_code,
                "network_failure_handled": net_fail_ok,
                "network_failure_error": net_fail_error[:220],
            },
        )
    )

    return results


def main() -> int:
    checks = run_checks()
    output = {
        "all_passed": all(check.ok for check in checks),
        "checks": [
            {"name": check.name, "ok": check.ok, "details": check.details}
            for check in checks
        ],
    }
    print(json.dumps(output, indent=2))
    return 0 if output["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
