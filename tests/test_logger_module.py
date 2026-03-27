import json

from backend.core.logger import configure_logging, log_event


def test_structured_logging_emits_json_payload(capsys) -> None:
    configure_logging()

    log_event(
        "unit_test_log",
        request_id="req-test-1",
        endpoint="/api/test",
        intent="scheme_query",
        confidence=88.5,
        user_input_length=22,
        response_time_ms=12.4,
        status="success",
        error_type=None,
    )

    captured = capsys.readouterr()
    line = next((item for item in captured.err.splitlines() if "unit_test_log" in item), "")
    assert line
    payload = json.loads(line)

    assert payload.get("event") == "unit_test_log"
    assert payload.get("timestamp") is not None
    assert payload.get("request_id") == "req-test-1"
    assert payload.get("endpoint") == "/api/test"
    assert payload.get("intent") == "scheme_query"
    assert payload.get("confidence") == 88.5
    assert payload.get("user_input_length") == 22
    assert payload.get("response_time_ms") == 12.4
    assert payload.get("status") == "success"
