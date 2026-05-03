import importlib
import io

from fastapi.testclient import TestClient
from PIL import Image


def _jpg_bytes(color, offset=0):
    image = Image.new("RGB", (64, 64), color)
    if offset:
        for x in range(10, 20):
            for y in range(10, 20):
                image.putpixel((x + offset, y), (255, 255, 255))
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _load_module(monkeypatch, tmp_path):
    monkeypatch.setenv("FRAUD_DB_PATH", str(tmp_path / "fraud.db"))
    import fraud_service

    return importlib.reload(fraud_service)


def test_static_capture_is_rejected(monkeypatch, tmp_path):
    fraud_service = _load_module(monkeypatch, tmp_path)
    monkeypatch.setattr(
        fraud_service,
        "_content_check",
        lambda image, complaint, claim_info=None: {"content_flag": False, "content_reason": "skipped"},
    )
    monkeypatch.setattr(fraud_service, "_behavior_flag", lambda user_id: {"behavior_flag": False, "trust_score": 82, "complaint_rate": 0.05})
    client = TestClient(fraud_service.app)

    frame = _jpg_bytes((120, 80, 60))
    response = client.post(
        "/verify-capture",
        files=[
            ("frames", ("frame0.jpg", frame, "image/jpeg")),
            ("frames", ("frame1.jpg", frame, "image/jpeg")),
            ("frames", ("frame2.jpg", frame, "image/jpeg")),
        ],
        data={"user_id": "USR001", "order_id": "ORD001", "complaint": "the food was damaged"},
    )

    payload = response.json()
    assert payload["valid"] is False
    assert "suspicious" in payload["reason"] or "could not be verified" in payload["reason"]


def test_live_capture_with_motion_passes(monkeypatch, tmp_path):
    fraud_service = _load_module(monkeypatch, tmp_path)
    monkeypatch.setattr(
        fraud_service,
        "_content_check",
        lambda image, complaint, claim_info=None: {"content_flag": False, "content_reason": "skipped"},
    )
    monkeypatch.setattr(fraud_service, "_behavior_flag", lambda user_id: {"behavior_flag": False, "trust_score": 82, "complaint_rate": 0.05})
    client = TestClient(fraud_service.app)

    response = client.post(
        "/verify-capture",
        files=[
            ("frames", ("frame0.jpg", _jpg_bytes((110, 90, 70), offset=0), "image/jpeg")),
            ("frames", ("frame1.jpg", _jpg_bytes((110, 90, 70), offset=4), "image/jpeg")),
            ("frames", ("frame2.jpg", _jpg_bytes((110, 90, 70), offset=8), "image/jpeg")),
        ],
        data={"user_id": "USR001", "order_id": "ORD001", "complaint": "the food was damaged"},
    )

    payload = response.json()
    assert payload["valid"] is True
    assert "continue" in payload["reason"]


def test_reused_media_is_flagged_for_review(monkeypatch, tmp_path):
    fraud_service = _load_module(monkeypatch, tmp_path)
    monkeypatch.setattr(
        fraud_service,
        "_content_check",
        lambda image, complaint, claim_info=None: {"content_flag": False, "content_reason": "skipped"},
    )
    monkeypatch.setattr(fraud_service, "_behavior_flag", lambda user_id: {"behavior_flag": False, "trust_score": 82, "complaint_rate": 0.05})
    client = TestClient(fraud_service.app)

    files = [
        ("frames", ("frame0.jpg", _jpg_bytes((150, 60, 40), offset=0), "image/jpeg")),
        ("frames", ("frame1.jpg", _jpg_bytes((150, 60, 40), offset=4), "image/jpeg")),
        ("frames", ("frame2.jpg", _jpg_bytes((150, 60, 40), offset=8), "image/jpeg")),
    ]
    data = {"user_id": "USR001", "order_id": "ORD100", "complaint": "the box was crushed"}

    first = client.post("/verify-capture", files=files, data=data)
    assert first.json()["valid"] is True

    second = client.post(
        "/verify-capture",
        files=files,
        data={"user_id": "USR001", "order_id": "ORD101", "complaint": "the box was crushed"},
    )
    payload = second.json()
    assert payload["valid"] is False
    assert "could not be verified" in payload["reason"] or "suspicious" in payload["reason"]


