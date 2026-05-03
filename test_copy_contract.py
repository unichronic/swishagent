import copy_contract


def test_copy_contract_requires_amount_and_coupon_term():
    contract = copy_contract.build_copy_contract(
        {
            "action": "info",
            "amount": 0,
            "message": "I can add a ₹78 coupon right away for the low chicken quantity.",
            "reason": "Offer coupon before refund or replacement",
            "_debug": {"issue_type": "portion_size", "active_item_name": "Chicken Rice Bowl"},
        },
        complaint="there was not enough chicken in the bowl",
        order_items={"items": [{"name": "Chicken Rice Bowl", "price": 260}]},
    )

    errors = copy_contract.validate_candidate("I can help with this right away.", contract)

    assert "missing_amount:₹78" in errors
    assert "missing_required_term:coupon" in errors
    assert "missing_required_term:chicken" in errors


def test_copy_contract_rejects_new_operational_claims():
    contract = copy_contract.build_copy_contract(
        {
            "action": "info",
            "amount": 0,
            "message": "I can add a ₹44 coupon now.",
            "reason": "Offer coupon before refund or replacement",
        },
        complaint="sandwich was soggy",
        order_items={"items": [{"name": "Grilled Paneer Club Sandwich", "price": 219}]},
    )

    errors = copy_contract.validate_candidate(
        "I asked the kitchen to remake it, and I can add a ₹44 coupon now.",
        contract,
    )

    assert "new_forbidden_claim:i asked the kitchen" in errors


def test_copy_contract_rejects_soft_check_promises():
    contract = copy_contract.build_copy_contract(
        {
            "action": "info",
            "amount": 0,
            "message": "The delay is noted against delivery.",
            "reason": "No explicit compensation request",
        },
        complaint="delivery was late",
        order_items={"items": []},
    )

    errors = copy_contract.validate_candidate("I can check on the delivery delay for you.", contract)

    assert "new_forbidden_claim:i can check" in errors


def test_copy_contract_preserves_uncertainty():
    contract = copy_contract.build_copy_contract(
        {
            "action": "info",
            "amount": 0,
            "message": "I can't verify the chicken quantity from logs, but I've logged it.",
            "reason": "No explicit compensation request",
            "_debug": {"issue_type": "portion_size"},
        },
        complaint="there was not enough chicken",
        order_items={"items": [{"name": "Chicken Rice Bowl", "price": 260}]},
    )

    errors = copy_contract.validate_candidate("You're right, there was not enough chicken.", contract)

    assert "uncertainty_weakened" in errors
    assert "uncertainty_upgraded_to_certainty" in errors
