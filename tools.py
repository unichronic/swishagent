import os
import json
from pathlib import Path

import requests
from dotenv import load_dotenv

from llm_client import call_gemini_multimodal
from order_data import ORDER_DATABASE

load_dotenv(Path(__file__).resolve().with_name(".env"))

KITCHEN_API = os.getenv("DATA_API_URL", "http://localhost:8081")
FLEET_API = os.getenv("DATA_API_URL", "http://localhost:8081")
TRUST_API = os.getenv("DATA_API_URL", "http://localhost:8081")
ORDER_API = os.getenv("DATA_API_URL", "http://localhost:8081")


def _safe_get(url: str, timeout: int = 3):
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _fallback_order(order_id: str) -> dict:
    return ORDER_DATABASE.get(order_id, {})


def _fallback_items(order_id: str) -> dict:
    order = _fallback_order(order_id)
    if order:
        return {"order_id": order_id, "items": order.get("items", [])}
    return {"order_id": order_id, "items": []}


def _fallback_trust(user_id: str) -> dict:
    return {
        "user_id": user_id,
        "score": 50,
        "total_orders": 0,
        "refund_requests": 0,
        "successful_orders": 0,
        "cancelled_orders": 0,
        "avg_order_value": None,
        "account_age_days": None,
        "last_order_date": None,
        "degraded": True,
        "notes": "Trust data unavailable; using neutral fallback",
    }


def _fallback_kitchen(order_id: str) -> dict:
    return {
        "order_id": order_id,
        "status": "unknown",
        "quality_out": "unknown",
        "prep_time_mins": None,
        "temperature_check": "unknown",
        "degraded": True,
        "notes": "Kitchen data unavailable; using neutral fallback",
    }


def _fallback_fleet(order_id: str) -> dict:
    return {
        "order_id": order_id,
        "within_geofence": None,
        "delay_mins": None,
        "traffic_flag": None,
        "delivered": None,
        "pickup_time": None,
        "delivery_time": None,
        "distance_km": None,
        "degraded": True,
        "notes": "Fleet data unavailable; using neutral fallback",
    }


def check_kitchen_log(order_id: str) -> dict:
    try:
        return _safe_get(f"{KITCHEN_API}/kitchen/log/{order_id}")
    except Exception:
        return _fallback_kitchen(order_id)


def check_fleet_status(order_id: str) -> dict:
    try:
        return _safe_get(f"{FLEET_API}/fleet/status/{order_id}")
    except Exception:
        return _fallback_fleet(order_id)


def get_trust_score(user_id: str) -> dict:
    try:
        return _safe_get(f"{TRUST_API}/trust/{user_id}")
    except Exception:
        return _fallback_trust(user_id)


def analyze_photo(image_url: str) -> dict:
    try:
        from google.genai import types as genai_types

        img_response = requests.get(image_url, timeout=5)
        img_response.raise_for_status()
        mime_type = img_response.headers.get("content-type", "image/jpeg").split(";")[0]
        response = call_gemini_multimodal(
            [
                genai_types.Part.from_bytes(data=img_response.content, mime_type=mime_type),
                (
                    'You are a food-delivery fraud detector. Respond in JSON only: '
                    '{"valid": true/false, "reason": "brief explanation", '
                    '"evidence_relevance": "food_visible|receipt_or_packaging|unrelated|unclear", '
                    '"visible_issue": "spill|damage|wrong_item|missing_context|quality_visible|none|unclear"}. '
                    "Mark invalid only for clear signs of editing or AI generation. "
                    "Use evidence_relevance and visible_issue to describe what the image can actually support."
                ),
            ]
        )
        text = response.text.strip()
        start, end = text.find("{"), text.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("no JSON in response")
        parsed = json.loads(text[start:end])
        parsed.setdefault("evidence_relevance", "unclear")
        parsed.setdefault("visible_issue", "unclear")
        return parsed
    except Exception as exc:
        print(f"photo analysis failed: {exc}")
        return {"valid": True, "reason": "analysis unavailable"}


def get_order_details(order_id: str) -> dict:
    try:
        return _safe_get(f"{ORDER_API}/order/{order_id}")
    except Exception:
        order = _fallback_order(order_id)
        if order:
            return {
                "order_id": order["order_id"],
                "status": order["status"],
                "total_amount": order["total_amount"],
                "placed_at": order["placed_at"],
                "delivered_at": order["delivered_at"],
                "restaurant_name": order["restaurant"],
                "delivery_address": order["delivery_address"],
                "payment_method": order["payment_method"],
                "delivery_partner_name": order["delivery_partner"],
                "delivery_partner_phone": order["delivery_partner_phone"],
            }
        return {"order_id": order_id, "status": "delivered", "total_amount": 0.0}


def get_order_items(order_id: str) -> dict:
    try:
        return _safe_get(f"{ORDER_API}/order/{order_id}/items")
    except Exception:
        return _fallback_items(order_id)


def get_order_item_details(order_id: str, item_name: str) -> dict:
    try:
        return _safe_get(f"{ORDER_API}/order/{order_id}/item/{item_name}")
    except Exception:
        items = _fallback_items(order_id).get("items", [])
        target = item_name.lower()
        for item in items:
            if target in item.get("name", "").lower():
                return item
        return {"error": "item details unavailable"}


def get_delivery_info(order_id: str) -> dict:
    try:
        return _safe_get(f"{ORDER_API}/order/{order_id}/delivery")
    except Exception:
        order = _fallback_order(order_id)
        if order:
            return {
                "order_id": order_id,
                "delivery_partner_name": order.get("delivery_partner"),
                "delivery_partner_phone": order.get("delivery_partner_phone"),
                "delivery_address": order.get("delivery_address"),
                "placed_at": order.get("placed_at"),
                "delivered_at": order.get("delivered_at"),
                "delivery_time_mins": order.get("delivery_time"),
            }
        return {"order_id": order_id}
