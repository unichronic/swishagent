"""
Deterministic Swish support agent service.

The model should not choose policy. We gather order evidence, resolve the next
allowed action in code, and return a short human-sounding message.
"""

import json
import logging
import os
import re
import time
from contextlib import ExitStack
from typing import Optional

from fastapi import FastAPI, Request
from pydantic import BaseModel

from llm_client import call_text
from rules import Rules, get_session, clear_session, get_session_state, mark_photo_provided, session_has_photo
from support_state import attach_artifacts, build_case_state
from tracing import langfuse_attributes, langfuse_observation, new_request_id, trace_event
from tools import (
    analyze_photo,
    check_fleet_status,
    check_kitchen_log,
    get_delivery_info,
    get_order_details,
    get_order_items,
    get_trust_score,
)

app = FastAPI()
logger = logging.getLogger("swish.agent_service")
INCLUDE_ASSESSMENT_DEBUG = os.getenv("AGENT_DEBUG_INCLUDE_ASSESSMENT", "0") == "1"

VALID_ACTIONS = {"info", "coupon", "credit", "refund", "replacement", "escalate", "live_capture"}


class Resolution(BaseModel):
    action: str
    amount: float
    message: str
    reason: str


class RunRequest(BaseModel):
    user_id: str
    order_id: str
    conversation_id: Optional[str] = None
    complaint: str
    photo_url: Optional[str] = None
    order_value: float = 0.0


def _extract_json_object(text: str) -> dict:
    if not text:
        return {}
    start = text.find("{")
    if start == -1:
        return {}
    depth = 0
    end = -1
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end == -1:
        return {}
    try:
        return json.loads(text[start:end])
    except Exception:
        return {}


def _call_text_with_trace(messages: list, **kwargs) -> str:
    try:
        return call_text(messages, **kwargs)
    except TypeError as exc:
        if "unexpected keyword argument" not in str(exc):
            raise
        fallback_kwargs = {
            key: value
            for key, value in kwargs.items()
            if key not in {"trace_name", "trace_metadata"}
        }
        return call_text(messages, **fallback_kwargs)


