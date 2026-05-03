from rules import Rules, clear_session, get_session, get_session_state, mark_photo_provided, session_has_photo


def _base_context():
    return {
        "kitchen": {
            "quality_out": "fair",
            "prep_time_mins": 6,
            "temperature_check": "warm",
        },
        "fleet": {
            "delay_mins": 4,
            "traffic_flag": False,
        },
        "trust": {
            "score": 92,
            "total_orders": 18,
        },
        "order_details": {
            "total_amount": 222,
        },
        "order_items": {
            "items": [
                {"name": "Classic Maggi", "price": 79},
                {"name": "Cold Coffee", "price": 120},
            ]
        },
    }


def _run_turn(session_id: str, complaint: str, order_value: float = 222, photo_url=None, photo_valid=None):
    history = get_session(session_id)
    history.append({"role": "user", "content": complaint})
    if photo_url:
        mark_photo_provided(session_id)
    ctx = _base_context()
    result = Rules.resolve(
        complaint=complaint,
        conversation_history=history,
        order_value=order_value,
        trust_score=ctx["trust"]["score"],
        kitchen=ctx["kitchen"],
        fleet=ctx["fleet"],
        trust=ctx["trust"],
        order_details=ctx["order_details"],
        order_items=ctx["order_items"],
        photo_url=photo_url,
        photo_valid=photo_valid,
        photo_in_session=session_has_photo(session_id),
        session_id=session_id,
    )
    history.append({"role": "bot", "content": result["message"]})
    return result


def test_refund_flow_is_deterministic():
    session_id = "test:refund"
    clear_session(session_id)

    first = _run_turn(session_id, "there was plastic in my maggi")
    assert first["action"] == "info"
    assert "coupon" not in first["message"].lower()

    second = _run_turn(session_id, "i want a refund", photo_url="https://example.com/proof.jpg", photo_valid=True)
    assert second["action"] == "info"
    assert "coupon" in second["message"].lower()

    third = _run_turn(session_id, "no i want refund")
    assert third["action"] == "info"
    assert "25%" in third["message"]

    fourth = _run_turn(session_id, "50%")
    assert fourth["action"] == "refund"
    assert fourth["amount"] == 111


def test_high_value_low_trust_refund_is_forced_toward_replacement():
    session_id = "test:refund-to-replacement"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    ctx["trust"]["score"] = 72
    ctx["order_items"] = {"items": [{"name": "Veg Pink Sauce Pasta", "price": 219}]}

    responses = []
    for msg in ["the pasta was bad", "i want a refund", "no i need a refund", "full"]:
        history.append({"role": "user", "content": msg})
        result = Rules.resolve(
            complaint=msg,
            conversation_history=history,
            order_value=756,
            trust_score=72,
            kitchen=ctx["kitchen"],
            fleet=ctx["fleet"],
            trust=ctx["trust"],
            order_details={"total_amount": 756},
            order_items=ctx["order_items"],
            session_id=session_id,
        )
        history.append({"role": "bot", "content": result["message"]})
        responses.append(result)

    assert result["action"] == "info"
    assert "can't lock in a cash refund" in responses[2]["message"].lower()
    assert "can't lock in a cash refund" in responses[3]["message"].lower()
    assert "fresh veg pink sauce pasta" in responses[2]["message"].lower()


def test_low_value_refund_request_stays_on_refund_path_when_more_economical():
    session_id = "test:low-value-refund-economical"
    clear_session(session_id)

    first = _run_turn(session_id, "i got the wrong item", order_value=168)
    assert first["action"] == "info"
    second = _run_turn(session_id, "i want a refund", order_value=168, photo_url="https://example.com/proof.jpg", photo_valid=True)
    assert second["action"] == "info"
    third = _run_turn(session_id, "no i need a refund", order_value=168)
    assert third["action"] == "info"
    assert "25%" in third["message"].lower()


def test_high_value_refund_request_can_be_steered_to_replacement_when_cheaper():
    session_id = "test:high-value-replacement-economical"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    ctx["trust"]["score"] = 92
    ctx["order_items"] = {"items": [{"name": "Veg Pink Sauce Pasta", "price": 219}]}

    history.append({"role": "user", "content": "the pasta was bad"})
    first = Rules.resolve(
        complaint="the pasta was bad",
        conversation_history=history,
        order_value=756,
        trust_score=92,
        kitchen=ctx["kitchen"],
        fleet=ctx["fleet"],
        trust=ctx["trust"],
        order_details={"total_amount": 756},
        order_items=ctx["order_items"],
        session_id=session_id,
    )
    history.append({"role": "bot", "content": first["message"]})

    history.append({"role": "user", "content": "i want a refund"})
    second = Rules.resolve(
        complaint="i want a refund",
        conversation_history=history,
        order_value=756,
        trust_score=92,
        kitchen=ctx["kitchen"],
        fleet=ctx["fleet"],
        trust=ctx["trust"],
        order_details={"total_amount": 756},
        order_items=ctx["order_items"],
        session_id=session_id,
    )
    history.append({"role": "bot", "content": second["message"]})

    history.append({"role": "user", "content": "no i need a refund"})
    third = Rules.resolve(
        complaint="no i need a refund",
        conversation_history=history,
        order_value=756,
        trust_score=92,
        kitchen=ctx["kitchen"],
        fleet=ctx["fleet"],
        trust=ctx["trust"],
        order_details={"total_amount": 756},
        order_items=ctx["order_items"],
        session_id=session_id,
    )
    assert third["action"] == "info"
    assert "fresh veg pink sauce pasta" in third["message"].lower()


def test_replacement_flow_is_deterministic():
    session_id = "test:replacement"
    clear_session(session_id)

    _run_turn(session_id, "coffee was too sweet")
    second = _run_turn(session_id, "i want a replacement")
    assert second["action"] == "info"
    assert "coupon" in second["message"].lower()

    third = _run_turn(session_id, "no i want another one")
    assert third["action"] == "info"
    assert "fresh" in third["message"].lower()

    fourth = _run_turn(session_id, "yes same items")
    assert fourth["action"] == "replacement"
    assert "cold coffee" in fourth["message"].lower()
    assert "that wasn't right" not in fourth["message"].lower()


def test_active_complaint_status_followup_does_not_become_order_info_query():
    session_id = "test:active-complaint-status-followup"
    clear_session(session_id)

    first = _run_turn(session_id, "Classic Maggi was soggy")
    assert first["action"] == "info"

    history = get_session(session_id)
    history.append({"role": "user", "content": "what happens now?"})
    ctx = _base_context()
    result = Rules.resolve(
        complaint="what happens now?",
        conversation_history=history,
        order_value=222,
        trust_score=ctx["trust"]["score"],
        kitchen=ctx["kitchen"],
        fleet=ctx["fleet"],
        trust=ctx["trust"],
        order_details=ctx["order_details"],
        order_items=ctx["order_items"],
        session_id=session_id,
        assessment={
            "issue_type": "info_query",
            "issue_confidence": 0.92,
            "info_query": "status",
            "info_query_confidence": 0.9,
            "requested_resolution": "none",
            "requested_resolution_confidence": 0.9,
            "turn_act": "ask_status",
            "turn_act_confidence": 0.9,
        },
    )

    assert result["action"] == "info"
    assert result["reason"] == "User asked for active complaint status"
    assert "quality issue" in result["message"].lower()
    assert "marked delivered" not in result["message"].lower()


def test_active_coupon_followup_keeps_pending_resolution_state():
    session_id = "test:active-coupon-followup-keeps-pending"
    clear_session(session_id)

    _run_turn(session_id, "Classic Maggi was soggy")
    coupon_offer = _run_turn(session_id, "refund chahiye")
    assert coupon_offer["action"] == "info"
    assert get_session_state(session_id).get("pending") == "coupon"

    history = get_session(session_id)
    history.append({"role": "user", "content": "what is the final next step?"})
    ctx = _base_context()
    followup = Rules.resolve(
        complaint="what is the final next step?",
        conversation_history=history,
        order_value=222,
        trust_score=ctx["trust"]["score"],
        kitchen=ctx["kitchen"],
        fleet=ctx["fleet"],
        trust=ctx["trust"],
        order_details=ctx["order_details"],
        order_items=ctx["order_items"],
        session_id=session_id,
        assessment={
            "issue_type": "info_query",
            "issue_confidence": 0.9,
            "info_query": "status",
            "info_query_confidence": 0.9,
            "requested_resolution": "none",
            "requested_resolution_confidence": 0.9,
            "turn_act": "ask_status",
            "turn_act_confidence": 0.9,
        },
    )

    assert followup["reason"] == "User asked for active complaint status"
    assert "coupon" in followup["message"].lower()
    assert get_session_state(session_id).get("pending") == "coupon"


def test_delay_refund_pressure_never_moves_to_replacement_confirmation():
    session_id = "test:delay-refund-pressure-no-replacement"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    ctx["fleet"] = {"delay_mins": 25, "traffic_flag": True}
    ctx["order_items"] = {"items": [{"name": "Peri Peri French Fries", "price": 209}]}

    outputs = []
    for msg in [
        "food is fine but delivery was too late",
        "compensation for delay",
        "refund for delay",
        "don't ask food photo",
        "give final answer",
    ]:
        history.append({"role": "user", "content": msg})
        result = Rules.resolve(
            complaint=msg,
            conversation_history=history,
            order_value=478,
            trust_score=ctx["trust"]["score"],
            kitchen=ctx["kitchen"],
            fleet=ctx["fleet"],
            trust=ctx["trust"],
            order_details={"total_amount": 478},
            order_items=ctx["order_items"],
            session_id=session_id,
            assessment={
                "issue_type": "delay",
                "issue_confidence": 0.9,
                "requested_resolution": "refund" if "refund" in msg else "coupon" if "compensation" in msg else "none",
                "requested_resolution_confidence": 0.9,
                "info_query": "none",
                "info_query_confidence": 0.9,
                "turn_act": "switch_resolution" if "refund" in msg else "none",
                "turn_act_confidence": 0.9,
                "economic_preference": "replacement",
                "economic_confidence": 0.95,
            },
        )
        history.append({"role": "bot", "content": result["message"]})
        outputs.append(result)

    combined = " ".join(output["message"].lower() for output in outputs)
    assert "fresh item" not in combined
    assert "remade" not in combined
    assert "replacement" not in combined
    assert "replacement confirmation" not in " ".join(output["reason"].lower() for output in outputs)


def test_delay_replacement_assessment_is_forced_back_to_coupon_path():
    session_id = "test:delay-replacement-assessment-blocked"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    ctx["fleet"] = {"delay_mins": 18, "traffic_flag": True}
    ctx["order_items"] = {"items": [{"name": "Classic Maggi", "price": 79}]}

    outputs = []
    for msg in ["delivery was late", "send replacement for delay", "yes replacement"]:
        history.append({"role": "user", "content": msg})
        result = Rules.resolve(
            complaint=msg,
            conversation_history=history,
            order_value=168,
            trust_score=ctx["trust"]["score"],
            kitchen=ctx["kitchen"],
            fleet=ctx["fleet"],
            trust=ctx["trust"],
            order_details={"total_amount": 168},
            order_items=ctx["order_items"],
            session_id=session_id,
            assessment={
                "issue_type": "delay",
                "issue_confidence": 0.9,
                "requested_resolution": "replacement",
                "requested_resolution_confidence": 0.9,
                "info_query": "none",
                "info_query_confidence": 0.9,
                "turn_act": "switch_resolution",
                "turn_act_confidence": 0.9,
                "economic_preference": "replacement",
                "economic_confidence": 0.95,
            },
        )
        history.append({"role": "bot", "content": result["message"]})
        outputs.append(result)

    combined = " ".join(output["message"].lower() for output in outputs)
    assert "fresh item" not in combined
    assert "remade" not in combined
    assert "replacement" not in combined
    assert any("coupon" in output["message"].lower() for output in outputs)


def test_payment_query_ignores_item_semantic_conflict_guard():
    session_id = "test:payment-query-no-item-clarification"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    history.append({"role": "user", "content": "payment issue hai shayad"})
    result = Rules.resolve(
        complaint="payment issue hai shayad",
        conversation_history=history,
        order_value=478,
        trust_score=ctx["trust"]["score"],
        kitchen=ctx["kitchen"],
        fleet=ctx["fleet"],
        trust=ctx["trust"],
        order_details={"total_amount": 478, "status": "delivered"},
        order_items=ctx["order_items"],
        session_id=session_id,
        assessment={
            "issue_type": "info_query",
            "issue_confidence": 0.9,
            "requested_resolution": "none",
            "requested_resolution_confidence": 0.9,
            "info_query": "status",
            "info_query_confidence": 0.9,
            "turn_act": "ask_status",
            "turn_act_confidence": 0.9,
            "selected_item_conflict": True,
            "mentioned_item_name": "Classic Maggi",
            "semantic_risk": True,
            "semantic_confidence": 0.95,
            "recommended_next_step": "clarify",
            "clarification_needed": True,
        },
    )

    assert result["action"] == "info"
    assert result["reason"] == "User asked for order information, not a complaint resolution"
    assert "wrong item" not in result["message"].lower()
    assert "which item" not in result["message"].lower()


def test_semantic_clarification_confirmation_keeps_original_issue_context():
    session_id = "test:semantic-clarification-confirmation-keeps-context"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    ctx["order_items"] = {"items": [{"name": "Butter Chicken Rice Bowl", "price": 269}]}

    history.append({"role": "user", "content": "Something is missing from Butter Chicken Rice Bowl"})
    first = Rules.resolve(
        complaint="Something is missing from Butter Chicken Rice Bowl",
        conversation_history=history,
        order_value=269,
        trust_score=ctx["trust"]["score"],
        kitchen=ctx["kitchen"],
        fleet=ctx["fleet"],
        trust=ctx["trust"],
        order_details={"total_amount": 269},
        order_items=ctx["order_items"],
        session_id=session_id,
        assessment={
            "issue_type": "missing_item",
            "issue_confidence": 0.91,
            "active_item_name": "Butter Chicken Rice Bowl",
        },
    )
    history.append({"role": "bot", "content": first["message"]})

    history.append({"role": "user", "content": "there was a piece of vegetable in my chicken bowl"})
    clarification = Rules.resolve(
        complaint="there was a piece of vegetable in my chicken bowl",
        conversation_history=history,
        order_value=269,
        trust_score=ctx["trust"]["score"],
        kitchen=ctx["kitchen"],
        fleet=ctx["fleet"],
        trust=ctx["trust"],
        order_details={"total_amount": 269},
        order_items=ctx["order_items"],
        session_id=session_id,
        assessment={
            "issue_type": "quality",
            "issue_confidence": 0.88,
            "active_item_name": "Butter Chicken Rice Bowl",
            "mentioned_item_name": "Butter Chicken Rice Bowl",
            "semantic_risk": True,
            "semantic_confidence": 0.93,
            "semantic_risk_reason": "selected issue category does not match described ingredient issue",
            "recommended_next_step": "clarify",
            "clarification_needed": True,
            "fault_hint": "kitchen",
        },
    )
    history.append({"role": "bot", "content": clarification["message"]})

    assert clarification["action"] == "info"
    assert "right item" not in clarification["message"].lower()
    assert "prep-side quality issue" in clarification["message"].lower()
    assert "logs still don't point" not in clarification["message"].lower()
    assert get_session_state(session_id).get("pending") is None


def test_solid_food_sauce_spill_stays_damage_not_liquid_spill():
    assert Rules._detect_issue_type("Grilled Paneer Club Sandwich spill ho gaya", "Grilled Paneer Club Sandwich") == "damaged"
    assert Rules._strong_text_issue_override(
        "matlab sauce bahar nikal gaya aur bread soggy ho gayi",
        "damaged",
    ) == "damaged"
    assert Rules._strong_text_issue_override(
        "Roohafza Sharbat bag ke andar spill ho gaya",
        "damaged",
    ) == "spill_leak"
    assert not Rules._has_strong_new_issue_signal("packaging open thi", "damaged")
    assert not Rules._has_strong_new_issue_signal("sauce bahar nikal gaya aur bread soggy ho gayi", "damaged")


def test_typo_followup_after_review_is_recognized_without_llm():
    session_id = "test:typo-followup-after-review"
    clear_session(session_id)
    state = get_session_state(session_id)
    state["case_issue_type"] = "portion_size"
    state["issue_type"] = "portion_size"
    state["last_action"] = "escalate"
    state["conversation_mode"] = "review"

    assert Rules._is_followup_or_evidence_turn("dont ask agin same thing")


def test_unverifiable_replacement_request_pushes_coupon_then_escalates_review():
    session_id = "test:replacement-needs-review"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    ctx["kitchen"] = {"quality_out": "good", "prep_time_mins": 12, "temperature_check": "hot"}
    ctx["fleet"] = {"delay_mins": 1, "traffic_flag": False}
    ctx["order_items"] = {"items": [{"name": "Peri Peri French Fries", "price": 209}]}

    turns = [
        "the fries were less in quantity",
        "i want a replacement",
        "no i need another fries",
        "still no i need another one",
        "replacement only",
    ]
    outputs = []
    for msg in turns:
        history.append({"role": "user", "content": msg})
        result = Rules.resolve(
            complaint=msg,
            conversation_history=history,
            order_value=209,
            trust_score=92,
            kitchen=ctx["kitchen"],
            fleet=ctx["fleet"],
            trust=ctx["trust"],
            order_details={"total_amount": 209},
            order_items=ctx["order_items"],
            session_id=session_id,
        )
        history.append({"role": "bot", "content": result["message"]})
        outputs.append(result)

    assert "₹42" in outputs[1]["message"]
    assert outputs[2]["action"] == "info"
    assert "coupon" in outputs[2]["message"].lower()
    assert outputs[4]["action"] == "escalate"
    assert "review" in outputs[4]["message"].lower()


def test_weak_evidence_quality_replacement_persistence_moves_to_review():
    session_id = "test:quality-replacement-weak-evidence-review"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    ctx["kitchen"] = {"quality_out": "good", "prep_time_mins": 12, "temperature_check": "hot"}
    ctx["fleet"] = {"delay_mins": 1, "traffic_flag": False}
    ctx["trust"] = {"score": 92, "total_orders": 18}
    ctx["order_items"] = {"items": [{"name": "Peri Peri French Fries", "price": 209}]}

    turns = [
        "the fries were totally soggy",
        "can i get a replacement?",
        "no i need another fries",
        "replacement only",
    ]
    outputs = []
    for msg in turns:
        history.append({"role": "user", "content": msg})
        result = Rules.resolve(
            complaint=msg,
            conversation_history=history,
            order_value=478,
            trust_score=ctx["trust"]["score"],
            kitchen=ctx["kitchen"],
            fleet=ctx["fleet"],
            trust=ctx["trust"],
            order_details={"total_amount": 478},
            order_items=ctx["order_items"],
            session_id=session_id,
        )
        history.append({"role": "bot", "content": result["message"]})
        outputs.append(result)

    assert outputs[1]["action"] == "info"
    assert "coupon" in outputs[1]["message"].lower()
    assert outputs[3]["action"] == "escalate"
    assert "review" in outputs[3]["message"].lower()


