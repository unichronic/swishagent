"""
Contracts for LLM humanization.

The LLM may improve tone, but this module defines what must be preserved and
what must never be invented in customer-visible copy.
"""

from __future__ import annotations

import re
from typing import Any, Optional


COMPONENT_TERMS = {
    "chicken",
    "paneer",
    "fries",
    "rice",
    "noodles",
    "sauce",
    "cheese",
    "maggi",
    "samosa",
    "aloo",
    "pasta",
}

UNCERTAINTY_MARKERS = {
    "can't verify",
    "cannot verify",
    "can't confirm",
    "cannot confirm",
    "don't have enough",
    "do not have enough",
    "doesn't prove",
    "don't prove",
    "not clear",
    "not clearly",
    "not cleanly",
    "can't tell",
    "cannot tell",
}

FORBIDDEN_NEW_CLAIMS = {
    "meant to be",
    "snack-sized",
    "standard portion",
    "quality check",
    "team will review",
    "review it again",
    "you don't need to take any action",
    "approved action",
    "approved amount",
    "wallet",
    "free",
    "i asked the kitchen",
    "i have asked the kitchen",
    "i can check",
    "check on",
    "kitchen will",
    "dispatch will",
    "rider will",
    "team will",
    "it is on the way",
    "on its way",
}


def _lower(value: Optional[str]) -> str:
    return (value or "").strip().lower().replace("’", "'").replace("‘", "'")


def _money_values(text: str) -> list[str]:
    return [match.replace(" ", "") for match in re.findall(r"₹\s*\d+(?:\.\d+)?", text or "")]


def _sentences(text: str) -> list[str]:
    return [part for part in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if part]


def _item_terms(order_items: dict[str, Any]) -> set[str]:
    if not isinstance(order_items, dict):
        return set()
    stopwords = {"style", "classic", "dark", "chocolate", "veg", "non", "with", "and", "the"}
    terms: set[str] = set()
    for item in order_items.get("items", [])[:4]:
        name = str(item.get("name", "")).lower()
        for token in re.findall(r"[a-z0-9]+", name):
            if len(token) >= 4 and token not in stopwords:
                terms.add(token)
    return terms


def _required_component_terms(complaint: str, original: str) -> set[str]:
    complaint_lower = _lower(complaint)
    original_lower = _lower(original)
    complaint_components = {
        term for term in COMPONENT_TERMS if re.search(rf"\b{re.escape(term)}\b", complaint_lower)
    }
    original_components = {
        term for term in COMPONENT_TERMS if re.search(rf"\b{re.escape(term)}\b", original_lower)
    }
    return complaint_components & original_components


def build_copy_contract(
    resolution: dict[str, Any],
    *,
    complaint: str,
    order_items: dict[str, Any],
) -> dict[str, Any]:
    original = str(resolution.get("message") or "")
    original_lower = _lower(original)
    debug = resolution.get("_debug") or {}
    action = str(resolution.get("action") or "")
    amount = float(resolution.get("amount") or 0)
    required_terms = set()

    for term in _item_terms(order_items):
        if term in original_lower:
            required_terms.add(term)
    required_terms.update(_required_component_terms(complaint, original))

    if "coupon" in original_lower:
        required_terms.add("coupon")
    if "refund" in original_lower:
        required_terms.add("refund")
    if any(term in original_lower for term in ("replacement", "remake", "fresh")):
        required_terms.add("fresh_or_replacement")
    if "photo" in original_lower or "video" in original_lower:
        required_terms.add("visual_evidence")

    return {
        "action": action,
        "amount": amount,
        "reason": str(resolution.get("reason") or ""),
        "issue_type": debug.get("issue_type") or "",
        "item_name": debug.get("active_item_name") or "",
        "customer_meaning": debug.get("customer_meaning") or "",
        "reasoning_brief": debug.get("reasoning_brief") or "",
        "semantic_uncertainty": debug.get("uncertainty_reason") or "",
        "original_message": original,
        "required_terms": sorted(required_terms),
        "required_money_values": _money_values(original),
        "uncertainty_required": any(marker in original_lower for marker in UNCERTAINTY_MARKERS),
        "forbidden_new_claims": sorted(FORBIDDEN_NEW_CLAIMS),
        "max_sentences": 2,
        "max_chars": 320,
    }


def validate_candidate(candidate: str, contract: dict[str, Any]) -> list[str]:
    candidate_lower = _lower(candidate)
    original_lower = _lower(str(contract.get("original_message") or ""))
    errors: list[str] = []

    if not candidate_lower:
        return ["empty_message"]
    if len(candidate) > int(contract.get("max_chars") or 320):
        errors.append("message_too_long")
    if len(_sentences(candidate)) > int(contract.get("max_sentences") or 2):
        errors.append("too_many_sentences")

    for claim in contract.get("forbidden_new_claims") or []:
        claim_lower = _lower(str(claim))
        if claim_lower in candidate_lower and claim_lower not in original_lower:
            errors.append(f"new_forbidden_claim:{claim_lower}")

    for money in contract.get("required_money_values") or []:
        if str(money).replace(" ", "") not in candidate.replace(" ", ""):
            errors.append(f"missing_amount:{money}")

    for term in contract.get("required_terms") or []:
        if term == "fresh_or_replacement":
            if not any(word in candidate_lower for word in ("fresh", "replacement", "remake", "remade")):
                errors.append("missing_replacement_term")
        elif term == "visual_evidence":
            if not any(word in candidate_lower for word in ("photo", "video", "camera", "capture", "send", "upload")):
                errors.append("missing_visual_evidence_term")
        elif str(term) not in candidate_lower:
            errors.append(f"missing_required_term:{term}")

    if contract.get("uncertainty_required"):
        if not any(marker in candidate_lower for marker in UNCERTAINTY_MARKERS):
            errors.append("uncertainty_weakened")
        certainty_upgrades = (
            "i can see",
            "i confirmed",
            "clearly",
            "definitely",
            "you are right",
            "you're right",
            "was too small",
            "was not enough",
        )
        if any(phrase in candidate_lower and phrase not in original_lower for phrase in certainty_upgrades):
            errors.append("uncertainty_upgraded_to_certainty")

    if contract.get("action") == "info":
        approval_patterns = (
            r"\bapproved\b.{0,25}\b(refund|coupon|credit|replacement|remake)\b",
            r"\b(refund|coupon|credit|replacement|remake)\b.{0,25}\bapproved\b",
            r"\badded\b.{0,20}\b(coupon|credit|refund)\b",
        )
        if any(re.search(pattern, candidate_lower) for pattern in approval_patterns):
            errors.append("info_claims_compensation_approved")

    return errors