def _assess_case(
    complaint: str,
    history: list,
    order_details: dict,
    order_items: dict,
    kitchen: dict,
    fleet: dict,
    trust: dict,
) -> tuple[dict, dict]:
    item_names = [item.get("name", "item") for item in order_items.get("items", [])[:8]] if isinstance(order_items, dict) else []
    recent_history = history[-6:]
    messages = [
        {
            "role": "system",
            "content": (
                "You are a support case analyst. Read the conversation and order evidence, then return JSON only. "
                "Do not decide payouts. Classify the user's latest message. "
                "The customer may use typos, merged words, slang, shorthand, or broken grammar. Infer the intended meaning, not the literal spelling. "
                "Treat typo-heavy or broken customer text as normal support chat and classify what they likely mean. "
                "Use only these enums: "
                'issue_type=["quality","temperature","delay","wrong_item","missing_item","damaged","spill_leak","foreign_object","portion_size","info_query","other"], '
                'requested_resolution=["none","refund","replacement","coupon","credit"], '
                'info_query=["none","items","total","status"], '
                'issue_severity=["low","medium","high"], '
                'dietary_severity=["none","low","medium","high"], '
                'fault_hint=["kitchen","delivery","unclear"], '
                'dietary_direction=["none","nonveg_in_veg","veg_in_nonveg","allergen","unknown"], '
                'resolution_change=["none","refund_after_replacement","replacement_after_refund","refund_after_coupon","replacement_after_coupon"], '
                'economic_preference=["coupon","refund","replacement","escalate"], '
                'tone_guardrail=["neutral","sensitive","persuasive","operational"], '
                'negotiation_strength=["none","light","medium"], '
                'turn_act=["none","confirm","reject","switch_resolution","ask_status","ask_cause","clarify"], '
                'recommended_next_step=["explain","clarify","coupon","refund","replacement","live_capture","escalate"]. '
                "If the user is asking whether the replacement will be correct this time, set assurance_query=true. "
                "Set visual_evidence_useful=true only if a photo or live capture would materially help verify the complaint. "
                "Issue-type guidance: "
                "use quality for taste, texture, stale, undercooked, overcooked, burnt, soggy food, too dry, too spicy, too salty, too sweet, bland, or generally poor quality complaints unless the complaint is clearly about leaked contents or physical damage. "
                "Use temperature for hot items arriving cold or not hot enough, and cold items arriving warm or not cold enough. "
                "Use delay for late delivery, ETA, where-is-my-order, or running-behind complaints. "
                "Use wrong_item for got-something-else or not-what-I-ordered complaints. "
                "Use missing_item for left-out or part-of-the-order-missing complaints. "
                "Use damaged for crushed, broken, torn, smashed, or damaged packaging/item complaints when the contents are not clearly described as leaked or spilled out. "
                "Use spill_leak for leaking, spilled, burst-open, opened-and-spilled, or contents-coming-out complaints. "
                "Use foreign_object for hair, plastic, glass, stone, insect, or non-veg-in-veg contamination complaints. "
                "Use portion_size for too little, too small, skimpy, light-for-the-price, less quantity, or under-portioned complaints. "
                "Semantic safety guidance: set selected_item_conflict=true when the structured/picked item or prior item conflicts with the item the customer is actually describing. "
                "If selected_item_conflict=true, set mentioned_item_name to the closest order item the customer appears to mean and recommended_next_step=clarify unless the customer clearly corrected the item. "
                "Set semantic_risk=true when common sense says the deterministic flow may act on the wrong item, wrong issue, wrong category, or unsafe dietary interpretation. Set semantic_confidence from 0 to 1. "
                "Set dietary_direction explicitly: nonveg_in_veg for meat/egg/chicken in veg/vegetarian food; veg_in_nonveg for plant/vegetable in meat/non-veg food; allergen for allergy/allergen risk; none otherwise. "
                "Dietary asymmetry: non-veg in veg/vegetarian food is high dietary_severity and foreign_object/sensitive; vegetable/veg in non-veg food is usually low dietary_severity and quality/prep mix-up unless the customer mentions allergy, religion, or a strict dietary restriction that makes it serious. "
                "Visual-evidence guidance: usually true for wrong_item, missing_item in multi-item orders, damaged, spill_leak, and foreign_object; usually false for quality, temperature, delay, and portion_size. "
                "Set issue_confidence, requested_resolution_confidence, turn_act_confidence, and info_query_confidence as numbers from 0 to 1. "
                "Set fault_hint based on what the evidence most plausibly suggests, but use unclear if the evidence does not support a confident cause. "
                "Swish controls the kitchen, dispatch, and delivery leg, so choose the fix that addresses the actual miss without wasting margin. "
                "Set economic_preference based on the lowest-cost meaningful resolution given the complaint, evidence, order value, item value, and remake practicality. "
                "Prefer coupon when the case is weak, goodwill can reasonably close the issue, or the user asks for a remake/refund without enough proof. "
                "Prefer replacement when Swish can realistically remake the affected item and that is more useful to the customer than a cash refund. "
                "Prefer refund only when the item/order failure is clear, replacement is not the right fix, or the complaint is serious enough that cash back is the fair resolution. "
                "Set turn_act to describe what the user is doing in this turn: confirming, rejecting, switching what they want, asking status, or asking cause. "
                "Set resolution_change when the customer asks to change an already active resolution, for example refund_after_replacement when they ask for refund after replacement was approved. "
                "Set recommended_next_step to the most sensible immediate support move, but do not assume you can override policy. Use clarify when the latest user turn is too ambiguous to act on safely. "
                "Set economic_confidence as a number from 0 to 1. "
                "Set tone_guardrail to the safest conversational mode for the next reply: "
                "sensitive for safety, contamination, dietary, or more serious complaint handling; "
                "persuasive when a coupon-first negotiation is appropriate; "
                "neutral for ordinary explanation turns; "
                "operational for direct confirmation or status replies. "
                "Set negotiation_strength to none, light, or medium. Use none when the reply should not negotiate. Use light for sensitive serious complaints. Use medium for ordinary coupon-first objection handling. "
                "Set negotiation_allowed=true only when the next reply should actively persuade the customer toward the offered option. "
                "If an item is clearly referenced, set active_item_name to one of the order item names exactly. "
                "If you are not confident about issue_type, requested_resolution, turn_act, or info_query, use the safest enum value and low confidence instead of guessing. "
                "Examples:\n"
                '1. Latest message: "food ws cold n late" -> {"issue_type":"temperature","requested_resolution":"none","turn_act":"none","recommended_next_step":"explain"}\n'
                '2. Latest message: "fine then refund it" while coupon was offered -> {"requested_resolution":"refund","turn_act":"switch_resolution","recommended_next_step":"coupon"}\n'
                '3. Latest message: "it was off" with no clear ask -> {"issue_type":"other","requested_resolution":"none","turn_act":"clarify","recommended_next_step":"clarify"}'
            ),
        },
        {
            "role": "user",
            "content": (
                f"Latest customer message: {complaint}\n"
                f"Recent conversation: {recent_history}\n"
                f"Order items: {item_names}\n"
                f"Order details: {order_details}\n"
                f"Kitchen: {kitchen}\n"
                f"Fleet: {fleet}\n"
                f"Trust: {trust}\n"
                "If the text is messy, first mentally normalize what the customer probably meant, then classify it.\n"
                'Return JSON only with keys: issue_type, issue_confidence, requested_resolution, requested_resolution_confidence, info_query, info_query_confidence, assurance_query, turn_act, turn_act_confidence, issue_severity, active_item_name, selected_item_conflict, mentioned_item_name, semantic_risk, semantic_confidence, semantic_risk_reason, dietary_severity, dietary_direction, visual_evidence_useful, fault_hint, recommended_next_step, clarification_needed, resolution_change, economic_preference, economic_confidence, tone_guardrail, negotiation_allowed, negotiation_strength, notes.'
            ),
        },
    ]
    try:
        raw = _call_text_with_trace(
            messages,
            temperature=0.1,
            trace_name="llm.assess_case",
            trace_metadata={"component": "assessment"},
        )
        assessment = _extract_json_object(raw)
        if assessment:
            return assessment, {"status": "ok", "raw_preview": raw[:200]}
        return {}, {"status": "invalid_json", "raw_preview": raw[:200]}
    except Exception as exc:
        return {}, {"status": "error", "error": str(exc)}