def test_replacement_reaffirmation_without_strong_evidence_does_not_auto_approve():
    session_id = "test:replacement-reaffirmation-weak-evidence-review"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    ctx["kitchen"] = {"quality_out": "good", "prep_time_mins": 12, "temperature_check": "hot"}
    ctx["fleet"] = {"delay_mins": 1, "traffic_flag": False}
    ctx["trust"] = {"score": 92, "total_orders": 18}
    ctx["order_items"] = {"items": [{"name": "Peri Peri French Fries", "price": 209}]}

    turns = [
        "the fries were totally soggy",
        "can i get a replacement?",
        "no i need another fries",
        "replacement only",
        "no i want replacement",
    ]
    last = None
    for msg in turns:
        history.append({"role": "user", "content": msg})
        last = Rules.resolve(
            complaint=msg,
            conversation_history=history,
            order_value=478,
            trust_score=ctx["trust"]["score"],
            kitchen=ctx["kitchen"],
            fleet=ctx["fleet"],
            trust=ctx["trust"],
            order_details={"total_amount": 478},
            order_items=ctx["order_items"],
            session_id=session_id,
        )
        history.append({"role": "bot", "content": last["message"]})

    assert last is not None
    assert last["action"] == "escalate"
    assert "review" in last["message"].lower()


def test_structured_item_conflict_asks_before_acting_on_selected_item():
    session_id = "test:structured-item-conflict-before-action"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    ctx["order_items"] = {
        "items": [
            {"name": "Roohafza Sharbat", "price": 79},
            {"name": "Dark Chocolate Oreo Shake", "price": 189},
        ]
    }

    complaint = "Damaged or spilled Affected item is Dark Chocolate Oreo Shake. my roohafza was spilled"
    history.append({"role": "user", "content": complaint})
    result = Rules.resolve(
        complaint=complaint,
        conversation_history=history,
        order_value=756,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 20, "temperature_check": "hot"},
        fleet={"delay_mins": 15, "traffic_flag": True},
        trust={"score": 92, "total_orders": 18},
        order_details={"total_amount": 756},
        order_items=ctx["order_items"],
        session_id=session_id,
        assessment={
            "issue_type": "spill_leak",
            "issue_confidence": 0.86,
            "active_item_name": "Dark Chocolate Oreo Shake",
            "fault_hint": "delivery",
        },
    )

    assert result["action"] == "info"
    assert "wrong item" in result["message"].lower() or "roohafza sharbat" in result["message"].lower()
    assert "dark chocolate oreo shake was marked okay" not in result["message"].lower()
    assert get_session_state(session_id).get("pending") == "semantic_clarification"


def test_invalid_live_capture_escalates_without_compensation():
    session_id = "test:invalid-capture-review"
    clear_session(session_id)

    _run_turn(session_id, "i want a replacement because the packaging was crushed and leaking", order_value=650)
    result = _run_turn(
        session_id,
        "here is the video",
        order_value=650,
        photo_url="https://example.com/capture.jpg",
        photo_valid=False,
    )
    assert result["action"] == "escalate"
    assert "review" in result["message"].lower()


def test_photo_evidence_is_scoped_to_the_current_item_case():
    session_id = "test:photo-scoped-to-case"
    clear_session(session_id)

    history = get_session(session_id)
    order_items = {
        "items": [
            {"name": "Roohafza Sharbat", "price": 99},
            {"name": "Dark Chocolate Oreo Shake", "price": 189},
        ]
    }

    turns = [
        (
            "roohafza sharbat was spilled",
            {
                "issue_type": "spill_leak",
                "issue_confidence": 0.95,
                "active_item_name": "Roohafza Sharbat",
            },
            None,
            None,
        ),
        (
            "photo attached",
            {
                "issue_type": "spill_leak",
                "issue_confidence": 0.95,
                "active_item_name": "Roohafza Sharbat",
                "requested_resolution": "replacement",
                "requested_resolution_confidence": 0.95,
            },
            "https://example.com/sharbat.jpg",
            True,
        ),
        (
            "dark chocolate oreo shake also spilled, replace that one",
            {
                "issue_type": "spill_leak",
                "issue_confidence": 0.95,
                "active_item_name": "Dark Chocolate Oreo Shake",
                "requested_resolution": "replacement",
                "requested_resolution_confidence": 0.95,
            },
            None,
            None,
        ),
    ]

    outputs = []
    for complaint, assessment, photo_url, photo_valid in turns:
        if photo_url:
            mark_photo_provided(session_id)
        history.append({"role": "user", "content": complaint})
        result = Rules.resolve(
            complaint=complaint,
            conversation_history=history,
            order_value=756,
            trust_score=85,
            kitchen={"quality_out": "good", "prep_time_mins": 20, "temperature_check": "hot"},
            fleet={"delay_mins": 15, "traffic_flag": True},
            trust={"score": 85, "total_orders": 16},
            order_details={"total_amount": 756},
            order_items=order_items,
            session_id=session_id,
            assessment=assessment,
            photo_url=photo_url,
            photo_valid=photo_valid,
            photo_in_session=session_has_photo(session_id),
        )
        history.append({"role": "bot", "content": result["message"]})
        outputs.append(result)

    assert outputs[1]["action"] == "info"
    assert outputs[2]["action"] == "live_capture"
    assert "photo" in outputs[2]["message"].lower()


def test_delay_complaint_asking_what_happened_keeps_delay_explanation():
    session_id = "test:delay-ask-cause"
    clear_session(session_id)

    history = get_session(session_id)
    history.append({"role": "user", "content": "mera order bahut late aaya kya hua tha"})
    result = Rules.resolve(
        complaint="mera order bahut late aaya kya hua tha",
        conversation_history=history,
        order_value=168,
        trust_score=82,
        kitchen={"quality_out": "good", "prep_time_mins": 10, "temperature_check": "hot"},
        fleet={"delay_mins": 22, "traffic_flag": True},
        trust={"score": 82, "total_orders": 12},
        order_details={"total_amount": 168, "status": "delivered", "delivered_at": "16th Apr 2026, 02:55 pm"},
        order_items={"items": [{"name": "Classic Maggi", "price": 79}]},
        session_id=session_id,
        assessment={
            "issue_type": "delay",
            "issue_confidence": 0.95,
            "info_query": "status",
            "info_query_confidence": 0.95,
            "turn_act": "ask_cause",
            "turn_act_confidence": 0.9,
        },
    )

    assert result["action"] == "info"
    assert result["reason"] == "User asked for the cause of an identified issue"
    assert "delay" in result["message"].lower() or "late" in result["message"].lower()


def test_high_severity_foreign_object_followup_escalates_without_needing_explicit_refund_request():
    session_id = "test:foreign-object-followup-escalates"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    ctx["order_items"] = {"items": [{"name": "Dhaba Style Chicken Curry Rice Bowl", "price": 269}]}

    first_turns = [
        (
            "there was a piece of plastic in my chicken bowl",
            {
                "issue_type": "foreign_object",
                "issue_confidence": 0.98,
                "issue_severity": "high",
                "active_item_name": "Dhaba Style Chicken Curry Rice Bowl",
                "recommended_next_step": "live_capture",
                "visual_evidence_useful": True,
            },
        ),
        (
            "this is outrageous",
            {
                "issue_type": "foreign_object",
                "issue_confidence": 0.98,
                "issue_severity": "high",
                "active_item_name": "Dhaba Style Chicken Curry Rice Bowl",
                "recommended_next_step": "escalate",
                "turn_act": "none",
                "turn_act_confidence": 0.9,
            },
        ),
    ]

    outputs = []
    for msg, assessment in first_turns:
        history.append({"role": "user", "content": msg})
        result = Rules.resolve(
            complaint=msg,
            conversation_history=history,
            order_value=756,
            trust_score=85,
            kitchen={"quality_out": "good", "prep_time_mins": 20, "temperature_check": "hot"},
            fleet={"delay_mins": 15, "traffic_flag": True},
            trust=ctx["trust"],
            order_details={"total_amount": 756},
            order_items=ctx["order_items"],
            session_id=session_id,
            assessment=assessment,
        )
        history.append({"role": "bot", "content": result["message"]})
        outputs.append(result)

    assert outputs[0]["action"] == "info"
    assert outputs[1]["action"] == "escalate"
    assert "can't close this properly" in outputs[1]["message"].lower()


def test_benign_ingredient_mismatch_is_not_classified_as_foreign_object():
    session_id = "test:ingredient-mismatch-not-foreign-object"
    clear_session(session_id)

    history = get_session(session_id)
    history.append({"role": "user", "content": "there was a piece of vegetable in my chicken bowl"})
    result = Rules.resolve(
        complaint="there was a piece of vegetable in my chicken bowl",
        conversation_history=history,
        order_value=756,
        trust_score=85,
        kitchen={"quality_out": "good", "prep_time_mins": 20, "temperature_check": "hot"},
        fleet={"delay_mins": 15, "traffic_flag": True},
        trust={"score": 85, "total_orders": 20},
        order_details={"total_amount": 756},
        order_items={"items": [{"name": "Dhaba Style Chicken Curry Rice Bowl", "price": 269}]},
        session_id=session_id,
    )

    assert result["_debug"]["issue_type"] != "foreign_object"


def test_llm_overcall_to_foreign_object_is_downgraded_for_benign_ingredient_mismatch():
    session_id = "test:ingredient-mismatch-downgrade"
    clear_session(session_id)

    history = get_session(session_id)
    history.append({"role": "user", "content": "there was a piece of vegetable in my chicken bowl"})
    result = Rules.resolve(
        complaint="there was a piece of vegetable in my chicken bowl",
        conversation_history=history,
        order_value=756,
        trust_score=85,
        kitchen={"quality_out": "good", "prep_time_mins": 20, "temperature_check": "hot"},
        fleet={"delay_mins": 15, "traffic_flag": True},
        trust={"score": 85, "total_orders": 20},
        order_details={"total_amount": 756},
        order_items={"items": [{"name": "Dhaba Style Chicken Curry Rice Bowl", "price": 269}]},
        session_id=session_id,
        assessment={
            "issue_type": "foreign_object",
            "issue_confidence": 0.95,
            "active_item_name": "Dhaba Style Chicken Curry Rice Bowl",
            "issue_severity": "high",
        },
    )

    assert result["_debug"]["issue_type"] == "quality"
    assert result["_debug"]["fault"] == "kitchen"
    assert result["_debug"]["visual_evidence_useful"] is False


def test_strong_replacement_evidence_skips_coupon_loop_and_moves_to_confirmation():
    session_id = "test:strong-replacement-skips-coupon-loop"
    clear_session(session_id)

    history = get_session(session_id)
    history.append({"role": "user", "content": "dark chocolate oreo shake spilled badly"})
    first = Rules.resolve(
        complaint="dark chocolate oreo shake spilled badly",
        conversation_history=history,
        order_value=756,
        trust_score=85,
        kitchen={"quality_out": "good", "prep_time_mins": 20, "temperature_check": "hot"},
        fleet={"delay_mins": 15, "traffic_flag": True},
        trust={"score": 85, "total_orders": 20},
        order_details={"total_amount": 756},
        order_items={"items": [{"name": "Dark Chocolate Oreo Shake", "price": 189}]},
        session_id=session_id,
        assessment={
            "issue_type": "spill_leak",
            "issue_confidence": 0.95,
            "active_item_name": "Dark Chocolate Oreo Shake",
            "visual_evidence_useful": True,
        },
    )
    history.append({"role": "bot", "content": first["message"]})

    history.append({"role": "user", "content": "photo attached"})
    second = Rules.resolve(
        complaint="photo attached",
        conversation_history=history,
        order_value=756,
        trust_score=85,
        kitchen={"quality_out": "good", "prep_time_mins": 20, "temperature_check": "hot"},
        fleet={"delay_mins": 15, "traffic_flag": True},
        trust={"score": 85, "total_orders": 20},
        order_details={"total_amount": 756},
        order_items={"items": [{"name": "Dark Chocolate Oreo Shake", "price": 189}]},
        session_id=session_id,
        assessment={
            "issue_type": "spill_leak",
            "issue_confidence": 0.95,
            "active_item_name": "Dark Chocolate Oreo Shake",
            "requested_resolution": "replacement",
            "requested_resolution_confidence": 0.95,
            "visual_evidence_useful": True,
        },
        photo_url="https://example.com/shake.jpg",
        photo_valid=True,
        photo_in_session=True,
    )
    history.append({"role": "bot", "content": second["message"]})

    history.append({"role": "user", "content": "replace it"})
    third = Rules.resolve(
        complaint="replace it",
        conversation_history=history,
        order_value=756,
        trust_score=85,
        kitchen={"quality_out": "good", "prep_time_mins": 20, "temperature_check": "hot"},
        fleet={"delay_mins": 15, "traffic_flag": True},
        trust={"score": 85, "total_orders": 20},
        order_details={"total_amount": 756},
        order_items={"items": [{"name": "Dark Chocolate Oreo Shake", "price": 189}]},
        session_id=session_id,
        assessment={
            "issue_type": "spill_leak",
            "issue_confidence": 0.95,
            "active_item_name": "Dark Chocolate Oreo Shake",
            "requested_resolution": "replacement",
            "requested_resolution_confidence": 0.95,
            "turn_act": "confirm",
            "turn_act_confidence": 0.95,
            "visual_evidence_useful": True,
        },
        photo_in_session=True,
    )

    assert second["action"] == "info"
    assert second["reason"] == "Strong evidence supports moving directly to replacement confirmation"
    assert third["action"] == "replacement"
    assert "fresh dark chocolate oreo shake" in third["message"].lower()


def test_escalated_case_does_not_reopen_into_photo_collection():
    session_id = "test:escalated-case-stays-escalated"
    clear_session(session_id)

    history = get_session(session_id)
    history.append({"role": "user", "content": "there was plastic in my food"})
    first = Rules.resolve(
        complaint="there was plastic in my food",
        conversation_history=history,
        order_value=756,
        trust_score=85,
        kitchen={"quality_out": "good", "prep_time_mins": 20, "temperature_check": "hot"},
        fleet={"delay_mins": 15, "traffic_flag": True},
        trust={"score": 85, "total_orders": 20},
        order_details={"total_amount": 756},
        order_items={"items": [{"name": "Dhaba Style Chicken Curry Rice Bowl", "price": 269}]},
        session_id=session_id,
        assessment={
            "issue_type": "foreign_object",
            "issue_confidence": 0.98,
            "issue_severity": "high",
            "active_item_name": "Dhaba Style Chicken Curry Rice Bowl",
        },
    )
    history.append({"role": "bot", "content": first["message"]})

    history.append({"role": "user", "content": "this is outrageous"})
    second = Rules.resolve(
        complaint="this is outrageous",
        conversation_history=history,
        order_value=756,
        trust_score=85,
        kitchen={"quality_out": "good", "prep_time_mins": 20, "temperature_check": "hot"},
        fleet={"delay_mins": 15, "traffic_flag": True},
        trust={"score": 85, "total_orders": 20},
        order_details={"total_amount": 756},
        order_items={"items": [{"name": "Dhaba Style Chicken Curry Rice Bowl", "price": 269}]},
        session_id=session_id,
        assessment={
            "issue_type": "foreign_object",
            "issue_confidence": 0.98,
            "issue_severity": "high",
            "active_item_name": "Dhaba Style Chicken Curry Rice Bowl",
            "recommended_next_step": "escalate",
        },
    )
    history.append({"role": "bot", "content": second["message"]})

    history.append({"role": "user", "content": "but i need refund compensation"})
    third = Rules.resolve(
        complaint="but i need refund compensation",
        conversation_history=history,
        order_value=756,
        trust_score=85,
        kitchen={"quality_out": "good", "prep_time_mins": 20, "temperature_check": "hot"},
        fleet={"delay_mins": 15, "traffic_flag": True},
        trust={"score": 85, "total_orders": 20},
        order_details={"total_amount": 756},
        order_items={"items": [{"name": "Dhaba Style Chicken Curry Rice Bowl", "price": 269}]},
        session_id=session_id,
        assessment={
            "issue_type": "foreign_object",
            "issue_confidence": 0.98,
            "issue_severity": "high",
            "active_item_name": "Dhaba Style Chicken Curry Rice Bowl",
            "requested_resolution": "refund",
            "requested_resolution_confidence": 0.95,
        },
    )

    assert second["action"] == "escalate"
    assert third["action"] == "escalate"
    assert third["reason"] == "Case already marked for manual review"


def test_replacement_approval_does_not_reopen_confirmation_loop():
    session_id = "test:replacement-approved-stays-approved"
    clear_session(session_id)

    history = get_session(session_id)
    order_items = {"items": [{"name": "Dark Chocolate Oreo Shake", "price": 189}]}

    turns = [
        (
            "shake spilled badly",
            {
                "issue_type": "spill_leak",
                "issue_confidence": 0.95,
                "active_item_name": "Dark Chocolate Oreo Shake",
                "visual_evidence_useful": True,
            },
            None,
            None,
        ),
        (
            "photo attached",
            {
                "issue_type": "spill_leak",
                "issue_confidence": 0.95,
                "active_item_name": "Dark Chocolate Oreo Shake",
                "requested_resolution": "replacement",
                "requested_resolution_confidence": 0.95,
                "visual_evidence_useful": True,
            },
            "https://example.com/shake.jpg",
            True,
        ),
        (
            "yes replace it",
            {
                "issue_type": "spill_leak",
                "issue_confidence": 0.95,
                "active_item_name": "Dark Chocolate Oreo Shake",
                "requested_resolution": "replacement",
                "requested_resolution_confidence": 0.95,
                "turn_act": "confirm",
                "turn_act_confidence": 0.95,
            },
            None,
            None,
        ),
    ]

    last = None
    for complaint, assessment, photo_url, photo_valid in turns:
        history.append({"role": "user", "content": complaint})
        last = Rules.resolve(
            complaint=complaint,
            conversation_history=history,
            order_value=756,
            trust_score=85,
            kitchen={"quality_out": "good", "prep_time_mins": 20, "temperature_check": "hot"},
            fleet={"delay_mins": 15, "traffic_flag": True},
            trust={"score": 85, "total_orders": 20},
            order_details={"total_amount": 756},
            order_items=order_items,
            session_id=session_id,
            assessment=assessment,
            photo_url=photo_url,
            photo_valid=photo_valid,
            photo_in_session=bool(photo_url),
        )
        history.append({"role": "bot", "content": last["message"]})

    history.append({"role": "user", "content": "yeah get me another one"})
    after = Rules.resolve(
        complaint="yeah get me another one",
        conversation_history=history,
        order_value=756,
        trust_score=85,
        kitchen={"quality_out": "good", "prep_time_mins": 20, "temperature_check": "hot"},
        fleet={"delay_mins": 15, "traffic_flag": True},
        trust={"score": 85, "total_orders": 20},
        order_details={"total_amount": 756},
        order_items=order_items,
        session_id=session_id,
        assessment={
            "issue_type": "spill_leak",
            "issue_confidence": 0.95,
            "active_item_name": "Dark Chocolate Oreo Shake",
            "requested_resolution": "replacement",
            "requested_resolution_confidence": 0.95,
            "turn_act": "confirm",
            "turn_act_confidence": 0.95,
        },
    )

    assert last["action"] == "replacement"
    assert after["action"] == "info"
    assert after["reason"] == "Replacement already approved"


