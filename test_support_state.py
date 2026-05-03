from support_state import action_lifecycle, attach_artifacts, build_case_state, ops_incident, style_warnings, support_ticket


def _case_state():
    return build_case_state(
        user_id="USER123",
        order_id="ORD001",
        session_id="support:case",
        complaint="fries were soggy and i want replacement",
        order_details={"total_amount": 478, "restaurant_name": "Fulfilling Dinner"},
        order_items={"items": [{"name": "Peri Peri French Fries", "price": 209}]},
        kitchen={"status": "ready", "quality_out": "fair"},
        fleet={"delay_mins": 4},
        trust={"score": 92, "total_orders": 18, "refund_requests": 1},
        assessment={"issue_type": "quality", "active_item_name": "Peri Peri French Fries"},
        resolution_debug={
            "issue_type": "quality",
            "issue_severity": "medium",
            "evidence_strength": "weak",
            "requested_resolution": "replacement",
            "active_item_name": "Peri Peri French Fries",
            "fault": "kitchen",
        },
    )


def test_case_state_carries_margin_and_resolution_inputs():
    case_state = _case_state()

    assert case_state["selected_item"] == "Peri Peri French Fries"
    assert case_state["final_issue_type"] == "quality"
    assert case_state["evidence_status"] == "weak"
    assert case_state["risk_tier"] == "low"
    assert case_state["item_value"] == 209
    assert case_state["replacement_feasible"] is True
    assert case_state["max_auto_compensation"] == 63
    assert case_state["ops_context"]["owner_area"] == "kitchen"


def test_action_lifecycle_records_post_decision_status():
    lifecycle = action_lifecycle("refund", 120, _case_state())

    assert lifecycle["action"] == "refund"
    assert lifecycle["amount"] == 120
    assert lifecycle["status"] == "approved_pending_execution"
    assert lifecycle["next_status_owner"] == "payout"
    assert lifecycle["reference_id"].startswith("refund_")


def test_incident_and_ticket_are_structured():
    case_state = _case_state()
    incident = ops_incident("replacement", case_state)
    ticket = support_ticket("escalate", "manual review", case_state)

    assert incident["owner_area"] == "kitchen"
    assert incident["status"] == "open"
    assert ticket["ticket_id"].startswith("ticket_")
    assert ticket["status"] == "open"


def test_attach_artifacts_persists_state_objects():
    state = {}
    result = attach_artifacts(
        state,
        {
            "action": "replacement",
            "amount": 0,
            "message": "I've approved a fresh item replacement.",
            "reason": "Replacement approved after confirmation",
        },
        _case_state(),
    )

    assert "case_state" in state
    assert state["action_lifecycles"][0]["action"] == "replacement"
    assert state["ops_incidents"][0]["issue_type"] == "quality"
    assert result["action_status"]["status"] == "approved_pending_execution"
    assert result["case_state"]["selected_item"] == "Peri Peri French Fries"


def test_style_warnings_catch_non_human_or_internal_copy():
    warnings = style_warnings("As per policy, approved action is refund to avoid company loss.")

    assert "policy_like" in warnings
    assert "internal_leak" in warnings
