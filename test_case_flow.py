import case_flow


def test_pending_replacement_confirmation_is_not_approved_replacement():
    state = {}

    case_flow.set_pending_replacement_confirmation(state)

    assert state["pending"] == case_flow.PENDING_REPLACEMENT_CONFIRM
    assert state["desired_resolution"] == "replacement"
    assert state.get("last_action") != "replacement"
    assert state.get("approved_replacement_status") is None


def test_replacement_approval_sets_terminal_replacement_state():
    state = {"pending": case_flow.PENDING_REPLACEMENT_CONFIRM, "desired_resolution": "replacement"}

    case_flow.mark_replacement_approved(state, "Peri Peri French Fries")

    assert state["pending"] is None
    assert state["last_action"] == "replacement"
    assert state["approved_replacement_item_name"] == "Peri Peri French Fries"
    assert state["approved_replacement_status"] == case_flow.APPROVED_REPLACEMENT


def test_refund_review_after_replacement_cancels_active_resolution():
    state = {
        "pending": case_flow.PENDING_REPLACEMENT_CONFIRM,
        "desired_resolution": "replacement",
        "approved_replacement_item_name": "Classic Maggi",
        "approved_replacement_status": case_flow.APPROVED_REPLACEMENT,
    }

    case_flow.request_refund_review_after_replacement(state)

    assert state["pending"] is None
    assert state["desired_resolution"] is None
    assert state["approved_replacement_status"] == case_flow.CANCEL_REQUESTED_FOR_REFUND_REVIEW
    assert state["replacement_change_requested"] == "refund"


def test_terminal_action_helper_marks_only_real_actions():
    state = {}

    case_flow.mark_terminal_action(state, "info", "Classic Maggi")
    assert state == {}

    case_flow.mark_terminal_action(state, "replacement", "Classic Maggi")
    assert state["last_action"] == "replacement"
    assert state["approved_replacement_status"] == case_flow.APPROVED_REPLACEMENT


def test_semantic_clarification_transition_round_trip():
    state = {}

    case_flow.set_pending_semantic_clarification(
        state,
        item_name="Roohafza Sharbat",
        issue_type="spill_leak",
        fault="delivery",
        prep_anomaly=False,
        message="actually roohafza spilled",
        reason="selected item conflict",
    )

    assert state["pending"] == case_flow.PENDING_SEMANTIC_CLARIFICATION
    assert state["desired_resolution"] is None
    assert state["pending_semantic_item_name"] == "Roohafza Sharbat"

    case_flow.confirm_semantic_clarification(
        state,
        item_name="Roohafza Sharbat",
        issue_type="spill_leak",
        prep_anomaly=False,
    )

    assert state["pending"] is None
    assert state["case_issue_type"] == "spill_leak"
    assert state["conversation_mode"] == case_flow.MODE_ACTIVE_COMPLAINT
    assert state["active_item_name"] == "Roohafza Sharbat"


def test_review_and_resolved_transitions_are_explicit():
    state = {}

    case_flow.mark_escalated(state, mode=case_flow.MODE_REVIEW)
    assert state["pending"] is None
    assert state["desired_resolution"] is None
    assert state["last_action"] == "escalate"
    assert state["conversation_mode"] == case_flow.MODE_REVIEW

    repeat_count = case_flow.mark_review_repeat(state)
    assert repeat_count == 1
    assert state["conversation_mode"] == case_flow.MODE_REVIEW

    case_flow.mark_user_resolved(state, issue_type="quality")
    assert state["case_resolved_by_user"] is True
    assert state["conversation_mode"] == case_flow.MODE_RESOLVED
    assert state["case_issue_type"] == "quality"

    resolved_repeat_count = case_flow.preserve_resolved_case_context(state, issue_type="quality")
    assert resolved_repeat_count == 1
    assert state["conversation_mode"] == case_flow.MODE_RESOLVED