def test_replacement_status_survives_refund_review_request():
    session_id = "test:replacement-status-survives-refund-review"
    clear_session(session_id)

    history = get_session(session_id)
    order_items = {"items": [{"name": "Dark Chocolate Oreo Shake", "price": 189}]}

    turns = [
        (
            "shake spilled badly",
            {
                "issue_type": "spill_leak",
                "issue_confidence": 0.95,
                "issue_severity": "medium",
                "active_item_name": "Dark Chocolate Oreo Shake",
                "visual_evidence_useful": True,
            },
            None,
            None,
        ),
        (
            "photo attached",
            {
                "issue_type": "spill_leak",
                "issue_confidence": 0.95,
                "issue_severity": "medium",
                "active_item_name": "Dark Chocolate Oreo Shake",
                "requested_resolution": "replacement",
                "requested_resolution_confidence": 0.95,
                "visual_evidence_useful": True,
            },
            "https://example.com/shake.jpg",
            True,
        ),
        (
            "yes replace it",
            {
                "issue_type": "spill_leak",
                "issue_confidence": 0.95,
                "issue_severity": "medium",
                "active_item_name": "Dark Chocolate Oreo Shake",
                "requested_resolution": "replacement",
                "requested_resolution_confidence": 0.95,
                "turn_act": "confirm",
                "turn_act_confidence": 0.95,
            },
            None,
            None,
        ),
    ]

    replacement = None
    for complaint, assessment, photo_url, photo_valid in turns:
        history.append({"role": "user", "content": complaint})
        replacement = Rules.resolve(
            complaint=complaint,
            conversation_history=history,
            order_value=756,
            trust_score=85,
            kitchen={"quality_out": "good", "prep_time_mins": 20, "temperature_check": "hot"},
            fleet={"delay_mins": 15, "traffic_flag": True},
            trust={"score": 85, "total_orders": 20},
            order_details={"total_amount": 756},
            order_items=order_items,
            session_id=session_id,
            assessment=assessment,
            photo_url=photo_url,
            photo_valid=photo_valid,
            photo_in_session=bool(photo_url),
        )
        history.append({"role": "bot", "content": replacement["message"]})

    assert replacement["action"] == "replacement"

    history.append({"role": "user", "content": "can I get a refund instead?"})
    refund_review = Rules.resolve(
        complaint="can I get a refund instead?",
        conversation_history=history,
        order_value=756,
        trust_score=85,
        kitchen={"quality_out": "good", "prep_time_mins": 20, "temperature_check": "hot"},
        fleet={"delay_mins": 15, "traffic_flag": True},
        trust={"score": 85, "total_orders": 20},
        order_details={"total_amount": 756},
        order_items=order_items,
        session_id=session_id,
        assessment={
            "issue_type": "spill_leak",
            "issue_confidence": 0.95,
            "issue_severity": "medium",
            "active_item_name": "Dark Chocolate Oreo Shake",
            "requested_resolution": "refund",
            "requested_resolution_confidence": 0.95,
            "turn_act": "switch_resolution",
            "turn_act_confidence": 0.95,
        },
    )
    history.append({"role": "bot", "content": refund_review["message"]})

    assert refund_review["action"] == "escalate"
    assert get_session_state(session_id).get("last_action") == "escalate"
    assert get_session_state(session_id).get("approved_replacement_item_name") == "Dark Chocolate Oreo Shake"
    assert get_session_state(session_id).get("approved_replacement_status") == "cancel_requested_for_refund_review"

    history.append({"role": "user", "content": "in how much time will my replacemetn arrive?"})
    status = Rules.resolve(
        complaint="in how much time will my replacemetn arrive?",
        conversation_history=history,
        order_value=756,
        trust_score=85,
        kitchen={"quality_out": "good", "prep_time_mins": 20, "temperature_check": "hot"},
        fleet={"delay_mins": 15, "traffic_flag": True},
        trust={"score": 85, "total_orders": 20},
        order_details={"total_amount": 756},
        order_items=order_items,
        session_id=session_id,
        assessment={
            "issue_type": "other",
            "issue_confidence": 0.2,
            "turn_act": "ask_status",
            "turn_act_confidence": 0.8,
        },
    )

    assert status["action"] == "info"
    assert status["reason"] == "User asked for approved replacement status"
    assert "cancelled" in status["message"].lower()
    assert "refund change for review" in status["message"].lower()
    assert "15 to 20 mins" not in status["message"]
    assert "already marked for review" not in status["message"].lower()


def test_emotional_followup_does_not_reclassify_established_case():
    session_id = "test:emotional-followup-inherits-case"
    clear_session(session_id)

    history = get_session(session_id)
    order_items = {"items": [{"name": "Dhaba Style Chicken Curry Rice Bowl", "price": 269}]}

    first = Rules.resolve(
        complaint="there was a piece of vegetable in my chicken bowl",
        conversation_history=[{"role": "user", "content": "there was a piece of vegetable in my chicken bowl"}],
        order_value=756,
        trust_score=85,
        kitchen={"quality_out": "good", "prep_time_mins": 20, "temperature_check": "hot"},
        fleet={"delay_mins": 15, "traffic_flag": True},
        trust={"score": 85, "total_orders": 20},
        order_details={"total_amount": 756},
        order_items=order_items,
        session_id=session_id,
        assessment={
            "issue_type": "foreign_object",
            "issue_confidence": 0.95,
            "active_item_name": "Dhaba Style Chicken Curry Rice Bowl",
            "issue_severity": "high",
        },
    )
    history.append({"role": "user", "content": "there was a piece of vegetable in my chicken bowl"})
    history.append({"role": "bot", "content": first["message"]})

    history.append({"role": "user", "content": "this is outrageous"})
    second = Rules.resolve(
        complaint="this is outrageous",
        conversation_history=history,
        order_value=756,
        trust_score=85,
        kitchen={"quality_out": "good", "prep_time_mins": 20, "temperature_check": "hot"},
        fleet={"delay_mins": 15, "traffic_flag": True},
        trust={"score": 85, "total_orders": 20},
        order_details={"total_amount": 756},
        order_items=order_items,
        session_id=session_id,
        assessment={
            "issue_type": "foreign_object",
            "issue_confidence": 0.98,
            "issue_severity": "high",
            "recommended_next_step": "escalate",
        },
    )

    assert first["_debug"]["issue_type"] == "quality"
    assert second["_debug"]["issue_type"] == "quality"
    assert second["action"] == "info"


def test_concrete_followup_can_change_issue_type_when_user_adds_new_detail():
    session_id = "test:concrete-followup-does-not-force-old-case"
    clear_session(session_id)

    history = get_session(session_id)
    order_items = {"items": [{"name": "Dhaba Style Chicken Curry Rice Bowl", "price": 269}]}

    first = Rules.resolve(
        complaint="there was a piece of vegetable in my chicken bowl",
        conversation_history=[{"role": "user", "content": "there was a piece of vegetable in my chicken bowl"}],
        order_value=756,
        trust_score=85,
        kitchen={"quality_out": "good", "prep_time_mins": 20, "temperature_check": "cold"},
        fleet={"delay_mins": 15, "traffic_flag": True},
        trust={"score": 85, "total_orders": 20},
        order_details={"total_amount": 756},
        order_items=order_items,
        session_id=session_id,
        assessment={
            "issue_type": "foreign_object",
            "issue_confidence": 0.95,
            "active_item_name": "Dhaba Style Chicken Curry Rice Bowl",
            "issue_severity": "high",
        },
    )
    history.append({"role": "user", "content": "there was a piece of vegetable in my chicken bowl"})
    history.append({"role": "bot", "content": first["message"]})

    history.append({"role": "user", "content": "it was cold too"})
    second = Rules.resolve(
        complaint="it was cold too",
        conversation_history=history,
        order_value=756,
        trust_score=85,
        kitchen={"quality_out": "good", "prep_time_mins": 20, "temperature_check": "cold"},
        fleet={"delay_mins": 15, "traffic_flag": True},
        trust={"score": 85, "total_orders": 20},
        order_details={"total_amount": 756},
        order_items=order_items,
        session_id=session_id,
        assessment={
            "issue_type": "temperature",
            "issue_confidence": 0.95,
            "issue_severity": "medium",
        },
    )

    assert first["_debug"]["issue_type"] == "quality"
    assert second["_debug"]["issue_type"] == "temperature"


def test_non_serious_refund_escalates_after_coupon_instead_of_auto_refund():
    session_id = "test:non-serious-refund-review"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    ctx["kitchen"] = {"quality_out": "good", "prep_time_mins": 12, "temperature_check": "hot"}
    ctx["fleet"] = {"delay_mins": 1, "traffic_flag": False}
    ctx["order_items"] = {"items": [{"name": "Peri Peri French Fries", "price": 209}]}

    for msg in ["the fries were less in quantity", "i want a refund"]:
        history.append({"role": "user", "content": msg})
        result = Rules.resolve(
            complaint=msg,
            conversation_history=history,
            order_value=478,
            trust_score=92,
            kitchen=ctx["kitchen"],
            fleet=ctx["fleet"],
            trust=ctx["trust"],
            order_details={"total_amount": 478},
            order_items=ctx["order_items"],
            session_id=session_id,
        )
        history.append({"role": "bot", "content": result["message"]})

    history.append({"role": "user", "content": "no i need a refund"})
    first_push = Rules.resolve(
        complaint="no i need a refund",
        conversation_history=history,
        order_value=478,
        trust_score=92,
        kitchen=ctx["kitchen"],
        fleet=ctx["fleet"],
        trust=ctx["trust"],
        order_details={"total_amount": 478},
        order_items=ctx["order_items"],
        session_id=session_id,
    )
    history.append({"role": "bot", "content": first_push["message"]})
    assert first_push["action"] == "info"
    assert "coupon" in first_push["message"].lower()

    history.append({"role": "user", "content": "still no i need a refund"})
    result = Rules.resolve(
        complaint="still no i need a refund",
        conversation_history=history,
        order_value=478,
        trust_score=92,
        kitchen=ctx["kitchen"],
        fleet=ctx["fleet"],
        trust=ctx["trust"],
        order_details={"total_amount": 478},
        order_items=ctx["order_items"],
        session_id=session_id,
    )
    assert result["action"] == "escalate"
    assert "refund" in result["message"].lower()
    assert "review" in result["message"].lower()


def test_portion_size_refund_path_uses_smarter_economic_preference():
    session_id = "test:portion-refund-smart-econ"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    ctx["kitchen"] = {"quality_out": "good", "prep_time_mins": 10, "temperature_check": "hot"}
    ctx["fleet"] = {"delay_mins": 2, "traffic_flag": False}
    ctx["order_items"] = {"items": [{"name": "Peri Peri French Fries", "price": 209}]}

    for msg in ["peri peri french fries were less in quantity", "i want a refund", "no i need a refund"]:
        history.append({"role": "user", "content": msg})
        result = Rules.resolve(
            complaint=msg,
            conversation_history=history,
            order_value=478,
            trust_score=92,
            kitchen=ctx["kitchen"],
            fleet=ctx["fleet"],
            trust=ctx["trust"],
            order_details={"total_amount": 478},
            order_items=ctx["order_items"],
            session_id=session_id,
        )
        history.append({"role": "bot", "content": result["message"]})

    assert result["action"] == "info"
    assert "coupon" in result["message"].lower()

    history.append({"role": "user", "content": "still no i need a refund"})
    result = Rules.resolve(
        complaint="still no i need a refund",
        conversation_history=history,
        order_value=478,
        trust_score=92,
        kitchen=ctx["kitchen"],
        fleet=ctx["fleet"],
        trust=ctx["trust"],
        order_details={"total_amount": 478},
        order_items=ctx["order_items"],
        session_id=session_id,
    )
    assert result["action"] == "escalate"
    assert "review" in result["message"].lower()
    assert "fresh peri peri french fries" not in result["message"].lower()


def test_too_less_phrase_is_understood_on_first_turn():
    session_id = "test:too-less-first-turn"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    ctx["kitchen"] = {"quality_out": "good", "prep_time_mins": 12, "temperature_check": "hot"}
    ctx["fleet"] = {"delay_mins": 5, "traffic_flag": False}
    ctx["order_items"] = {"items": [{"name": "Peri Peri French Fries", "price": 209}]}

    history.append({"role": "user", "content": "the fries were too less"})
    result = Rules.resolve(
        complaint="the fries were too less",
        conversation_history=history,
        order_value=478,
        trust_score=82,
        kitchen=ctx["kitchen"],
        fleet=ctx["fleet"],
        trust=ctx["trust"],
        order_details={"total_amount": 478},
        order_items=ctx["order_items"],
        session_id=session_id,
    )

    assert result["_debug"]["issue_type"] == "portion_size"
    assert "portion size" in result["message"].lower() or "light for what you paid" in result["message"].lower()


def test_non_veg_in_veg_with_valid_photo_moves_to_real_refund_path():
    session_id = "test:dietary-violation-refund"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    ctx["trust"]["score"] = 82
    ctx["kitchen"] = {"quality_out": "good", "prep_time_mins": 20, "temperature_check": "hot"}
    ctx["fleet"] = {"delay_mins": 15, "traffic_flag": True}
    ctx["order_items"] = {"items": [{"name": "Veg Pink Sauce Pasta", "price": 219}]}

    turns = [
        ("there was a piece of chick in themy veg pasta", None, None),
        ("CAN I get a refund", None, None),
        ("photo attached", "https://example.com/photo.jpg", True),
        ("no i need a refund", None, None),
    ]
    outputs = []
    for complaint, photo_url, photo_valid in turns:
        if photo_url:
            mark_photo_provided(session_id)
        history.append({"role": "user", "content": complaint})
        result = Rules.resolve(
            complaint=complaint,
            conversation_history=history,
            order_value=756,
            trust_score=82,
            kitchen=ctx["kitchen"],
            fleet=ctx["fleet"],
            trust=ctx["trust"],
            order_details={"total_amount": 756},
            order_items=ctx["order_items"],
            photo_url=photo_url,
            photo_valid=photo_valid,
            photo_in_session=session_has_photo(session_id),
            session_id=session_id,
        )
        history.append({"role": "bot", "content": result["message"]})
        outputs.append(result)

    assert outputs[0]["_debug"]["issue_type"] == "foreign_object"
    assert outputs[1]["action"] == "live_capture"
    assert outputs[2]["action"] == "info"
    assert "coupon" in outputs[2]["message"].lower()
    assert outputs[3]["action"] == "info"
    assert "25%" in outputs[3]["message"]


def test_truncated_non_veg_in_veg_phrase_is_detected_as_serious_dietary_violation():
    session_id = "test:dietary-violation-typo"
    clear_session(session_id)

    history = get_session(session_id)
    history.append({"role": "user", "content": "there was a piece of chick in themy veg pasta"})
    result = Rules.resolve(
        complaint="there was a piece of chick in themy veg pasta",
        conversation_history=history,
        order_value=756,
        trust_score=82,
        kitchen={"quality_out": "good", "prep_time_mins": 20, "temperature_check": "hot"},
        fleet={"delay_mins": 15, "traffic_flag": True},
        trust={"score": 82, "total_orders": 16},
        order_details={"total_amount": 756},
        order_items={"items": [{"name": "Veg Pink Sauce Pasta", "price": 219}]},
        session_id=session_id,
    )

    assert result["_debug"]["issue_type"] == "foreign_object"
    assert "safety" in result["message"].lower() or "shouldn't have happened" in result["message"].lower()


def test_llm_economic_preference_can_override_generic_cost_formula_when_valid():
    session_id = "test:llm-economic-preference"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    ctx["kitchen"] = {"quality_out": "good", "prep_time_mins": 10, "temperature_check": "hot"}
    ctx["fleet"] = {"delay_mins": 2, "traffic_flag": False}
    ctx["order_items"] = {"items": [{"name": "Peri Peri French Fries", "price": 209}]}

    history.append({"role": "user", "content": "the fries were less in quantity"})
    first = Rules.resolve(
        complaint="the fries were less in quantity",
        conversation_history=history,
        order_value=478,
        trust_score=92,
        kitchen=ctx["kitchen"],
        fleet=ctx["fleet"],
        trust=ctx["trust"],
        order_details={"total_amount": 478},
        order_items=ctx["order_items"],
        session_id=session_id,
        assessment={
            "issue_type": "portion_size",
            "issue_confidence": 0.9,
            "issue_severity": "low",
            "economic_preference": "refund",
            "economic_confidence": 0.88,
        },
    )
    history.append({"role": "bot", "content": first["message"]})

    history.append({"role": "user", "content": "i want a refund"})
    second = Rules.resolve(
        complaint="i want a refund",
        conversation_history=history,
        order_value=478,
        trust_score=92,
        kitchen=ctx["kitchen"],
        fleet=ctx["fleet"],
        trust=ctx["trust"],
        order_details={"total_amount": 478},
        order_items=ctx["order_items"],
        session_id=session_id,
            assessment={
                "requested_resolution": "refund",
                "requested_resolution_confidence": 0.91,
                "economic_preference": "refund",
                "economic_confidence": 0.88,
            },
    )
    history.append({"role": "bot", "content": second["message"]})

    history.append({"role": "user", "content": "no i need a refund"})
    third = Rules.resolve(
        complaint="no i need a refund",
        conversation_history=history,
        order_value=478,
        trust_score=92,
        kitchen=ctx["kitchen"],
        fleet=ctx["fleet"],
        trust=ctx["trust"],
        order_details={"total_amount": 478},
        order_items=ctx["order_items"],
        session_id=session_id,
            assessment={
                "requested_resolution": "refund",
                "requested_resolution_confidence": 0.91,
                "economic_preference": "refund",
                "economic_confidence": 0.88,
            },
    )

    assert third["action"] == "info"
    assert "coupon" in third["message"].lower()


def test_replacement_request_does_not_mention_refund_when_user_wants_replacement():
    session_id = "test:replacement-no-refund-mention"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    ctx["trust"]["score"] = 85
    ctx["order_items"] = {"items": [{"name": "Veg Pink Sauce Pasta", "price": 219}]}

    for msg in ["the pasta was too dry", "can i get a replacement order?", "no i need another pasta"]:
        history.append({"role": "user", "content": msg})
        result = Rules.resolve(
            complaint=msg,
            conversation_history=history,
            order_value=756,
            trust_score=85,
            kitchen={"quality_out": "fair", "prep_time_mins": 20, "temperature_check": "hot"},
            fleet={"delay_mins": 4, "traffic_flag": False},
            trust=ctx["trust"],
            order_details={"total_amount": 756},
            order_items=ctx["order_items"],
            session_id=session_id,
        )
        history.append({"role": "bot", "content": result["message"]})

    assert result["action"] == "info"
    assert "refund" not in result["message"].lower()
    assert "fresh veg pink sauce pasta" in result["message"].lower()


