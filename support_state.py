import hashlib
import re
import time
from typing import Any, Optional


def _lower(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(part or "") for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def _find_item(order_items: dict, item_name: Optional[str]) -> dict:
    if not isinstance(order_items, dict) or not item_name:
        return {}
    target = _lower(item_name)
    for item in order_items.get("items", []):
        name = _lower(item.get("name"))
        if target and (target == name or target in name or name in target):
            return item
    return {}


def _risk_tier(issue_type: str, issue_severity: str, order_value: float, trust_score: float, evidence_status: str) -> str:
    if trust_score <= 40 or order_value >= 900:
        return "high"
    if issue_type == "foreign_object" and issue_severity == "high":
        return "high"
    if issue_severity == "high" or order_value >= 500:
        return "medium" if evidence_status == "strong" else "high"
    return "low"


def _owner_area(issue_type: str, fault: str) -> str:
    if issue_type in {"wrong_item", "missing_item", "foreign_object", "portion_size", "quality"}:
        return "kitchen"
    if issue_type in {"spill_leak", "damaged"}:
        return "delivery" if fault == "delivery" else "packing"
    if issue_type in {"delay", "temperature"}:
        return "delivery" if fault == "delivery" else "kitchen"
    return "support"


def _max_auto_compensation(risk_tier: str, item_value: float, order_value: float, evidence_status: str) -> float:
    base = item_value if item_value > 0 else order_value
    if base <= 0:
        return 0.0
    if risk_tier == "high":
        return float(min(base, order_value))
    if evidence_status == "strong":
        return float(min(base, 250))
    return float(max(30, min(100, round(base * 0.3))))


def build_case_state(
    *,
    user_id: str,
    order_id: str,
    session_id: str,
    complaint: str,
    order_details: dict,
    order_items: dict,
    kitchen: dict,
    fleet: dict,
    trust: dict,
    assessment: dict,
    resolution_debug: dict,
) -> dict:
    item_name = (
        resolution_debug.get("active_item_name")
        or assessment.get("active_item_name")
        or "item"
    )
    item = _find_item(order_items, item_name)
    item_value = float(item.get("price") or 0.0)
    order_value = float(order_details.get("total_amount") or resolution_debug.get("order_value") or 0.0)
    issue_type = resolution_debug.get("issue_type") or assessment.get("issue_type") or "other"
    issue_severity = resolution_debug.get("issue_severity") or assessment.get("issue_severity") or "medium"
    evidence_status = resolution_debug.get("evidence_strength") or "weak"
    trust_score = float(trust.get("score", 50))
    fault = resolution_debug.get("fault") or assessment.get("fault_hint") or "unclear"
    risk_tier = _risk_tier(issue_type, issue_severity, order_value, trust_score, evidence_status)
    replacement_cost = item_value + 70 if item_value > 0 else order_value

    return {
        "case_id": _stable_id("case", session_id, order_id, item_name, issue_type),
        "user_id": user_id,
        "order_id": order_id,
        "session_id": session_id,
        "selected_item": item_name,
        "selected_issue_bucket": assessment.get("issue_type") or issue_type,
        "final_issue_type": issue_type,
        "evidence_status": evidence_status,
        "desired_resolution": resolution_debug.get("requested_resolution") or "none",
        "risk_tier": risk_tier,
        "item_value": item_value,
        "order_value": order_value,
        "customer_claim_history": {
            "trust_score": trust_score,
            "refund_requests": int(trust.get("refund_requests") or 0),
            "total_orders": int(trust.get("total_orders") or 0),
        },
        "ops_context": {
            "owner_area": _owner_area(issue_type, fault),
            "fault_hint": fault,
            "kitchen_status": kitchen.get("status"),
            "quality_out": kitchen.get("quality_out"),
            "fleet_delay_mins": fleet.get("delay_mins"),
            "restaurant_name": order_details.get("restaurant_name"),
        },
        "replacement_feasible": bool(item_name != "item" and replacement_cost <= max(order_value, 320)),
        "estimated_replacement_cost": float(replacement_cost),
        "max_auto_compensation": _max_auto_compensation(risk_tier, item_value, order_value, evidence_status),
        "latest_customer_text": complaint,
    }


def action_lifecycle(action: str, amount: float, case_state: dict) -> Optional[dict]:
    if action not in {"coupon", "credit", "refund", "replacement"}:
        return None
    reference_id = _stable_id(action, case_state.get("case_id"), int(time.time() // 60))
    if action == "refund":
        eta = "Refund approval is recorded. Processing status should be tracked by the payout layer."
    elif action == "replacement":
        eta = "Replacement approval is recorded. Dispatch status should be tracked by the fulfillment layer."
    else:
        eta = "Coupon approval is recorded. Redemption status should be tracked by the rewards layer."
    return {
        "reference_id": reference_id,
        "action": action,
        "amount": float(amount or 0.0),
        "status": "approved_pending_execution",
        "next_status_owner": "payout" if action in {"refund", "coupon", "credit"} else "fulfillment",
        "customer_status_note": eta,
    }


def ops_incident(action: str, case_state: dict) -> Optional[dict]:
    issue_type = case_state.get("final_issue_type")
    if issue_type in {None, "info_query", "other"} and action == "info":
        return None
    if action == "info" and case_state.get("evidence_status") == "weak":
        return None
    owner = case_state.get("ops_context", {}).get("owner_area") or "support"
    return {
        "incident_id": _stable_id("inc", case_state.get("case_id"), owner),
        "status": "open",
        "owner_area": owner,
        "issue_type": issue_type,
        "risk_tier": case_state.get("risk_tier"),
        "item": case_state.get("selected_item"),
        "order_id": case_state.get("order_id"),
    }


def support_ticket(action: str, reason: str, case_state: dict) -> Optional[dict]:
    if action != "escalate":
        return None
    priority = "high" if case_state.get("risk_tier") == "high" else "normal"
    return {
        "ticket_id": _stable_id("ticket", case_state.get("case_id"), reason),
        "status": "open",
        "priority": priority,
        "response_sla": "within 4 hours" if priority == "high" else "within 24 hours",
        "reason": reason,
    }


def style_warnings(message: str) -> list[str]:
    lowered = _lower(message)
    warnings = []
    patterns = {
        "llm_like": ["as an ai", "i understand your concern", "i completely understand"],
        "policy_like": ["as per policy", "policy says", "eligible only"],
        "internal_leak": ["approved action", "approved amount", "margin", "company loss"],
        "false_followup": ["i will check", "i'll check", "team will review", "i'll call"],
    }
    for label, phrases in patterns.items():
        if any(phrase in lowered for phrase in phrases):
            warnings.append(label)
    sentences = [part for part in re.split(r"(?<=[.!?])\s+", message.strip()) if part]
    if len(sentences) > 3:
        warnings.append("too_long")
    return warnings


def attach_artifacts(state: dict, resolution: dict, case_state: dict) -> dict:
    warnings = style_warnings(resolution.get("message", ""))
    if resolution.get("reason") == "LLM semantic guard requested clarification":
        if warnings:
            resolution["style_warnings"] = warnings
        return resolution

    lifecycle = action_lifecycle(resolution.get("action"), float(resolution.get("amount") or 0.0), case_state)
    incident = None if _is_status_only_reason(resolution.get("reason", "")) else ops_incident(resolution.get("action"), case_state)
    ticket = support_ticket(resolution.get("action"), resolution.get("reason", ""), case_state)

    state["case_state"] = case_state
    if lifecycle:
        state.setdefault("action_lifecycles", []).append(lifecycle)
        state["action_lifecycles"] = state["action_lifecycles"][-10:]
        resolution["action_status"] = lifecycle
    if incident:
        state.setdefault("ops_incidents", []).append(incident)
        state["ops_incidents"] = state["ops_incidents"][-10:]
        resolution["ops_incident"] = incident
    if ticket:
        state.setdefault("support_tickets", []).append(ticket)
        state["support_tickets"] = state["support_tickets"][-10:]
        resolution["support_ticket"] = ticket
    if warnings:
        resolution["style_warnings"] = warnings
    resolution["case_state"] = {
        key: case_state.get(key)
        for key in [
            "case_id",
            "selected_item",
            "final_issue_type",
            "evidence_status",
            "desired_resolution",
            "risk_tier",
            "max_auto_compensation",
            "replacement_feasible",
        ]
    }
    return resolution


def _is_status_only_reason(reason: str) -> bool:
    return reason in {
        "Replacement already approved",
        "User asked for active complaint status",
        "User asked for approved replacement status",
        "User asked for order information during an active resolution flow",
        "User asked for order information, not a complaint resolution",
    }