def _can_skip_assessment(complaint: str, session_id: str, has_photo: bool) -> tuple[bool, str]:
    if has_photo:
        return False, "photo_turn"
    state = get_session_state(session_id)
    if not state:
        return False, "new_session"
    text = complaint.strip().lower()
    if not text:
        return False, "empty"
    current_issue = state.get("case_issue_type") or state.get("issue_type") or "other"
    if Rules._has_strong_new_issue_signal(text, current_issue):
        return False, "new_issue_signal"

    deterministic_pending = state.get("pending") in {"coupon", "refund_amount", "replacement_confirm", "photo"}
    terminal_or_review = state.get("last_action") in {"escalate", "refund", "replacement", "coupon"} or state.get("case_resolved_by_user")
    followup = (
        Rules._is_followup_or_evidence_turn(text)
        or Rules._is_case_scope_or_support_pressure_turn(text)
        or Rules._is_generic_info_followup(text)
        or Rules._is_resolution_only_turn(text)
        or Rules._detect_requested_resolution(text, state) != "none"
    )
    if deterministic_pending and followup:
        return True, "pending_followup"
    if terminal_or_review and followup:
        return True, "terminal_followup"
    if state.get("conversation_mode") in {"active_complaint", "review", "resolved"} and followup:
        return True, "active_case_followup"
    return False, "needs_assessment"