def test_high_value_complaint_requests_photo():
    session_id = "test:photo"
    clear_session(session_id)

    result = _run_turn(session_id, "i want a refund because the packaging was crushed and leaking", order_value=650)
    assert result["action"] == "live_capture"
    assert "photo" in result["message"].lower()


def test_low_trust_refund_escalates():
    session_id = "test:lowtrust"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    ctx["trust"]["score"] = 45

    history.append({"role": "user", "content": "i want refund"})
    first = Rules.resolve(
        complaint="i want refund",
        conversation_history=history,
        order_value=222,
        trust_score=45,
        kitchen=ctx["kitchen"],
        fleet=ctx["fleet"],
        trust=ctx["trust"],
        order_details=ctx["order_details"],
        order_items=ctx["order_items"],
        session_id=session_id,
    )
    history.append({"role": "bot", "content": first["message"]})

    history.append({"role": "user", "content": "no refund"})
    second = Rules.resolve(
        complaint="no refund",
        conversation_history=history,
        order_value=222,
        trust_score=45,
        kitchen=ctx["kitchen"],
        fleet=ctx["fleet"],
        trust=ctx["trust"],
        order_details=ctx["order_details"],
        order_items=ctx["order_items"],
        session_id=session_id,
    )
    history.append({"role": "bot", "content": second["message"]})

    assert second["action"] == "escalate"


def test_order_items_question_is_not_treated_as_complaint():
    session_id = "test:info-query"
    clear_session(session_id)

    result = _run_turn(session_id, "what were the items in this order?", order_value=222)
    assert result["action"] == "info"
    assert "butter" not in result["message"].lower()
    assert "classic maggi" in result["message"].lower() or "cold coffee" in result["message"].lower()


def test_high_value_first_complaint_does_not_force_photo_without_comp_request():
    session_id = "test:high-value-no-photo-first-turn"
    clear_session(session_id)

    result = _run_turn(session_id, "the coffee was too bitter", order_value=650)
    assert result["action"] == "info"
    assert "photo" not in result["message"].lower()


def test_replacement_flow_keeps_original_item_when_user_stops_naming_it():
    session_id = "test:item-memory"
    clear_session(session_id)

    _run_turn(session_id, "the maggi came too soggy", order_value=168)
    _run_turn(session_id, "can you get me a replacement order?", order_value=168)
    third = _run_turn(session_id, "no i need a full replacement order", order_value=168)
    assert "classic maggi" in third["message"].lower()

    fourth = _run_turn(session_id, "yes", order_value=168)
    assert fourth["action"] == "replacement"
    assert "classic maggi" in fourth["message"].lower()


def test_followup_messages_do_not_repeat_same_opener():
    session_id = "test:human-tone"
    clear_session(session_id)

    first = _run_turn(session_id, "the maggi came too soggy", order_value=168)
    second = _run_turn(session_id, "but it was still soggy when it arrived", order_value=168)

    assert first["action"] == "info"
    assert second["action"] == "info"
    assert first["message"] != second["message"]


def test_typo_replacement_request_is_understood():
    session_id = "test:fuzzy-replacement"
    clear_session(session_id)

    _run_turn(session_id, "the maggi came soggy", order_value=168)
    result = _run_turn(session_id, "can i get a replcemnt", order_value=168)
    assert result["action"] == "info"
    assert "coupon" in result["message"].lower()


def test_eta_after_replacement_uses_replacement_state():
    session_id = "test:replacement-eta"
    clear_session(session_id)

    _run_turn(session_id, "the maggi came soggy", order_value=168)
    _run_turn(session_id, "i want a replacement", order_value=168)
    _run_turn(session_id, "no i need another maggi", order_value=168)
    replacement = _run_turn(session_id, "yes", order_value=168)
    assert replacement["action"] == "replacement"

    eta = _run_turn(session_id, "in how long will i get it?", order_value=168)
    assert eta["action"] == "info"
    assert "15 to 20" in eta["message"] or "eta" in eta["message"].lower() or "update in-app" in eta["message"].lower()


def test_high_value_temperature_replacement_does_not_force_photo():
    session_id = "test:no-photo-for-cold-drink"
    clear_session(session_id)

    _run_turn(session_id, "the roohafza isnt cold", order_value=756)
    result = _run_turn(session_id, "can i get a replacement?", order_value=756)
    assert result["action"] == "info"
    assert "coupon" in result["message"].lower()


def test_high_value_non_visual_refund_request_does_not_force_photo():
    session_id = "test:no-photo-for-non-visual-high-value"
    clear_session(session_id)

    _run_turn(session_id, "the biryani tasted terrible", order_value=820)
    result = _run_turn(session_id, "i want a refund", order_value=820)
    assert result["action"] == "info"
    assert "coupon" in result["message"].lower()


def test_assurance_after_replacement_is_grounded_and_english():
    session_id = "test:assurance"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    ctx["fleet"] = {"delay_mins": 15, "traffic_flag": True}
    ctx["order_items"] = {"items": [{"name": "Roohafza Sharbat", "price": 79}]}

    for msg in [
        "the roohafza isnt cold",
        "i want a replacement",
        "no i need another roohafza",
        "yes",
        "are you sure it will be cold this time?",
    ]:
        history.append({"role": "user", "content": msg})
        result = Rules.resolve(
            complaint=msg,
            conversation_history=history,
            order_value=756,
            trust_score=92,
            kitchen=ctx["kitchen"],
            fleet=ctx["fleet"],
            trust=ctx["trust"],
            order_details={"total_amount": 756},
            order_items=ctx["order_items"],
            session_id=session_id,
        )
        history.append({"role": "bot", "content": result["message"]})

    assert result["action"] == "info"
    assert "kitchen" in result["message"].lower()
    assert "promise" in result["message"].lower()
    assert "bhai" not in result["message"].lower()


def test_spill_complaint_does_not_default_to_kitchen_when_logs_point_to_transit():
    session_id = "test:spill-transit"
    clear_session(session_id)

    history = get_session(session_id)
    history.append({"role": "user", "content": "the salad was all spilled"})
    result = Rules.resolve(
        complaint="the salad was all spilled",
        conversation_history=history,
        order_value=627,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 15, "temperature_check": "cold"},
        fleet={"delay_mins": 8, "traffic_flag": True},
        trust={"score": 92, "total_orders": 18},
        order_details={"total_amount": 627},
        order_items={"items": [{"name": "Caesar Salad", "price": 259}]},
        session_id=session_id,
    )
    assert result["action"] == "info"
    assert "transit" in result["message"].lower() or "delivery" in result["message"].lower()
    assert "kitchen miss" not in result["message"].lower()


def test_good_logs_quality_complaint_stays_honest_when_fault_is_unclear():
    session_id = "test:unclear-quality"
    clear_session(session_id)

    history = get_session(session_id)
    history.append({"role": "user", "content": "the pasta tasted terrible"})
    result = Rules.resolve(
        complaint="the pasta tasted terrible",
        conversation_history=history,
        order_value=219,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 12, "temperature_check": "hot"},
        fleet={"delay_mins": 2, "traffic_flag": False},
        trust={"score": 92, "total_orders": 18},
        order_details={"total_amount": 219},
        order_items={"items": [{"name": "Veg Pink Sauce Pasta", "price": 219}]},
        session_id=session_id,
    )
    assert result["action"] == "info"
    assert "don't point" in result["message"].lower() or "don't" in result["message"].lower()
    assert "kitchen miss" not in result["message"].lower()


def test_temperature_complaint_can_blame_delivery_when_logs_support_it():
    session_id = "test:temp-delivery"
    clear_session(session_id)

    history = get_session(session_id)
    history.append({"role": "user", "content": "the coffee was warm"})
    result = Rules.resolve(
        complaint="the coffee was warm",
        conversation_history=history,
        order_value=159,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 11, "temperature_check": "cold"},
        fleet={"delay_mins": 16, "traffic_flag": True},
        trust={"score": 92, "total_orders": 18},
        order_details={"total_amount": 159},
        order_items={"items": [{"name": "Classic Cold Coffee", "price": 159}]},
        session_id=session_id,
    )
    assert result["action"] == "info"
    assert "delivery delay" in result["message"].lower() or "delivery" in result["message"].lower()


def test_wrong_item_refund_request_requires_visual_evidence_then_returns_to_coupon_flow():
    session_id = "test:wrong-item-coverage"
    clear_session(session_id)

    history = get_session(session_id)
    order_items = {"items": [{"name": "Veg Burger", "price": 180}, {"name": "Fries", "price": 80}]}

    turns = [
        ("i got the wrong item", None, None, False),
        ("i want a refund", None, None, False),
        ("photo attached", "https://example.com/proof.jpg", True, True),
    ]
    outputs = []
    for complaint, photo_url, photo_valid, photo_in_session in turns:
        if photo_url:
            mark_photo_provided(session_id)
        history.append({"role": "user", "content": complaint})
        result = Rules.resolve(
            complaint=complaint,
            conversation_history=history,
            order_value=260,
            trust_score=92,
            kitchen={"quality_out": "good", "prep_time_mins": 10, "temperature_check": "hot"},
            fleet={"delay_mins": 3, "traffic_flag": False},
            trust={"score": 92, "total_orders": 18},
            order_details={"total_amount": 260},
            order_items=order_items,
            photo_url=photo_url,
            photo_valid=photo_valid,
            photo_in_session=session_has_photo(session_id) or photo_in_session,
            session_id=session_id,
        )
        history.append({"role": "bot", "content": result["message"]})
        outputs.append(result)

    assert outputs[0]["_debug"]["issue_type"] == "wrong_item"
    assert outputs[1]["action"] == "live_capture"
    assert "photo" in outputs[1]["message"].lower()
    assert outputs[2]["action"] == "info"
    assert "coupon" in outputs[2]["message"].lower()


def test_missing_item_replacement_request_uses_missing_item_photo_message_then_coupon():
    session_id = "test:missing-item-coverage"
    clear_session(session_id)

    history = get_session(session_id)
    order_items = {"items": [{"name": "Veg Burger", "price": 180}, {"name": "Fries", "price": 80}]}

    turns = [
        ("one item was missing", None, None, False),
        ("i need a replacement", None, None, False),
        ("photo attached", "https://example.com/proof.jpg", True, True),
    ]
    outputs = []
    for complaint, photo_url, photo_valid, photo_in_session in turns:
        if photo_url:
            mark_photo_provided(session_id)
        history.append({"role": "user", "content": complaint})
        result = Rules.resolve(
            complaint=complaint,
            conversation_history=history,
            order_value=260,
            trust_score=92,
            kitchen={"quality_out": "good", "prep_time_mins": 10, "temperature_check": "hot"},
            fleet={"delay_mins": 3, "traffic_flag": False},
            trust={"score": 92, "total_orders": 18},
            order_details={"total_amount": 260},
            order_items=order_items,
            photo_url=photo_url,
            photo_valid=photo_valid,
            photo_in_session=session_has_photo(session_id) or photo_in_session,
            session_id=session_id,
        )
        history.append({"role": "bot", "content": result["message"]})
        outputs.append(result)

    assert outputs[0]["_debug"]["issue_type"] == "missing_item"
    assert outputs[1]["action"] == "live_capture"
    assert "what arrived" in outputs[1]["message"].lower()
    assert outputs[2]["action"] == "info"
    assert "coupon" in outputs[2]["message"].lower()


def test_damaged_replacement_request_uses_general_evidence_gated_coupon_flow():
    session_id = "test:damaged-coverage"
    clear_session(session_id)

    history = get_session(session_id)
    order_items = {"items": [{"name": "Noodles", "price": 220}]}

    turns = [
        ("the packaging was crushed and damaged", None, None, False),
        ("i want a replacement", None, None, False),
        ("photo attached", "https://example.com/proof.jpg", True, True),
    ]
    outputs = []
    for complaint, photo_url, photo_valid, photo_in_session in turns:
        if photo_url:
            mark_photo_provided(session_id)
        history.append({"role": "user", "content": complaint})
        result = Rules.resolve(
            complaint=complaint,
            conversation_history=history,
            order_value=320,
            trust_score=92,
            kitchen={"quality_out": "good", "prep_time_mins": 10, "temperature_check": "hot"},
            fleet={"delay_mins": 12, "traffic_flag": True},
            trust={"score": 92, "total_orders": 18},
            order_details={"total_amount": 320},
            order_items=order_items,
            photo_url=photo_url,
            photo_valid=photo_valid,
            photo_in_session=session_has_photo(session_id) or photo_in_session,
            session_id=session_id,
        )
        history.append({"role": "bot", "content": result["message"]})
        outputs.append(result)

    assert outputs[0]["_debug"]["issue_type"] == "damaged"
    assert "transit" in outputs[0]["message"].lower() or "delivery" in outputs[0]["message"].lower()
    assert outputs[1]["action"] == "live_capture"
    assert outputs[2]["action"] == "info"
    assert "coupon" in outputs[2]["message"].lower()


def test_delay_refund_request_stays_on_non_visual_refund_path():
    session_id = "test:delay-coverage"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = {
        "kitchen": {"quality_out": "good", "prep_time_mins": 10, "temperature_check": "hot"},
        "fleet": {"delay_mins": 22, "traffic_flag": True},
        "trust": {"score": 92, "total_orders": 18},
        "order_details": {"total_amount": 320},
        "order_items": {"items": [{"name": "Noodles", "price": 220}]},
    }

    outputs = []
    for msg in ["my order is very late", "i want a refund", "no i need a refund"]:
        history.append({"role": "user", "content": msg})
        result = Rules.resolve(
            complaint=msg,
            conversation_history=history,
            order_value=320,
            trust_score=92,
            kitchen=ctx["kitchen"],
            fleet=ctx["fleet"],
            trust=ctx["trust"],
            order_details=ctx["order_details"],
            order_items=ctx["order_items"],
            session_id=session_id,
        )
        history.append({"role": "bot", "content": result["message"]})
        outputs.append(result)

    second, third = outputs[1], outputs[2]

    assert second["action"] == "info"
    assert "coupon" in second["message"].lower()
    assert "photo" not in second["message"].lower()
    assert third["action"] == "info"
    assert "25%" in third["message"]


def test_portion_size_phrasings_are_detected_and_explained_credibly():
    session_id = "test:portion-size-language"
    clear_session(session_id)

    history = get_session(session_id)
    history.append({"role": "user", "content": "i got very less food"})
    result = Rules.resolve(
        complaint="i got very less food",
        conversation_history=history,
        order_value=219,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 12, "temperature_check": "hot"},
        fleet={"delay_mins": 2, "traffic_flag": False},
        trust={"score": 92, "total_orders": 18},
        order_details={"total_amount": 219},
        order_items={"items": [{"name": "Veg Pink Sauce Pasta", "price": 219}]},
        session_id=session_id,
    )
    assert result["action"] == "info"
    assert "portion size" in result["message"].lower() or "under-portioned" in result["message"].lower() or "felt under-portioned" in result["message"].lower()
    assert "logging this against the kitchen" in result["message"].lower() or "noted it" in result["message"].lower()


def test_portion_size_not_enough_food_phrase_is_detected():
    session_id = "test:portion-not-enough"
    clear_session(session_id)

    history = get_session(session_id)
    history.append({"role": "user", "content": "this was not enough food for what i paid"})
    result = Rules.resolve(
        complaint="this was not enough food for what i paid",
        conversation_history=history,
        order_value=219,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 12, "temperature_check": "hot"},
        fleet={"delay_mins": 2, "traffic_flag": False},
        trust={"score": 92, "total_orders": 18},
        order_details={"total_amount": 219},
        order_items={"items": [{"name": "Veg Pink Sauce Pasta", "price": 219}]},
        session_id=session_id,
    )
    assert result["action"] == "info"
    assert "verify portion size" in result["message"].lower()


def test_portion_size_message_does_not_parrot_customer_complaint():
    session_id = "test:portion-parrot"
    clear_session(session_id)

    history = get_session(session_id)
    history.append({"role": "user", "content": "peri peri french fries were less in quantity"})
    result = Rules.resolve(
        complaint="peri peri french fries were less in quantity",
        conversation_history=history,
        order_value=478,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 10, "temperature_check": "hot"},
        fleet={"delay_mins": 2, "traffic_flag": False},
        trust={"score": 92, "total_orders": 18},
        order_details={"total_amount": 478},
        order_items={"items": [{"name": "Peri Peri French Fries", "price": 209}]},
        session_id=session_id,
    )
    assert result["action"] == "info"
    assert "less in quantity" not in result["message"].lower()
    assert "seemed less than usual" not in result["message"].lower()
    assert "logging this against the kitchen" in result["message"].lower()


def test_assessment_can_understand_collapsed_typo_portion_phrase():
    session_id = "test:portion-veryless"
    clear_session(session_id)

    history = get_session(session_id)
    history.append({"role": "user", "content": "the fries were veryless"})
    result = Rules.resolve(
        complaint="the fries were veryless",
        conversation_history=history,
        order_value=478,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 10, "temperature_check": "hot"},
        fleet={"delay_mins": 2, "traffic_flag": False},
        trust={"score": 92, "total_orders": 18},
        order_details={"total_amount": 478},
        order_items={"items": [{"name": "Peri Peri French Fries", "price": 209}]},
        session_id=session_id,
        assessment={
            "issue_type": "portion_size",
            "issue_confidence": 0.81,
            "active_item_name": "Peri Peri French Fries",
        },
    )
    assert result["action"] == "info"
    assert "portion size" in result["message"].lower() or "sounds light" in result["message"].lower()


def test_assessment_can_upgrade_ambiguous_issue_type_to_portion_size():
    session_id = "test:assessment-portion"
    clear_session(session_id)

    history = get_session(session_id)
    history.append({"role": "user", "content": "this felt skimpy for the price"})
    result = Rules.resolve(
        complaint="this felt skimpy for the price",
        conversation_history=history,
        order_value=219,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 12, "temperature_check": "hot"},
        fleet={"delay_mins": 2, "traffic_flag": False},
        trust={"score": 92, "total_orders": 18},
        order_details={"total_amount": 219},
        order_items={"items": [{"name": "Veg Pink Sauce Pasta", "price": 219}]},
        session_id=session_id,
        assessment={
            "issue_type": "portion_size",
            "issue_confidence": 0.91,
            "visual_evidence_useful": False,
        },
    )
    assert result["action"] == "info"
    assert "under-portioned" in result["message"].lower() or "portion size" in result["message"].lower()
    assert result["_debug"]["issue_type_source"] == "llm"


