import resolution_policy


def test_refund_hard_block_moves_high_value_low_trust_to_replacement():
    assert resolution_policy.refund_hard_block(order_value=650, trust_score=80) is True
    assert resolution_policy.preferred_refund_resolution(
        order_value=650,
        item_price=209,
        trust_score=80,
        desired_resolution="refund",
        issue_type="quality",
        issue_severity="medium",
        evidence_strength="weak",
        economic_preference=None,
    ) == "replacement"


def test_low_value_strong_wrong_item_prefers_refund_when_economic():
    assert resolution_policy.default_economic_preference(
        desired_resolution="refund",
        issue_type="wrong_item",
        issue_severity="high",
        evidence_strength="strong",
        order_value=168,
        item_price=79,
        trust_score=92,
    ) == "refund"


def test_replacement_request_without_strong_evidence_stays_coupon_first():
    assert resolution_policy.default_economic_preference(
        desired_resolution="replacement",
        issue_type="quality",
        issue_severity="medium",
        evidence_strength="weak",
        order_value=478,
        item_price=209,
        trust_score=92,
    ) == "coupon"
    assert resolution_policy.economic_preference_allowed(
        economic_preference="replacement",
        issue_type="quality",
        evidence_strength="weak",
        desired_resolution="replacement",
    ) is False


def test_replacement_negotiation_limit_is_bounded_by_margin_and_severity():
    assert resolution_policy.replacement_negotiation_turn_limit(
        order_value=478,
        item_price=209,
        coupon_amount=63,
        issue_severity="high",
        evidence_strength="strong",
        economic_preference="replacement",
    ) == 1
    assert resolution_policy.replacement_negotiation_turn_limit(
        order_value=168,
        item_price=120,
        coupon_amount=140,
        issue_severity="high",
        evidence_strength="strong",
        economic_preference="replacement",
    ) == 0
