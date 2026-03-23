from backend.utils import session_manager


def test_single_central_session_manager_module_exports() -> None:
    assert callable(session_manager.create_session)
    assert callable(session_manager.get_session)
    assert callable(session_manager.update_session)
    assert callable(session_manager.delete_session)


def test_session_roundtrip_consistency() -> None:
    session_id = "session-consistency-1"
    session_manager.delete_session(session_id)

    created = session_manager.create_session(session_id)
    assert created["session_id"] == session_id

    created["last_intent"] = "apply_loan"
    session_manager.update_session(session_id, created)

    fetched = session_manager.get_session(session_id)
    assert fetched["session_id"] == session_id
    assert fetched.get("last_intent") == "apply_loan"


def test_memory_session_cleanup_api_is_safe() -> None:
    removed = session_manager.cleanup_expired_sessions()
    assert isinstance(removed, int)
    assert removed >= 0