def test_llm_assessment_can_handle_typo_heavy_portion_complaint():
    session_id = "test:assessment-typo-portion"
    clear_session(session_id)

    history = get_session(session_id)
    history.append({"role": "user", "content": "fries wr vry less fr price"})
    result = Rules.resolve(
        complaint="fries wr vry less fr price",
        conversation_history=history,
        order_value=478,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 10, "temperature_check": "hot"},
        fleet={"delay_mins": 2, "traffic_flag": False},
        trust={"score": 92, "total_orders": 18},
        order_details={"total_amount": 478},
        order_items={"items": [{"name": "Peri Peri French Fries", "price": 209}]},
        session_id=session_id,
        assessment={
            "issue_type": "portion_size",
            "issue_confidence": 0.62,
            "visual_evidence_useful": False,
            "active_item_name": "Peri Peri French Fries",
        },
    )
    assert result["action"] == "info"
    assert "sounds light for what you paid" in result["message"].lower() or "portion size" in result["message"].lower()
    assert result["_debug"]["issue_type_source"] == "llm"


def test_first_complaint_does_not_force_empathy_starter_for_generic_issue():
    session_id = "test:no-forced-starter"
    clear_session(session_id)

    history = get_session(session_id)
    history.append({"role": "user", "content": "the fries were veryless"})
    result = Rules.resolve(
        complaint="the fries were veryless",
        conversation_history=history,
        order_value=478,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 10, "temperature_check": "hot"},
        fleet={"delay_mins": 2, "traffic_flag": False},
        trust={"score": 92, "total_orders": 18},
        order_details={"total_amount": 478},
        order_items={"items": [{"name": "Peri Peri French Fries", "price": 209}]},
        session_id=session_id,
    )
    assert result["action"] == "info"
    assert not result["message"].lower().startswith("that’s a fair call")
    assert not result["message"].lower().startswith("sorry about that")


def test_portion_size_coupon_offer_uses_portion_specific_language():
    session_id = "test:portion-tone"
    clear_session(session_id)

    history = get_session(session_id)
    history.append({"role": "user", "content": "the fries were less in quantity"})
    first = Rules.resolve(
        complaint="the fries were less in quantity",
        conversation_history=history,
        order_value=478,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 10, "temperature_check": "hot"},
        fleet={"delay_mins": 2, "traffic_flag": False},
        trust={"score": 92, "total_orders": 18},
        order_details={"total_amount": 478},
        order_items={"items": [{"name": "Peri Peri French Fries", "price": 209}]},
        session_id=session_id,
    )
    history.append({"role": "bot", "content": first["message"]})

    history.append({"role": "user", "content": "i want a refund"})
    second = Rules.resolve(
        complaint="i want a refund",
        conversation_history=history,
        order_value=478,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 10, "temperature_check": "hot"},
        fleet={"delay_mins": 2, "traffic_flag": False},
        trust={"score": 92, "total_orders": 18},
        order_details={"total_amount": 478},
        order_items={"items": [{"name": "Peri Peri French Fries", "price": 209}]},
        session_id=session_id,
    )

    assert second["action"] == "info"
    assert "fries quantity" in second["message"].lower()
    assert "coupon" in second["message"].lower()


def test_foreign_object_coupon_offer_avoids_generic_quality_language():
    session_id = "test:foreign-object-tone"
    clear_session(session_id)

    history = get_session(session_id)
    history.append({"role": "user", "content": "there was plastic in my veg pasta"})
    first = Rules.resolve(
        complaint="there was plastic in my veg pasta",
        conversation_history=history,
        order_value=756,
        trust_score=82,
        kitchen={"quality_out": "good", "prep_time_mins": 20, "temperature_check": "hot"},
        fleet={"delay_mins": 15, "traffic_flag": True},
        trust={"score": 82, "total_orders": 16},
        order_details={"total_amount": 756},
        order_items={"items": [{"name": "Veg Pink Sauce Pasta", "price": 219}]},
        session_id=session_id,
    )
    history.append({"role": "bot", "content": first["message"]})

    history.append({"role": "user", "content": "i want a refund"})
    second = Rules.resolve(
        complaint="i want a refund",
        conversation_history=history,
        order_value=756,
        trust_score=82,
        kitchen={"quality_out": "good", "prep_time_mins": 20, "temperature_check": "hot"},
        fleet={"delay_mins": 15, "traffic_flag": True},
        trust={"score": 82, "total_orders": 16},
        order_details={"total_amount": 756},
        order_items={"items": [{"name": "Veg Pink Sauce Pasta", "price": 219}]},
        photo_url="https://example.com/photo.jpg",
        photo_valid=True,
        photo_in_session=True,
        session_id=session_id,
    )

    assert second["action"] == "info"
    assert "quality complaint" not in second["message"].lower()
    assert "next step" in second["message"].lower() or "moving for you" in second["message"].lower()


def test_sensitive_tone_guardrail_softens_refund_reinforcement_language():
    session_id = "test:sensitive-tone-guardrail"
    clear_session(session_id)

    history = get_session(session_id)
    outputs = []
    for msg, assessment, photo_url, photo_valid, photo_in_session in [
        (
            "there was plastic in my veg pasta",
            {
                "issue_type": "foreign_object",
                "issue_confidence": 0.92,
                "issue_severity": "high",
                "tone_guardrail": "sensitive",
                "negotiation_allowed": True,
                "negotiation_strength": "light",
            },
            None,
            None,
            False,
        ),
        (
            "i want a refund",
            {
                "requested_resolution": "refund",
                "requested_resolution_confidence": 0.95,
                "issue_type": "foreign_object",
                "issue_confidence": 0.92,
                "issue_severity": "high",
                "tone_guardrail": "sensitive",
                "negotiation_allowed": True,
                "negotiation_strength": "light",
            },
            "https://example.com/photo.jpg",
            True,
            True,
        ),
        (
            "no i still want a refund",
            {
                "requested_resolution": "refund",
                "requested_resolution_confidence": 0.95,
                "turn_act": "switch_resolution",
                "turn_act_confidence": 0.94,
                "issue_type": "foreign_object",
                "issue_confidence": 0.92,
                "tone_guardrail": "sensitive",
                "negotiation_allowed": True,
                "negotiation_strength": "light",
            },
            None,
            None,
            False,
        ),
    ]:
        if photo_url:
            mark_photo_provided(session_id)
        history.append({"role": "user", "content": msg})
        result = Rules.resolve(
            complaint=msg,
            conversation_history=history,
            order_value=756,
            trust_score=82,
            kitchen={"quality_out": "good", "prep_time_mins": 20, "temperature_check": "hot"},
            fleet={"delay_mins": 15, "traffic_flag": True},
            trust={"score": 82, "total_orders": 16},
            order_details={"total_amount": 756},
            order_items={"items": [{"name": "Veg Pink Sauce Pasta", "price": 219}]},
            session_id=session_id,
            assessment=assessment,
            photo_url=photo_url,
            photo_valid=photo_valid,
            photo_in_session=session_has_photo(session_id) or photo_in_session,
        )
        history.append({"role": "bot", "content": result["message"]})
        outputs.append(result)

    assert outputs[1]["action"] == "info"
    assert "moving for you" in outputs[1]["message"].lower() or "next step" in outputs[1]["message"].lower()
    assert "quality complaint" not in outputs[1]["message"].lower()
    assert "because this is more serious" not in outputs[1]["message"].lower()


def test_negotiation_disallowed_replacement_offer_goes_direct():
    session_id = "test:no-negotiation-replacement"
    clear_session(session_id)

    history = get_session(session_id)
    history.append({"role": "user", "content": "the order was off"})
    first = Rules.resolve(
        complaint="the order was off",
        conversation_history=history,
        order_value=168,
        trust_score=92,
        kitchen={"quality_out": "fair", "prep_time_mins": 18, "temperature_check": "warm"},
        fleet={"delay_mins": 0, "traffic_flag": False},
        trust={"score": 92, "total_orders": 18},
        order_details={"total_amount": 168},
        order_items={"items": [{"name": "Classic Maggi", "price": 79}]},
        session_id=session_id,
        assessment={
            "issue_type": "quality",
            "issue_confidence": 0.8,
        },
    )
    history.append({"role": "bot", "content": first["message"]})
    history.append({"role": "user", "content": "i want a replacement"})
    second = Rules.resolve(
        complaint="i want a replacement",
        conversation_history=history,
        order_value=168,
        trust_score=92,
        kitchen={"quality_out": "fair", "prep_time_mins": 18, "temperature_check": "warm"},
        fleet={"delay_mins": 0, "traffic_flag": False},
        trust={"score": 92, "total_orders": 18},
        order_details={"total_amount": 168},
        order_items={"items": [{"name": "Classic Maggi", "price": 79}]},
        session_id=session_id,
        assessment={
            "requested_resolution": "replacement",
            "requested_resolution_confidence": 0.94,
            "issue_type": "quality",
            "issue_confidence": 0.8,
            "active_item_name": "Classic Maggi",
            "tone_guardrail": "operational",
            "negotiation_allowed": False,
            "negotiation_strength": "none",
        },
    )

    assert second["action"] == "info"
    assert "coupon" in second["message"].lower() or "review" in second["message"].lower()
    assert "fresh classic maggi" not in second["message"].lower()


def test_delay_coupon_offer_stays_delay_specific():
    session_id = "test:delay-tone"
    clear_session(session_id)

    history = get_session(session_id)
    history.append({"role": "user", "content": "my order is very late"})
    first = Rules.resolve(
        complaint="my order is very late",
        conversation_history=history,
        order_value=320,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 10, "temperature_check": "hot"},
        fleet={"delay_mins": 22, "traffic_flag": True},
        trust={"score": 92, "total_orders": 18},
        order_details={"total_amount": 320},
        order_items={"items": [{"name": "Noodles", "price": 220}]},
        session_id=session_id,
    )
    history.append({"role": "bot", "content": first["message"]})

    history.append({"role": "user", "content": "i want a refund"})
    second = Rules.resolve(
        complaint="i want a refund",
        conversation_history=history,
        order_value=320,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 10, "temperature_check": "hot"},
        fleet={"delay_mins": 22, "traffic_flag": True},
        trust={"score": 92, "total_orders": 18},
        order_details={"total_amount": 320},
        order_items={"items": [{"name": "Noodles", "price": 220}]},
        session_id=session_id,
    )

    assert second["action"] == "info"
    assert "for the delay" in second["message"].lower()


def test_unclear_coupon_reply_gets_clarification_instead_of_repeat():
    session_id = "test:clarify-coupon"
    clear_session(session_id)

    _run_turn(session_id, "the maggi was soggy", order_value=168)
    _run_turn(session_id, "i want a refund", order_value=168)
    result = _run_turn(session_id, "whatever works ig", order_value=168)
    assert result["action"] == "info"
    assert "just to be sure" in result["message"].lower()
    assert "coupon, a refund, or a replacement" in result["message"].lower()


def test_refund_amount_parser_handles_number_inside_natural_phrase():
    session_id = "test:refund-natural-number"
    clear_session(session_id)

    _run_turn(session_id, "i got the wrong item", order_value=168)
    _run_turn(session_id, "i want a refund", order_value=168, photo_url="https://example.com/proof.jpg", photo_valid=True)
    _run_turn(session_id, "no i need a refund", order_value=168)
    result = _run_turn(session_id, "75 is gtg", order_value=168)
    assert result["action"] == "refund"
    assert result["amount"] == 126


def test_assessment_can_trigger_live_capture_for_ambiguous_visual_complaint():
    session_id = "test:assessment-visual"
    clear_session(session_id)

    history = get_session(session_id)
    history.append({"role": "user", "content": "the box was a mess when it got here"})
    result = Rules.resolve(
        complaint="the box was a mess when it got here",
        conversation_history=history,
        order_value=627,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 15, "temperature_check": "cold"},
        fleet={"delay_mins": 8, "traffic_flag": True},
        trust={"score": 92, "total_orders": 18},
        order_details={"total_amount": 627},
        order_items={"items": [{"name": "Caesar Salad", "price": 259}, {"name": "Cold Coffee", "price": 159}]},
        session_id=session_id,
        assessment={
            "issue_type": "spill_leak",
            "issue_confidence": 0.88,
            "requested_resolution": "refund",
            "visual_evidence_useful": True,
        },
    )
    assert result["action"] == "live_capture"
    assert "photo" in result["message"].lower()


def test_fuzzy_item_matching_keeps_item_name_for_typos():
    session_id = "test:fuzzy-item"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    ctx["order_items"] = {
        "items": [
            {"name": "Roohafza Sharbat", "price": 79},
            {"name": "Dark Chocolate Oreo Shake", "price": 189},
        ]
    }

    history.append({"role": "user", "content": "the rooafza isnt cold"})
    first = Rules.resolve(
        complaint="the rooafza isnt cold",
        conversation_history=history,
        order_value=756,
        trust_score=ctx["trust"]["score"],
        kitchen=ctx["kitchen"],
        fleet=ctx["fleet"],
        trust=ctx["trust"],
        order_details=ctx["order_details"],
        order_items=ctx["order_items"],
        session_id=session_id,
    )
    history.append({"role": "bot", "content": first["message"]})

    history.append({"role": "user", "content": "can i get a replacement?"})
    second = Rules.resolve(
        complaint="can i get a replacement?",
        conversation_history=history,
        order_value=756,
        trust_score=ctx["trust"]["score"],
        kitchen=ctx["kitchen"],
        fleet=ctx["fleet"],
        trust=ctx["trust"],
        order_details=ctx["order_details"],
        order_items=ctx["order_items"],
        session_id=session_id,
    )
    history.append({"role": "bot", "content": second["message"]})

    history.append({"role": "user", "content": "no I ened another cold reooafxa"})
    result = Rules.resolve(
        complaint="no I ened another cold reooafxa",
        conversation_history=history,
        order_value=756,
        trust_score=ctx["trust"]["score"],
        kitchen=ctx["kitchen"],
        fleet=ctx["fleet"],
        trust=ctx["trust"],
        order_details=ctx["order_details"],
        order_items=ctx["order_items"],
        session_id=session_id,
    )
    assert "roohafza" in result["message"].lower()


def test_refund_request_after_replacement_approval_does_not_restart_coupon_loop():
    session_id = "test:refund-after-replacement"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    ctx["trust"]["score"] = 82
    ctx["kitchen"] = {"quality_out": "fair", "prep_time_mins": 18, "temperature_check": "warm"}
    ctx["fleet"] = {"delay_mins": 0, "traffic_flag": False}
    ctx["order_items"] = {"items": [{"name": "Classic Maggi", "price": 79}]}

    for msg in [
        "the maggi came soggy",
        "can I get an replacment",
        "I want the replacment",
        "yes",
        "how long will it take?",
        "then leave get me a refund instead",
    ]:
        history.append({"role": "user", "content": msg})
        result = Rules.resolve(
            complaint=msg,
            conversation_history=history,
            order_value=168,
            trust_score=82,
            kitchen=ctx["kitchen"],
            fleet=ctx["fleet"],
            trust=ctx["trust"],
            order_details={"total_amount": 168},
            order_items=ctx["order_items"],
            session_id=session_id,
        )
        history.append({"role": "bot", "content": result["message"]})

    assert result["action"] == "escalate"
    assert "cancelled" in result["message"].lower()
    assert "refund change for review" in result["message"].lower()


def test_pending_replacement_status_question_does_not_confirm_replacement():
    session_id = "test:pending-replacement-status-not-confirmation"
    clear_session(session_id)

    state = get_session_state(session_id)
    state["pending"] = "replacement_confirm"
    state["desired_resolution"] = "replacement"
    state["case_issue_type"] = "spill_leak"
    state["issue_type"] = "spill_leak"
    state["active_item_name"] = "Classic Maggi"
    state["order_value"] = 168
    state["evidence_strength"] = "strong"

    history = get_session(session_id)
    history.append({"role": "bot", "content": "I can get a fresh Classic Maggi remade for you instead. Want me to go ahead with that?"})
    complaint = "in how much time will my replacement arrive?"
    history.append({"role": "user", "content": complaint})

    result = Rules.resolve(
        complaint=complaint,
        conversation_history=history,
        order_value=168,
        trust_score=92,
        kitchen={"quality_out": "fair", "prep_time_mins": 6, "temperature_check": "warm"},
        fleet={"delay_mins": 4, "traffic_flag": False},
        trust={"score": 92, "total_orders": 18},
        order_details={"total_amount": 168},
        order_items={"items": [{"name": "Classic Maggi", "price": 79}]},
        session_id=session_id,
    )

    assert result["action"] == "info"
    assert result["reason"] in {
        "User asked for active complaint status",
        "User asked about pending replacement status",
    }
    assert "need you to confirm" in result["message"].lower()
    assert get_session_state(session_id).get("pending") == "replacement_confirm"
    assert get_session_state(session_id).get("last_action") != "replacement"


def test_replacement_intent_in_coupon_state_is_not_misread_as_coupon_acceptance():
    session_id = "test:replacement-not-coupon-accept"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    ctx["trust"]["score"] = 82
    ctx["kitchen"] = {"quality_out": "fair", "prep_time_mins": 18, "temperature_check": "warm"}
    ctx["fleet"] = {"delay_mins": 0, "traffic_flag": False}
    ctx["order_items"] = {"items": [{"name": "Classic Maggi", "price": 79}]}

    for msg in [
        "the maggi came soggy",
        "can you just get me a refund?",
        "okay then just get me another maggi",
    ]:
        history.append({"role": "user", "content": msg})
        result = Rules.resolve(
            complaint=msg,
            conversation_history=history,
            order_value=168,
            trust_score=82,
            kitchen=ctx["kitchen"],
            fleet=ctx["fleet"],
            trust=ctx["trust"],
            order_details={"total_amount": 168},
            order_items=ctx["order_items"],
            session_id=session_id,
        )
        history.append({"role": "bot", "content": result["message"]})

    assert result["action"] == "info"
    assert "fresh classic maggi" in result["message"].lower()


def test_yess_confirms_replacement_without_extra_loop():
    session_id = "test:yess-replacement"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    ctx["order_items"] = {"items": [{"name": "Classic Maggi", "price": 79}]}

    for msg in ["the maggi came soggy", "i want a replacement", "i want the replacment", "yess"]:
        history.append({"role": "user", "content": msg})
        result = Rules.resolve(
            complaint=msg,
            conversation_history=history,
            order_value=168,
            trust_score=82,
            kitchen={"quality_out": "fair", "prep_time_mins": 18, "temperature_check": "warm"},
            fleet={"delay_mins": 0, "traffic_flag": False},
            trust=ctx["trust"],
            order_details={"total_amount": 168},
            order_items=ctx["order_items"],
            session_id=session_id,
        )
        history.append({"role": "bot", "content": result["message"]})

    assert result["action"] == "replacement"


