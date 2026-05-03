from rules import clear_session, get_session, get_session_state, mark_photo_provided, session_has_photo


def test_session_history_and_state_round_trip():
    session_id = "test:session-store"
    clear_session(session_id)

    history = get_session(session_id)
    history.append({"role": "user", "content": "hello"})
    history.append({"role": "bot", "content": "hi"})

    state = get_session_state(session_id)
    state["pending"] = "coupon"
    state["desired_resolution"] = "refund"

    fresh_history = get_session(session_id)
    fresh_state = get_session_state(session_id)

    assert len(fresh_history) == 2
    assert fresh_history[0]["content"] == "hello"
    assert fresh_state["pending"] == "coupon"
    assert fresh_state["desired_resolution"] == "refund"


def test_session_photo_marker_persists_until_clear():
    session_id = "test:session-photo"
    clear_session(session_id)

    assert session_has_photo(session_id) is False
    mark_photo_provided(session_id)
    assert session_has_photo(session_id) is True

    clear_session(session_id)
    assert session_has_photo(session_id) is False