def test_expected_visual_claim_maps_complaint_types(monkeypatch, tmp_path):
    fraud_service = _load_module(monkeypatch, tmp_path)
    responses = iter(
        [
            '{"expected_visual_claim":"damage_or_spill","requires_food_evidence":true,"confidence":0.9}',
            '{"expected_visual_claim":"wrong_item","requires_food_evidence":true,"confidence":0.9}',
            '{"expected_visual_claim":"contamination_or_foreign_object","requires_food_evidence":true,"confidence":0.9}',
        ]
    )
    monkeypatch.setattr(fraud_service, "call_text", lambda messages, **kwargs: next(responses))

    fraud_service._assess_visual_claim.cache_clear()
    assert fraud_service._assess_visual_claim("the drink spilled everywhere")["expected_visual_claim"] == "damage_or_spill"
    assert fraud_service._assess_visual_claim("this is the wrong item")["expected_visual_claim"] == "wrong_item"
    assert fraud_service._assess_visual_claim("there was chicken in my veg pasta")["expected_visual_claim"] == "contamination_or_foreign_object"


def test_content_check_uses_claim_specific_support(monkeypatch, tmp_path):
    fraud_service = _load_module(monkeypatch, tmp_path)

    class FakeResponse:
        text = '{"shows_food": true, "relevant": true, "supports_claim": false, "notes": "food is visible but no spill is visible"}'

    monkeypatch.setattr(
        fraud_service,
        "call_text",
        lambda messages, **kwargs: '{"expected_visual_claim":"damage_or_spill","requires_food_evidence":true,"confidence":0.92}',
    )
    monkeypatch.setattr(fraud_service, "call_gemini_multimodal", lambda contents: FakeResponse())
    image = Image.new("RGB", (80, 80), (140, 90, 70))
    for x in range(15, 35):
        for y in range(20, 45):
            image.putpixel((x, y), (220, 220, 220))
    result = fraud_service._content_check(image, "the drink was spilled")
    assert result["content_flag"] is True
    assert "spill" in result["content_reason"].lower()


def test_claim_assessment_falls_back_to_generic_when_llm_fails(monkeypatch, tmp_path):
    fraud_service = _load_module(monkeypatch, tmp_path)
    monkeypatch.setattr(fraud_service, "call_text", lambda messages, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    fraud_service._assess_visual_claim.cache_clear()

    result = fraud_service._assess_visual_claim("food looked weird")

    assert result["expected_visual_claim"] == "generic_food_evidence"
    assert result["requires_food_evidence"] is True


def test_missing_item_not_prefiltered_as_non_visual(monkeypatch, tmp_path):
    fraud_service = _load_module(monkeypatch, tmp_path)
    fraud_service._assess_visual_claim.cache_clear()
    monkeypatch.setattr(
        fraud_service,
        "call_text",
        lambda messages, **kwargs: '{"expected_visual_claim":"missing_item","requires_food_evidence":true,"confidence":0.93}',
    )

    result = fraud_service._assess_visual_claim("one drink is missing from my order")

    assert result["expected_visual_claim"] == "missing_item"
    assert result["requires_food_evidence"] is True


def test_content_check_fails_closed_when_visual_proof_required_but_unavailable(monkeypatch, tmp_path):
    fraud_service = _load_module(monkeypatch, tmp_path)
    image = Image.new("RGB", (80, 80), (140, 90, 70))
    for x in range(15, 35):
        for y in range(20, 45):
            image.putpixel((x, y), (220, 220, 220))
    claim_info = {
        "expected_visual_claim": "wrong_item",
        "requires_food_evidence": True,
        "confidence": 0.95,
    }
    monkeypatch.setattr(
        fraud_service,
        "call_gemini_multimodal",
        lambda contents: (_ for _ in ()).throw(RuntimeError("mm unavailable")),
    )

    result = fraud_service._content_check(image, "this is the wrong item", claim_info=claim_info)

    assert result["content_flag"] is True
    assert "visual proof" in result["content_reason"].lower()
