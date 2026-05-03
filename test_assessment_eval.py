import agent_service
from fastapi.testclient import TestClient


def _sample_context():
    return {
        "history": [{"role": "user", "content": "my order was wrong"}],
        "order_details": {"order_id": "ORD001", "total_amount": 222},
        "order_items": {"items": [{"name": "Classic Maggi", "price": 79}]},
        "kitchen": {"quality_out": "good"},
        "fleet": {"delay_mins": 0},
        "trust": {"score": 88},
    }


def test_assessment_eval_parses_valid_json(monkeypatch):
    captured = {}

    def fake_call_text(messages, temperature=0.1):
        captured["messages"] = messages
        return (
            '{"issue_type":"wrong_item","issue_confidence":0.92,"requested_resolution":"refund",'
            '"requested_resolution_confidence":0.88,"info_query":"none","info_query_confidence":0.9,'
            '"assurance_query":false,"turn_act":"switch_resolution","turn_act_confidence":0.74,'
            '"issue_severity":"medium","active_item_name":"Classic Maggi","selected_item_conflict":false,'
            '"mentioned_item_name":"Classic Maggi","semantic_risk":false,"semantic_confidence":0.9,'
            '"semantic_risk_reason":"","dietary_severity":"none","visual_evidence_useful":true,'
            '"fault_hint":"kitchen","recommended_next_step":"coupon","clarification_needed":false,'
            '"economic_preference":"refund","economic_confidence":0.8,"tone_guardrail":"neutral",'
            '"negotiation_allowed":true,"negotiation_strength":"light","notes":"test"}'
        )

    monkeypatch.setattr(agent_service, "call_text", fake_call_text)
    ctx = _sample_context()
    assessment, meta = agent_service._assess_case(
        complaint="you sent the wrong item",
        history=ctx["history"],
        order_details=ctx["order_details"],
        order_items=ctx["order_items"],
        kitchen=ctx["kitchen"],
        fleet=ctx["fleet"],
        trust=ctx["trust"],
    )

    assert meta["status"] == "ok"
    assert assessment["issue_type"] == "wrong_item"
    assert assessment["requested_resolution"] == "refund"
    prompt_text = captured["messages"][0]["content"] + captured["messages"][1]["content"]
    assert "selected_item_conflict" in prompt_text
    assert "semantic_risk" in prompt_text
    assert "dietary_severity" in prompt_text


def test_assessment_eval_marks_invalid_json(monkeypatch):
    monkeypatch.setattr(agent_service, "call_text", lambda messages, temperature=0.1: "not json at all")
    ctx = _sample_context()
    assessment, meta = agent_service._assess_case(
        complaint="you sent the wrong item",
        history=ctx["history"],
        order_details=ctx["order_details"],
        order_items=ctx["order_items"],
        kitchen=ctx["kitchen"],
        fleet=ctx["fleet"],
        trust=ctx["trust"],
    )

    assert assessment == {}
    assert meta["status"] == "invalid_json"


def test_assessment_eval_marks_provider_error(monkeypatch):
    def fake_call_text(messages, temperature=0.1):
        raise RuntimeError("provider down")

    monkeypatch.setattr(agent_service, "call_text", fake_call_text)
    ctx = _sample_context()
    assessment, meta = agent_service._assess_case(
        complaint="my food was cold",
        history=ctx["history"],
        order_details=ctx["order_details"],
        order_items=ctx["order_items"],
        kitchen=ctx["kitchen"],
        fleet=ctx["fleet"],
        trust=ctx["trust"],
    )

    assert assessment == {}
    assert meta["status"] == "error"
    assert "provider down" in meta["error"]


def test_humanize_prompt_does_not_include_internal_action_or_amount(monkeypatch):
    captured = {}

    def fake_call_text_with_trace(messages, **kwargs):
        captured["messages"] = messages
        return '{"message":"I can offer a coupon here."}'

    monkeypatch.setattr(agent_service, "_call_text_with_trace", fake_call_text_with_trace)
    result = agent_service._humanize_message(
        {
            "action": "info",
            "amount": 81,
            "message": "I can offer a coupon here.",
            "reason": "Offer coupon before refund or replacement",
        },
        complaint="I need compensation",
        order_items={"items": [{"name": "Roohafza Sharbat", "price": 99}]},
        history=[{"role": "user", "content": "I need compensation"}],
    )

    user_prompt = captured["messages"][1]["content"]
    assert "Approved action" not in user_prompt
    assert "Approved amount" not in user_prompt
    assert result["message"] == "I can offer a coupon here."


