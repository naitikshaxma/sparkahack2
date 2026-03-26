import pytest

from backend.models.api_models import AutofillRequest
from backend.routes import voice_routes


@pytest.mark.anyio
async def test_autofill_missing_session_id():
    payload = AutofillRequest(session_id="")
    result = await voice_routes.trigger_autofill(payload)

    assert result.get("status") == "autofill_not_started"
    assert result.get("validation_passed") is False
    assert result.get("validation_error") == "missing_session_id"


@pytest.mark.anyio
async def test_autofill_session_not_found(monkeypatch):
    monkeypatch.setattr("backend.routes.voice_routes.get_session", lambda _sid: None)

    payload = AutofillRequest(session_id="auto-1")
    result = await voice_routes.trigger_autofill(payload)

    assert result.get("status") == "autofill_not_started"
    assert result.get("validation_error") == "session_not_found"


@pytest.mark.anyio
async def test_autofill_session_not_complete(monkeypatch):
    monkeypatch.setattr(
        "backend.routes.voice_routes.get_session",
        lambda _sid: {"session_id": "auto-2", "session_complete": False},
    )

    payload = AutofillRequest(session_id="auto-2")
    result = await voice_routes.trigger_autofill(payload)

    assert result.get("status") == "autofill_not_started"
    assert result.get("validation_error") == "session_not_complete"


class _FakeProc:
    def __init__(self, returncode: int, stdout: str, stderr: str = "") -> None:
        self.returncode = returncode
        self._stdout = stdout.encode("utf-8")
        self._stderr = stderr.encode("utf-8")

    async def communicate(self):
        return self._stdout, self._stderr


@pytest.mark.anyio
async def test_autofill_success_and_partial_failure(monkeypatch):
    monkeypatch.setattr(
        "backend.routes.voice_routes.get_session",
        lambda _sid: {"session_id": "auto-3", "session_complete": True, "name": "Test User"},
    )

    async def _success_exec(*args, **kwargs):
        return _FakeProc(returncode=0, stdout="AUTOFILL_RESULT:done")

    monkeypatch.setattr("backend.routes.voice_routes.asyncio.create_subprocess_exec", _success_exec)
    success = await voice_routes.trigger_autofill(AutofillRequest(session_id="auto-3"))
    assert success.get("status") == "autofill_completed"
    assert success.get("validation_passed") is True

    async def _partial_exec(*args, **kwargs):
        return _FakeProc(returncode=0, stdout="AUTOFILL_RESULT:partial")

    monkeypatch.setattr("backend.routes.voice_routes.asyncio.create_subprocess_exec", _partial_exec)
    failed = await voice_routes.trigger_autofill(AutofillRequest(session_id="auto-3"))
    assert failed.get("status") == "autofill_failed"
    assert failed.get("validation_error") == "autofill_failed"
