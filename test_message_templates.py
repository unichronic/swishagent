import message_templates


def test_photo_message_names_missing_item_evidence_context():
    assert message_templates.photo_message(
        order_value=450,
        issue_type="missing_item",
        item_name="Butter Chicken Rice Bowl",
    ) == "Please upload a photo of what arrived so I can verify what is missing before deciding the fix."


def test_photo_message_uses_item_name_for_physical_issue():
    assert message_templates.photo_message(
        order_value=450,
        issue_type="spill_leak",
        item_name="Roohafza Sharbat",
    ) == "Please upload a photo or short video of the Roohafza Sharbat as it arrived, especially the packaging and spill/damage."


def test_semantic_confirmation_handles_prep_anomaly_without_wrong_category():
    message = message_templates.semantic_confirmation_message(
        item_name="Butter Chicken Rice Bowl",
        issue_type="quality",
        fault="kitchen",
        prep_anomaly=True,
    )

    assert "prep-side quality issue" in message
    assert "selected issue category" not in message


def test_active_case_status_for_cancelled_replacement_refund_review():
    message = message_templates.replacement_status_message(
        {
            "approved_replacement_item_name": "Peri Peri French Fries",
            "approved_replacement_status": "cancel_requested_for_refund_review",
        }
    )

    assert "no longer being treated as the active fix" in message
    assert "refund change for review" in message


def test_active_case_status_photo_pending_uses_issue_label():
    message = message_templates.active_case_status_message(
        {
            "pending": "photo",
            "case_issue_type": "portion_size",
            "active_item_name": "Butter Chicken Rice Bowl",
        },
        item_name="Butter Chicken Rice Bowl",
        standard_coupon_amount=50,
    )

    assert message == (
        "I've noted the quantity issue for Butter Chicken Rice Bowl. "
        "I still need a photo or video before I can decide compensation in chat."
    )


def test_coupon_reinforcement_does_not_directly_approve_unverified_replacement():
    message = message_templates.coupon_reinforcement_message(
        coupon_amount=42,
        desired_resolution="replacement",
        item_name="Peri Peri French Fries",
        push_count=1,
        evidence_strength="weak",
        issue_type="quality",
    )

    assert "don't have enough to approve a remake directly yet" in message
    assert "coupon right now" in message


def test_review_repeat_message_is_not_antagonistic():
    message = message_templates.review_repeat_message()

    assert "already marked for review" in message
    assert "keep repeating" not in message.lower()
    assert "restating" not in message.lower()