def test_humanizer_rejects_invented_product_policy_claims(monkeypatch):
    monkeypatch.setattr(
        agent_service,
        "_call_text_with_trace",
        lambda messages, **kwargs: '{"message":"The samosa is meant to be a small snack-sized portion."}',
    )
    result = agent_service._humanize_message(
        {
            "action": "info",
            "amount": 0,
            "message": "I can't verify portion size reliably after delivery, but I've logged it against the kitchen.",
            "reason": "No explicit compensation request",
        },
        complaint="there was not enough aloo in the samosa",
        order_items={"items": [{"name": "Mini Punjabi Aloo Samosa", "price": 99}]},
        history=[{"role": "user", "content": "there was not enough aloo in the samosa"}],
    )

    assert result["message"] == "I can't verify portion size reliably after delivery, but I've logged it against the kitchen."


def test_humanizer_rejects_invented_compensation_claims(monkeypatch):
    monkeypatch.setattr(
        agent_service,
        "_call_text_with_trace",
        lambda messages, **kwargs: '{"message":"I’ll add 20% back to your wallet for the wait."}',
    )
    original = "I can see why that was frustrating. The delay happened after the kitchen finished it."
    result = agent_service._humanize_message(
        {
            "action": "info",
            "amount": 0,
            "message": original,
            "reason": "No explicit compensation request",
        },
        complaint="this is outrageous",
        order_items={"items": [{"name": "Dhaba Style Chicken Curry Rice Bowl", "price": 269}]},
        history=[{"role": "user", "content": "this is outrageous"}],
    )

    assert result["message"] == original


def test_humanizer_rejects_component_portion_scope_drift(monkeypatch):
    monkeypatch.setattr(
        agent_service,
        "_call_text_with_trace",
        lambda messages, **kwargs: '{"message":"The bowl was too small for what you paid."}',
    )
    original = "I can add a ₹78 coupon right away for the low chicken quantity. Want me to put that through?"
    result = agent_service._humanize_message(
        {
            "action": "info",
            "amount": 0,
            "message": original,
            "reason": "Offer coupon before refund or replacement",
            "_debug": {"issue_type": "portion_size"},
        },
        complaint="there was not enough chicken in the bowl",
        order_items={"items": [{"name": "Chicken Rice Bowl", "price": 260}]},
        history=[{"role": "user", "content": "there was not enough chicken in the bowl"}],
    )

    assert result["message"] == original


def test_humanizer_allows_safe_component_portion_rewrite(monkeypatch):
    monkeypatch.setattr(
        agent_service,
        "_call_text_with_trace",
        lambda messages, **kwargs: '{"message":"I can add a ₹78 coupon for the low chicken quantity. Want me to do that?"}',
    )
    result = agent_service._humanize_message(
        {
            "action": "info",
            "amount": 0,
            "message": "I can add a ₹78 coupon right away for the low chicken quantity. Want me to put that through?",
            "reason": "Offer coupon before refund or replacement",
            "_debug": {"issue_type": "portion_size"},
        },
        complaint="there was not enough chicken in the bowl",
        order_items={"items": [{"name": "Chicken Rice Bowl", "price": 260}]},
        history=[{"role": "user", "content": "there was not enough chicken in the bowl"}],
    )

    assert result["message"] == "I can add a ₹78 coupon for the low chicken quantity. Want me to do that?"


def test_humanizer_rejects_uncertainty_upgrade(monkeypatch):
    monkeypatch.setattr(
        agent_service,
        "_call_text_with_trace",
        lambda messages, **kwargs: '{"message":"You are right, there was not enough chicken."}',
    )
    original = "I can't verify the chicken quantity or portion size from logs after delivery, but I'm logging this against the kitchen for the Chicken Rice Bowl."
    result = agent_service._humanize_message(
        {
            "action": "info",
            "amount": 0,
            "message": original,
            "reason": "No explicit compensation request",
            "_debug": {"issue_type": "portion_size"},
        },
        complaint="there was not enough chicken in the bowl",
        order_items={"items": [{"name": "Chicken Rice Bowl", "price": 260}]},
        history=[{"role": "user", "content": "there was not enough chicken in the bowl"}],
    )

    assert result["message"] == original