def _fetch_with_trace(request_id: str, name: str, fn, *args) -> dict:
    started = time.perf_counter()
    try:
        with langfuse_observation(
            f"dependency.{name}",
            input={"dependency": name, "args": [str(arg) for arg in args]},
            metadata={"request_id": request_id},
        ) as observation:
            payload = fn(*args)
            observation.update(
                output={
                    "degraded": bool(isinstance(payload, dict) and payload.get("degraded")),
                    "keys": sorted(payload.keys()) if isinstance(payload, dict) else None,
                }
            )
        trace_event(
            logger,
            "dependency_fetch",
            request_id=request_id,
            dependency=name,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            degraded=bool(isinstance(payload, dict) and payload.get("degraded")),
        )
        return payload
    except Exception as exc:
        trace_event(
            logger,
            "dependency_fetch_failed",
            request_id=request_id,
            dependency=name,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            error=str(exc),
        )
        raise


def _humanize_message(
    resolution: dict,
    complaint: str,
    order_items: dict,
    history: list,
) -> dict:
    original = resolution.get("message", "")
    if resolution.get("action") in {"replacement", "refund", "live_capture"}:
        return resolution
    allowed_reasons = {
        "No explicit compensation request",
        "Offer coupon before refund or replacement",
        "Reinforcing coupon because replacement cannot be verified cleanly",
        "Coupon rejected, asking to confirm replacement",
        "Steering refund request toward replacement",
        "Refund blocked for high-value low-trust case",
        "Refund request steered back to replacement for economic reasons",
        "Need clarification on coupon decision",
    }
    if resolution.get("reason") not in allowed_reasons:
        return resolution
    item_names = [item.get("name", "item") for item in order_items.get("items", [])[:4]] if isinstance(order_items, dict) else []
    last_bot = next((msg.get("content", "") for msg in reversed(history[:-1]) if msg.get("role") == "bot"), "")
    messages = [
        {
            "role": "system",
            "content": (
                "Rewrite support messages to sound like a real human support agent in chat, not like a model or a policy script. "
                "Keep the exact action, item, amount, and outcome unchanged. "
                "Use a calm objection-handling style: brief acknowledgment, plain reason, one practical option, direct close. "
                "When the original is negotiating toward a coupon or remake, keep that negotiation gentle and specific. "
                "Do not add policy, promises, apologies beyond one brief acknowledgment, or new facts. "
                "Do not repeat or lightly paraphrase the customer's complaint back to them. "
                "Show you understood it without mirroring their exact wording. "
                "Do not use em dashes. Do not sound polished, poetic, or salesy. "
                "Use plain English only. No Hindi or Hinglish. Short, direct, natural. "
                "Do not start with 'Got it' unless the original already does. "
                "Do not say 'should help', 'on the way', 'I asked the kitchen', 'I'll pass this to the team', or anything stronger than the original. "
                "Do not mention internal economics, policy, margin, or company loss. "
                "Do not add product intent or product-sizing claims such as saying an item is meant to be small, snack-sized, standard, or expected. "
                "Do not invent review steps, quality checks, or customer next actions unless the original already says them. "
                'Reply in JSON only as {"message":"..."} and keep it to max 2 sentences.'
            ),
        },
        {
            "role": "user",
            "content": (
                f"Customer said: {complaint}\n"
                f"Recent bot message: {last_bot}\n"
                f"Items in order: {', '.join(item_names)}\n"
                f"Original message: {original}\n"
                "Rewrite:"
            ),
        },
    ]
    try:
        rewritten = _call_text_with_trace(
            messages,
            temperature=0.5,
            trace_name="llm.humanize_message",
            trace_metadata={"component": "humanize", "approved_action": resolution.get("action")},
        ).strip()
        parsed = _extract_json_object(rewritten)
        if not parsed:
            return resolution
        candidate = parsed.get("message")
        if candidate:
            if _humanizer_changed_meaning(candidate, original, complaint, resolution, order_items):
                return resolution
            resolution["message"] = Rules._enforce_content({"message": candidate}).get("message", original)
    except Exception:
        pass
    return resolution


