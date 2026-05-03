from response_quality import evaluate_response_quality, evaluate_response_with_llm_judge


def test_quality_eval_catches_action_message_mismatch():
    errors = evaluate_response_quality(
        {
            "action": "live_capture",
            "amount": 0,
            "message": "Photo attached now, we can continue.",
            "reason": "Photo required before compensation decision",
        },
        complaint="drink spilled",
        expected_issue_type="spill_leak",
    )

    assert "live_capture_claims_photo_already_attached" in errors


def test_quality_eval_catches_component_portion_scope_drift():
    errors = evaluate_response_quality(
        {
            "action": "info",
            "amount": 0,
            "message": "The bowl was too small for what you paid.",
            "reason": "Offer coupon before refund or replacement",
            "_debug": {"issue_type": "portion_size", "active_item_name": "Chicken Rice Bowl"},
        },
        complaint="there was not enough chicken in the bowl",
        order_items={"items": [{"name": "Chicken Rice Bowl"}]},
    )

    assert "portion_component_reframed_as_whole_item_size" in errors


def test_quality_eval_catches_info_message_claiming_approval():
    errors = evaluate_response_quality(
        {
            "action": "info",
            "amount": 0,
            "message": "I have approved the refund for you.",
            "reason": "Offer coupon before refund or replacement",
            "_debug": {"issue_type": "quality"},
        },
        complaint="food was bad",
        expected_issue_type="quality",
    )

    assert "info_message_claims_compensation_approved" in errors


def test_quality_eval_accepts_grounded_coupon_offer():
    errors = evaluate_response_quality(
        {
            "action": "info",
            "amount": 0,
            "message": "I can add a ₹78 coupon for the low chicken quantity. Want me to do that?",
            "reason": "Offer coupon before refund or replacement",
            "_debug": {"issue_type": "portion_size", "active_item_name": "Chicken Rice Bowl"},
        },
        complaint="there was not enough chicken in the bowl",
        order_items={"items": [{"name": "Chicken Rice Bowl"}]},
    )

    assert errors == []


def test_quality_eval_catches_wrong_item_reference():
    errors = evaluate_response_quality(
        {
            "action": "info",
            "amount": 0,
            "message": "I have noted this against the Roohafza Sharbat.",
            "reason": "No explicit compensation request",
            "_debug": {"issue_type": "quality", "active_item_name": "Veg Pink Sauce Pasta"},
        },
        complaint="the pasta was dry",
        order_items={"items": [{"name": "Roohafza Sharbat"}, {"name": "Veg Pink Sauce Pasta"}]},
        expected_item_name="Veg Pink Sauce Pasta",
    )

    assert "message_mentions_wrong_order_item:Roohafza Sharbat" in errors


def test_quality_eval_catches_active_complaint_status_misroute():
    errors = evaluate_response_quality(
        {
            "action": "info",
            "amount": 0,
            "message": "This order is marked delivered and it shows as delivered at 8:27 PM.",
            "reason": "User asked for order information, not a complaint resolution",
            "_debug": {"issue_type": "spill_leak", "active_item_name": "Roohafza Sharbat"},
        },
        complaint="what happens now?",
        expected_issue_type="spill_leak",
        expected_item_name="Roohafza Sharbat",
    )

    assert "active_complaint_followup_misrouted_to_order_info" in errors


def test_quality_eval_catches_repeated_review_email():
    errors = evaluate_response_quality(
        {
            "action": "escalate",
            "amount": 0,
            "message": "Please email hello@justswish.in and the team can review it from there.",
            "reason": "Case already marked for manual review",
        },
        previous_messages=[
            "Please email hello@justswish.in and the team can review it from there.",
            "Please email hello@justswish.in and the team can review it from there.",
        ],
    )

    assert "exact_message_repeated" in errors
    assert "review_email_repeated_too_often" in errors


def test_llm_judge_wrapper_combines_deterministic_and_judge_errors(monkeypatch):
    monkeypatch.setattr(
        "response_quality.call_gemini_judge",
        lambda messages: (
            '{"passed":false,"semantic_score":0.4,"tone_score":0.9,"policy_score":0.8,'
            '"understood_customer":false,"preserved_item":true,"preserved_issue":false,'
            '"preserved_action":true,"policy_safe":true,"human_tone":true,'
            '"no_overpromise":true,"clarification_good":true,"errors":["missed component"],"notes":"bad"}'
        ),
    )

    result = evaluate_response_with_llm_judge(
        {
            "action": "info",
            "amount": 0,
            "message": "The bowl was too small for what you paid.",
            "reason": "Offer coupon before refund or replacement",
            "_debug": {"issue_type": "portion_size", "active_item_name": "Chicken Rice Bowl"},
        },
        complaint="there was not enough chicken in the bowl",
        order_items={"items": [{"name": "Chicken Rice Bowl"}]},
    )

    assert result["status"] == "ok"
    assert result["passed"] is False
    assert "portion_component_reframed_as_whole_item_size" in result["errors"]
    assert "judge_did_not_understand_customer" in result["errors"]
    assert "semantic_score_below_0.75:0.4" in result["errors"]
    assert "judge:missed component" in result["errors"]


def test_llm_judge_wrapper_accepts_good_response(monkeypatch):
    monkeypatch.setattr(
        "response_quality.call_gemini_judge",
        lambda messages: (
            '{"passed":true,"semantic_score":0.95,"tone_score":0.9,"policy_score":0.92,'
            '"understood_customer":true,"preserved_item":true,"preserved_issue":true,'
            '"preserved_action":true,"policy_safe":true,"human_tone":true,'
            '"no_overpromise":true,"clarification_good":true,"errors":[],"notes":"good"}'
        ),
    )

    result = evaluate_response_with_llm_judge(
        {
            "action": "info",
            "amount": 0,
            "message": "I can add a ₹78 coupon for the low chicken quantity. Want me to do that?",
            "reason": "Offer coupon before refund or replacement",
            "_debug": {"issue_type": "portion_size", "active_item_name": "Chicken Rice Bowl"},
        },
        complaint="there was not enough chicken in the bowl",
        order_items={"items": [{"name": "Chicken Rice Bowl"}]},
    )

    assert result["passed"] is True
    assert result["errors"] == []


def test_llm_judge_wrapper_reports_invalid_json(monkeypatch):
    monkeypatch.setattr("response_quality.call_gemini_judge", lambda messages: "not json")

    result = evaluate_response_with_llm_judge(
        {"action": "info", "amount": 0, "message": "Okay.", "reason": "No explicit compensation request"},
        complaint="food was bad",
    )

    assert result["status"] == "invalid_json"
    assert "judge_invalid_json" in result["errors"]
