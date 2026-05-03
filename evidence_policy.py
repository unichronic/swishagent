"""
Evidence policy for support decisions.

This module decides when visual proof is useful, whether existing proof applies
to the current case, and how strong the available evidence is.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


PHYSICAL_ISSUE_TYPES = {"damaged", "spill_leak", "wrong_item", "missing_item", "foreign_object"}


def _lower(value: Optional[Any]) -> str:
    return str(value or "").strip().lower()


def needs_photo(
    *,
    explicit_comp: bool,
    photo_present: bool,
    visual_evidence_useful: bool,
) -> bool:
    if photo_present:
        return False
    if explicit_comp and visual_evidence_useful:
        return True
    return False


def photo_case_key(*, issue_type: str, item_name: Optional[str]) -> str:
    return f"{issue_type}:{_lower(item_name)}"


def evidence_strength(
    *,
    issue_type: str,
    fault: str,
    kitchen: Dict[str, Any],
    fleet: Dict[str, Any],
    photo_present: bool,
    photo_valid: Optional[bool],
    visual_evidence_useful: bool,
) -> str:
    if photo_present and photo_valid is not False:
        return "strong"
    if issue_type in {"delay", "wrong_item", "missing_item", "foreign_object"}:
        return "strong"
    if issue_type in {"spill_leak", "damaged"} and fault in {"kitchen", "delivery"}:
        return "strong"
    if issue_type == "temperature" and fault in {"kitchen", "delivery"} and (fleet.get("delay_mins") or 0) >= 10:
        return "strong"
    if issue_type == "quality" and _lower(kitchen.get("quality_out")) in {"bad", "fair"}:
        return "strong"
    if visual_evidence_useful:
        return "weak"
    return "weak"


def visual_evidence_useful(
    *,
    issue_type: str,
    order_items: Dict[str, Any],
    assessed_visual_evidence: Optional[bool],
    assessed_issue_confidence: Optional[float],
    min_visual_decision_confidence: float,
) -> bool:
    item_count = len(order_items.get("items", [])) if isinstance(order_items, dict) else 0
    default_useful = issue_type in PHYSICAL_ISSUE_TYPES
    if issue_type == "missing_item" and item_count < 2:
        default_useful = False

    if assessed_visual_evidence is None:
        return default_useful

    confidence = assessed_issue_confidence or 0.0
    if confidence < min_visual_decision_confidence:
        return default_useful

    if not default_useful:
        return False
    return assessed_visual_evidence


def cannot_provide_photo(text: str) -> bool:
    lowered = _lower(text)
    if not lowered:
        return False
    return any(
        phrase in lowered
        for phrase in [
            "camera not working",
            "camra not working",
            "camra not wrking",
            "can't upload photo",
            "cannot upload photo",
            "cant upload photo",
            "can't share photo",
            "cannot share photo",
            "no photo",
            "photo nahi",
            "image nahi",
            "can't upload image",
            "cannot upload image",
        ]
    )
