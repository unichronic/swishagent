import agent_service


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
    def fake_call_text(messages, temperature=0.1):
        return (
            '{"issue_type":"wrong_item","issue_confidence":0.92,"requested_resolution":"refund",'
            '"requested_resolution_confidence":0.88,"info_query":"none","info_query_confidence":0.9,'
            '"assurance_query":false,"turn_act":"switch_resolution","turn_act_confidence":0.74,'
            '"issue_severity":"medium","active_item_name":"Classic Maggi","visual_evidence_useful":true,'
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