def test_llm_turn_act_switch_resolution_beats_coupon_acceptance():
    session_id = "test:turn-act-switch-over-okay"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    ctx["order_items"] = {"items": [{"name": "Classic Maggi", "price": 79}]}

    for msg, assessment in [
        ("the maggi came soggy", None),
        ("can you just get me a refund?", {"requested_resolution": "refund", "requested_resolution_confidence": 0.92, "turn_act": "switch_resolution", "turn_act_confidence": 0.92}),
        ("okay then just get me another maggi", {"requested_resolution": "replacement", "requested_resolution_confidence": 0.92, "turn_act": "switch_resolution", "turn_act_confidence": 0.92}),
    ]:
        history.append({"role": "user", "content": msg})
        result = Rules.resolve(
            complaint=msg,
            conversation_history=history,
            order_value=168,
            trust_score=82,
            kitchen={"quality_out": "fair", "prep_time_mins": 18, "temperature_check": "warm"},
            fleet={"delay_mins": 0, "traffic_flag": False},
            trust=ctx["trust"],
            order_details={"total_amount": 168},
            order_items=ctx["order_items"],
            session_id=session_id,
            assessment=assessment,
        )
        history.append({"role": "bot", "content": result["message"]})

    assert result["action"] == "info"
    assert "fresh classic maggi" in result["message"].lower()


def test_llm_turn_act_confirm_accepts_yess():
    session_id = "test:turn-act-yess"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    ctx["order_items"] = {"items": [{"name": "Classic Maggi", "price": 79}]}

    for msg, assessment in [
        ("the maggi came soggy", None),
        ("i want a replacement", {"requested_resolution": "replacement", "requested_resolution_confidence": 0.93, "turn_act": "switch_resolution", "turn_act_confidence": 0.93}),
        ("i want the replacment", {"requested_resolution": "replacement", "requested_resolution_confidence": 0.93, "turn_act": "switch_resolution", "turn_act_confidence": 0.93}),
        ("yess", {"turn_act": "confirm", "turn_act_confidence": 0.91}),
    ]:
        history.append({"role": "user", "content": msg})
        result = Rules.resolve(
            complaint=msg,
            conversation_history=history,
            order_value=168,
            trust_score=82,
            kitchen={"quality_out": "fair", "prep_time_mins": 18, "temperature_check": "warm"},
            fleet={"delay_mins": 0, "traffic_flag": False},
            trust=ctx["trust"],
            order_details={"total_amount": 168},
            order_items=ctx["order_items"],
            session_id=session_id,
            assessment=assessment,
        )
        history.append({"role": "bot", "content": result["message"]})

    assert result["action"] == "replacement"


def test_high_severity_replacement_path_negotiates_before_confirming_replacement():
    session_id = "test:strong-replacement-negotiation"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    ctx["order_items"] = {"items": [{"name": "Roohafza Sharbat", "price": 99}]}

    for msg, assessment in [
        ("sharbat was spilled", {"issue_type": "spill_leak", "issue_confidence": 0.91, "active_item_name": "Roohafza Sharbat"}),
        ("i need a replacement", {"requested_resolution": "replacement", "requested_resolution_confidence": 0.94, "turn_act": "switch_resolution", "turn_act_confidence": 0.94, "issue_type": "spill_leak", "issue_confidence": 0.91, "active_item_name": "Roohafza Sharbat"}),
        ("photo attached", {"issue_type": "spill_leak", "issue_confidence": 0.91, "requested_resolution": "replacement", "requested_resolution_confidence": 0.94, "active_item_name": "Roohafza Sharbat"},),
        ("then arrange replacement", {"issue_type": "spill_leak", "issue_confidence": 0.91, "active_item_name": "Roohafza Sharbat", "requested_resolution": "replacement", "requested_resolution_confidence": 0.94, "turn_act": "confirm", "turn_act_confidence": 0.94}),
    ]:
        history.append({"role": "user", "content": msg})
        result = Rules.resolve(
            complaint=msg,
            conversation_history=history,
            order_value=756,
            trust_score=82,
            kitchen={"quality_out": "good", "prep_time_mins": 20, "temperature_check": "hot"},
            fleet={"delay_mins": 15, "traffic_flag": True},
            trust=ctx["trust"],
            order_details={"total_amount": 756},
            order_items=ctx["order_items"],
            session_id=session_id,
            assessment=assessment,
            photo_url="https://example.com/p.jpg" if msg == "photo attached" else None,
            photo_valid=True if msg == "photo attached" else None,
            photo_in_session=True if msg == "photo attached" else False,
        )
        history.append({"role": "bot", "content": result["message"]})

    assert "fresh roohafza sharbat" in history[-1]["content"].lower()
    assert result["action"] == "replacement"


def test_high_severity_foreign_object_replacement_path_also_negotiates_before_confirming():
    session_id = "test:high-severity-foreign-object-replacement-negotiation"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    ctx["order_items"] = {"items": [{"name": "Veg Pink Sauce Pasta", "price": 219}]}

    turns = [
        (
            "there was plastic in my veg pasta",
            {"issue_type": "foreign_object", "issue_confidence": 0.94, "issue_severity": "high"},
            None,
            None,
            False,
        ),
        (
            "i need a replacement",
            {
                "requested_resolution": "replacement",
                "requested_resolution_confidence": 0.95,
                "turn_act": "switch_resolution",
                "turn_act_confidence": 0.95,
                "issue_type": "foreign_object",
                "issue_confidence": 0.94,
                "issue_severity": "high",
            },
            None,
            None,
            False,
        ),
        (
            "photo attached",
            {
                "issue_type": "foreign_object",
                "issue_confidence": 0.94,
                "issue_severity": "high",
                "requested_resolution": "replacement",
                "requested_resolution_confidence": 0.95,
            },
            "https://example.com/photo.jpg",
            True,
            True,
        ),
        (
            "no i still need a replacement",
            {
                "requested_resolution": "replacement",
                "requested_resolution_confidence": 0.95,
                "turn_act": "switch_resolution",
                "turn_act_confidence": 0.94,
            },
            None,
            None,
            False,
        ),
    ]

    outputs = []
    for msg, assessment, photo_url, photo_valid, photo_in_session in turns:
        if photo_url:
            mark_photo_provided(session_id)
        history.append({"role": "user", "content": msg})
        result = Rules.resolve(
            complaint=msg,
            conversation_history=history,
            order_value=756,
            trust_score=82,
            kitchen={"quality_out": "good", "prep_time_mins": 20, "temperature_check": "hot"},
            fleet={"delay_mins": 15, "traffic_flag": True},
            trust=ctx["trust"],
            order_details={"total_amount": 756},
            order_items=ctx["order_items"],
            session_id=session_id,
                assessment=assessment,
                photo_url=photo_url,
                photo_valid=photo_valid,
                photo_in_session=session_has_photo(session_id) or photo_in_session,
            )
        history.append({"role": "bot", "content": result["message"]})
        outputs.append(result)

    assert outputs[2]["action"] == "info"
    assert "coupon" in outputs[2]["message"].lower()
    assert outputs[3]["action"] == "info"
    assert "coupon" in outputs[3]["message"].lower()
    assert "fresh veg pink sauce pasta" not in outputs[3]["message"].lower()


def test_llm_can_force_clarification_for_ambiguous_turn():
    session_id = "test:llm-clarify-ambiguous"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    msg = "its just off"
    history.append({"role": "user", "content": msg})
    result = Rules.resolve(
        complaint=msg,
        conversation_history=history,
        order_value=149,
        trust_score=86,
        kitchen={"quality_out": "good", "prep_time_mins": 12, "temperature_check": "hot"},
        fleet={"delay_mins": 0, "traffic_flag": False},
        trust=ctx["trust"],
        order_details={"total_amount": 149},
        order_items=ctx["order_items"],
        session_id=session_id,
        assessment={
            "issue_type": "other",
            "issue_confidence": 0.52,
            "turn_act": "clarify",
            "recommended_next_step": "clarify",
            "clarification_needed": True,
        },
    )

    assert result["action"] == "info"
    assert "make sure i get this right" in result["message"].lower()
    assert result["_debug"]["clarification_needed"] is True


def test_assessment_low_confidence_does_not_fallback_to_phrase_matching():
    session_id = "test:no-understanding-fallback"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    msg = "the fries were veryless"
    history.append({"role": "user", "content": msg})
    result = Rules.resolve(
        complaint=msg,
        conversation_history=history,
        order_value=149,
        trust_score=86,
        kitchen={"quality_out": "good", "prep_time_mins": 12, "temperature_check": "hot"},
        fleet={"delay_mins": 0, "traffic_flag": False},
        trust=ctx["trust"],
        order_details={"total_amount": 149},
        order_items={"items": [{"name": "Peri Peri French Fries", "price": 149}]},
        session_id=session_id,
        assessment={
            "issue_type": "other",
            "issue_confidence": 0.2,
            "requested_resolution": "none",
            "turn_act": "none",
        },
    )

    assert result["action"] == "info"
    assert "make sure i get this right" in result["message"].lower()
    assert result["_debug"]["issue_type"] == "other"


def test_low_confidence_requested_resolution_clarifies_instead_of_switching_flow():
    session_id = "test:low-confidence-resolution"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    history.append({"role": "user", "content": "the order was off"})
    first = Rules.resolve(
        complaint="the order was off",
        conversation_history=history,
        order_value=149,
        trust_score=86,
        kitchen={"quality_out": "good", "prep_time_mins": 12, "temperature_check": "hot"},
        fleet={"delay_mins": 0, "traffic_flag": False},
        trust=ctx["trust"],
        order_details={"total_amount": 149},
        order_items=ctx["order_items"],
        session_id=session_id,
        assessment={
            "issue_type": "other",
            "issue_confidence": 0.44,
            "requested_resolution": "refund",
            "requested_resolution_confidence": 0.31,
            "turn_act": "clarify",
            "turn_act_confidence": 0.72,
            "clarification_needed": True,
            "recommended_next_step": "clarify",
        },
    )

    assert first["action"] == "info"
    assert "make sure i get this right" in first["message"].lower()
    assert first["_debug"]["requested_resolution"] == "none"


def test_low_confidence_turn_act_does_not_confirm_pending_replacement():
    session_id = "test:low-confidence-turn-act"
    clear_session(session_id)
    history = get_session(session_id)
    ctx = _base_context()
    ctx["order_items"] = {"items": [{"name": "Classic Maggi", "price": 79}]}

    for msg, assessment in [
        ("the maggi came soggy", None),
        ("i want a replacement", {"requested_resolution": "replacement", "requested_resolution_confidence": 0.93, "turn_act": "switch_resolution", "turn_act_confidence": 0.92, "issue_type": "quality", "issue_confidence": 0.9}),
        ("yes", {"turn_act": "confirm", "turn_act_confidence": 0.22}),
    ]:
        history.append({"role": "user", "content": msg})
        result = Rules.resolve(
            complaint=msg,
            conversation_history=history,
            order_value=168,
            trust_score=82,
            kitchen={"quality_out": "fair", "prep_time_mins": 18, "temperature_check": "warm"},
            fleet={"delay_mins": 0, "traffic_flag": False},
            trust=ctx["trust"],
            order_details={"total_amount": 168},
            order_items=ctx["order_items"],
            session_id=session_id,
            assessment=assessment,
        )
        history.append({"role": "bot", "content": result["message"]})

    assert result["action"] == "info"
    assert "just to be sure" in result["message"].lower() or "want me to go ahead" in result["message"].lower()


def test_llm_fault_hint_can_break_unclear_tie_but_not_override_clear_data():
    session_id = "test:llm-fault-hint"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    msg = "the roohafza was not cold enough"
    history.append({"role": "user", "content": msg})
    result = Rules.resolve(
        complaint=msg,
        conversation_history=history,
        order_value=99,
        trust_score=88,
        kitchen={"quality_out": "good", "prep_time_mins": 8, "temperature_check": "hot"},
        fleet={"delay_mins": 0, "traffic_flag": False},
        trust=ctx["trust"],
        order_details={"total_amount": 99},
        order_items={"items": [{"name": "Roohafza Sharbat", "price": 99}]},
        session_id=session_id,
        assessment={
            "issue_type": "temperature",
            "issue_confidence": 0.84,
            "fault_hint": "delivery",
        },
    )

    assert result["_debug"]["fault"] == "delivery"
    assert result["_debug"]["fault_source"] == "llm"

    clear_session(session_id)
    history = get_session(session_id)
    history.append({"role": "user", "content": msg})
    result = Rules.resolve(
        complaint=msg,
        conversation_history=history,
        order_value=99,
        trust_score=88,
        kitchen={"quality_out": "fair", "prep_time_mins": 8, "temperature_check": "warm"},
        fleet={"delay_mins": 15, "traffic_flag": True},
        trust=ctx["trust"],
        order_details={"total_amount": 99},
        order_items={"items": [{"name": "Roohafza Sharbat", "price": 99}]},
        session_id=session_id,
        assessment={
            "issue_type": "temperature",
            "issue_confidence": 0.84,
            "fault_hint": "delivery",
        },
    )

    assert result["_debug"]["fault"] == "kitchen"
    assert result["_debug"]["fault_source"] == "fallback"


def test_strong_hinglish_spill_signal_overrides_generic_quality_assessment():
    session_id = "test:hinglish-spill-override"
    clear_session(session_id)

    history = get_session(session_id)
    msg = "Roohafza Sharbat bag me spill ho gaya tha aur refund chahiye"
    history.append({"role": "user", "content": msg})
    result = Rules.resolve(
        complaint=msg,
        conversation_history=history,
        order_value=756,
        trust_score=88,
        kitchen={"quality_out": "good", "prep_time_mins": 12, "temperature_check": "hot"},
        fleet={"delay_mins": 15, "traffic_flag": True},
        trust={"score": 88, "total_orders": 24},
        order_details={"total_amount": 756},
        order_items={"items": [{"name": "Roohafza Sharbat", "price": 79}]},
        session_id=session_id,
        assessment={
            "issue_type": "quality",
            "issue_confidence": 0.91,
            "requested_resolution": "refund",
            "requested_resolution_confidence": 0.92,
            "active_item_name": "Roohafza Sharbat",
        },
    )

    assert result["action"] == "live_capture"
    assert get_session_state(session_id)["issue_type"] == "spill_leak"


def test_strong_hinglish_quantity_signal_overrides_generic_quality_assessment():
    session_id = "test:hinglish-portion-override"
    clear_session(session_id)

    history = get_session(session_id)
    msg = "Mini Punjabi Aloo Samosa quantity bahut kam thi"
    history.append({"role": "user", "content": msg})
    result = Rules.resolve(
        complaint=msg,
        conversation_history=history,
        order_value=437,
        trust_score=88,
        kitchen={"quality_out": "good", "prep_time_mins": 12, "temperature_check": "hot"},
        fleet={"delay_mins": 3, "traffic_flag": False},
        trust={"score": 88, "total_orders": 24},
        order_details={"total_amount": 437},
        order_items={"items": [{"name": "Mini Punjabi Aloo Samosa", "price": 99}]},
        session_id=session_id,
        assessment={
            "issue_type": "quality",
            "issue_confidence": 0.91,
            "active_item_name": "Mini Punjabi Aloo Samosa",
        },
    )

    assert result["_debug"]["issue_type"] == "portion_size"
    assert "portion" in result["message"].lower() or "light" in result["message"].lower()


def test_resolution_followup_keeps_active_portion_case():
    session_id = "test:portion-followup-keeps-case"
    clear_session(session_id)

    first = _run_turn(session_id, "Mini Punjabi Aloo Samosa quantity bahut kam thi", order_value=437)
    second = _run_turn(session_id, "coupon ya refund kya milega", order_value=437)

    assert first["_debug"]["issue_type"] == "portion_size"
    assert second["_debug"]["issue_type"] == "portion_size"


def test_hinglish_status_query_is_detected():
    session_id = "test:status-batao"
    clear_session(session_id)

    result = _run_turn(session_id, "status batao", order_value=168)

    assert result["_debug"]["issue_type"] == "info_query"
    assert "marked" in result["message"].lower() or "progress" in result["message"].lower()


def test_safety_case_stays_sticky_across_followups():
    session_id = "test:sticky-safety-followups"
    clear_session(session_id)

    first = _run_turn(session_id, "Classic Maggi me plastic ka piece mila")
    second = _run_turn(session_id, "please escalate this")
    third = _run_turn(session_id, "refund se zyada mujhe safety concern hai")

    assert first["_debug"]["issue_type"] == "foreign_object"
    assert second["_debug"]["issue_type"] == "foreign_object"
    assert get_session_state(session_id)["issue_type"] == "foreign_object"


def test_spill_case_stays_sticky_across_evidence_and_update_followups():
    session_id = "test:sticky-spill-followups"
    clear_session(session_id)

    first = _run_turn(session_id, "Cold Coffee bag me spill ho gaya")
    second = _run_turn(session_id, "photo bhej diya")
    third = _run_turn(session_id, "will I get any update in the app?")

    assert first["_debug"]["issue_type"] == "spill_leak"
    assert second["_debug"]["issue_type"] == "spill_leak"
    assert third["_debug"]["issue_type"] == "spill_leak"


def test_delay_only_case_does_not_become_food_quality_or_replacement():
    session_id = "test:sticky-delay-followups"
    clear_session(session_id)

    first = _run_turn(session_id, "order 25 minute late tha but food okay hai", order_value=168)
    second = _run_turn(session_id, "coupon milega kya delay ke liye?", order_value=168)
    third = _run_turn(session_id, "can you confirm what you have noted?", order_value=168)
    fourth = _run_turn(session_id, "Don't convert this into food quality complaint", order_value=168)

    assert first["_debug"]["issue_type"] == "delay"
    assert second["_debug"]["issue_type"] == "delay"
    assert third["_debug"]["issue_type"] == "delay"
    assert fourth["_debug"]["issue_type"] == "delay"
    assert "fresh item" not in third["message"].lower()


def test_non_delivery_delivery_partner_signal_maps_to_missing_item():
    session_id = "test:delivery-partner-non-delivery"
    clear_session(session_id)

    first = _run_turn(session_id, "rider ne bola item nahi hai but app delivered dikha raha hai")
    second = _run_turn(session_id, "mujhe order receive nahi hua")

    assert first["_debug"]["issue_type"] == "missing_item"
    assert second["_debug"]["issue_type"] == "missing_item"


def test_payment_billing_query_does_not_become_food_quality():
    session_id = "test:payment-billing-info"
    clear_session(session_id)

    first = _run_turn(session_id, "payment cut gaya but order fail ho gaya")
    second = _run_turn(session_id, "UPI se amount debit hua")
    third = _run_turn(session_id, "refund timeline batao")
    fourth = _run_turn(session_id, "Stop asking about food, order was fine")
    fifth = _run_turn(session_id, "I have already explained this twice, read the chat properly.")

    assert first["_debug"]["issue_type"] == "info_query"
    assert second["_debug"]["issue_type"] == "info_query"
    assert third["_debug"]["issue_type"] == "info_query"
    assert fourth["_debug"]["issue_type"] == "info_query"
    assert fifth["_debug"]["issue_type"] == "info_query"