def _humanizer_changed_meaning(
    candidate: str,
    original: str,
    complaint: str,
    resolution: dict,
    order_items: dict,
) -> bool:
    if _humanizer_added_new_claims(candidate, original):
        return True
    if _humanizer_dropped_required_terms(candidate, original, complaint, resolution, order_items):
        return True
    if _humanizer_weakened_uncertainty(candidate, original):
        return True
    return False


def _humanizer_added_new_claims(candidate: str, original: str) -> bool:
    candidate_lower = candidate.lower()
    original_lower = original.lower()
    forbidden_patterns = [
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
    ]
    if any(pattern in candidate_lower and pattern not in original_lower for pattern in forbidden_patterns):
        return True
    resolution_terms = ["refund", "remake", "replacement", "replace", "fresh", "send it", "send a new"]
    if any(term in candidate_lower and term not in original_lower for term in resolution_terms):
        return True
    if ("₹" in candidate or "%" in candidate_lower or "coupon" in candidate_lower or "credit" in candidate_lower) and not (
        "₹" in original or "%" in original_lower or "coupon" in original_lower or "credit" in original_lower
    ):
        return True
    for amount in re.findall(r"₹\s*\d+", original):
        if amount.replace(" ", "") not in candidate.replace(" ", ""):
            return True
    if "coupon" in original_lower and "coupon" not in candidate_lower:
        return True
    return False


def _humanizer_dropped_required_terms(
    candidate: str,
    original: str,
    complaint: str,
    resolution: dict,
    order_items: dict,
) -> bool:
    candidate_lower = candidate.lower()
    original_lower = original.lower()
    complaint_lower = complaint.lower()
    debug = resolution.get("_debug") or {}
    issue_type = debug.get("issue_type")

    item_terms = _meaningful_item_terms(order_items)
    original_item_terms = {term for term in item_terms if term in original_lower}
    if original_item_terms and not any(term in candidate_lower for term in original_item_terms):
        return True

    component_terms = {
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
    }
    complaint_components = {term for term in component_terms if re.search(rf"\b{re.escape(term)}\b", complaint_lower)}
    original_components = {term for term in component_terms if re.search(rf"\b{re.escape(term)}\b", original_lower)}
    required_components = complaint_components & original_components
    if required_components and not any(re.search(rf"\b{re.escape(term)}\b", candidate_lower) for term in required_components):
        return True

    if issue_type == "portion_size" or "quantity" in original_lower or "portion" in original_lower:
        if required_components and not any(term in candidate_lower for term in ["quantity", "portion", "less", "low", "short", "enough"]):
            return True
        whole_item_reframes = [
            "bowl was small",
            "bowl is small",
            "too light",
            "light for",
            "too small",
            "small bowl",
            "small portion",
        ]
        if required_components and any(phrase in candidate_lower for phrase in whole_item_reframes):
            return True

    issue_terms = {
        "spill_leak": ["spill", "spilled", "leak", "leaked"],
        "wrong_item": ["wrong item", "different item"],
        "missing_item": ["missing", "not made it", "left out"],
        "delay": ["delay", "late", "behind"],
    }
    for term in issue_terms.get(issue_type, []):
        if term in original_lower and term not in candidate_lower:
            return True
    return False


def _meaningful_item_terms(order_items: dict) -> set[str]:
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