def test_run_falls_back_to_rules_when_assessment_provider_fails(monkeypatch):
    client = TestClient(agent_service.app)

    monkeypatch.setattr(agent_service, "get_order_details", lambda order_id: {"order_id": order_id, "total_amount": 222})
    monkeypatch.setattr(
        agent_service,
        "get_order_items",
        lambda order_id: {"items": [{"name": "Classic Maggi", "price": 79}]},
    )
    monkeypatch.setattr(agent_service, "check_kitchen_log", lambda order_id: {"quality_out": "good", "temperature_check": "cold"})
    monkeypatch.setattr(agent_service, "check_fleet_status", lambda order_id: {"delay_mins": 0, "traffic_flag": False})
    monkeypatch.setattr(agent_service, "get_trust_score", lambda user_id: {"score": 88, "total_orders": 12})
    monkeypatch.setattr(agent_service, "get_delivery_info", lambda order_id: {"status": "delivered"})
    monkeypatch.setattr(agent_service, "_assess_case", lambda **kwargs: ({}, {"status": "error", "error": "provider down"}))
    monkeypatch.setattr(agent_service, "_humanize_message", lambda resolution, complaint, order_items, history: resolution)

    response = client.post(
        "/run",
        json={
            "user_id": "USER123",
            "order_id": "ORD001",
            "conversation_id": "test:assessment-fallback",
            "complaint": "my food was cold",
            "order_value": 222,
        },
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["action"] == "info"
    assert payload["reason"] != "assessment_unavailable:error"


def test_run_returns_case_state_lifecycle_and_ops_artifacts(monkeypatch):
    client = TestClient(agent_service.app)

    monkeypatch.setattr(agent_service, "get_order_details", lambda order_id: {"order_id": order_id, "total_amount": 478})
    monkeypatch.setattr(
        agent_service,
        "get_order_items",
        lambda order_id: {"items": [{"name": "Peri Peri French Fries", "price": 209}]},
    )
    monkeypatch.setattr(agent_service, "check_kitchen_log", lambda order_id: {"status": "ready", "quality_out": "fair"})
    monkeypatch.setattr(agent_service, "check_fleet_status", lambda order_id: {"delay_mins": 4, "traffic_flag": False})
    monkeypatch.setattr(agent_service, "get_trust_score", lambda user_id: {"score": 92, "total_orders": 18, "refund_requests": 1})
    monkeypatch.setattr(agent_service, "get_delivery_info", lambda order_id: {"status": "delivered"})
    monkeypatch.setattr(
        agent_service,
        "_assess_case",
        lambda **kwargs: (
            {"issue_type": "quality", "issue_confidence": 0.9, "active_item_name": "Peri Peri French Fries"},
            {"status": "ok", "raw_preview": "{}"},
        ),
    )
    monkeypatch.setattr(agent_service, "_humanize_message", lambda resolution, complaint, order_items, history: resolution)

    def fake_resolve(**kwargs):
        return {
            "action": "replacement",
            "amount": 0,
            "message": "I've approved a fresh Peri Peri French Fries replacement.",
            "reason": "Replacement approved after confirmation",
            "_debug": {
                "issue_type": "quality",
                "issue_severity": "medium",
                "evidence_strength": "weak",
                "requested_resolution": "replacement",
                "active_item_name": "Peri Peri French Fries",
                "fault": "kitchen",
            },
        }

    monkeypatch.setattr(agent_service.Rules, "resolve", staticmethod(fake_resolve))

    response = client.post(
        "/run",
        json={
            "user_id": "USER123",
            "order_id": "ORD001",
            "conversation_id": "test:artifacts",
            "complaint": "fries were soggy and i want replacement",
            "order_value": 478,
        },
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["case_state"]["selected_item"] == "Peri Peri French Fries"
    assert payload["case_state"]["risk_tier"] == "low"
    assert payload["action_status"]["action"] == "replacement"
    assert payload["action_status"]["status"] == "approved_pending_execution"
    assert payload["ops_incident"]["owner_area"] == "kitchen"

    status_response = client.get(
        "/case_status",
        params={
            "user_id": "USER123",
            "order_id": "ORD001",
            "conversation_id": "test:artifacts",
        },
    )
    status_payload = status_response.json()
    assert status_payload["case_state"]["selected_item"] == "Peri Peri French Fries"
    assert status_payload["action_lifecycles"][0]["action"] == "replacement"
    assert status_payload["ops_incidents"][0]["owner_area"] == "kitchen"


def test_agent_error_creates_support_ticket(monkeypatch):
    client = TestClient(agent_service.app)

    monkeypatch.setattr(agent_service, "get_order_details", lambda order_id: (_ for _ in ()).throw(RuntimeError("data down")))

    response = client.post(
        "/run",
        json={
            "user_id": "USER123",
            "order_id": "ORD001",
            "conversation_id": "test:error-ticket",
            "complaint": "support is not working",
            "order_value": 478,
        },
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["action"] == "escalate"
    assert payload["support_ticket"]["status"] == "open"
    assert "explain it again" in payload["message"].lower()
