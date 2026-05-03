import evidence_policy


def test_photo_requirement_depends_on_compensation_and_visual_usefulness():
    assert evidence_policy.needs_photo(explicit_comp=True, photo_present=False, visual_evidence_useful=True) is True
    assert evidence_policy.needs_photo(explicit_comp=False, photo_present=False, visual_evidence_useful=True) is False
    assert evidence_policy.needs_photo(explicit_comp=True, photo_present=True, visual_evidence_useful=True) is False


def test_photo_case_key_scopes_evidence_to_issue_and_item():
    assert evidence_policy.photo_case_key(issue_type="spill_leak", item_name="Roohafza Sharbat") == "spill_leak:roohafza sharbat"
    assert evidence_policy.photo_case_key(issue_type="quality", item_name=None) == "quality:"


def test_evidence_strength_uses_photo_and_operational_signals():
    assert evidence_policy.evidence_strength(
        issue_type="quality",
        fault="kitchen",
        kitchen={"quality_out": "fair"},
        fleet={},
        photo_present=False,
        photo_valid=None,
        visual_evidence_useful=False,
    ) == "strong"
    assert evidence_policy.evidence_strength(
        issue_type="spill_leak",
        fault="unclear",
        kitchen={},
        fleet={},
        photo_present=False,
        photo_valid=None,
        visual_evidence_useful=True,
    ) == "weak"
    assert evidence_policy.evidence_strength(
        issue_type="quality",
        fault="unclear",
        kitchen={},
        fleet={},
        photo_present=True,
        photo_valid=True,
        visual_evidence_useful=True,
    ) == "strong"


def test_visual_evidence_useful_respects_defaults_and_llm_confidence():
    multi_item_order = {"items": [{"name": "A"}, {"name": "B"}]}
    single_item_order = {"items": [{"name": "A"}]}

    assert evidence_policy.visual_evidence_useful(
        issue_type="missing_item",
        order_items=multi_item_order,
        assessed_visual_evidence=None,
        assessed_issue_confidence=None,
        min_visual_decision_confidence=0.6,
    ) is True
    assert evidence_policy.visual_evidence_useful(
        issue_type="missing_item",
        order_items=single_item_order,
        assessed_visual_evidence=True,
        assessed_issue_confidence=0.95,
        min_visual_decision_confidence=0.6,
    ) is False
    assert evidence_policy.visual_evidence_useful(
        issue_type="quality",
        order_items=multi_item_order,
        assessed_visual_evidence=True,
        assessed_issue_confidence=0.95,
        min_visual_decision_confidence=0.6,
    ) is False


def test_cannot_provide_photo_signals():
    assert evidence_policy.cannot_provide_photo("camera not working") is True
    assert evidence_policy.cannot_provide_photo("photo nahi bhej sakta") is True
    assert evidence_policy.cannot_provide_photo("photo attached") is False