def _humanizer_weakened_uncertainty(candidate: str, original: str) -> bool:
    candidate_lower = candidate.lower()
    original_lower = original.lower()
    uncertainty_markers = [
        "can't verify",
        "cannot verify",
        "can't confirm",
        "cannot confirm",
        "don't prove",
        "doesn't prove",
        "don't cleanly show",
        "doesn't cleanly show",
        "not clearly",
        "not cleanly",
    ]
    if any(marker in original_lower for marker in uncertainty_markers):
        candidate_kept_uncertainty = any(
            marker in candidate_lower
            for marker in [
                "can't verify",
                "cannot verify",
                "can't confirm",
                "cannot confirm",
                "don't have enough",
                "do not have enough",
                "doesn't prove",
                "don't prove",
                "not clear",
                "not cleanly",
                "can't tell",
                "cannot tell",
            ]
        )
        if not candidate_kept_uncertainty:
            return True
    certainty_upgrades = [
        "i can see",
        "i confirmed",
        "clearly",
        "definitely",
        "you are right",
        "you're right",
        "was too small",
        "was not enough",
    ]
    if any(marker in original_lower for marker in uncertainty_markers):
        if any(phrase in candidate_lower and phrase not in original_lower for phrase in certainty_upgrades):
            return True
    return False


