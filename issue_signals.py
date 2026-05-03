"""
Reusable lexical issue signals.

These are intentionally narrow text signals. Higher-level semantic decisions
still belong in semantic_policy.py and business policy still belongs in rules.py.
"""

from __future__ import annotations

import re
from typing import Optional


PORTION_COMPONENT_PATTERN = r"(?:chicken|paneer|fries|rice|noodles|sauce|cheese|maggi|samosa)"


def lower(text: Optional[str]) -> str:
    return (text or "").strip().lower()


def is_portion_signal(text: str) -> bool:
    text = lower(text)
    if re.search(rf"\bnot\s+enough\s+{PORTION_COMPONENT_PATTERN}\b", text):
        return True
    if re.search(rf"\b{PORTION_COMPONENT_PATTERN}\s+(?:qty|qnty|quantity|portion)\s+(?:was\s+|is\s+)?(?:too\s+|very\s+)?(?:less|low|kam)\b", text):
        return True
    if re.search(r"\b(qty|qnty|quantity|portion)\s+(?:too\s+|vry\s+|very\s+)?(less|low|kam)\b", text):
        return True
    if re.search(r"\b(quantity|qty|qnty|portion)\s+(bahut\s+|too\s+|vry\s+|very\s+)?(kam|less|low)\b", text):
        return True
    if re.search(r"\b(kam|less)\s+(quantity|qty|qnty|portion)\b", text):
        return True
    if re.search(r"\b(?:tiny|small)\s+(?:portion|serving|pieces?|pices)\b", text):
        return True
    if re.search(r"\b(?:pieces?|pices)\s+(?:tha|the|were|was)?.{0,20}\b(?:tiny|small|less|kam)\b", text):
        return True
    if re.search(r"\b(?:too|very)\s+less\b", text):
        return True
    if re.search(r"\b(?:was|were|is)\s+less\b", text):
        return True
    return any(
        phrase in text
        for phrase in [
            "small portion",
            "too little",
            "less quantity",
            "less in quantity",
            "tiny portion",
            "portion was small",
            "quantity was less",
            "very little",
            "very less",
            "very less food",
            "less food",
            "not enough food",
            "not enough for what i paid",
            "hardly any",
            "small serving",
            "under portion",
            "underportioned",
            "under-portioned",
            "too less",
            "bahut kam thi",
            "bahut kam tha",
            "quantity kam thi",
            "quantity kam tha",
            "size very small",
            "size bahut small",
            "pieces small",
            "pices small",
            "qty issue",
            "qnty issue",
        ]
    )


def is_solid_item_spill_damage(text: str) -> bool:
    text = lower(text)
    if not re.search(r"\b(spill|spilled|spillage|leak|leaked|leaking|sauce bahar|sauce out)\b", text):
        return False
    solid_terms = ["sandwich", "burger", "wrap", "bread", "fries", "samosa", "momos", "roll"]
    liquid_terms = ["drink", "shake", "coffee", "sharbat", "curry", "gravy", "soup", "beverage", "cup", "bottle"]
    if any(term in text for term in liquid_terms):
        return False
    return any(term in text for term in solid_terms)


def spill_or_damage_issue(text: str, current_issue_type: str = "quality") -> Optional[str]:
    text = lower(text)
    if is_solid_item_spill_damage(text):
        return "damaged"
    spill_context = any(
        token in text
        for token in (
            "bag",
            "cup",
            "bottle",
            "container",
            "box",
            "drink",
            "shake",
            "coffee",
            "sharbat",
            "curry",
            "salad",
            "bowl",
            "pasta",
            "sauce",
            "gravy",
            "leak",
            "leaked",
            "leaking",
            "andar",
        )
    )
    if re.search(r"\b(spill|spilled|spillage|leak|leaked|leaking|leked|leking|gir gaya|gir gya|gir gayi|gir gayi thi)\b", text):
        return "spill_leak" if spill_context else "damaged"
    if "bag me spill" in text or "bag mein spill" in text or "andar spill" in text:
        return "spill_leak"
    if any(word in text for word in ["spilled", "leaked", "leaking", "leked", "leking", "opened and spilled", "burst open"]):
        return "spill_leak"
    if any(word in text for word in ["damaged", "crushed", "broken", "soggy packaging"]):
        return "damaged"
    return None


def is_quality_signal(text: str) -> bool:
    text = lower(text)
    return any(word in text for word in ["sweet", "meetha", "salty", "bland", "burnt", "raw", "soggy", "terrible", "inedible", "bad taste"])


def is_temperature_signal(text: str) -> bool:
    text = lower(text)
    return bool(
        re.search(r"\b(cold|not hot|thanda|lukewarm|room temp|temperature|garam nahi|not warm)\b", text)
        or "ice melted" in text
    )


def is_delay_signal(text: str) -> bool:
    text = lower(text)
    return any(word in text for word in ["late", "delay", "delayed", "where is my order"]) or bool(re.search(r"\beta\b", text))
