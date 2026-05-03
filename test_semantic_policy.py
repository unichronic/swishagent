from semantic_policy import normalize_semantic_facts


def test_semantic_policy_keeps_plant_in_nonveg_benign_across_phrases():
    examples = [
        "there was a vegetable piece in my chicken bowl",
        "onion found in non veg rice bowl",
        "extra capsicum in the mutton bowl",
    ]

    for text in examples:
        facts = normalize_semantic_facts(text=text, assessment={"dietary_severity": "high"}, state={})
        assert facts.dietary_direction == "veg_in_nonveg"
        assert facts.benign_ingredient_mismatch is True
        assert facts.serious_dietary_violation is False
        assert facts.prep_anomaly is True


def test_semantic_policy_keeps_nonveg_in_veg_serious():
    examples = [
        "there is chicken in my veg pasta and I am vegetarian",
        "egg piece in paneer bowl",
        "meat bits in vegetarian pasta",
    ]

    for text in examples:
        facts = normalize_semantic_facts(text=text, assessment={}, state={})
        assert facts.dietary_direction == "nonveg_in_veg"
        assert facts.serious_dietary_violation is True
        assert facts.benign_ingredient_mismatch is False


def test_semantic_policy_detects_resolution_change_from_state():
    facts = normalize_semantic_facts(
        text="can I get a refund instead?",
        assessment={},
        state={"approved_replacement_item_name": "Classic Maggi"},
    )

    assert facts.resolution_change == "refund_after_replacement"


def test_semantic_policy_uses_llm_canonical_fields_when_text_is_short():
    facts = normalize_semantic_facts(
        text="this is not okay",
        assessment={"dietary_direction": "nonveg_in_veg", "resolution_change": "refund_after_replacement"},
        state={},
    )

    assert facts.dietary_direction == "nonveg_in_veg"
    assert facts.serious_dietary_violation is True
    assert facts.resolution_change == "refund_after_replacement"
