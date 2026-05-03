"""
User-visible support copy for the Swish agent.

Decision policy should live outside this module. These helpers only turn
already-decided state into concise customer-facing messages.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def _lower(text: Optional[str]) -> str:
    return (text or "").strip().lower()


def replacement_steer_message(item_name: str, hard_block_refund: bool) -> str:
    if hard_block_refund:
        return f"I can't lock in a cash refund directly in chat here. What I can still offer is a fresh {item_name}, or I can send the refund request for review."
    return f"A fresh {item_name} is the fix I can approve directly here. If you still want a cash refund instead, I need to send that for review."


def replacement_confirm_message(item_name: str) -> str:
    return f"I can get a fresh {item_name} remade for you instead. Want me to go ahead with that?"


def issue_negotiation_frame(issue_type: str, desired_resolution: str, evidence_strength: str) -> str:
    if issue_type == "delay":
        return "the delay was longer than it should've been"
    if issue_type == "portion_size":
        return "the quantity concern is hard to verify after delivery"
    if issue_type == "temperature":
        return "it should've reached you in better shape"
    if issue_type == "foreign_object":
        return "this is more serious than a normal quality complaint"
    if issue_type == "wrong_item":
        return "you should've had the right item in the first place"
    if issue_type == "missing_item":
        return "the order should've reached you complete"
    if issue_type in {"spill_leak", "damaged"}:
        return "it should've arrived usable"
    if desired_resolution == "replacement" and evidence_strength != "strong":
        return "I don't want to promise a remake I can't verify cleanly"
    return "this should've landed better than it did"


def coupon_reinforcement_message(
    coupon_amount: float,
    desired_resolution: str,
    item_name: str,
    push_count: int,
    evidence_strength: str,
    issue_type: str = "quality",
    tone_guardrail: str = "neutral",
    negotiation_strength: str = "medium",
) -> str:
    amount = int(coupon_amount)
    frame = issue_negotiation_frame(issue_type, desired_resolution, evidence_strength)
    if desired_resolution == "replacement" and evidence_strength != "strong":
        if push_count <= 1:
            return (
                f"I get why you're asking for a fresh {item_name}. I don't have enough to approve a remake directly yet, "
                f"but I can add a ₹{amount} coupon right now. Want me to do that?"
            )
        return (
            f"I still can't approve the remake cleanly from what I have here. "
            f"I can add the ₹{amount} coupon now, or move this for review if that doesn't work."
        )
    if desired_resolution == "replacement":
        if push_count <= 1:
            if tone_guardrail == "sensitive" or negotiation_strength == "light":
                return (
                    f"I get why you'd want this remade. The quickest thing I can put through right now is the ₹{amount} coupon. "
                    f"If that still doesn't help, I can take you to the next step."
                )
            return (
                f"I get why you'd want this remade because {frame}. I can put through the ₹{amount} coupon right now, "
                f"and if that still doesn't work I can move to the next fix with you."
            )
        return (
            f"If the coupon still doesn't work for you, I can move to a fresh {item_name} next. "
            f"Want me to do that?"
        )
    if desired_resolution == "refund":
        if push_count <= 1:
            if tone_guardrail == "sensitive" or negotiation_strength == "light":
                return (
                    f"I hear you. I can't approve cash back directly from this chat yet, but I can add a ₹{amount} coupon now. "
                    f"If that doesn't work for you, I'll move it for review."
                )
            return (
                f"I can't approve a cash refund directly from what I have here. "
                f"The direct option I can apply now is a ₹{amount} coupon."
            )
        return (
            f"I can still add the ₹{amount} coupon right now. If that doesn't work for you, "
            f"I'll move the case for review instead of promising a refund I can't approve here."
        )
    return (
        f"I can put through the ₹{amount} coupon now if that helps. "
        f"If not, tell me the fix you'd rather go with."
    )


def coupon_context_message(
    issue_type: str,
    item_name: str,
    coupon_amount: float,
    portion_component: Optional[str] = None,
) -> str:
    amount = int(coupon_amount)
    if issue_type == "delay":
        noted = "a delivery delay"
    elif issue_type == "portion_size" and portion_component:
        noted = f"a {portion_component} quantity concern on the {item_name}"
    elif issue_type == "portion_size":
        noted = f"a quantity issue on the {item_name}"
    elif issue_type in {"spill_leak", "damaged"}:
        noted = f"a spill or damage issue with the {item_name}"
    elif issue_type == "missing_item":
        noted = f"a missing item issue for the {item_name}"
    elif issue_type == "wrong_item":
        noted = f"a wrong item issue for the {item_name}"
    else:
        noted = f"a quality issue with the {item_name}"
    return f"I've noted this as {noted}. The direct option I can apply in chat is the ₹{amount} coupon."


def issue_label(issue_type: str) -> str:
    labels = {
        "quality": "quality issue",
        "temperature": "temperature issue",
        "delay": "delivery delay",
        "wrong_item": "wrong-item issue",
        "missing_item": "missing-item issue",
        "damaged": "spill or damage issue",
        "spill_leak": "spill issue",
        "foreign_object": "safety issue",
        "portion_size": "quantity issue",
    }
    return labels.get(issue_type, "order issue")


def active_case_status_message(
    state: Dict[str, Any],
    item_name: str,
    standard_coupon_amount: float,
) -> str:
    issue_type = state.get("case_issue_type") or state.get("issue_type") or "quality"
    target = item_name if item_name and item_name != "item" else state.get("active_item_name") or "this order"
    if state.get("last_action") == "escalate":
        return "This is already marked for review. I can add your latest note here, but I can't approve another automatic fix in chat."
    if state.get("last_action") in {"refund", "replacement", "coupon", "credit"}:
        return "The action on this case is already recorded. I can keep the order context attached if you need to follow up."
    if state.get("pending") == "photo":
        return f"I've noted the {issue_label(issue_type)} for {target}. I still need a photo or video before I can decide compensation in chat."
    if state.get("pending") == "coupon":
        amount = int(float(state.get("coupon_amount") or standard_coupon_amount))
        return f"I've noted the {issue_label(issue_type)} for {target}. The direct option I can apply in chat is the ₹{amount} coupon."
    if state.get("pending") == "replacement_confirm":
        return f"I've noted the {issue_label(issue_type)} for {target}. I need you to confirm whether you want me to proceed with the fresh item."
    if state.get("pending") == "refund_amount":
        return f"I've noted the {issue_label(issue_type)} for {target}. I need the refund level from you: 25%, 50%, 75%, or full."
    return f"I've noted the {issue_label(issue_type)} for {target}. Tell me whether you want a coupon, refund, replacement, or just want this logged."


def review_escalation_message(
    resolution_type: str,
    *,
    item_name: Optional[str] = None,
    issue_type: Optional[str] = None,
) -> str:
    target = item_name if item_name and item_name != "item" else "this order"
    label = issue_label(issue_type or "quality")
    if resolution_type == "replacement":
        return (
            f"I don't have enough verified evidence to approve a remake for {target} from chat. "
            "I've moved it to review so the team can check the order context."
        )
    if resolution_type == "refund":
        return (
            f"I can't lock in a cash refund for the {label} on {target} from what I can verify here. "
            "I've moved it to review so a person can check the order context."
        )
    return f"I can't close this properly from chat alone for the {label} on {target}, so I've moved it to review with the order context attached."


def review_repeat_message() -> str:
    return "This is already marked for review. I can keep your latest note attached here, but I can't approve another automatic action in chat."


def semantic_clarification_message(
    selected_item: str,
    mentioned_item: Optional[str],
    semantic_risk_reason: Optional[str],
) -> str:
    if mentioned_item and selected_item and selected_item != "item" and _lower(mentioned_item) != _lower(selected_item):
        return f"I might be looking at the wrong item. You selected {selected_item}, but your message sounds like {mentioned_item}. Which item should I handle?"
    if mentioned_item and selected_item and selected_item != "item":
        return f"I’m looking at {selected_item}. Your message sounds like a different issue from the option selected. Should I handle it based on what you described?"
    if mentioned_item:
        return f"I want to make sure I handle the right item. Are you asking about {mentioned_item}?"
    if semantic_risk_reason:
        return "I want to make sure I don't handle this under the wrong issue. Can you confirm which item and issue I should check?"
    return "I want to make sure I don't handle the wrong thing. Which item and issue should I check?"


def semantic_confirmation_message(
    item_name: str,
    issue_type: str,
    fault: str,
    prep_anomaly: bool,
) -> str:
    if prep_anomaly or (issue_type == "quality" and fault == "kitchen"):
        return f"Got it. I’ll handle this as a prep-side quality issue for {item_name}. Tell me if you only want this logged or want me to check the available fix."
    label = issue_label(issue_type)
    return f"Got it. I’ll handle this as a {label} for {item_name}. Tell me if you only want this logged or want me to check the available fix."


def photo_message(order_value: float, issue_type: str, item_name: str = "item") -> str:
    if issue_type == "missing_item":
        return "Please upload a photo of what arrived so I can verify what is missing before deciding the fix."
    if issue_type == "wrong_item":
        target = item_name if item_name and item_name != "item" else "item"
        return f"Please upload a photo showing the {target} you received. I need that proof before deciding compensation in chat."
    if issue_type in {"spill_leak", "damaged"}:
        target = item_name if item_name and item_name != "item" else "item"
        return f"Please upload a photo or short video of the {target} as it arrived, especially the packaging and spill/damage."
    target = item_name if item_name and item_name != "item" else "item"
    return f"Please upload a clear photo of the {target}. I need that before taking a compensation action in chat."


def replacement_status_message(state: Dict[str, Any]) -> str:
    item_name = (
        state.get("approved_replacement_item_name")
        or state.get("last_item_name")
        or state.get("active_item_name")
        or "replacement"
    )
    if state.get("approved_replacement_status") == "cancel_requested_for_refund_review":
        return f"The fresh {item_name} is no longer being treated as the active fix in this chat. I’ve marked it to be cancelled and sent your refund change for review."
    return f"The fresh {item_name} has already been approved. I don't have a live ETA here yet, but these usually go out in around 15 to 20 mins and you'll see the update in-app."
