import issue_signals


def test_portion_signals_cover_component_and_hinglish_quantity():
    examples = [
        "there was not enough chicken in the bowl",
        "fries qty was very less",
        "quantity bahut kam thi",
        "pieces small",
    ]

    for text in examples:
        assert issue_signals.is_portion_signal(text) is True


def test_spill_signal_separates_solid_damage_from_liquid_spill():
    assert issue_signals.spill_or_damage_issue("Grilled Paneer Club Sandwich spill ho gaya") == "damaged"
    assert issue_signals.spill_or_damage_issue("Roohafza Sharbat bag ke andar spill ho gaya") == "spill_leak"
    assert issue_signals.spill_or_damage_issue("my order is late", "spill_leak") is None


def test_quality_delay_and_temperature_signals_are_reusable():
    assert issue_signals.is_quality_signal("fries were soggy") is True
    assert issue_signals.is_delay_signal("where is my order eta?") is True
    assert issue_signals.is_temperature_signal("food was not hot") is True