def test_another_person_is_not_misread_as_replacement_request():
    session_id = "test:another-person-not-replacement"
    clear_session(session_id)

    first = _run_turn(session_id, "order 25 minute late tha but food okay hai", order_value=168)
    second = _run_turn(session_id, "I don't want to explain this again to another person", order_value=168)

    assert first["_debug"]["issue_type"] == "delay"
    assert second["_debug"]["requested_resolution"] == "none"
    assert "fresh item" not in second["message"].lower()


def test_negated_refund_does_not_start_compensation_flow():
    session_id = "test:refund-negation"
    clear_session(session_id)

    first = _run_turn(session_id, "order 25 minute late tha but food okay hai", order_value=168)
    second = _run_turn(session_id, "food refund nahi chahiye", order_value=168)

    assert first["_debug"]["issue_type"] == "delay"
    assert second["_debug"]["requested_resolution"] == "none"
    assert second["action"] == "info"


def test_spill_scope_correction_keeps_spill_case():
    session_id = "test:spill-scope-correction"
    clear_session(session_id)

    first = _run_turn(session_id, "Roohafza Sharbat leaked all over the bag", order_value=756)
    second = _run_turn(session_id, "pasta box bhi wet ho gaya, don't call this taste issue", order_value=756)
    third = _run_turn(session_id, "Mark this as spill, not quality", order_value=756)

    assert first["_debug"]["issue_type"] == "spill_leak"
    assert second["_debug"]["issue_type"] == "spill_leak"
    assert third["_debug"]["issue_type"] == "spill_leak"


def test_delivery_time_complaint_without_delay_word_stays_delay():
    session_id = "test:delivery-time-without-delay-word"
    clear_session(session_id)

    first = _run_turn(session_id, "Your app promises 10 minute delivery but my order took 40 minutes", order_value=168)
    second = _run_turn(session_id, "Food was okay, I want delivery compensation only", order_value=168)

    assert first["_debug"]["issue_type"] == "delay"
    assert second["_debug"]["issue_type"] == "delay"
    assert "fresh item" not in second["message"].lower()


def test_app_availability_complaint_does_not_become_food_quality_case():
    session_id = "test:app-availability-info-query"
    clear_session(session_id)

    first = _run_turn(session_id, "Every time I open app it says surge or kitchen cleaning")
    second = _run_turn(session_id, "I cannot even place order, don't ask which food was bad")
    third = _run_turn(session_id, "I have pass balance stuck because I cannot order")

    assert first["_debug"]["issue_type"] == "info_query"
    assert second["_debug"]["issue_type"] == "info_query"
    assert third["_debug"]["issue_type"] == "info_query"


def test_spill_confirmation_language_does_not_drift_to_damage():
    session_id = "test:spill-confirmation-not-damage"
    clear_session(session_id)

    first = _run_turn(session_id, "Roohafza Sharbat leaked all over the bag", order_value=756)
    second = _run_turn(session_id, "Confirm this is spill or packing issue, not taste issue", order_value=756)

    assert first["_debug"]["issue_type"] == "spill_leak"
    assert second["_debug"]["issue_type"] == "spill_leak"


def test_identity_question_does_not_escalate_or_drop_active_case():
    session_id = "test:identity-question-active-case"
    clear_session(session_id)
    state = get_session_state(session_id)
    state.update(
        {
            "pending": "replacement_confirm",
            "desired_resolution": "replacement",
            "issue_type": "wrong_item",
            "case_issue_type": "wrong_item",
            "issue_severity": "high",
            "evidence_strength": "strong",
            "economic_preference": "replacement",
            "active_item_name": "Classic Maggi",
            "active_item_price": 79,
            "order_value": 222,
        }
    )
    history = get_session(session_id)
    history.append({"role": "user", "content": "Are you human or ai"})
    ctx = _base_context()

    result = Rules.resolve(
        complaint="Are you human or ai",
        conversation_history=history,
        order_value=222,
        trust_score=ctx["trust"]["score"],
        kitchen=ctx["kitchen"],
        fleet=ctx["fleet"],
        trust=ctx["trust"],
        order_details=ctx["order_details"],
        order_items=ctx["order_items"],
        session_id=session_id,
        assessment={
            "issue_type": "other",
            "issue_confidence": 0.8,
            "requested_resolution": "none",
            "requested_resolution_confidence": 0.9,
            "info_query": "none",
            "info_query_confidence": 0.9,
            "turn_act": "none",
            "turn_act_confidence": 0.9,
        },
    )

    assert result["action"] == "info"
    assert "support chat" in result["message"].lower()
    assert get_session_state(session_id)["pending"] == "replacement_confirm"


def test_repeated_refund_pressure_after_replacement_steer_moves_to_review():
    session_id = "test:replacement-refund-pressure-review"
    clear_session(session_id)
    state = get_session_state(session_id)
    state.update(
        {
            "pending": "replacement_confirm",
            "desired_resolution": "replacement",
            "issue_type": "wrong_item",
            "case_issue_type": "wrong_item",
            "issue_severity": "high",
            "evidence_strength": "strong",
            "economic_preference": "replacement",
            "active_item_name": "Classic Maggi",
            "active_item_price": 79,
            "order_value": 500,
        }
    )
    ctx = _base_context()

    first = Rules.resolve(
        complaint="No I need refund",
        conversation_history=[{"role": "user", "content": "No I need refund"}],
        order_value=500,
        trust_score=ctx["trust"]["score"],
        kitchen=ctx["kitchen"],
        fleet=ctx["fleet"],
        trust=ctx["trust"],
        order_details=ctx["order_details"],
        order_items=ctx["order_items"],
        session_id=session_id,
        assessment={
            "issue_type": "wrong_item",
            "issue_confidence": 0.9,
            "requested_resolution": "refund",
            "requested_resolution_confidence": 0.95,
            "turn_act": "switch_resolution",
            "turn_act_confidence": 0.95,
            "economic_preference": "replacement",
            "economic_confidence": 0.9,
        },
    )
    second = Rules.resolve(
        complaint="Give me refund of 269",
        conversation_history=[{"role": "user", "content": "Give me refund of 269"}],
        order_value=500,
        trust_score=ctx["trust"]["score"],
        kitchen=ctx["kitchen"],
        fleet=ctx["fleet"],
        trust=ctx["trust"],
        order_details=ctx["order_details"],
        order_items=ctx["order_items"],
        session_id=session_id,
        assessment={
            "issue_type": "wrong_item",
            "issue_confidence": 0.9,
            "requested_resolution": "refund",
            "requested_resolution_confidence": 0.95,
            "turn_act": "switch_resolution",
            "turn_act_confidence": 0.95,
            "economic_preference": "replacement",
            "economic_confidence": 0.9,
        },
    )

    assert first["action"] == "info"
    assert "review" in first["message"].lower()
    assert second["action"] == "escalate"


def test_refund_steering_does_not_create_unconfirmed_replacement_pending_state():
    session_id = "test:refund-steer-not-replacement-pending"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    ctx["order_items"] = {"items": [{"name": "Classic Cold Coffee", "price": 269}]}
    common = {
        "order_value": 478,
        "trust_score": 92,
        "kitchen": {"quality_out": "good", "prep_time_mins": 8, "temperature_check": "cold"},
        "fleet": {"delay_mins": 1, "traffic_flag": False},
        "trust": ctx["trust"],
        "order_details": {"total_amount": 478},
        "order_items": ctx["order_items"],
        "session_id": session_id,
    }

    turns = [
        (
            "i got a different drink",
            {
                "issue_type": "wrong_item",
                "issue_confidence": 0.9,
                "active_item_name": "Classic Cold Coffee",
            },
            None,
            None,
        ),
        (
            "i need my refund",
            {
                "issue_type": "wrong_item",
                "issue_confidence": 0.9,
                "requested_resolution": "refund",
                "requested_resolution_confidence": 0.95,
                "active_item_name": "Classic Cold Coffee",
            },
            "https://example.com/proof.jpg",
            True,
        ),
        (
            "i need refund",
            {
                "issue_type": "wrong_item",
                "issue_confidence": 0.9,
                "requested_resolution": "refund",
                "requested_resolution_confidence": 0.95,
                "turn_act": "switch_resolution",
                "turn_act_confidence": 0.95,
                "economic_preference": "replacement",
                "economic_confidence": 0.9,
                "active_item_name": "Classic Cold Coffee",
            },
            None,
            None,
        ),
    ]

    for msg, assessment, photo_url, photo_valid in turns:
        if photo_url:
            mark_photo_provided(session_id)
        history.append({"role": "user", "content": msg})
        result = Rules.resolve(
            complaint=msg,
            conversation_history=history,
            assessment=assessment,
            photo_url=photo_url,
            photo_valid=photo_valid,
            photo_in_session=session_has_photo(session_id),
            **common,
        )
        history.append({"role": "bot", "content": result["message"]})

    state = get_session_state(session_id)
    assert result["action"] == "info"
    assert "fresh classic cold coffee" in result["message"].lower()
    assert state.get("pending") == "coupon"
    assert state.get("desired_resolution") == "refund"
    assert state.get("last_action") != "replacement"

    history.append({"role": "user", "content": "no i never confirmed replacement give me refund"})
    result = Rules.resolve(
        complaint="no i never confirmed replacement give me refund",
        conversation_history=history,
        assessment={
            "issue_type": "wrong_item",
            "issue_confidence": 0.9,
            "requested_resolution": "refund",
            "requested_resolution_confidence": 0.95,
            "turn_act": "switch_resolution",
            "turn_act_confidence": 0.95,
            "economic_preference": "replacement",
            "economic_confidence": 0.9,
            "active_item_name": "Classic Cold Coffee",
        },
        **common,
    )

    assert result["action"] == "escalate"
    assert "refund" in result["message"].lower()
    assert get_session_state(session_id).get("last_action") != "replacement"


def test_active_issue_followup_is_not_routed_to_order_status():
    session_id = "test-active-issue-not-order-status"
    clear_session(session_id)
    state = get_session_state(session_id)
    state.update({"issue_type": "wrong_item", "case_issue_type": "wrong_item", "active_item_name": "Classic Maggi"})
    ctx = _base_context()

    result = Rules.resolve(
        complaint="What about my issue",
        conversation_history=[{"role": "user", "content": "What about my issue"}],
        order_value=222,
        trust_score=ctx["trust"]["score"],
        kitchen=ctx["kitchen"],
        fleet=ctx["fleet"],
        trust=ctx["trust"],
        order_details=ctx["order_details"],
        order_items=ctx["order_items"],
        session_id=session_id,
        assessment={
            "issue_type": "info_query",
            "issue_confidence": 0.9,
            "info_query": "status",
            "info_query_confidence": 0.9,
            "requested_resolution": "none",
            "turn_act": "ask_status",
            "turn_act_confidence": 0.9,
        },
    )

    assert result["action"] == "info"
    assert "delivered at" not in result["message"].lower()
    assert "wrong-item" in result["message"].lower() or "wrong item" in result["message"].lower()


def test_dead_food_text_overrides_spill_category_to_quality():
    session_id = "test-dead-food-quality"
    clear_session(session_id)
    ctx = _base_context()

    result = Rules.resolve(
        complaint="Damaged or spilled Affected item is Classic Maggi. Dead food",
        conversation_history=[{"role": "user", "content": "Damaged or spilled Affected item is Classic Maggi. Dead food"}],
        order_value=222,
        trust_score=ctx["trust"]["score"],
        kitchen=ctx["kitchen"],
        fleet=ctx["fleet"],
        trust=ctx["trust"],
        order_details=ctx["order_details"],
        order_items=ctx["order_items"],
        session_id=session_id,
        assessment={
            "issue_type": "spill_leak",
            "issue_confidence": 0.9,
            "requested_resolution": "none",
            "requested_resolution_confidence": 0.9,
            "turn_act": "none",
            "turn_act_confidence": 0.9,
        },
    )

    assert result["_debug"]["issue_type"] == "quality"
    assert "spill" not in result["message"].lower()


def test_portion_coupon_copy_does_not_state_claim_as_verified_fact():
    session_id = "test-portion-copy-not-fact"
    clear_session(session_id)

    first = _run_turn(session_id, "Classic Maggi had only 1 piece when 5 was shown", order_value=222)
    second = _run_turn(session_id, "I want refund", order_value=222)

    assert first["_debug"]["issue_type"] == "portion_size"
    assert "only had" not in second["message"].lower()
    assert "i can apply" in second["message"].lower() or "coupon" in second["message"].lower()


def test_replacement_confirmation_pressure_escalates_instead_of_looping():
    session_id = "test:replacement-pressure-breaks-loop"
    clear_session(session_id)

    first = _run_turn(session_id, "Classic Maggi soggy thi, fresh replacement bhejo abhi", order_value=168)
    second = _run_turn(session_id, "I need a senior person to look at this if you cannot solve it.", order_value=168)

    assert first["action"] in {"info", "replacement", "escalate"}
    assert second["action"] == "escalate"
    assert "fresh Classic Maggi sent out" not in second["message"]


def test_component_portion_complaint_does_not_reframe_whole_item_as_small():
    session_id = "test:component-portion-language"
    clear_session(session_id)

    history = get_session(session_id)
    order_items = {"items": [{"name": "Dhaba Style Chicken Curry Rice Bowl", "price": 269}]}
    history.append({"role": "user", "content": "there was not enough chicken"})
    first = Rules.resolve(
        complaint="there was not enough chicken",
        conversation_history=history,
        order_value=756,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 20, "temperature_check": "hot"},
        fleet={"delay_mins": 15, "traffic_flag": True},
        trust={"score": 92, "total_orders": 18},
        order_details={"total_amount": 756},
        order_items=order_items,
        session_id=session_id,
        assessment={
            "issue_type": "portion_size",
            "issue_confidence": 0.92,
            "active_item_name": "Dhaba Style Chicken Curry Rice Bowl",
        },
    )

    assert first["_debug"]["issue_type"] == "portion_size"
    assert "chicken quantity" in first["message"].lower()
    assert "light for what you paid" not in first["message"].lower()
    assert "bowl was small" not in first["message"].lower()


def test_false_promise_filter_handles_curly_apostrophe():
    response = Rules._enforce_content(
        {
            "action": "info",
            "message": "I can add a coupon now. I’ll check if we can remake the sandwich instead.",
        },
        {},
    )

    assert "check if we can" not in response["message"].lower()
    assert response["message"] == "I can add a coupon now."


def test_false_promise_filter_handles_i_can_check():
    response = Rules._enforce_content(
        {
            "action": "info",
            "message": "I can check on the delivery delay for you. The delay is already noted.",
        },
        {},
    )

    assert "check on" not in response["message"].lower()
    assert response["message"] == "The delay is already noted."


def test_duplicate_review_copy_stays_customer_safe():
    state = {"recent_bot_messages": []}
    message = "This is already marked for review. I can keep your latest note attached here, but I can't approve another automatic action in chat."

    first = Rules._enforce_content({"action": "escalate", "message": message}, state)
    second = Rules._enforce_content({"action": "escalate", "message": message}, state)

    combined = f"{first['message']} {second['message']}".lower()
    assert "keep repeating" not in combined
    assert "restating" not in combined
    assert "already marked for review" in combined


def test_pending_photo_flow_does_not_skip_to_coupon_without_evidence():
    session_id = "test:pending-photo-does-not-skip"
    clear_session(session_id)

    first = _run_turn(session_id, "Roohafza Sharbat spilled, I want compensation", order_value=756)
    second = _run_turn(session_id, "I want compensation", order_value=756)

    assert first["action"] == "live_capture"
    assert second["action"] == "live_capture"
    assert "photo" in second["message"].lower()


def test_wrong_category_prefix_does_not_turn_benign_vegetable_into_wrong_item():
    session_id = "test:wrong-prefix-ingredient-mismatch"
    clear_session(session_id)

    history = get_session(session_id)
    complaint = "Wrong or different item Affected item is Butter Chicken Rice Bowl. There was a piece of vegetable in my chicken bowl"
    history.append({"role": "user", "content": complaint})
    result = Rules.resolve(
        complaint=complaint,
        conversation_history=history,
        order_value=478,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 20, "temperature_check": "hot"},
        fleet={"delay_mins": 5, "traffic_flag": False},
        trust={"score": 92, "total_orders": 18},
        order_details={"total_amount": 478},
        order_items={"items": [{"name": "Butter Chicken Rice Bowl", "price": 269}]},
        session_id=session_id,
    )

    assert result["_debug"]["issue_type"] == "quality"
    assert "wrong item was packed" not in result["message"].lower()


def test_quality_replacement_request_gets_coupon_or_review_before_remake():
    session_id = "test:quality-replacement-not-instant"
    clear_session(session_id)

    first = _run_turn(session_id, "Classic Maggi came soggy", order_value=168)
    second = _run_turn(session_id, "Can I get a replacement", order_value=168)

    assert first["_debug"]["issue_type"] == "quality"
    assert second["action"] == "info"
    assert "coupon" in second["message"].lower() or "review" in second["message"].lower()
    assert "fresh classic maggi" not in second["message"].lower()


def test_component_portion_followup_stays_portion_size():
    session_id = "test:component-portion-followup"
    clear_session(session_id)

    history = get_session(session_id)
    order_items = {"items": [{"name": "Chicken Rice Bowl", "price": 260}]}
    for complaint in [
        "there was not enough chicken in the bowl",
        "I paid for chicken bowl, chicken quantity was too low",
    ]:
        history.append({"role": "user", "content": complaint})
        result = Rules.resolve(
            complaint=complaint,
            conversation_history=history,
            order_value=260,
            trust_score=92,
            kitchen={"quality_out": "good", "prep_time_mins": 10, "temperature_check": "hot"},
            fleet={"delay_mins": 3, "traffic_flag": False},
            trust={"score": 92, "total_orders": 18},
            order_details={"total_amount": 260},
            order_items=order_items,
            session_id=session_id,
        )
        history.append({"role": "bot", "content": result["message"]})

    assert result["_debug"]["issue_type"] == "portion_size"
    assert "quality issue" not in result["message"].lower()


def test_actual_item_correction_overrides_picker_item():
    session_id = "test:actual-item-correction"
    clear_session(session_id)

    history = get_session(session_id)
    complaint = "Issue picker says Oreo shake but actually my Roohafza spilled"
    history.append({"role": "user", "content": complaint})
    result = Rules.resolve(
        complaint=complaint,
        conversation_history=history,
        order_value=240,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 8, "temperature_check": "cold"},
        fleet={"delay_mins": 3, "traffic_flag": False},
        trust={"score": 92, "total_orders": 18},
        order_details={"total_amount": 240},
        order_items={"items": [{"name": "Oreo Shake", "price": 120}, {"name": "Roohafza", "price": 120}]},
        session_id=session_id,
    )

    assert result["_debug"]["active_item_name"] == "Roohafza"
    assert "roohafza" in result["message"].lower()


