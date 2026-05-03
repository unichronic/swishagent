"""
Semantic normalization for support policy decisions.

This layer turns raw LLM labels and customer text into canonical facts that the
policy engine can consume. The goal is to keep business policy away from raw
phrases and model overcalls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
import re


ALLOWED_DIETARY_DIRECTIONS = {
    "none",
    "nonveg_in_veg",
    "veg_in_nonveg",
    "allergen",
    "unknown",
}

ALLOWED_RESOLUTION_CHANGES = {
    "none",
    "refund_after_replacement",
    "replacement_after_refund",
    "refund_after_coupon",
    "replacement_after_coupon",
}


def _lower(text: Optional[str]) -> str:
    return (text or "").strip().lower()


def _enum(value: Any, allowed: set[str], default: str = "none") -> str:
    return value if isinstance(value, str) and value in allowed else default


@dataclass(frozen=True)
class SemanticFacts:
    dietary_direction: str = "none"
    resolution_change: str = "none"
    benign_ingredient_mismatch: bool = False
    serious_dietary_violation: bool = False
    prep_anomaly: bool = False
    replacement_status_query: bool = False


def normalize_semantic_facts(
    *,
    text: str,
    assessment: Dict[str, Any],
    state: Optional[Dict[str, Any]] = None,
) -> SemanticFacts:
    lowered = _lower(text)
    state = state or {}
    dietary_direction = _enum(
        assessment.get("dietary_direction"),
        ALLOWED_DIETARY_DIRECTIONS,
        default="none",
    )
    resolution_change = _enum(
        assessment.get("resolution_change"),
        ALLOWED_RESOLUTION_CHANGES,
        default="none",
    )

    detected_direction = _detect_dietary_direction(lowered)
    if detected_direction != "none":
        dietary_direction = detected_direction
    elif dietary_direction == "none" and _looks_like_benign_ingredient_mismatch(lowered):
        dietary_direction = "veg_in_nonveg"

    if resolution_change == "none":
        resolution_change = _detect_resolution_change(lowered, state)

    benign = dietary_direction == "veg_in_nonveg" or _looks_like_benign_ingredient_mismatch(lowered)
    serious = dietary_direction in {"nonveg_in_veg", "allergen"}
    prep_anomaly = benign or _looks_like_benign_ingredient_mismatch(lowered)
    replacement_status_query = _is_replacement_status_query(lowered, state)

    return SemanticFacts(
        dietary_direction=dietary_direction,
        resolution_change=resolution_change,
        benign_ingredient_mismatch=benign,
        serious_dietary_violation=serious,
        prep_anomaly=prep_anomaly,
        replacement_status_query=replacement_status_query,
    )


def _detect_dietary_direction(text: str) -> str:
    if not text:
        return "none"
    if _has_allergen_marker(text):
        return "allergen"
    if _looks_like_nonveg_in_veg(text):
        return "nonveg_in_veg"
    if _looks_like_veg_in_nonveg(text):
        return "veg_in_nonveg"
    return "none"


def _has_allergen_marker(text: str) -> bool:
    allergen_markers = ["allergy", "allergic", "allergen"]
    allergen_terms = ["peanut", "peanuts", "nut", "nuts", "cashew", "dairy", "milk"]
    return any(term in text for term in allergen_markers) and any(term in text for term in allergen_terms)


def _looks_like_nonveg_in_veg(text: str) -> bool:
    nonveg_pattern = r"(?:chicken|chick|egg|meat|fish|mutton|beef|prawn|pork)"
    veg_context_pattern = r"(?:veg|vegetarian|veggie|paneer|jain)"
    return bool(
        re.search(rf"\b{nonveg_pattern}\b.{{0,60}}\b{veg_context_pattern}\b", text)
        or re.search(rf"\b{veg_context_pattern}\b.{{0,60}}\b{nonveg_pattern}\b", text)
        or re.search(rf"\b(piece|bits?|chunks?)\s+of\s+{nonveg_pattern}\b", text)
    )


def _looks_like_veg_in_nonveg(text: str) -> bool:
    if _has_serious_restriction_marker(text):
        return False
    if _looks_like_nonveg_in_veg(text):
        return False
    plant_pattern = r"(?:vegetable|vegetables|veggie|veggies|veg|onion|capsicum|pepper|corn|herb|masala)"
    nonveg_context_pattern = r"(?:non veg|non-veg|chicken|meat|fish|mutton|beef|prawn|pork)"
    return bool(
        re.search(rf"\b{plant_pattern}\b.{{0,60}}\b{nonveg_context_pattern}\b", text)
        or re.search(rf"\b{nonveg_context_pattern}\b.{{0,60}}\b{plant_pattern}\b", text)
    )


def _has_serious_restriction_marker(text: str) -> bool:
    return any(
        marker in text
        for marker in ["allergy", "allergic", "allergen", "religion", "religious", "fasting", "vrat", "jain"]
    )


def _looks_like_benign_ingredient_mismatch(text: str) -> bool:
    if not text:
        return False
    mismatch_patterns = [
        r"\bpiece of (?:a |an )?(vegetable|veggies|onion|capsicum|pepper|corn)\b",
        r"\b(vegetable|veggies|onion|capsicum|pepper|corn)\s+piece\b",
        r"\b(extra|unexpected|wrong)\s+(vegetable|veggies|onion|capsicum|pepper|corn|sauce)\b",
    ]
    return any(re.search(pattern, text) for pattern in mismatch_patterns) or (
        "shouldn't be in" in text
        and any(term in text for term in ["vegetable", "veggies", "onion", "capsicum", "pepper", "corn", "sauce"])
    )


def _detect_resolution_change(text: str, state: Dict[str, Any]) -> str:
    if not text:
        return "none"
    if state.get("approved_replacement_item_name") and _mentions_refund(text):
        return "refund_after_replacement"
    if state.get("last_action") == "refund" and _mentions_replacement(text):
        return "replacement_after_refund"
    if state.get("pending") == "coupon" and _mentions_refund(text):
        return "refund_after_coupon"
    if state.get("pending") == "coupon" and _mentions_replacement(text):
        return "replacement_after_coupon"
    return "none"


def _is_replacement_status_query(text: str, state: Dict[str, Any]) -> bool:
    if not state.get("approved_replacement_item_name") or not text:
        return False
    replacement_terms = ["replacement", "replacemetn", "replace", "remake", "fresh item", "fresh one"]
    status_terms = [
        "when",
        "time",
        "how much time",
        "how long",
        "eta",
        "arrive",
        "arrives",
        "arriving",
        "deliver",
        "delivery",
        "status",
        "update",
    ]
    return any(term in text for term in replacement_terms) and any(term in text for term in status_terms)


def _mentions_refund(text: str) -> bool:
    return "refund" in text or "money back" in text or "cash back" in text


def _mentions_replacement(text: str) -> bool:
    return any(term in text for term in ["replacement", "replacemetn", "replace", "another", "fresh one"])
