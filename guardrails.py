"""
Legacy guardrails shim.

The active policy engine now lives in rules.py. This module remains import-safe
for older scripts and documents that still reference Guardrails.
"""

from typing import Any, Dict, List

from rules import Rules


class ConversationState:
    def __init__(self):
        self.tier = 1
        self.user_asked_for_compensation = False
        self.offered_coupon = False
        self.user_rejected_coupon = False
        self.messages: List[Dict[str, str]] = []

    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content.lower()})


class Guardrails:
    @staticmethod
    def enforce_3tier_logic(
        response: Dict[str, Any],
        state: ConversationState,
        trust_score: float,
    ) -> Dict[str, Any]:
        return Rules._enforce_content(response)

    @staticmethod
    def validate_trust_based_limits(
        response: Dict[str, Any],
        trust_score: float,
        order_value: float,
    ) -> Dict[str, Any]:
        if response.get("action") == "refund" and trust_score <= Rules.REFUND_TRUST_THRESHOLD:
            return {
                "action": "escalate",
                "amount": 0.0,
                "message": "This needs a quick manual review, so I've escalated it to the team. They'll reach out within 24hrs.",
                "reason": "Refund above trust threshold",
            }
        return Rules._enforce_content(response)