def test_llm_semantic_conflict_forces_item_clarification_before_policy_action():
    session_id = "test:semantic-item-conflict"
    clear_session(session_id)

    history = get_session(session_id)
    complaint = "I selected Roohafza Sharbat but the fries are missing"
    history.append({"role": "user", "content": complaint})
    result = Rules.resolve(
        complaint=complaint,
        conversation_history=history,
        order_value=478,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 8, "temperature_check": "hot"},
        fleet={"delay_mins": 4, "traffic_flag": False},
        trust={"score": 92, "total_orders": 18},
        order_details={"total_amount": 478},
        order_items={"items": [{"name": "Roohafza Sharbat", "price": 79}, {"name": "Peri Peri French Fries", "price": 209}]},
        session_id=session_id,
        assessment={
            "issue_type": "missing_item",
            "issue_confidence": 0.91,
            "active_item_name": "Roohafza Sharbat",
            "selected_item_conflict": True,
            "mentioned_item_name": "Peri Peri French Fries",
            "semantic_risk": True,
            "semantic_confidence": 0.93,
            "recommended_next_step": "clarify",
            "clarification_needed": True,
        },
    )

    assert result["action"] == "info"
    assert result["reason"] == "LLM semantic guard requested clarification"
    assert result["_debug"]["selected_item_conflict"] is True
    assert "roohafza" in result["message"].lower()
    assert "fries" in result["message"].lower()
    assert "which item" in result["message"].lower()
    assert result["action"] not in {"coupon", "refund", "replacement", "live_capture"}


def test_llm_high_dietary_severity_can_upgrade_common_sense_safety_case():
    session_id = "test:semantic-dietary-high"
    clear_session(session_id)

    history = get_session(session_id)
    complaint = "there is chicken in my veg pasta and I am vegetarian"
    history.append({"role": "user", "content": complaint})
    result = Rules.resolve(
        complaint=complaint,
        conversation_history=history,
        order_value=219,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 8, "temperature_check": "hot"},
        fleet={"delay_mins": 4, "traffic_flag": False},
        trust={"score": 92, "total_orders": 18},
        order_details={"total_amount": 219},
        order_items={"items": [{"name": "Veg Pink Sauce Pasta", "price": 219}]},
        session_id=session_id,
        assessment={
            "issue_type": "quality",
            "issue_confidence": 0.88,
            "active_item_name": "Veg Pink Sauce Pasta",
            "dietary_severity": "high",
            "semantic_risk": True,
            "semantic_confidence": 0.9,
            "tone_guardrail": "sensitive",
        },
    )

    assert result["_debug"]["issue_type"] == "foreign_object"
    assert result["_debug"]["issue_severity"] == "high"
    assert result["_debug"]["dietary_severity"] == "high"


def test_resolved_dietary_direction_does_not_trigger_vague_semantic_clarification():
    session_id = "test:semantic-dietary-no-vague-clarify"
    clear_session(session_id)

    history = get_session(session_id)
    complaint = "there is chicken in my veg pasta and I am vegetarian"
    history.append({"role": "user", "content": complaint})
    result = Rules.resolve(
        complaint=complaint,
        conversation_history=history,
        order_value=219,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 8, "temperature_check": "hot"},
        fleet={"delay_mins": 4, "traffic_flag": False},
        trust={"score": 92, "total_orders": 18},
        order_details={"total_amount": 219},
        order_items={"items": [{"name": "Veg Pink Sauce Pasta", "price": 219}]},
        session_id=session_id,
        assessment={
            "issue_type": "quality",
            "issue_confidence": 0.88,
            "active_item_name": "Veg Pink Sauce Pasta",
            "dietary_severity": "high",
            "dietary_direction": "nonveg_in_veg",
            "semantic_risk": True,
            "semantic_confidence": 0.9,
            "recommended_next_step": "clarify",
            "clarification_needed": True,
        },
    )

    assert result["_debug"]["issue_type"] == "foreign_object"
    assert result["reason"] != "LLM semantic guard requested clarification"
    assert "different issue from the option selected" not in result["message"].lower()


def test_llm_low_dietary_severity_keeps_veg_in_nonveg_as_prep_quality_issue():
    session_id = "test:semantic-dietary-low"
    clear_session(session_id)

    history = get_session(session_id)
    complaint = "there was a vegetable piece in my chicken bowl"
    history.append({"role": "user", "content": complaint})
    result = Rules.resolve(
        complaint=complaint,
        conversation_history=history,
        order_value=269,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 8, "temperature_check": "hot"},
        fleet={"delay_mins": 4, "traffic_flag": False},
        trust={"score": 92, "total_orders": 18},
        order_details={"total_amount": 269},
        order_items={"items": [{"name": "Butter Chicken Rice Bowl", "price": 269}]},
        session_id=session_id,
        assessment={
            "issue_type": "quality",
            "issue_confidence": 0.88,
            "active_item_name": "Butter Chicken Rice Bowl",
            "dietary_severity": "low",
            "semantic_risk": False,
            "semantic_confidence": 0.86,
        },
    )

    assert result["_debug"]["issue_type"] == "quality"
    assert result["_debug"]["dietary_severity"] == "low"
    assert "wrong item" not in result["message"].lower()


def test_llm_high_dietary_overcall_does_not_turn_veg_in_nonveg_into_safety_case():
    session_id = "test:semantic-dietary-high-overcall-veg-in-nonveg"
    clear_session(session_id)

    history = get_session(session_id)
    complaint = "there was a vegetable piece in my chicken bowl"
    history.append({"role": "user", "content": complaint})
    result = Rules.resolve(
        complaint=complaint,
        conversation_history=history,
        order_value=269,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 8, "temperature_check": "hot"},
        fleet={"delay_mins": 4, "traffic_flag": False},
        trust={"score": 92, "total_orders": 18},
        order_details={"total_amount": 269},
        order_items={"items": [{"name": "Butter Chicken Rice Bowl", "price": 269}]},
        session_id=session_id,
        assessment={
            "issue_type": "foreign_object",
            "issue_confidence": 0.92,
            "issue_severity": "high",
            "active_item_name": "Butter Chicken Rice Bowl",
            "dietary_severity": "high",
            "semantic_risk": True,
            "semantic_confidence": 0.91,
            "fault_hint": "kitchen",
        },
    )

    assert result["_debug"]["issue_type"] == "quality"
    assert result["_debug"]["issue_severity"] != "high"
    assert "safety" not in result["message"].lower()


def test_identity_question_does_not_escalate_active_support_case():
    session_id = "test:identity-question-no-escalation"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    ctx["order_items"] = {"items": [{"name": "Caesar Salad (Non-Veg)", "price": 269}]}

    for msg in ["my salad was too salty", "i want refund"]:
        history.append({"role": "user", "content": msg})
        result = Rules.resolve(
            complaint=msg,
            conversation_history=history,
            order_value=478,
            trust_score=92,
            kitchen={"quality_out": "good", "prep_time_mins": 8, "temperature_check": "hot"},
            fleet={"delay_mins": 2, "traffic_flag": False},
            trust=ctx["trust"],
            order_details={"total_amount": 478},
            order_items=ctx["order_items"],
            session_id=session_id,
        )
        history.append({"role": "bot", "content": result["message"]})

    history.append({"role": "user", "content": "are you human or ai"})
    result = Rules.resolve(
        complaint="are you human or ai",
        conversation_history=history,
        order_value=478,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 8, "temperature_check": "hot"},
        fleet={"delay_mins": 2, "traffic_flag": False},
        trust=ctx["trust"],
        order_details={"total_amount": 478},
        order_items=ctx["order_items"],
        session_id=session_id,
    )

    assert result["action"] == "info"
    assert "support chat" in result["message"].lower()
    assert "email" not in result["message"].lower()


def test_replacement_refund_pressure_moves_to_review_instead_of_looping_replacement():
    session_id = "test:replacement-refund-pressure-review"
    clear_session(session_id)

    history = get_session(session_id)
    state = get_session_state(session_id)
    state.update(
        {
            "last_action": "replacement",
            "issue_type": "quality",
            "case_issue_type": "quality",
            "case_issue_severity": "medium",
            "case_evidence_strength": "weak",
            "economic_preference": "replacement",
            "active_item_name": "Peri Peri French Fries",
            "active_item_price": 209,
            "approved_replacement_item_name": "Peri Peri French Fries",
            "approved_replacement_status": "approved",
            "order_value": 478,
        }
    )
    ctx = _base_context()
    ctx["order_items"] = {"items": [{"name": "Peri Peri French Fries", "price": 209}]}
    common = {
        "order_value": 478,
        "trust_score": 92,
        "kitchen": {"quality_out": "poor", "prep_time_mins": 14, "temperature_check": "warm"},
        "fleet": {"delay_mins": 1, "traffic_flag": False},
        "trust": ctx["trust"],
        "order_details": {"total_amount": 478},
        "order_items": ctx["order_items"],
        "session_id": session_id,
    }

    history.append({"role": "user", "content": "can i get a refund instead"})
    first_switch = Rules.resolve(complaint="can i get a refund instead", conversation_history=history, **common)
    history.append({"role": "bot", "content": first_switch["message"]})

    history.append({"role": "user", "content": "no let the refund be"})
    second_switch = Rules.resolve(complaint="no let the refund be", conversation_history=history, **common)

    assert first_switch["action"] in {"info", "escalate"}
    assert second_switch["action"] == "escalate"
    assert "review" in second_switch["message"].lower()
    assert "replacement" not in second_switch["message"].lower() or "review" in second_switch["message"].lower()


def test_active_issue_followup_does_not_turn_into_order_status_info():
    session_id = "test:active-issue-followup-not-order-status"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    ctx["order_items"] = {"items": [{"name": "Grilled Paneer Club Sandwich", "price": 209}]}

    history.append({"role": "user", "content": "sandwich had the wrong filling"})
    first = Rules.resolve(
        complaint="sandwich had the wrong filling",
        conversation_history=history,
        order_value=478,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 9, "temperature_check": "hot"},
        fleet={"delay_mins": 1, "traffic_flag": False},
        trust=ctx["trust"],
        order_details={"total_amount": 478, "status": "delivered"},
        order_items=ctx["order_items"],
        session_id=session_id,
    )
    history.append({"role": "bot", "content": first["message"]})

    history.append({"role": "user", "content": "what about my issue"})
    result = Rules.resolve(
        complaint="what about my issue",
        conversation_history=history,
        order_value=478,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 9, "temperature_check": "hot"},
        fleet={"delay_mins": 1, "traffic_flag": False},
        trust=ctx["trust"],
        order_details={"total_amount": 478, "status": "delivered"},
        order_items=ctx["order_items"],
        session_id=session_id,
        assessment={"info_query": "status", "info_query_confidence": 0.91},
    )

    assert result["action"] == "info"
    assert "delivered" not in result["message"].lower()
    assert "issue" in result["message"].lower() or "complaint" in result["message"].lower()


def test_absurd_vague_food_complaint_stays_quality_not_spill():
    assert Rules._detect_issue_type("dead food", "Mini Punjabi Aloo Samosa") == "quality"
    assert Rules._strong_text_issue_override("the food was dead", "spill_leak") == "quality"


def test_portion_copy_does_not_assert_unverified_piece_count():
    session_id = "test:portion-copy-no-unverified-count"
    clear_session(session_id)

    history = get_session(session_id)
    order_items = {"items": [{"name": "Butter Chicken Rice Bowl", "price": 269}]}
    history.append({"role": "user", "content": "there was not enough chicken in the bowl"})
    result = Rules.resolve(
        complaint="there was not enough chicken in the bowl",
        conversation_history=history,
        order_value=269,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 8, "temperature_check": "hot"},
        fleet={"delay_mins": 1, "traffic_flag": False},
        trust={"score": 92, "total_orders": 18},
        order_details={"total_amount": 269},
        order_items=order_items,
        session_id=session_id,
    )

    lowered = result["message"].lower()
    assert "only had" not in lowered
    assert "too light" not in lowered
    assert "quantity concern" in lowered or "portion size" in lowered


def test_ordinary_quality_coupon_is_capped_without_strong_evidence():
    session_id = "test:ordinary-quality-coupon-cap"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    ctx["order_items"] = {"items": [{"name": "Caesar Salad (Non-Veg)", "price": 269}]}
    common = {
        "order_value": 478,
        "trust_score": 92,
        "kitchen": {"quality_out": "good", "prep_time_mins": 8, "temperature_check": "hot"},
        "fleet": {"delay_mins": 1, "traffic_flag": False},
        "trust": ctx["trust"],
        "order_details": {"total_amount": 478},
        "order_items": ctx["order_items"],
        "session_id": session_id,
    }

    for msg in ["my salad was too salty", "i want a refund"]:
        history.append({"role": "user", "content": msg})
        result = Rules.resolve(complaint=msg, conversation_history=history, **common)
        history.append({"role": "bot", "content": result["message"]})

    assert result["action"] == "info"
    assert result["_debug"]["issue_type"] == "quality"
    assert result["_debug"]["coupon_amount"] <= 50
    assert "₹78" not in result["message"]


def test_empty_package_entire_order_goes_to_live_capture_without_semantic_clarification():
    session_id = "test:empty-package-entire-order"
    clear_session(session_id)

    history = get_session(session_id)
    complaint = "Affected item is Entire order. The order delivered was inconsistent, I received empty package"
    history.append({"role": "user", "content": complaint})
    result = Rules.resolve(
        complaint=complaint,
        conversation_history=history,
        order_value=756,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 20, "temperature_check": "hot"},
        fleet={"delay_mins": 15, "traffic_flag": True},
        trust={"score": 92, "total_orders": 18},
        order_details={"total_amount": 756},
        order_items={
            "items": [
                {"name": "Dhaba Style Chicken Curry Rice Bowl", "price": 269},
                {"name": "Veg Pink Sauce Pasta", "price": 219},
            ]
        },
        session_id=session_id,
        assessment={
            "issue_type": "other",
            "issue_confidence": 0.8,
            "active_item_name": "Entire order",
            "semantic_risk": True,
            "semantic_confidence": 0.9,
            "recommended_next_step": "clarify",
            "clarification_needed": True,
        },
    )

    assert result["action"] == "live_capture"
    assert get_session_state(session_id).get("issue_type") == "missing_item"
    assert get_session_state(session_id).get("active_item_name") == "Entire order"
    assert "are you asking about" not in result["message"].lower()


def test_photo_turn_for_clear_wrong_item_does_not_reopen_semantic_clarification():
    session_id = "test:wrong-item-photo-no-semantic-loop"
    clear_session(session_id)

    history = get_session(session_id)
    ctx = _base_context()
    ctx["order_items"] = {"items": [{"name": "Caesar Salad (Non-Veg)", "price": 259}]}
    first = Rules.resolve(
        complaint="wrong item, got veg sandwich instead of Caesar Salad",
        conversation_history=[{"role": "user", "content": "wrong item, got veg sandwich instead of Caesar Salad"}],
        order_value=627,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 15, "temperature_check": "cold"},
        fleet={"delay_mins": 8, "traffic_flag": True},
        trust=ctx["trust"],
        order_details={"total_amount": 627},
        order_items=ctx["order_items"],
        session_id=session_id,
    )
    history.append({"role": "user", "content": "wrong item, got veg sandwich instead of Caesar Salad"})
    history.append({"role": "bot", "content": first["message"]})
    mark_photo_provided(session_id)

    history.append({"role": "user", "content": "Refund, you delivered wrong item"})
    result = Rules.resolve(
        complaint="Refund, you delivered wrong item",
        conversation_history=history,
        order_value=627,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 15, "temperature_check": "cold"},
        fleet={"delay_mins": 8, "traffic_flag": True},
        trust=ctx["trust"],
        order_details={"total_amount": 627},
        order_items=ctx["order_items"],
        session_id=session_id,
        photo_url="https://example.com/proof.jpg",
        photo_valid=True,
        photo_in_session=session_has_photo(session_id),
        assessment={
            "issue_type": "wrong_item",
            "issue_confidence": 0.9,
            "requested_resolution": "refund",
            "requested_resolution_confidence": 0.9,
            "active_item_name": "Caesar Salad (Non-Veg)",
            "semantic_risk": True,
            "semantic_confidence": 0.9,
            "recommended_next_step": "clarify",
            "clarification_needed": True,
        },
    )

    assert result["action"] == "info"
    assert "confirm which item" not in result["message"].lower()
    assert "coupon" in result["message"].lower() or "refund" in result["message"].lower()


def test_review_repeat_messages_follow_latest_user_intent():
    state = {"active_item_name": "Classic Cold Coffee", "escalation_repeat_count": 2}
    refund = Rules._review_repeat_message(state, "GIVE ME MY REFUND", "Classic Cold Coffee")
    supervisor = Rules._review_repeat_message(state, "I want supervisor", "Classic Cold Coffee")
    hungry = Rules._review_repeat_message(state, "I am hungry and have no food", "Classic Cold Coffee")

    assert "refund" in refund.lower() or "cash" in refund.lower()
    assert "supervisor" in supervisor.lower()
    assert "usable meal" in hungry.lower()
    assert len({refund, supervisor, hungry}) == 3


def test_vague_quality_copy_does_not_blame_delivery_delay():
    session_id = "test:vague-quality-no-delay-blame"
    clear_session(session_id)

    history = get_session(session_id)
    complaint = "Damaged or spilled Affected item is Mini Punjabi Aloo Samosa. Dead food"
    history.append({"role": "user", "content": complaint})
    result = Rules.resolve(
        complaint=complaint,
        conversation_history=history,
        order_value=437,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 14, "temperature_check": "hot"},
        fleet={"delay_mins": 3, "traffic_flag": False},
        trust={"score": 92, "total_orders": 18},
        order_details={"total_amount": 437},
        order_items={"items": [{"name": "Mini Punjabi Aloo Samosa", "price": 99}]},
        session_id=session_id,
    )

    assert result["_debug"]["issue_type"] == "quality"
    assert "delivery leg" not in result["message"].lower()
    assert "3-minute delay" not in result["message"].lower()


def test_semantic_clarification_issue_confirmation_is_understood():
    session_id = "test:semantic-that-is-issue"
    clear_session(session_id)
    state = get_session_state(session_id)
    state.update(
        {
            "pending": "semantic_clarification",
            "pending_semantic_item_name": "Classic Cold Coffee",
            "pending_semantic_issue_type": "wrong_item",
            "pending_semantic_fault": "kitchen",
            "pending_semantic_prep_anomaly": False,
        }
    )
    history = get_session(session_id)
    history.append({"role": "user", "content": "That is fcking issue"})

    result = Rules.resolve(
        complaint="That is fcking issue",
        conversation_history=history,
        order_value=627,
        trust_score=92,
        kitchen={"quality_out": "good", "prep_time_mins": 15, "temperature_check": "cold"},
        fleet={"delay_mins": 8, "traffic_flag": True},
        trust={"score": 92, "total_orders": 18},
        order_details={"total_amount": 627},
        order_items={"items": [{"name": "Classic Cold Coffee", "price": 159}]},
        session_id=session_id,
    )

    assert result["reason"] == "Semantic clarification confirmed"
    assert "wrong-item issue" in result["message"].lower()
