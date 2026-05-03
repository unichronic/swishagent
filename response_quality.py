import re
from typing import Any, Optional

from support_state import style_warnings


VALID_ACTIONS = {"info", "coupon", "credit", "refund", "replacement", "escalate", "live_capture"}
COMPENSATION_WORDS = ("refund", "coupon", "credit", "wallet", "replacement", "remake", "fresh")
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


def _lower(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", _lower(value))


def _sentences(message: str) -> list[str]:
    return [part for part in re.split(r"(?<=[.!?])\s+", message.strip()) if part]


def _money_values(text: str) -> list[float]:
    values = []
    for match in re.findall(r"₹\s*(\d+(?:\.\d+)?)", text):
        try:
            values.append(float(match))
        except ValueError:
            pass
    return values


def _order_item_names(order_items: Optional[dict]) -> list[str]:
    if not isinstance(order_items, dict):
        return []
    names = []
    for item in order_items.get("items", []):
        name = str(item.get("name", "")).strip()
        if name:
            names.append(name)
    return names


def _mentions_item(message: str, item_name: str) -> bool:
    message_lower = _lower(message)
    item_lower = _lower(item_name)
    if not item_lower:
        return False
    if item_lower in message_lower:
        return True
    tokens = [token for token in re.findall(r"[a-z0-9]+", item_lower) if len(token) >= 4]
    return any(token in message_lower for token in tokens)


def _mentioned_order_items(message: str, order_items: Optional[dict]) -> list[str]:
    return [name for name in _order_item_names(order_items) if _mentions_item(message, name)]


def _complaint_components(complaint: str) -> set[str]:
    complaint_lower = _lower(complaint)
    return {term for term in COMPONENT_TERMS if re.search(rf"\b{re.escape(term)}\b", complaint_lower)}


def _message_has_quantity_language(message: str) -> bool:
    lowered = _lower(message)
    return any(term in lowered for term in ("quantity", "portion", "less", "low", "short", "enough", "missing"))


def _action_message_errors(action: str, amount: float, message: str) -> list[str]:
    lowered = _lower(message)
    errors = []
    if action not in VALID_ACTIONS:
        errors.append(f"invalid_action:{action}")
    if action == "live_capture" and not any(term in lowered for term in ("photo", "video", "camera", "capture", "upload", "send")):
        errors.append("live_capture_without_capture_instruction")
    if action == "live_capture" and "photo attached" in lowered:
        errors.append("live_capture_claims_photo_already_attached")
    if action == "refund" and "refund" not in lowered:
        errors.append("refund_action_without_refund_copy")
    if action in {"coupon", "credit"} and action not in lowered:
        errors.append(f"{action}_action_without_{action}_copy")
    if action == "replacement" and not any(term in lowered for term in ("replacement", "fresh", "remade", "remake")):
        errors.append("replacement_action_without_replacement_copy")
    if action == "escalate" and not any(term in lowered for term in ("review", "email", "manual", "take it further", "can't", "cannot")):
        errors.append("escalation_without_review_copy")
    if action in {"refund", "coupon", "credit"} and amount > 0:
        amounts = _money_values(message)
        if not amounts or not any(abs(value - amount) < 0.01 for value in amounts):
            errors.append("approved_amount_missing_or_changed")
    if action == "info":
        approval_patterns = (
            r"\bapproved\b.{0,25}\b(refund|coupon|credit|replacement|remake)\b",
            r"\b(refund|coupon|credit|replacement|remake)\b.{0,25}\bapproved\b",
            r"\badded\b.{0,20}\b(coupon|credit|refund)\b",
        )
        if any(re.search(pattern, lowered) for pattern in approval_patterns):
            errors.append("info_message_claims_compensation_approved")
    if action not in {"refund"} and "full refund" in lowered:
        errors.append("non_refund_message_promises_full_refund")
    return errors


def _semantic_errors(
    *,
    message: str,
    complaint: str,
    issue_type: str,
    expected_item_name: str,
    order_items: Optional[dict],
    reason: str,
) -> list[str]:
    lowered = _lower(message)
    errors = []
    if issue_type == "portion_size":
        components = _complaint_components(complaint)
        if components and any(phrase in lowered for phrase in ("bowl was small", "bowl is small", "small bowl", "too small", "too light", "light for")):
            errors.append("portion_component_reframed_as_whole_item_size")
        if components and not _message_has_quantity_language(message) and "which item" not in lowered:
            errors.append("portion_reply_dropped_quantity_scope")
    if issue_type == "spill_leak" and any(term in lowered for term in ("taste", "quality issue")) and not any(term in lowered for term in ("spill", "leak")):
        errors.append("spill_reply_drifted_to_quality")
    if issue_type == "delay" and any(term in lowered for term in ("fresh item", "replacement")) and "delay" not in lowered:
        errors.append("delay_reply_drifted_to_replacement")
    if issue_type == "info_query" and any(term in lowered for term in ("quality issue", "food issue", "refund approved")):
        errors.append("info_query_reply_drifted_to_complaint")
    if issue_type == "quality" and "wrong item was packed" in lowered:
        errors.append("quality_reply_drifted_to_wrong_item")
    if any(term in lowered for term in ("you're right", "you are right", "definitely")) and "can't verify" in lowered:
        errors.append("reply_mixes_certainty_and_uncertainty")
    mentioned_items = _mentioned_order_items(message, order_items)
    if expected_item_name and mentioned_items and reason != "LLM semantic guard requested clarification":
        unexpected = [name for name in mentioned_items if _lower(name) != _lower(expected_item_name)]
        if unexpected and not _mentions_item(message, expected_item_name):
            errors.append(f"message_mentions_wrong_order_item:{unexpected[0]}")
    return errors


def _conversation_errors(message: str, previous_messages: Optional[list[str]]) -> list[str]:
    if not previous_messages:
        return []
    normalized = _normalize(message)
    previous = [_normalize(item) for item in previous_messages if item]
    errors = []
    if normalized and previous.count(normalized) >= 1:
        errors.append("exact_message_repeated")
    review_repeats = sum(1 for item in previous if "email hello@justswish.in" in item)
    if "email hello@justswish.in" in normalized and review_repeats >= 2:
        errors.append("review_email_repeated_too_often")
    return errors


def evaluate_response_quality(
    response: dict[str, Any],
    *,
    complaint: str = "",
    order_items: Optional[dict] = None,
    expected_issue_type: str = "",
    expected_item_name: str = "",
    previous_messages: Optional[list[str]] = None,
) -> list[str]:
    message = str(response.get("message") or "")
    action = str(response.get("action") or "")
    amount = float(response.get("amount") or 0.0)
    reason = str(response.get("reason") or "")
    debug = response.get("_debug") or {}
    case_state = response.get("case_state") or {}
    issue_type = expected_issue_type or debug.get("issue_type") or case_state.get("final_issue_type") or ""
    item_name = expected_item_name or debug.get("active_item_name") or case_state.get("selected_item") or ""
    errors = []
    if not message.strip():
        errors.append("empty_message")
        return errors
    errors.extend(f"style:{warning}" for warning in style_warnings(message))
    if len(message) > 360:
        errors.append("message_too_long")
    if len(_sentences(message)) > 3:
        errors.append("too_many_sentences")
    if message.count("₹") > 2:
        errors.append("too_many_amounts")
    lowered = _lower(message)
    if any(term in lowered for term in ("approved action", "approved amount", "company loss", "margin")):
        errors.append("internal_policy_leak")
    max_auto = case_state.get("max_auto_compensation")
    if action in {"refund", "coupon", "credit"} and max_auto is not None and amount > float(max_auto) + 0.01:
        errors.append("amount_exceeds_case_max_auto_compensation")
    errors.extend(_action_message_errors(action, amount, message))
    errors.extend(
        _semantic_errors(
            message=message,
            complaint=complaint,
            issue_type=str(issue_type),
            expected_item_name=str(item_name or ""),
            order_items=order_items,
            reason=reason,
        )
    )
    errors.extend(_conversation_errors(message, previous_messages))
    return errors
