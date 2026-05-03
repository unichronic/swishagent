"""
Structured conversation-state transitions for support cases.

Rules may still decide *when* to transition, but the shape of common states
belongs here so offered, pending, approved, and review states do not blur.
"""

from __future__ import annotations

from typing import Any, MutableMapping, Optional


PENDING_PHOTO = "photo"
PENDING_COUPON = "coupon"
PENDING_REFUND_AMOUNT = "refund_amount"
PENDING_REPLACEMENT_CONFIRM = "replacement_confirm"
PENDING_SEMANTIC_CLARIFICATION = "semantic_clarification"

ACTION_REFUND = "refund"
ACTION_REPLACEMENT = "replacement"
ACTION_COUPON = "coupon"
ACTION_CREDIT = "credit"
ACTION_ESCALATE = "escalate"

MODE_ACTIVE_COMPLAINT = "active_complaint"
MODE_INFO_ONLY = "info_only"
MODE_REVIEW = "review"
MODE_RESOLVED = "resolved"

APPROVED_REPLACEMENT = "approved"
CANCEL_REQUESTED_FOR_REFUND_REVIEW = "cancel_requested_for_refund_review"


def clear_resolution(state: MutableMapping[str, Any]) -> None:
    state["pending"] = None
    state["desired_resolution"] = None


def clear_pending(state: MutableMapping[str, Any]) -> None:
    state["pending"] = None


def set_pending_photo(state: MutableMapping[str, Any], desired_resolution: Optional[str] = None) -> None:
    state["pending"] = PENDING_PHOTO
    state["desired_resolution"] = desired_resolution if desired_resolution in {"refund", "replacement"} else None


def set_pending_coupon(state: MutableMapping[str, Any], desired_resolution: str, coupon_amount: float) -> None:
    state["pending"] = PENDING_COUPON
    state["desired_resolution"] = desired_resolution
    state["coupon_amount"] = coupon_amount
    state["coupon_push_count"] = 0


def set_pending_refund_amount(state: MutableMapping[str, Any]) -> None:
    state["pending"] = PENDING_REFUND_AMOUNT
    state["desired_resolution"] = ACTION_REFUND


def set_pending_replacement_confirmation(state: MutableMapping[str, Any]) -> None:
    state["pending"] = PENDING_REPLACEMENT_CONFIRM
    state["desired_resolution"] = ACTION_REPLACEMENT


def set_pending_semantic_clarification(
    state: MutableMapping[str, Any],
    *,
    item_name: str,
    issue_type: str,
    fault: str,
    prep_anomaly: bool,
    message: str,
    reason: Optional[str],
) -> None:
    state["pending"] = PENDING_SEMANTIC_CLARIFICATION
    state["pending_semantic_item_name"] = item_name
    state["pending_semantic_issue_type"] = issue_type
    state["pending_semantic_fault"] = fault
    state["pending_semantic_prep_anomaly"] = prep_anomaly
    state["pending_semantic_message"] = message
    state["pending_semantic_reason"] = reason
    state["desired_resolution"] = None


def confirm_semantic_clarification(
    state: MutableMapping[str, Any],
    *,
    item_name: str,
    issue_type: str,
    prep_anomaly: bool,
) -> None:
    clear_resolution(state)
    state["issue_type"] = issue_type
    state["case_issue_type"] = issue_type
    state["conversation_mode"] = MODE_ACTIVE_COMPLAINT
    state["active_item_name"] = item_name
    state["prep_anomaly"] = prep_anomaly


def set_conversation_mode_for_issue(state: MutableMapping[str, Any], issue_type: str, prior_case_issue_type: Optional[str]) -> None:
    if issue_type == "info_query" and (not prior_case_issue_type or prior_case_issue_type == "info_query"):
        state["conversation_mode"] = MODE_INFO_ONLY
    elif issue_type != "info_query":
        state["conversation_mode"] = MODE_ACTIVE_COMPLAINT


def force_delay_resolution_to_coupon(state: MutableMapping[str, Any]) -> None:
    state["desired_resolution"] = ACTION_COUPON
    state["economic_preference"] = ACTION_COUPON


def mark_refund_approved(state: MutableMapping[str, Any]) -> None:
    state["pending"] = None
    state["last_action"] = ACTION_REFUND


def mark_replacement_approved(state: MutableMapping[str, Any], item_name: str) -> None:
    state["pending"] = None
    state["last_action"] = ACTION_REPLACEMENT
    state["last_item_name"] = item_name
    state["approved_replacement_item_name"] = item_name
    state["approved_replacement_status"] = APPROVED_REPLACEMENT


def request_refund_review_after_replacement(state: MutableMapping[str, Any]) -> None:
    clear_resolution(state)
    state["approved_replacement_status"] = CANCEL_REQUESTED_FOR_REFUND_REVIEW
    state["replacement_change_requested"] = ACTION_REFUND


def mark_escalated(state: MutableMapping[str, Any], *, mode: Optional[str] = None) -> None:
    clear_resolution(state)
    state["last_action"] = ACTION_ESCALATE
    if mode:
        state["conversation_mode"] = mode


def mark_review_repeat(state: MutableMapping[str, Any]) -> int:
    clear_pending(state)
    state["conversation_mode"] = MODE_REVIEW
    state["escalation_repeat_count"] = int(state.get("escalation_repeat_count") or 0) + 1
    return int(state["escalation_repeat_count"])


def mark_user_resolved(state: MutableMapping[str, Any], *, issue_type: str) -> None:
    clear_resolution(state)
    state["case_resolved_by_user"] = True
    state["conversation_mode"] = MODE_RESOLVED
    state["issue_type"] = issue_type
    state["case_issue_type"] = issue_type


def preserve_resolved_case_context(state: MutableMapping[str, Any], *, issue_type: str) -> int:
    state["conversation_mode"] = MODE_RESOLVED
    state["issue_type"] = issue_type
    state["case_issue_type"] = issue_type
    state["resolved_repeat_count"] = int(state.get("resolved_repeat_count") or 0) + 1
    return int(state["resolved_repeat_count"])


def mark_terminal_action(state: MutableMapping[str, Any], action: str, item_name: str) -> None:
    if action not in {ACTION_COUPON, ACTION_CREDIT, ACTION_REFUND, ACTION_REPLACEMENT, ACTION_ESCALATE}:
        return
    state["last_action"] = action
    if action == ACTION_REPLACEMENT:
        state["last_item_name"] = item_name
        state["approved_replacement_item_name"] = item_name
        state["approved_replacement_status"] = APPROVED_REPLACEMENT