@app.post("/run")
def run(req: RunRequest, request: Request):
    request_id = request.headers.get("X-Request-ID") or new_request_id()
    started = time.perf_counter()
    span_stack = ExitStack()
    run_observation = None
    try:
        session_id = req.conversation_id or f"support:{req.user_id}:{req.order_id}"
        span_stack.enter_context(
            langfuse_attributes(
                user_id=req.user_id,
                session_id=session_id,
                trace_name="swish.support.run",
                metadata={
                    "request_id": request_id,
                    "order_id": req.order_id,
                    "conversation_id": req.conversation_id,
                },
                tags=["support-agent", "swish"],
            )
        )
        run_observation = span_stack.enter_context(
            langfuse_observation(
                "agent.run",
                input={
                    "complaint": req.complaint,
                    "order_id": req.order_id,
                    "has_photo": bool(req.photo_url),
                    "order_value": req.order_value,
                },
                metadata={"request_id": request_id},
                trace_id_seed=request_id,
            )
        )
        history = get_session(session_id)
        history.append({"role": "user", "content": req.complaint})
        trace_event(
            logger,
            "agent_run_started",
            request_id=request_id,
            user_id=req.user_id,
            order_id=req.order_id,
            conversation_id=req.conversation_id,
            has_photo=bool(req.photo_url),
            history_len=len(history),
        )

        if req.photo_url:
            mark_photo_provided(session_id)

        order_details = _fetch_with_trace(request_id, "order_details", get_order_details, req.order_id)
        order_items = _fetch_with_trace(request_id, "order_items", get_order_items, req.order_id)
        kitchen = _fetch_with_trace(request_id, "kitchen", check_kitchen_log, req.order_id)
        fleet = _fetch_with_trace(request_id, "fleet", check_fleet_status, req.order_id)
        trust = _fetch_with_trace(request_id, "trust", get_trust_score, req.user_id)
        _ = _fetch_with_trace(request_id, "delivery", get_delivery_info, req.order_id)

        photo_valid = None
        photo_analysis = {}
        if req.photo_url:
            photo_analysis = _fetch_with_trace(request_id, "photo_analysis", analyze_photo, req.photo_url)
            photo_valid = photo_analysis.get("valid", True)
            if photo_analysis.get("evidence_relevance") == "unrelated":
                photo_valid = False

        order_value = req.order_value or float(order_details.get("total_amount") or 0.0)
        assessment_started = time.perf_counter()
        skip_assessment, assessment_skip_reason = _can_skip_assessment(
            req.complaint,
            session_id,
            bool(req.photo_url),
        )
        if skip_assessment:
            assessment = {}
            assessment_meta = {"status": "skipped", "reason": assessment_skip_reason}
        else:
            assessment, assessment_meta = _assess_case(
                complaint=req.complaint,
                history=history,
                order_details=order_details,
                order_items=order_items,
                kitchen=kitchen,
                fleet=fleet,
                trust=trust,
            )
        trace_event(
            logger,
            "assessment_completed",
            request_id=request_id,
            status=assessment_meta.get("status"),
            duration_ms=round((time.perf_counter() - assessment_started) * 1000, 2),
            parsed=bool(assessment),
            issue_type=assessment.get("issue_type") if assessment else None,
            requested_resolution=assessment.get("requested_resolution") if assessment else None,
        )
        assessment_fallback_used = assessment_meta.get("status") not in {"ok", "skipped"}
        if assessment_fallback_used:
            logger.warning(
                "assessment_failed order_id=%s user_id=%s status=%s raw_preview=%s error=%s",
                req.order_id,
                req.user_id,
                assessment_meta.get("status"),
                assessment_meta.get("raw_preview"),
                assessment_meta.get("error"),
            )
            trace_event(
                logger,
                "assessment_fallback",
                request_id=request_id,
                status=assessment_meta.get("status"),
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            assessment = {}
        logger.info(
            "assessment_raw order_id=%s user_id=%s raw_preview=%s parsed=%s",
            req.order_id,
            req.user_id,
            assessment_meta.get("raw_preview"),
            json.dumps(assessment, ensure_ascii=True, sort_keys=True),
        )
        with langfuse_observation(
            "rules.resolve",
            input={
                "complaint": req.complaint,
                "order_value": order_value,
                "trust_score": float(trust.get("score", 50)),
                "photo_valid": photo_valid,
                "photo_analysis": photo_analysis,
                "photo_in_session": session_has_photo(session_id),
                "assessment": assessment,
                "assessment_status": assessment_meta.get("status"),
            },
            metadata={"request_id": request_id},
        ) as rules_observation:
            resolution = Rules.resolve(
                complaint=req.complaint,
                conversation_history=history,
                order_value=order_value,
                trust_score=float(trust.get("score", 50)),
                kitchen=kitchen,
                fleet=fleet,
                trust=trust,
                order_details=order_details,
                order_items=order_items,
                photo_url=req.photo_url,
                photo_valid=photo_valid,
                photo_in_session=session_has_photo(session_id),
                session_id=session_id,
                assessment=assessment,
            )
            rules_observation.update(
                output={
                    "action": resolution.get("action"),
                    "amount": resolution.get("amount"),
                    "reason": resolution.get("reason"),
                    "debug": resolution.get("_debug"),
                }
            )
        debug_meta = resolution.get("_debug", {})
        if not debug_meta:
            state_snapshot = get_session_state(session_id)
            debug_meta = {
                "issue_type": state_snapshot.get("issue_type"),
                "issue_severity": state_snapshot.get("issue_severity"),
                "evidence_strength": state_snapshot.get("evidence_strength"),
                "requested_resolution": state_snapshot.get("desired_resolution") or "none",
                "active_item_name": state_snapshot.get("active_item_name"),
                "fault": state_snapshot.get("fault") or state_snapshot.get("ops_fault"),
            }
        logger.info(
            "turn_analysis order_id=%s user_id=%s assessment_status=%s issue_type=%s issue_type_source=%s issue_confidence=%s requested_resolution=%s active_item=%s issue_severity=%s evidence_strength=%s economic_preference=%s visual_evidence_useful=%s visual_evidence_source=%s fault=%s fault_source=%s turn_act=%s recommended_next_step=%s clarification_needed=%s",
            req.order_id,
            req.user_id,
            assessment_meta.get("status"),
            debug_meta.get("issue_type"),
            debug_meta.get("issue_type_source"),
            debug_meta.get("issue_confidence"),
            debug_meta.get("requested_resolution"),
            debug_meta.get("active_item_name"),
            debug_meta.get("issue_severity"),
            debug_meta.get("evidence_strength"),
            debug_meta.get("economic_preference"),
            debug_meta.get("visual_evidence_useful"),
            debug_meta.get("visual_evidence_source"),
            debug_meta.get("fault"),
            debug_meta.get("fault_source"),
            debug_meta.get("turn_act"),
            debug_meta.get("recommended_next_step"),
            debug_meta.get("clarification_needed"),
        )
        case_state = build_case_state(
            user_id=req.user_id,
            order_id=req.order_id,
            session_id=session_id,
            complaint=req.complaint,
            order_details=order_details,
            order_items=order_items,
            kitchen=kitchen,
            fleet=fleet,
            trust=trust,
            assessment=assessment,
            resolution_debug=debug_meta,
        )
        resolution = _humanize_message(resolution, req.complaint, order_items, history)
        resolution = attach_artifacts(get_session_state(session_id), resolution, case_state)
        if INCLUDE_ASSESSMENT_DEBUG:
            resolution["_assessment"] = {"meta": assessment_meta, "parsed": assessment}
        resolution.pop("_debug", None)

        if resolution.get("action") not in VALID_ACTIONS:
            raise ValueError(f"bad action: {resolution.get('action')}")

        history.append({"role": "bot", "content": resolution.get("message", "")})
        trace_event(
            logger,
            "decision_completed",
            request_id=request_id,
            status="ok",
            action=resolution.get("action"),
            amount=resolution.get("amount"),
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            reason=resolution.get("reason"),
        )
        if run_observation is not None:
            run_observation.update(
                output={
                    "action": resolution.get("action"),
                    "amount": resolution.get("amount"),
                    "reason": resolution.get("reason"),
                    "message": resolution.get("message"),
                },
                metadata={
                    "status": "ok",
                    "assessment_status": assessment_meta.get("status"),
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
        return resolution
    except Exception as exc:
        session_id = req.conversation_id or f"support:{req.user_id}:{req.order_id}"
        error_response = {
            "action": "escalate",
            "amount": 0.0,
            "message": "Something broke on our side, so I can't sort this properly in chat right now. I've created a support review for this order so you don't have to explain it again.",
            "reason": str(exc),
            "support_ticket": {
                "ticket_id": f"ticket_{request_id}",
                "status": "open",
                "priority": "normal",
                "response_sla": "within 24 hours",
                "reason": "agent_error",
            },
        }
        try:
            history = get_session(session_id)
            history.append({"role": "bot", "content": error_response["message"]})
        except Exception:
            pass
        trace_event(
            logger,
            "decision_failed",
            request_id=request_id,
            action=error_response["action"],
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            error=str(exc),
        )
        if run_observation is not None:
            run_observation.update(
                output=error_response,
                level="ERROR",
                status_message=str(exc),
                metadata={"status": "error", "duration_ms": round((time.perf_counter() - started) * 1000, 2)},
            )
        return error_response
    finally:
        span_stack.close()


@app.post("/clear_session")
def clear_session_endpoint(user_id: str, order_id: str, conversation_id: Optional[str] = None):
    session_id = conversation_id or f"support:{user_id}:{order_id}"
    clear_session(session_id)
    return {"status": "cleared", "session_id": session_id}


@app.get("/case_status")
def case_status_endpoint(user_id: str, order_id: str, conversation_id: Optional[str] = None):
    session_id = conversation_id or f"support:{user_id}:{order_id}"
    state = get_session_state(session_id)
    return {
        "status": "ok",
        "user_id": user_id,
        "order_id": order_id,
        "conversation_id": conversation_id,
        "case_state": state.get("case_state"),
        "action_lifecycles": state.get("action_lifecycles", []),
        "ops_incidents": state.get("ops_incidents", []),
        "support_tickets": state.get("support_tickets", []),
    }


@app.get("/health")
def health():
    return {"status": "ok"}
