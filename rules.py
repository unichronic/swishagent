"""
Deterministic support rules for the Swish agent.

The LLM should not decide refunds, replacements, or conversation state.
This module is the single source of truth for policy, state transitions,
and human-sounding fallback messages.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from difflib import SequenceMatcher
import re

from session_store import SESSION_TTL_SECONDS, store as session_store

PHYSICAL_ISSUE_TYPES = {"damaged", "spill_leak", "wrong_item", "missing_item", "foreign_object"}


def _lower(text: Optional[str]) -> str:
    normalized = (text or "").strip().lower()
    return normalized


class Rules:
    HIGH_VALUE_THRESHOLD = 500
    LOW_VALUE_REFUND_THRESHOLD = 250
    LOW_TRUST_THRESHOLD = 40
    REFUND_TRUST_THRESHOLD = 80
    STANDARD_COUPON_AMOUNT = 50
    ESTIMATED_REPLACEMENT_OVERHEAD = 70
    MIN_ASSESSMENT_CONFIDENCE = 0.4
    MIN_VISUAL_DECISION_CONFIDENCE = 0.6
    MIN_RESOLUTION_CONFIDENCE = 0.55
    MIN_TURN_ACT_CONFIDENCE = 0.55
    MIN_INFO_QUERY_CONFIDENCE = 0.55
    MAX_COUPON_REINFORCEMENT_TURNS = 2
    MAX_HIGH_SEVERITY_REPLACEMENT_NEGOTIATION_TURNS = 1
    MIN_REPLACEMENT_NEGOTIATION_MARGIN = 60

    ALLOWED_ISSUE_TYPES = {
        "quality",
        "temperature",
        "delay",
        "wrong_item",
        "missing_item",
        "damaged",
        "spill_leak",
        "foreign_object",
        "portion_size",
        "info_query",
        "other",
    }
    ALLOWED_RESOLUTIONS = {"none", "refund", "replacement", "coupon", "credit"}
    ALLOWED_INFO_QUERIES = {"none", "items", "total", "status"}
    ALLOWED_SEVERITIES = {"low", "medium", "high"}
    ALLOWED_FAULT_HINTS = {"kitchen", "delivery", "unclear"}
    ALLOWED_ECONOMIC_PREFERENCES = {"coupon", "refund", "replacement", "escalate"}
    ALLOWED_TONE_GUARDRAILS = {"neutral", "sensitive", "persuasive", "operational"}
    ALLOWED_NEGOTIATION_STRENGTHS = {"none", "light", "medium"}
    ALLOWED_TURN_ACTS = {"none", "confirm", "reject", "switch_resolution", "ask_status", "ask_cause", "clarify"}
    ALLOWED_NEXT_STEPS = {"explain", "clarify", "coupon", "refund", "replacement", "live_capture", "escalate"}

    BANNED_PHRASES = [
        "i completely understand",
        "absolutely",
        "any inconvenience",
        "i apologize for the inconvenience",
    ]

    @staticmethod
    def resolve(
        complaint: str,
        conversation_history: List[Dict[str, str]],
        order_value: float,
        trust_score: float,
        kitchen: Dict[str, Any],
        fleet: Dict[str, Any],
        trust: Dict[str, Any],
        order_details: Dict[str, Any],
        order_items: Dict[str, Any],
        photo_url: Optional[str] = None,
        photo_valid: Optional[bool] = None,
        photo_in_session: bool = False,
        session_id: Optional[str] = None,
        assessment: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        state = get_session_state(session_id) if session_id else {}
        state["order_value"] = order_value
        history = conversation_history or []
        bot_count = sum(1 for msg in history if msg.get("role") == "bot")
        last_bot_msg = next((msg.get("content", "") for msg in reversed(history) if msg.get("role") == "bot"), "")
        user_text = _lower(complaint)
        assessment = assessment or {}
        assessment_provided = bool(assessment)
        matched_item = {} if assessment_provided else Rules._match_item(order_items, complaint)
        assessed_item_name = assessment.get("active_item_name")
        assessed_issue_type = Rules._validated_enum(assessment.get("issue_type"), Rules.ALLOWED_ISSUE_TYPES)
        assessed_resolution = Rules._validated_enum(assessment.get("requested_resolution"), Rules.ALLOWED_RESOLUTIONS)
        assessed_info_query = Rules._validated_enum(assessment.get("info_query"), Rules.ALLOWED_INFO_QUERIES)
        assessed_assurance_query = Rules._normalize_bool(assessment.get("assurance_query"))
        assessed_turn_act = Rules._validated_enum(assessment.get("turn_act"), Rules.ALLOWED_TURN_ACTS)
        assessed_resolution_confidence = Rules._normalize_confidence(assessment.get("requested_resolution_confidence"))
        assessed_info_query_confidence = Rules._normalize_confidence(assessment.get("info_query_confidence"))
        assessed_turn_act_confidence = Rules._normalize_confidence(assessment.get("turn_act_confidence"))
        assessed_visual_evidence = Rules._normalize_bool(assessment.get("visual_evidence_useful"))
        assessed_fault_hint = Rules._validated_enum(assessment.get("fault_hint"), Rules.ALLOWED_FAULT_HINTS)
        assessed_recommended_next_step = Rules._validated_enum(
            assessment.get("recommended_next_step"), Rules.ALLOWED_NEXT_STEPS
        )
        assessed_clarification_needed = Rules._normalize_bool(assessment.get("clarification_needed"))
        assessed_issue_confidence = Rules._normalize_confidence(assessment.get("issue_confidence"))
        assessed_issue_severity = Rules._validated_enum(assessment.get("issue_severity"), Rules.ALLOWED_SEVERITIES)
        assessed_economic_preference = Rules._validated_enum(
            assessment.get("economic_preference"), Rules.ALLOWED_ECONOMIC_PREFERENCES
        )
        assessed_economic_confidence = Rules._normalize_confidence(assessment.get("economic_confidence"))
        assessed_tone_guardrail = Rules._validated_enum(
            assessment.get("tone_guardrail"), Rules.ALLOWED_TONE_GUARDRAILS
        )
        assessed_negotiation_allowed = Rules._normalize_bool(assessment.get("negotiation_allowed"))
        assessed_negotiation_strength = Rules._validated_enum(
            assessment.get("negotiation_strength"), Rules.ALLOWED_NEGOTIATION_STRENGTHS
        )

        if assessed_item_name:
            item_from_assessment = Rules._find_item_by_name(order_items, assessed_item_name)
            if item_from_assessment:
                matched_item = item_from_assessment
        prior_case_issue_type = state.get("case_issue_type")
        prior_case_issue_severity = state.get("case_issue_severity")
        prior_case_evidence_strength = state.get("case_evidence_strength")
        prior_case_economic_preference = state.get("case_economic_preference")

        if matched_item.get("name"):
            state["active_item_name"] = matched_item.get("name")
            state["active_item_price"] = matched_item.get("price")
        item = matched_item or {}
        if not item and state.get("active_item_name"):
            item = {
                "name": state.get("active_item_name"),
                "price": state.get("active_item_price"),
            }
        elif item.get("name") and state.get("active_item_name") and not Rules._complaint_mentions_item(complaint, item):
            item = {
                "name": state.get("active_item_name"),
                "price": state.get("active_item_price"),
            }
        item_name = item.get("name") or "item"
        detected_issue_type = Rules._detect_issue_type(complaint, item_name) if not assessment_provided else "other"
        issue_type = Rules._choose_issue_type(
            detected_issue_type,
            assessed_issue_type,
            assessed_issue_confidence,
            assessment_provided=assessment_provided,
            assessed_info_query=assessed_info_query,
        )
        wants = Rules._choose_requested_resolution(
            assessed_resolution=assessed_resolution,
            assessed_resolution_confidence=assessed_resolution_confidence,
            assessed_issue_confidence=assessed_issue_confidence,
            assessment_provided=assessment_provided,
            state=state,
            complaint=complaint,
        ) or (
            (state.get("desired_resolution", "none") if state.get("pending") == "photo" else "none")
            if assessment_provided
            else Rules._detect_requested_resolution(complaint, state)
        )
        payment_or_billing_query = Rules._is_payment_or_billing_query(user_text) or (
            state.get("case_issue_type") == "info_query" and Rules._is_followup_or_evidence_turn(user_text)
        )
        if payment_or_billing_query:
            issue_type = "info_query"
            wants = "none"
        if Rules._is_non_delivery_signal(user_text):
            issue_type = "missing_item"
        if Rules._is_resolution_only_turn(complaint) and state.get("issue_type") and (
            issue_type == "other" or not assessment_provided
        ):
            issue_type = state.get("issue_type", issue_type)
        if (
            wants in {"refund", "replacement", "coupon", "credit"}
            and state.get("case_issue_type")
            and not Rules._has_concrete_issue_signal(user_text)
        ):
            issue_type = state.get("case_issue_type", issue_type)
        if assessment_provided and issue_type == "other" and wants in {"refund", "replacement"} and state.get("issue_type"):
            issue_type = state.get("issue_type", issue_type)
        if photo_url and state.get("issue_type"):
            issue_type = state.get("issue_type", issue_type)
        prep_anomaly = Rules._looks_like_prep_anomaly(user_text)
        if issue_type == "foreign_object" and prep_anomaly:
            issue_type = "quality"
        issue_type = Rules._strong_text_issue_override(user_text, issue_type)
        if payment_or_billing_query:
            issue_type = "info_query"
            wants = "none"
        info_query = Rules._choose_info_query(
            assessed_info_query=assessed_info_query,
            assessed_info_query_confidence=assessed_info_query_confidence,
            assessed_issue_confidence=assessed_issue_confidence,
            assessment_provided=assessment_provided,
            complaint=complaint,
        ) or ("none" if assessment_provided else Rules._detect_info_query(complaint))
        assurance_query = bool(assessed_assurance_query) or (False if assessment_provided else Rules._detect_assurance_query(complaint))
        turn_act = Rules._choose_turn_act(
            assessed_turn_act=assessed_turn_act,
            assessed_turn_act_confidence=assessed_turn_act_confidence,
            assessed_issue_confidence=assessed_issue_confidence,
            assessment_provided=assessment_provided,
            complaint=complaint,
            wants=wants,
            info_query=info_query,
        ) or ("none" if assessment_provided else Rules._detect_turn_act(complaint, wants, info_query))
        if Rules._should_inherit_case_issue_type(
            text=user_text,
            state=state,
            issue_type=issue_type,
            wants=wants,
            info_query=info_query,
            turn_act=turn_act,
        ):
            issue_type = state.get("case_issue_type", issue_type)
        is_abusive = Rules._is_abusive(complaint)
        inferred_fault = Rules._infer_fault(kitchen, fleet, issue_type)
        fault = Rules._choose_fault(inferred_fault, assessed_fault_hint, assessed_issue_confidence)
        if prep_anomaly:
            fault = "kitchen"
        issue_severity = Rules._choose_issue_severity(issue_type, assessed_issue_severity, assessed_issue_confidence, kitchen, fleet)
        explicit_comp = wants in {"refund", "replacement", "coupon", "credit"}
        current_turn_has_photo = bool(photo_url)
        current_case_photo_key = Rules._photo_case_key(issue_type, item.get("name"))
        if current_turn_has_photo and photo_valid is not False:
            state["photo_evidence_case"] = current_case_photo_key
        verified_photo_for_case = state.get("photo_evidence_case") == current_case_photo_key
        photo_present = bool(current_turn_has_photo or verified_photo_for_case)
        needs_visual = Rules._visual_evidence_useful(
            issue_type=issue_type,
            order_items=order_items,
            assessed_visual_evidence=assessed_visual_evidence,
            assessed_issue_confidence=assessed_issue_confidence,
        )
        if prep_anomaly:
            needs_visual = False
        evidence_strength = Rules._evidence_strength(
            issue_type=issue_type,
            fault=fault,
            kitchen=kitchen,
            fleet=fleet,
            photo_present=photo_present,
            photo_valid=photo_valid,
            visual_evidence_useful=needs_visual,
        )
        economic_preference = Rules._choose_economic_preference(
            desired_resolution=wants,
            issue_type=issue_type,
            issue_severity=issue_severity,
            evidence_strength=evidence_strength,
            order_value=order_value,
            item_price=item.get("price"),
            trust_score=trust_score,
            assessed_preference=assessed_economic_preference,
            assessed_confidence=assessed_economic_confidence,
        )
        clarification_needed = Rules._needs_clarification(
            complaint=complaint,
            issue_type=issue_type,
            wants=wants,
            info_query=info_query,
            turn_act=turn_act,
            assessed_clarification=assessed_clarification_needed,
            assessed_issue_confidence=assessed_issue_confidence,
            assessed_recommended_next_step=assessed_recommended_next_step,
            assessment_provided=assessment_provided,
        )
        tone_guardrail = Rules._choose_tone_guardrail(
            issue_type=issue_type,
            issue_severity=issue_severity,
            wants=wants,
            assurance_query=assurance_query,
            info_query=info_query,
            assessed_tone_guardrail=assessed_tone_guardrail,
            assessed_issue_confidence=assessed_issue_confidence,
        )
        negotiation_allowed = Rules._choose_negotiation_allowed(
            wants=wants,
            recommended_next_step=assessed_recommended_next_step,
            assessed_negotiation_allowed=assessed_negotiation_allowed,
            assessed_issue_confidence=assessed_issue_confidence,
        )
        negotiation_strength = Rules._choose_negotiation_strength(
            issue_type=issue_type,
            issue_severity=issue_severity,
            wants=wants,
            negotiation_allowed=negotiation_allowed,
            assessed_strength=assessed_negotiation_strength,
            assessed_issue_confidence=assessed_issue_confidence,
        )
        if issue_type == "info_query" and prior_case_issue_type:
            case_issue_type = prior_case_issue_type
            case_issue_severity = prior_case_issue_severity or issue_severity
            case_evidence_strength = prior_case_evidence_strength or evidence_strength
            case_economic_preference = prior_case_economic_preference or economic_preference
        else:
            case_issue_type = issue_type
            case_issue_severity = issue_severity
            case_evidence_strength = evidence_strength
            case_economic_preference = economic_preference
        coupon_amount = Rules._coupon_amount(order_value, item.get("price"))
        coupon_amount = Rules._adjust_coupon_amount(
            coupon_amount=coupon_amount,
            order_value=order_value,
            item_price=item.get("price"),
            desired_resolution=wants,
            evidence_strength=evidence_strength,
        )

        state["issue_type"] = issue_type
        state["issue_severity"] = issue_severity
        state["evidence_strength"] = evidence_strength
        state["visual_evidence_useful"] = needs_visual
        state["economic_preference"] = economic_preference
        state["case_issue_type"] = case_issue_type
        state["case_issue_severity"] = case_issue_severity
        state["case_evidence_strength"] = case_evidence_strength
        state["case_economic_preference"] = case_economic_preference
        state["coupon_amount"] = coupon_amount
        state["turn_act"] = turn_act
        state["tone_guardrail"] = tone_guardrail
        state["negotiation_allowed"] = negotiation_allowed
        state["negotiation_strength"] = negotiation_strength

        if state.get("pending") == "photo" and current_turn_has_photo and photo_valid is not False:
            state["pending"] = None

        if is_abusive:
            response = {
                "action": "escalate",
                "amount": 0.0,
                "message": "I can't keep this in chat as it stands. If you'd like to take it further, please email hello@justswish.in and the team can help from there.",
                "reason": "Abusive language detected",
            }
            Rules._store_terminal_state(state)
            return Rules._enforce_content(response)

        if photo_url and photo_valid is False:
            response = {
                "action": "escalate",
                "amount": 0.0,
                "message": "This needs a manual review. If you'd like to take it further, please email hello@justswish.in and the team can look into it from there.",
                "reason": "Photo failed verification",
            }
            Rules._store_terminal_state(state)
            return Rules._enforce_content(response)

        if state.get("last_action") == "escalate" and info_query == "none":
            issue_type = state.get("case_issue_type", issue_type)
            response = {
                "action": "escalate",
                "amount": 0.0,
                "message": Rules._review_escalation_message("case"),
                "reason": "Case already marked for manual review",
            }
            Rules._store_terminal_state(state)
            return Rules._enforce_content(response)

        photo_required = Rules._needs_photo(
            explicit_comp=explicit_comp,
            photo_present=photo_present,
            visual_evidence_useful=needs_visual,
        )
        if photo_required:
            state["pending"] = "photo"
            state["desired_resolution"] = wants if wants in {"refund", "replacement"} else None
            response = {
                "action": "live_capture",
                "amount": 0.0,
                "message": Rules._photo_message(order_value, issue_type),
                "reason": "Photo required before compensation decision",
            }
            return Rules._enforce_content(response)

        pending = state.get("pending")
        if pending and info_query != "none":
            response = {
                "action": "info",
                "amount": 0.0,
                "message": Rules._info_query_message(info_query, order_details, order_items, fleet, state, last_bot_msg),
                "reason": "User asked for order information during an active resolution flow",
            }
            Rules._store_terminal_state(state)
            response = Rules._enforce_content(response)
            response["_debug"] = {
                "issue_type": issue_type,
                "issue_type_source": "fallback",
                "issue_confidence": assessed_issue_confidence,
                "fault": fault,
                "fault_source": "llm" if fault == assessed_fault_hint and assessed_fault_hint else "fallback",
                "visual_evidence_useful": needs_visual,
                "requested_resolution": wants,
                "active_item_name": item.get("name") or state.get("active_item_name"),
                "issue_severity": issue_severity,
                "evidence_strength": evidence_strength,
                "economic_preference": economic_preference,
                "turn_act": turn_act,
                "info_query_confidence": assessed_info_query_confidence,
                "recommended_next_step": assessed_recommended_next_step or "fallback",
                "clarification_needed": clarification_needed,
                "tone_guardrail": tone_guardrail,
                "negotiation_allowed": negotiation_allowed,
                "negotiation_strength": negotiation_strength,
            }
            return response
        if pending == "coupon":
            response = Rules._handle_coupon_reply(
                complaint=complaint,
                order_value=order_value,
                trust_score=trust_score,
                state=state,
                coupon_amount=coupon_amount,
                item_name=item_name,
                turn_act=turn_act,
                wants=wants,
                assessment_provided=assessment_provided,
            )
        elif pending == "refund_amount":
            response = Rules._handle_refund_amount_reply(
                complaint=complaint,
                order_value=order_value,
                trust_score=trust_score,
                state=state,
                turn_act=turn_act,
                assessment_provided=assessment_provided,
            )
        elif pending == "replacement_confirm":
            response = Rules._handle_replacement_reply(
                complaint=complaint,
                trust_score=trust_score,
                state=state,
                item_name=item_name,
                turn_act=turn_act,
                wants=wants,
                assessment_provided=assessment_provided,
            )
        else:
            response = Rules._handle_fresh_turn(
                complaint=complaint,
                bot_count=bot_count,
                wants=wants,
                info_query=info_query,
                assurance_query=assurance_query,
                issue_type=issue_type,
                fault=fault,
                turn_act=turn_act,
                kitchen=kitchen,
                fleet=fleet,
                trust=trust,
                order_details=order_details,
                item_name=item_name,
                order_items=order_items,
                coupon_amount=coupon_amount,
                state=state,
                last_bot_msg=last_bot_msg,
                order_value=order_value,
                trust_score=trust_score,
                clarification_needed=clarification_needed,
                recommended_next_step=assessed_recommended_next_step,
            )

        Rules._mark_terminal_action(state, response, item_name)
        response = Rules._enforce_content(response)
        response["_debug"] = {
            "issue_type": issue_type,
            "issue_type_source": "llm" if assessment_provided and issue_type == assessed_issue_type and assessed_issue_type else "fallback",
            "issue_confidence": assessed_issue_confidence,
            "fault": fault,
            "fault_source": "llm" if fault == assessed_fault_hint and assessed_fault_hint else "fallback",
            "visual_evidence_useful": needs_visual,
            "visual_evidence_source": "llm"
            if assessed_visual_evidence is not None and assessed_issue_confidence is not None and assessed_issue_confidence >= Rules.MIN_VISUAL_DECISION_CONFIDENCE
            else "fallback",
            "requested_resolution": wants,
            "requested_resolution_confidence": assessed_resolution_confidence,
            "active_item_name": item.get("name") or state.get("active_item_name"),
            "issue_severity": issue_severity,
            "evidence_strength": evidence_strength,
            "economic_preference": economic_preference,
            "turn_act": turn_act,
            "turn_act_confidence": assessed_turn_act_confidence,
            "info_query_confidence": assessed_info_query_confidence,
            "recommended_next_step": assessed_recommended_next_step or "fallback",
            "clarification_needed": clarification_needed,
            "tone_guardrail": tone_guardrail,
            "negotiation_allowed": negotiation_allowed,
            "negotiation_strength": negotiation_strength,
        }
        return response

    @staticmethod
    def _handle_fresh_turn(
        complaint: str,
        bot_count: int,
        wants: str,
        info_query: str,
        assurance_query: bool,
        issue_type: str,
        fault: str,
        turn_act: str,
        kitchen: Dict[str, Any],
        fleet: Dict[str, Any],
        trust: Dict[str, Any],
        order_details: Dict[str, Any],
        item_name: str,
        order_items: Dict[str, Any],
        coupon_amount: float,
        state: Dict[str, Any],
        last_bot_msg: str,
        order_value: float,
        trust_score: float,
        clarification_needed: bool,
        recommended_next_step: Optional[str],
    ) -> Dict[str, Any]:
        issue_severity = state.get("issue_severity", "medium")
        if clarification_needed and wants == "none" and info_query == "none" and not assurance_query:
            state["pending"] = None
            return {
                "action": "info",
                "amount": 0.0,
                "message": Rules._clarification_message(state, issue_type),
                "reason": "Need clarification before acting on ambiguous user input",
            }

        if assurance_query and state.get("last_action") == "replacement":
            state["pending"] = None
            return {
                "action": "info",
                "amount": 0.0,
                "message": Rules._assurance_message(state, issue_type, fault),
                "reason": "User asked for reassurance after replacement approval",
            }

        if state.get("last_action") == "escalate" and info_query == "none":
            state["pending"] = None
            return {
                "action": "escalate",
                "amount": 0.0,
                "message": Rules._review_escalation_message("case"),
                "reason": "Case already marked for manual review",
            }

        if state.get("last_action") == "replacement" and info_query == "none" and wants == "replacement":
            state["pending"] = None
            return {
                "action": "info",
                "amount": 0.0,
                "message": Rules._info_query_message("status", order_details, order_items, fleet, state, last_bot_msg),
                "reason": "Replacement already approved",
            }

        if (
            recommended_next_step == "escalate"
            and issue_type == "foreign_object"
            and issue_severity == "high"
            and wants == "none"
            and bot_count > 0
        ):
            state["pending"] = None
            state["desired_resolution"] = None
            return {
                "action": "escalate",
                "amount": 0.0,
                "message": Rules._review_escalation_message("case"),
                "reason": "High-severity safety complaint requires manual review",
            }

        if info_query != "none" and issue_type != "info_query" and turn_act == "ask_cause":
            state["pending"] = None
            return {
                "action": "info",
                "amount": 0.0,
                "message": Rules._info_message(item_name, issue_type, fault, kitchen, fleet, trust, last_bot_msg),
                "reason": "User asked for the cause of an identified issue",
            }

        if wants == "refund" and state.get("last_action") == "replacement":
            if Rules._refund_allowed(
                trust_score=trust_score,
                issue_severity=state.get("case_issue_severity", state.get("issue_severity", issue_type)),
                evidence_strength=state.get("case_evidence_strength", state.get("evidence_strength", "weak")),
            ):
                state["pending"] = "refund_amount"
                state["desired_resolution"] = "refund"
                return {
                    "action": "info",
                    "amount": 0.0,
                    "message": "If you want to switch the approved replacement to a refund instead, tell me what refund feels fair here: 25%, 50%, 75%, or full.",
                    "reason": "User wants to switch an approved replacement to refund",
                }
            state["pending"] = None
            state["desired_resolution"] = None
            return {
                "action": "escalate",
                "amount": 0.0,
                "message": "The replacement is already approved. If you want that changed to a refund instead, I need to send it for review.",
                "reason": "Refund requested after replacement approval but cannot be auto-converted",
            }

        if info_query != "none":
            state["pending"] = None
            return {
                "action": "info",
                "amount": 0.0,
                "message": Rules._info_query_message(info_query, order_details, order_items, fleet, state, last_bot_msg),
                "reason": "User asked for order information, not a complaint resolution",
            }

        if bot_count == 0 and wants == "none":
            state["pending"] = None
            return {
                "action": "info",
                "amount": 0.0,
                "message": Rules._info_message(item_name, issue_type, fault, kitchen, fleet, trust, last_bot_msg),
                "reason": "First complaint gets explanation only",
            }

        if wants in {"refund", "replacement"}:
            if recommended_next_step == "escalate":
                state["pending"] = None
                state["desired_resolution"] = None
                return {
                    "action": "escalate",
                    "amount": 0.0,
                    "message": Rules._review_escalation_message(wants),
                    "reason": "LLM recommendation and policy both point to manual review",
                }
            if (
                wants == "replacement"
                and issue_type == "spill_leak"
                and state.get("evidence_strength") == "strong"
                and state.get("economic_preference") == "replacement"
            ):
                state["pending"] = "replacement_confirm"
                state["desired_resolution"] = "replacement"
                return {
                    "action": "info",
                    "amount": 0.0,
                    "message": Rules._replacement_confirm_message(item_name),
                    "reason": "Strong evidence supports moving directly to replacement confirmation",
                }
            state["pending"] = "coupon"
            state["desired_resolution"] = wants
            state["coupon_amount"] = coupon_amount
            state["coupon_push_count"] = 0
            return {
                "action": "info",
                "amount": 0.0,
                "message": Rules._coupon_offer_message(
                    coupon_amount=coupon_amount,
                    issue_type=issue_type,
                    issue_severity=state.get("issue_severity", "medium"),
                    desired_resolution=wants,
                    evidence_strength=state.get("evidence_strength", "weak"),
                    economic_preference=state.get("economic_preference"),
                    tone_guardrail=state.get("tone_guardrail", "neutral"),
                    negotiation_allowed=state.get("negotiation_allowed", False),
                    negotiation_strength=state.get("negotiation_strength", "none"),
                    order_value=order_value,
                    item_price=state.get("active_item_price"),
                    trust_score=trust_score,
                    item_name=item_name,
                    last_bot_msg=last_bot_msg,
                ),
                "reason": "Offer coupon before refund or replacement",
            }

        state["pending"] = None
        return {
            "action": "info",
            "amount": 0.0,
            "message": Rules._followup_info_message(item_name, issue_type, fault, kitchen, fleet, last_bot_msg),
            "reason": "No explicit compensation request",
        }

    @staticmethod
    def _pick_opening(options: List[str], last_bot_msg: str) -> str:
        last_lower = _lower(last_bot_msg)
        for option in options:
            if _lower(option) not in last_lower:
                return option
        return options[0]

    @staticmethod
    def _ack_prefix(last_bot_msg: str, loyal_customer: bool = False) -> str:
        if loyal_customer:
            return Rules._pick_opening(
                [
                    "That’s a fair call, especially since you order with us a lot.",
                    "You order with us often, so we should be doing better than this.",
                    "Not ideal, especially for someone who orders with us regularly.",
                ],
                last_bot_msg,
            )
        return Rules._pick_opening(
            [
                "That’s not how this should land.",
                "That’s not a great experience.",
                "That’s not what we want reaching you.",
                "That’s not good enough from our side.",
            ],
            last_bot_msg,
        )

    @staticmethod
    def _handle_coupon_reply(
        complaint: str,
        order_value: float,
        trust_score: float,
        state: Dict[str, Any],
        coupon_amount: float,
        item_name: str,
        turn_act: str,
        wants: str,
        assessment_provided: bool,
    ) -> Dict[str, Any]:
        user_text = _lower(complaint)
        desired = state.get("desired_resolution") or "refund"
        issue_severity = state.get("issue_severity", "medium")
        evidence_strength = state.get("evidence_strength", "weak")
        issue_type = state.get("issue_type", "quality")
        push_count = int(state.get("coupon_push_count") or 0)
        preferred_resolution = Rules._preferred_refund_resolution(
            order_value=order_value,
            item_price=state.get("active_item_price"),
            trust_score=trust_score,
            desired_resolution=desired,
            issue_type=issue_type,
            issue_severity=issue_severity,
            evidence_strength=evidence_strength,
            economic_preference=state.get("economic_preference"),
        )

        if turn_act == "switch_resolution" and state.get("desired_resolution") == "refund" and (
            wants == "refund" or (not assessment_provided and Rules._mentions_refund(user_text))
        ):
            desired = "refund"

        replacement_requested = wants == "replacement" if assessment_provided else Rules._mentions_replacement(user_text)
        refund_requested = wants == "refund" if assessment_provided else Rules._mentions_refund(user_text)

        if desired == "replacement" or (turn_act == "switch_resolution" and replacement_requested) or replacement_requested:
            state["coupon_push_count"] = push_count + 1
            if evidence_strength != "strong":
                if (
                    state["coupon_push_count"] >= Rules.MAX_COUPON_REINFORCEMENT_TURNS
                    and Rules._can_soft_approve_replacement(
                        issue_type=issue_type,
                        order_value=order_value,
                        item_price=state.get("active_item_price"),
                        trust_score=trust_score,
                        evidence_strength=evidence_strength,
                        economic_preference=state.get("economic_preference"),
                    )
                ):
                    state["pending"] = "replacement_confirm"
                    state["desired_resolution"] = "replacement"
                    return {
                        "action": "info",
                        "amount": 0.0,
                        "message": Rules._replacement_confirm_message(item_name),
                        "reason": "Repeated replacement request qualifies for low-risk remake confirmation",
                    }
                if state["coupon_push_count"] > Rules.MAX_COUPON_REINFORCEMENT_TURNS:
                    state["pending"] = None
                    state["desired_resolution"] = None
                    return {
                        "action": "escalate",
                        "amount": 0.0,
                        "message": Rules._review_escalation_message("replacement"),
                        "reason": "Replacement requested without enough evidence after repeated coupon steering",
                    }
                return {
                    "action": "info",
                    "amount": 0.0,
                    "message": Rules._coupon_reinforcement_message(
                        coupon_amount=float(state.get("coupon_amount", coupon_amount)),
                        desired_resolution="replacement",
                        item_name=item_name,
                        push_count=state["coupon_push_count"],
                        evidence_strength=evidence_strength,
                        issue_type=issue_type,
                        tone_guardrail=state.get("tone_guardrail", "neutral"),
                        negotiation_strength=state.get("negotiation_strength", "none"),
                    ),
                    "reason": "Reinforcing coupon because replacement cannot be verified cleanly",
                }
            replacement_negotiation_limit = Rules._replacement_negotiation_turn_limit(
                order_value=order_value,
                item_price=state.get("active_item_price"),
                coupon_amount=float(state.get("coupon_amount", coupon_amount)),
                issue_severity=issue_severity,
                evidence_strength=evidence_strength,
                economic_preference=state.get("economic_preference"),
            )
            if state["coupon_push_count"] <= replacement_negotiation_limit:
                return {
                    "action": "info",
                    "amount": 0.0,
                    "message": Rules._coupon_reinforcement_message(
                        coupon_amount=float(state.get("coupon_amount", coupon_amount)),
                        desired_resolution="replacement",
                        item_name=item_name,
                        push_count=state["coupon_push_count"],
                        evidence_strength=evidence_strength,
                        issue_type=issue_type,
                        tone_guardrail=state.get("tone_guardrail", "neutral"),
                        negotiation_strength=state.get("negotiation_strength", "none"),
                    ),
                    "reason": "Reinforcing coupon before approving replacement",
                }
            state["pending"] = "replacement_confirm"
            state["desired_resolution"] = "replacement"
            return {
                "action": "info",
                "amount": 0.0,
                "message": Rules._replacement_confirm_message(item_name),
                "reason": "Coupon rejected, asking to confirm replacement",
            }

        if preferred_resolution == "replacement":
            state["coupon_push_count"] = push_count + 1
            state["pending"] = "replacement_confirm"
            state["desired_resolution"] = "replacement"
            return {
                "action": "info",
                "amount": 0.0,
                "message": Rules._replacement_steer_message(
                    item_name=item_name,
                    hard_block_refund=Rules._refund_hard_block(order_value, trust_score),
                ),
                "reason": "Steering refund request toward replacement",
            }

        if turn_act == "confirm" or (not assessment_provided and turn_act == "none" and Rules._accepted(user_text)):
            state["pending"] = None
            return {
                "action": "coupon",
                "amount": float(state.get("coupon_amount", coupon_amount)),
                "message": f"Done. I've added a ₹{int(state.get('coupon_amount', coupon_amount))} coupon to your account.",
                "reason": "User accepted coupon offer",
            }

        if preferred_resolution == "escalate":
            state["pending"] = None
            state["desired_resolution"] = None
            return {
                "action": "escalate",
                "amount": 0.0,
                "message": Rules._review_escalation_message("refund"),
                "reason": "Refund requested but economics and evidence call for manual review",
            }

        if turn_act in {"reject", "switch_resolution"} or (not assessment_provided and Rules._rejected(user_text)) or refund_requested:
            state["coupon_push_count"] = push_count + 1
            if (
                preferred_resolution == "escalate"
                or (evidence_strength != "strong" and state["coupon_push_count"] < Rules.MAX_COUPON_REINFORCEMENT_TURNS)
            ) and state["coupon_push_count"] < Rules.MAX_COUPON_REINFORCEMENT_TURNS:
                return {
                    "action": "info",
                    "amount": 0.0,
                    "message": Rules._coupon_reinforcement_message(
                        coupon_amount=float(state.get("coupon_amount", coupon_amount)),
                        desired_resolution="refund",
                        item_name=item_name,
                        push_count=state["coupon_push_count"],
                        evidence_strength=evidence_strength,
                        issue_type=issue_type,
                        tone_guardrail=state.get("tone_guardrail", "neutral"),
                        negotiation_strength=state.get("negotiation_strength", "none"),
                    ),
                    "reason": "Reinforcing coupon before refund review",
                }
            if not Rules._refund_allowed(
                trust_score=trust_score,
                issue_severity=issue_severity,
                evidence_strength=evidence_strength,
            ):
                state["pending"] = None
                state["desired_resolution"] = None
                return {
                    "action": "escalate",
                    "amount": 0.0,
                    "message": Rules._review_escalation_message("refund"),
                    "reason": "Refund requested but policy requires manual review",
                }
            state["pending"] = "refund_amount"
            state["desired_resolution"] = "refund"
            return {
                "action": "info",
                "amount": 0.0,
                "message": "If a coupon doesn't cover it, tell me what feels fair here: 25%, 50%, 75%, or full.",
                "reason": "Coupon rejected, asking refund amount",
            }

        return {
            "action": "info",
            "amount": 0.0,
            "message": "Just to be sure, do you want the coupon, a refund, or a replacement?",
            "reason": "Need clarification on coupon decision",
        }

    @staticmethod
    def _handle_refund_amount_reply(
        complaint: str,
        order_value: float,
        trust_score: float,
        state: Dict[str, Any],
        turn_act: str,
        assessment_provided: bool,
    ) -> Dict[str, Any]:
        item_name = state.get("active_item_name") or "item"
        if Rules._refund_hard_block(order_value, trust_score):
            state["pending"] = "replacement_confirm"
            state["desired_resolution"] = "replacement"
            return {
                "action": "info",
                "amount": 0.0,
                "message": Rules._replacement_steer_message(item_name=item_name, hard_block_refund=True),
                "reason": "Refund blocked for high-value low-trust case",
            }

        pct = Rules._extract_refund_percentage(complaint)
        if pct is None:
            return {
                "action": "info",
                "amount": 0.0,
                "message": "Just to be sure, tell me the refund as 25, 50, 75, or full.",
                "reason": "Need clarification on refund amount",
            }

        if not Rules._refund_allowed(
            trust_score=trust_score,
            issue_severity=state.get("issue_severity", "medium"),
            evidence_strength=state.get("evidence_strength", "weak"),
        ):
            state["pending"] = None
            return {
                "action": "escalate",
                "amount": 0.0,
                "message": Rules._review_escalation_message("refund"),
                "reason": "Refund requested but policy requires manual review",
            }

        amount = round(order_value * pct, 2)
        state["pending"] = None
        state["last_action"] = "refund"
        return {
            "action": "refund",
            "amount": amount,
            "message": f"You're right, that wasn't good enough. I've approved a ₹{amount:.0f} refund.",
            "reason": "Refund approved after explicit amount selection",
        }

    @staticmethod
    def _handle_replacement_reply(
        complaint: str,
        trust_score: float,
        state: Dict[str, Any],
        item_name: str,
        turn_act: str,
        wants: str,
        assessment_provided: bool,
    ) -> Dict[str, Any]:
        user_text = _lower(complaint)
        order_value = float(state.get("order_value") or 0.0)
        hard_block_refund = Rules._refund_hard_block(order_value, trust_score)
        issue_severity = state.get("issue_severity", "medium")
        evidence_strength = state.get("evidence_strength", "weak")
        preferred_resolution = Rules._preferred_refund_resolution(
            order_value=order_value,
            item_price=state.get("active_item_price"),
            trust_score=trust_score,
            desired_resolution="refund",
            issue_type=state.get("issue_type", "quality"),
            issue_severity=issue_severity,
            evidence_strength=evidence_strength,
            economic_preference=state.get("economic_preference"),
        )

        refund_requested = wants == "refund" if assessment_provided else Rules._mentions_refund(user_text)
        replacement_reaffirmed = wants == "replacement" if assessment_provided else Rules._mentions_replacement(user_text)
        if (turn_act == "switch_resolution" and refund_requested) or (refund_requested and not hard_block_refund):
            if preferred_resolution == "replacement":
                return {
                    "action": "info",
                    "amount": 0.0,
                    "message": Rules._replacement_steer_message(item_name=item_name, hard_block_refund=False),
                    "reason": "Refund request steered back to replacement for economic reasons",
                }
            if preferred_resolution == "escalate":
                state["pending"] = None
                state["desired_resolution"] = None
                return {
                    "action": "escalate",
                    "amount": 0.0,
                    "message": Rules._review_escalation_message("refund"),
                    "reason": "Refund requested from replacement flow but economics require review",
                }
            if not Rules._refund_allowed(
                trust_score=trust_score,
                issue_severity=issue_severity,
                evidence_strength=evidence_strength,
            ):
                state["pending"] = None
                state["desired_resolution"] = None
                return {
                    "action": "escalate",
                    "amount": 0.0,
                    "message": Rules._review_escalation_message("refund"),
                    "reason": "Refund requested from replacement flow but policy requires review",
                }
            state["pending"] = "refund_amount"
            state["desired_resolution"] = "refund"
            return {
                "action": "info",
                "amount": 0.0,
                "message": "No problem. Tell me what refund feels fair here: 25%, 50%, 75%, or full.",
                "reason": "User switched from replacement to refund",
            }
        if refund_requested:
            return {
                "action": "info",
                "amount": 0.0,
                "message": Rules._replacement_steer_message(item_name=item_name, hard_block_refund=True),
                "reason": "Refund still blocked for high-value low-trust case",
            }

        if replacement_reaffirmed and turn_act in {"none", "switch_resolution", "clarify"}:
            turn_act = "confirm"

        if not (turn_act == "confirm" or (not assessment_provided and turn_act == "none" and Rules._accepted(user_text))):
            return {
                "action": "info",
                "amount": 0.0,
                "message": Rules._replacement_steer_message(item_name=item_name, hard_block_refund=hard_block_refund)
                if hard_block_refund
                else f"Just to be sure, do you want a fresh {item_name} sent out?",
                "reason": "Need clarification on replacement confirmation",
            }

        state["pending"] = None
        if evidence_strength != "strong":
            if Rules._can_soft_approve_replacement(
                issue_type=state.get("issue_type", "quality"),
                order_value=order_value,
                item_price=state.get("active_item_price"),
                trust_score=trust_score,
                evidence_strength=evidence_strength,
                economic_preference=state.get("economic_preference"),
            ):
                state["last_action"] = "replacement"
                return {
                    "action": "replacement",
                    "amount": 0.0,
                    "message": f"I've approved a fresh {item_name} replacement.",
                    "reason": "Low-risk replacement approved after confirmation",
                }
            return {
                "action": "escalate",
                "amount": 0.0,
                "message": Rules._review_escalation_message("replacement"),
                "reason": "Replacement requested but evidence is not strong enough for auto approval",
            }

        state["last_action"] = "replacement"
        state["last_item_name"] = item_name
        return {
            "action": "replacement",
            "amount": 0.0,
            "message": f"I've approved a fresh {item_name} replacement.",
            "reason": "Replacement approved after confirmation",
        }

    @staticmethod
    def _needs_photo(
        explicit_comp: bool,
        photo_present: bool,
        visual_evidence_useful: bool,
    ) -> bool:
        if photo_present:
            return False
        if explicit_comp and visual_evidence_useful:
            return True
        return False

    @staticmethod
    def _photo_case_key(issue_type: str, item_name: Optional[str]) -> str:
        return f"{issue_type}:{_lower(item_name)}"

    @staticmethod
    def _refund_hard_block(order_value: float, trust_score: float) -> bool:
        return order_value > Rules.HIGH_VALUE_THRESHOLD and trust_score <= Rules.REFUND_TRUST_THRESHOLD

    @staticmethod
    def _refund_allowed(
        trust_score: float,
        issue_severity: str,
        evidence_strength: str,
    ) -> bool:
        return (
            trust_score > Rules.REFUND_TRUST_THRESHOLD
            and issue_severity == "high"
            and evidence_strength == "strong"
        )

    @staticmethod
    def _preferred_refund_resolution(
        order_value: float,
        item_price: Optional[float],
        trust_score: float,
        desired_resolution: str,
        issue_type: str,
        issue_severity: str,
        evidence_strength: str,
        economic_preference: Optional[str],
    ) -> str:
        if desired_resolution != "refund":
            return desired_resolution
        if Rules._refund_hard_block(order_value, trust_score):
            return "replacement"

        if economic_preference in {"refund", "replacement", "escalate"}:
            return economic_preference
        if economic_preference == "escalate":
            return "refund"

        item_cost = float(item_price) if isinstance(item_price, (int, float)) else float(order_value)
        replacement_cost = item_cost + Rules.ESTIMATED_REPLACEMENT_OVERHEAD
        refund_cost = float(order_value)

        if issue_type == "portion_size":
            return "refund"
        if issue_type in {"wrong_item", "missing_item"} and evidence_strength == "strong":
            return "refund" if refund_cost <= replacement_cost else "replacement"
        if issue_type == "foreign_object" and issue_severity == "high":
            return "refund"
        if issue_type in {"spill_leak", "damaged"} and issue_severity == "high":
            return "replacement"
        if order_value <= Rules.LOW_VALUE_REFUND_THRESHOLD:
            return "refund"
        if refund_cost <= replacement_cost:
            return "refund"
        return "replacement"

    @staticmethod
    def _choose_economic_preference(
        desired_resolution: str,
        issue_type: str,
        issue_severity: str,
        evidence_strength: str,
        order_value: float,
        item_price: Optional[float],
        trust_score: float,
        assessed_preference: Optional[str],
        assessed_confidence: Optional[float],
    ) -> str:
        default = Rules._default_economic_preference(
            desired_resolution=desired_resolution,
            issue_type=issue_type,
            issue_severity=issue_severity,
            evidence_strength=evidence_strength,
            order_value=order_value,
            item_price=item_price,
            trust_score=trust_score,
        )
        if not assessed_preference:
            return default
        confidence = assessed_confidence or 0.0
        if confidence < 0.6:
            return default
        if not Rules._economic_preference_allowed(assessed_preference, issue_type, evidence_strength, desired_resolution):
            return default
        return assessed_preference

    @staticmethod
    def _default_economic_preference(
        desired_resolution: str,
        issue_type: str,
        issue_severity: str,
        evidence_strength: str,
        order_value: float,
        item_price: Optional[float],
        trust_score: float,
    ) -> str:
        if desired_resolution not in {"refund", "replacement"}:
            return "coupon"
        if desired_resolution == "replacement" and evidence_strength != "strong":
            return "coupon"
        if desired_resolution == "refund" and Rules._refund_hard_block(order_value, trust_score):
            return "replacement"
        if issue_type == "portion_size":
            return "refund"
        if issue_type == "foreign_object" and issue_severity == "high":
            return "refund"
        if desired_resolution == "refund" and evidence_strength == "strong" and order_value > Rules.LOW_VALUE_REFUND_THRESHOLD:
            item_cost = float(item_price) if isinstance(item_price, (int, float)) else float(order_value)
            replacement_cost = item_cost + Rules.ESTIMATED_REPLACEMENT_OVERHEAD
            return "replacement" if replacement_cost < float(order_value) else "refund"
        if desired_resolution == "refund" and issue_severity != "high":
            return "escalate"
        if issue_type in {"wrong_item", "missing_item"} and evidence_strength == "strong":
            return "replacement" if order_value > Rules.LOW_VALUE_REFUND_THRESHOLD else "refund"
        if issue_type in {"spill_leak", "damaged"} and issue_severity == "high":
            return "replacement"
        item_cost = float(item_price) if isinstance(item_price, (int, float)) else float(order_value)
        replacement_cost = item_cost + Rules.ESTIMATED_REPLACEMENT_OVERHEAD
        if desired_resolution == "refund":
            return "refund" if order_value <= replacement_cost else "replacement"
        return "replacement" if evidence_strength == "strong" else "coupon"

    @staticmethod
    def _economic_preference_allowed(
        economic_preference: str,
        issue_type: str,
        evidence_strength: str,
        desired_resolution: str,
    ) -> bool:
        if economic_preference == "replacement" and evidence_strength != "strong":
            return False
        if issue_type == "portion_size" and economic_preference == "replacement":
            return False
        if desired_resolution == "replacement" and economic_preference == "refund":
            return False
        return True

    @staticmethod
    def _adjust_coupon_amount(
        coupon_amount: float,
        order_value: float,
        item_price: Optional[float],
        desired_resolution: str,
        evidence_strength: str,
    ) -> float:
        if desired_resolution == "replacement" and evidence_strength != "strong":
            base = item_price if isinstance(item_price, (int, float)) and item_price > 0 else order_value
            if base <= 0:
                return 30.0
            return float(max(20, min(100, round(base * 0.2))))
        return coupon_amount

    @staticmethod
    def _estimated_replacement_cost(order_value: float, item_price: Optional[float]) -> float:
        item_cost = float(item_price) if isinstance(item_price, (int, float)) and item_price > 0 else float(order_value)
        return item_cost + Rules.ESTIMATED_REPLACEMENT_OVERHEAD

    @staticmethod
    def _replacement_negotiation_turn_limit(
        order_value: float,
        item_price: Optional[float],
        coupon_amount: float,
        issue_severity: str,
        evidence_strength: str,
        economic_preference: Optional[str],
    ) -> int:
        if evidence_strength != "strong":
            return Rules.MAX_COUPON_REINFORCEMENT_TURNS
        if economic_preference == "escalate":
            return 0
        if issue_severity != "high":
            return 0
        replacement_cost = Rules._estimated_replacement_cost(order_value, item_price)
        if replacement_cost - float(coupon_amount) < Rules.MIN_REPLACEMENT_NEGOTIATION_MARGIN:
            return 0
        return Rules.MAX_HIGH_SEVERITY_REPLACEMENT_NEGOTIATION_TURNS

    @staticmethod
    def _can_soft_approve_replacement(
        issue_type: str,
        order_value: float,
        item_price: Optional[float],
        trust_score: float,
        evidence_strength: str,
        economic_preference: Optional[str],
    ) -> bool:
        if issue_type not in {"quality", "temperature"}:
            return False
        if evidence_strength != "weak":
            return False
        if trust_score < Rules.REFUND_TRUST_THRESHOLD:
            return False
        replacement_cost = Rules._estimated_replacement_cost(order_value, item_price)
        if replacement_cost > 320:
            return False
        if economic_preference not in {None, "replacement", "coupon"}:
            return False
        return True

    @staticmethod
    def _replacement_steer_message(item_name: str, hard_block_refund: bool) -> str:
        if hard_block_refund:
            return f"I can't lock in a cash refund on this one, but I can still make this right with a fresh {item_name} if that works for you."
        return f"If the coupon doesn't feel enough, the cleaner fix I can do here is a fresh {item_name}."

    @staticmethod
    def _replacement_confirm_message(item_name: str) -> str:
        return f"I can get a fresh {item_name} remade for you instead. Want me to go ahead with that?"

    @staticmethod
    def _issue_negotiation_frame(issue_type: str, desired_resolution: str, evidence_strength: str) -> str:
        if issue_type == "delay":
            return "the delay was longer than it should've been"
        if issue_type == "portion_size":
            return "that felt light for what you paid"
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

    @staticmethod
    def _coupon_reinforcement_message(
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
        frame = Rules._issue_negotiation_frame(issue_type, desired_resolution, evidence_strength)
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
                        f"I get why you'd rather have cash back here. The fastest thing I can put through right now is the ₹{amount} coupon. "
                        f"If that doesn't work for you, I'll take it to the next step."
                    )
                return (
                    f"I get that you'd rather have cash back here because {frame}. The fastest fix I can put through right now "
                    f"is the ₹{amount} coupon."
                )
            return (
                f"I can still add the ₹{amount} coupon right now. If that doesn't work for you, "
                f"I'll move the case for review instead of promising a refund I can't approve here."
            )
        return (
            f"I can put through the ₹{amount} coupon now if that helps. "
            f"If not, tell me the fix you'd rather go with."
        )

    @staticmethod
    def _review_escalation_message(resolution_type: str) -> str:
        if resolution_type == "replacement":
            return "I can't verify enough on my side to approve a remake directly. If you'd like to take it further, please email hello@justswish.in and the team can review it from there."
        if resolution_type == "refund":
            return "I can't lock in a cash refund directly from what I can verify here. If you'd like to take it further, please email hello@justswish.in and the team can review it from there."
        return "I can't close this properly from chat alone. If you'd like to take it further, please email hello@justswish.in and the team can review it from there."

    @staticmethod
    def _choose_issue_severity(
        issue_type: str,
        assessed_issue_severity: Optional[str],
        assessed_issue_confidence: Optional[float],
        kitchen: Dict[str, Any],
        fleet: Dict[str, Any],
    ) -> str:
        confidence = assessed_issue_confidence or 0.0
        if assessed_issue_severity and confidence >= Rules.MIN_ASSESSMENT_CONFIDENCE:
            return assessed_issue_severity
        return Rules._default_issue_severity(issue_type, kitchen, fleet)

    @staticmethod
    def _choose_fault(
        inferred_fault: str,
        assessed_fault_hint: Optional[str],
        assessed_issue_confidence: Optional[float],
    ) -> str:
        if not assessed_fault_hint:
            return inferred_fault
        confidence = assessed_issue_confidence or 0.0
        if confidence < Rules.MIN_ASSESSMENT_CONFIDENCE:
            return inferred_fault
        if inferred_fault == "unclear":
            return assessed_fault_hint
        if assessed_fault_hint == inferred_fault:
            return inferred_fault
        return inferred_fault

    @staticmethod
    def _needs_clarification(
        complaint: str,
        issue_type: str,
        wants: str,
        info_query: str,
        turn_act: str,
        assessed_clarification: Optional[bool],
        assessed_issue_confidence: Optional[float],
        assessed_recommended_next_step: Optional[str],
        assessment_provided: bool = False,
    ) -> bool:
        if info_query != "none" or wants in {"refund", "replacement", "coupon", "credit"}:
            return False
        if turn_act in {"confirm", "reject", "switch_resolution", "ask_status", "ask_cause"}:
            return False
        confidence = assessed_issue_confidence or 0.0
        if (
            assessment_provided
            and issue_type not in {"other", "info_query"}
            and confidence >= 0.3
        ):
            return False
        if assessment_provided and confidence < Rules.MIN_ASSESSMENT_CONFIDENCE:
            return True
        if assessed_recommended_next_step == "clarify" and confidence >= 0.25:
            return True
        if assessed_clarification and confidence >= 0.25:
            return True
        text = _lower(complaint)
        short_tokens = re.findall(r"[a-z0-9]+", text)
        if len(short_tokens) <= 2 and confidence < 0.45:
            return True
        return False

    @staticmethod
    def _default_issue_severity(issue_type: str, kitchen: Dict[str, Any], fleet: Dict[str, Any]) -> str:
        if issue_type in {"foreign_object", "wrong_item", "missing_item", "spill_leak", "damaged"}:
            return "high"
        if issue_type == "delay":
            return "high" if (fleet.get("delay_mins") or 0) >= 20 else "medium"
        if issue_type in {"temperature", "quality"}:
            return "medium"
        return "low"

    @staticmethod
    def _clarification_message(state: Dict[str, Any], issue_type: str) -> str:
        item_name = state.get("active_item_name")
        if item_name and issue_type not in {"other", "quality"}:
            return f"I want to make sure I get this right. Was the issue with the {item_name} the quality, the temperature, or something else?"
        return "I want to make sure I get this right. Was the issue the item itself, the delivery, or were you looking for a refund or replacement?"

    @staticmethod
    def _evidence_strength(
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

    @staticmethod

    @staticmethod
    def _validated_enum(value: Any, allowed: set[str]) -> Optional[str]:
        if not isinstance(value, str):
            return None
        normalized = _lower(value)
        return normalized if normalized in allowed else None

    @staticmethod
    def _normalize_confidence(value: Any) -> Optional[float]:
        if isinstance(value, (int, float)):
            numeric = float(value)
        elif isinstance(value, str):
            try:
                numeric = float(value.strip())
            except ValueError:
                return None
        else:
            return None
        if 0 <= numeric <= 1:
            return numeric
        return None

    @staticmethod
    def _normalize_bool(value: Any) -> Optional[bool]:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = _lower(value)
            if lowered in {"true", "yes"}:
                return True
            if lowered in {"false", "no"}:
                return False
        return None

    @staticmethod
    def _choose_issue_type(
        detected_issue_type: str,
        assessed_issue_type: Optional[str],
        assessed_issue_confidence: Optional[float],
        assessment_provided: bool = False,
        assessed_info_query: Optional[str] = None,
    ) -> str:
        if assessment_provided:
            if assessed_info_query and assessed_info_query != "none" and assessed_issue_type in {None, "other", "info_query"}:
                return "info_query"
            if not assessed_issue_type:
                return "other"
            if assessed_issue_type == "other":
                return "other"
            confidence = assessed_issue_confidence or 0.0
            return assessed_issue_type if confidence >= Rules.MIN_ASSESSMENT_CONFIDENCE else "other"
        if not assessed_issue_type:
            return detected_issue_type
        if assessed_issue_type == "other":
            return detected_issue_type
        confidence = assessed_issue_confidence or 0.0
        if confidence >= Rules.MIN_ASSESSMENT_CONFIDENCE:
            return assessed_issue_type
        if detected_issue_type in {"quality", "other"} and confidence >= 0.3:
            return assessed_issue_type
        return detected_issue_type

    @staticmethod
    def _choose_requested_resolution(
        assessed_resolution: Optional[str],
        assessed_resolution_confidence: Optional[float],
        assessed_issue_confidence: Optional[float],
        assessment_provided: bool,
        state: Dict[str, Any],
        complaint: str,
    ) -> Optional[str]:
        if not assessment_provided:
            return None
        if not assessed_resolution:
            return state.get("desired_resolution", "none") if state.get("pending") == "photo" else "none"
        confidence = assessed_resolution_confidence
        if confidence is None:
            confidence = assessed_issue_confidence
        confidence = confidence or 0.0
        if confidence >= Rules.MIN_RESOLUTION_CONFIDENCE:
            return assessed_resolution
        if state.get("pending") == "photo":
            return state.get("desired_resolution", "none")
        return "none"

    @staticmethod
    def _choose_info_query(
        assessed_info_query: Optional[str],
        assessed_info_query_confidence: Optional[float],
        assessed_issue_confidence: Optional[float],
        assessment_provided: bool,
        complaint: str,
    ) -> Optional[str]:
        if not assessment_provided:
            return None
        if not assessed_info_query:
            return "none"
        confidence = assessed_info_query_confidence
        if confidence is None:
            confidence = assessed_issue_confidence
        confidence = confidence or 0.0
        return assessed_info_query if confidence >= Rules.MIN_INFO_QUERY_CONFIDENCE else "none"

    @staticmethod
    def _choose_turn_act(
        assessed_turn_act: Optional[str],
        assessed_turn_act_confidence: Optional[float],
        assessed_issue_confidence: Optional[float],
        assessment_provided: bool,
        complaint: str,
        wants: str,
        info_query: str,
    ) -> Optional[str]:
        if not assessment_provided:
            return None
        if not assessed_turn_act:
            return "none"
        confidence = assessed_turn_act_confidence
        if confidence is None:
            confidence = assessed_issue_confidence
        confidence = confidence or 0.0
        if confidence >= Rules.MIN_TURN_ACT_CONFIDENCE:
            return assessed_turn_act
        return "clarify"

    @staticmethod
    def _default_tone_guardrail(
        issue_type: str,
        issue_severity: str,
        wants: str,
        assurance_query: bool,
        info_query: str,
    ) -> str:
        if info_query != "none" or assurance_query:
            return "operational"
        if issue_type == "foreign_object":
            return "sensitive"
        if wants in {"refund", "replacement"}:
            return "persuasive" if issue_severity != "high" else "sensitive"
        if issue_severity == "high":
            return "sensitive"
        return "neutral"

    @staticmethod
    def _choose_tone_guardrail(
        issue_type: str,
        issue_severity: str,
        wants: str,
        assurance_query: bool,
        info_query: str,
        assessed_tone_guardrail: Optional[str],
        assessed_issue_confidence: Optional[float],
    ) -> str:
        default = Rules._default_tone_guardrail(issue_type, issue_severity, wants, assurance_query, info_query)
        confidence = assessed_issue_confidence or 0.0
        if assessed_tone_guardrail and confidence >= Rules.MIN_ASSESSMENT_CONFIDENCE:
            return assessed_tone_guardrail
        return default

    @staticmethod
    def _choose_negotiation_allowed(
        wants: str,
        recommended_next_step: Optional[str],
        assessed_negotiation_allowed: Optional[bool],
        assessed_issue_confidence: Optional[float],
    ) -> bool:
        default = wants in {"refund", "replacement"} and recommended_next_step != "escalate"
        confidence = assessed_issue_confidence or 0.0
        if assessed_negotiation_allowed is not None and confidence >= Rules.MIN_ASSESSMENT_CONFIDENCE:
            return assessed_negotiation_allowed
        return default

    @staticmethod
    def _choose_negotiation_strength(
        issue_type: str,
        issue_severity: str,
        wants: str,
        negotiation_allowed: bool,
        assessed_strength: Optional[str],
        assessed_issue_confidence: Optional[float],
    ) -> str:
        if not negotiation_allowed or wants not in {"refund", "replacement"}:
            default = "none"
        elif issue_type == "foreign_object" or issue_severity == "high":
            default = "light"
        else:
            default = "medium"
        confidence = assessed_issue_confidence or 0.0
        if assessed_strength and confidence >= Rules.MIN_ASSESSMENT_CONFIDENCE:
            return assessed_strength
        return default

    @staticmethod
    def _visual_evidence_useful(
        issue_type: str,
        order_items: Dict[str, Any],
        assessed_visual_evidence: Optional[bool],
        assessed_issue_confidence: Optional[float],
    ) -> bool:
        item_count = len(order_items.get("items", [])) if isinstance(order_items, dict) else 0
        default_useful = issue_type in PHYSICAL_ISSUE_TYPES
        if issue_type == "missing_item" and item_count < 2:
            default_useful = False

        if assessed_visual_evidence is None:
            return default_useful

        confidence = assessed_issue_confidence or 0.0
        if confidence < Rules.MIN_VISUAL_DECISION_CONFIDENCE:
            return default_useful

        if not default_useful:
            return False
        return assessed_visual_evidence

    @staticmethod
    def _detect_issue_type(complaint: str, item_name: str = "") -> str:
        text = _lower(complaint)
        if Rules._is_payment_or_billing_query(text):
            return "info_query"
        if Rules._is_non_delivery_signal(text):
            return "missing_item"
        if Rules._detect_info_query(complaint) != "none":
            return "info_query"
        if Rules._looks_like_ingredient_mismatch(text):
            return "quality"
        if Rules._looks_like_dietary_violation(text):
            return "foreign_object"
        if Rules._is_wrong_order_signal(text):
            return "wrong_item"
        if any(word in text for word in ["missing", "didn't get", "did not get", "not delivered", "left out"]):
            return "missing_item"
        if any(word in text for word in ["hair", "plastic", "stone", "glass", "insect", "bug"]):
            return "foreign_object"
        if any(word in text for word in ["spilled", "leaked", "leaking", "opened and spilled", "burst open"]):
            return "spill_leak"
        if any(word in text for word in ["damaged", "crushed", "broken", "soggy packaging"]):
            return "damaged"
        if any(
            word in text
            for word in [
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
            ]
        ):
            return "portion_size"
        if re.search(r"\b(?:too|very)\s+less\b", text):
            return "portion_size"
        if re.search(r"\b(?:was|were|is)\s+less\b", text):
            return "portion_size"
        if any(word in text for word in ["sweet", "meetha", "salty", "bland", "burnt", "raw", "soggy", "terrible", "inedible", "bad taste"]):
            return "quality"
        if Rules._is_temperature_signal(text):
            return "temperature"
        if any(word in text for word in ["late", "delay", "delayed", "where is my order", "eta"]):
            return "delay"
        if item_name and item_name.lower() in text:
            return "quality"
        return "quality"

    @staticmethod
    def _strong_text_issue_override(text: str, current_issue_type: str) -> str:
        if not text:
            return current_issue_type
        if Rules._is_payment_or_billing_query(text):
            return "info_query"
        if Rules._is_non_delivery_signal(text):
            return "missing_item"
        if Rules._is_wrong_order_signal(text):
            return "wrong_item"
        if Rules._is_spill_contamination_signal(text):
            return "spill_leak"
        if Rules._is_temperature_signal(text):
            return "temperature"
        if any(phrase in text for phrase in ["order hi nahi", "not my order", "different items", "kisi aur ka naam", "someone else"]):
            return "wrong_item"
        if Rules._looks_like_ingredient_mismatch(text):
            return "quality"
        if Rules._looks_like_dietary_violation(text):
            return "foreign_object"
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
        if re.search(r"\b(spill|spilled|spillage|leak|leaked|leaking|gir gaya|gir gya|gir gayi|gir gayi thi)\b", text):
            return "spill_leak" if spill_context else "damaged"
        if "bag me spill" in text or "bag mein spill" in text or "andar spill" in text:
            return "spill_leak"
        if re.search(r"\b(quantity|qty|portion)\s+(bahut\s+)?(kam|less|low)\b", text):
            return "portion_size"
        if re.search(r"\b(kam|less)\s+(quantity|portion)\b", text):
            return "portion_size"
        if any(phrase in text for phrase in ["bahut kam thi", "bahut kam tha", "quantity kam thi", "quantity kam tha", "size very small", "size bahut small", "pieces small"]):
            return "portion_size"
        return current_issue_type

    @staticmethod
    def _detect_requested_resolution(complaint: str, state: Dict[str, Any]) -> str:
        text = _lower(complaint)
        if Rules._negates_resolution(text, "refund"):
            return state.get("desired_resolution", "none") if state.get("pending") in {"coupon", "refund_amount"} else "none"
        if Rules._negates_resolution(text, "replacement"):
            return state.get("desired_resolution", "none") if state.get("pending") in {"coupon", "replacement_confirm"} else "none"
        if Rules._mentions_replacement(text):
            return "replacement"
        if Rules._mentions_refund(text):
            return "refund"
        if "coupon" in text:
            return "coupon"
        if "credit" in text or "wallet" in text:
            return "credit"
        return state.get("desired_resolution", "none") if state.get("pending") == "photo" else "none"

    @staticmethod
    def _detect_turn_act(complaint: str, requested_resolution: str, info_query: str) -> str:
        text = _lower(complaint)
        if info_query == "status":
            return "ask_status"
        if any(phrase in text for phrase in ["why was", "how did", "what happened", "why did"]):
            return "ask_cause"
        if requested_resolution in {"refund", "replacement", "coupon", "credit"} and any(
            phrase in text for phrase in ["instead", "rather", "leave", "just get me", "i want", "i need", "get me"]
        ):
            return "switch_resolution"
        if Rules._accepted(text):
            return "confirm"
        if Rules._rejected(text):
            return "reject"
        if requested_resolution in {"refund", "replacement"}:
            return "switch_resolution"
        return "none"

    @staticmethod
    def _is_resolution_only_turn(complaint: str) -> bool:
        text = _lower(complaint)
        if not text:
            return False
        if Rules._extract_refund_percentage(text) is not None or Rules._accepted(text) or Rules._rejected(text):
            return True
        if Rules._mentions_refund(text) or Rules._mentions_replacement(text):
            stripped = re.sub(r"\b(i|me|my|need|want|can|get|a|an|the|full|just|only|please|no)\b", " ", text)
            tokens = [tok for tok in re.findall(r"[a-z0-9]+", stripped) if tok]
            resolution_words = {"refund", "replacement", "replace", "another", "send", "fresh", "money", "back"}
            return all(token in resolution_words for token in tokens) if tokens else True
        return False

    @staticmethod
    def _looks_like_dietary_violation(text: str) -> bool:
        if not text:
            return False
        non_veg_terms = [
            "chicken",
            "chick",
            "egg",
            "meat",
            "fish",
            "mutton",
            "beef",
            "prawn",
            "pork",
        ]
        veg_context_terms = [
            "veg",
            "vegetarian",
            "veggie",
            "paneer",
        ]
        has_non_veg_term = any(term in text for term in non_veg_terms) or Rules._contains_fuzzy_keyword(
            text, non_veg_terms, threshold=0.74
        )
        if not has_non_veg_term:
            return False
        if any(re.search(rf"\b{re.escape(term)}\b", text) for term in veg_context_terms):
            return True
        return bool(re.search(r"\b(piece|bits?|chunks?)\s+of\s+(chick(?:en)?|egg|meat|fish|mutton|beef|prawn|pork)\b", text))

    @staticmethod
    def _looks_like_ingredient_mismatch(text: str) -> bool:
        if not text:
            return False
        benign_food_terms = [
            "vegetable",
            "veggies",
            "onion",
            "capsicum",
            "pepper",
            "corn",
            "sauce",
            "masala",
            "spice",
            "herb",
        ]
        mismatch_phrases = [
            r"\bpiece of (?:a |an )?(vegetable|veggies|onion|capsicum|pepper|corn)\b",
            r"\b(extra|unexpected|wrong)\s+(vegetable|veggies|onion|capsicum|pepper|corn|sauce)\b",
        ]
        if any(re.search(pattern, text) for pattern in mismatch_phrases):
            return True
        if "shouldn't be in" in text and any(term in text for term in benign_food_terms):
            return True
        return False

    @staticmethod
    def _looks_like_prep_anomaly(text: str) -> bool:
        return Rules._looks_like_ingredient_mismatch(text)

    @staticmethod
    def _is_emotional_followup(text: str) -> bool:
        if not text:
            return False
        emotional_phrases = [
            "this is outrageous",
            "outrageous",
            "ridiculous",
            "unacceptable",
            "this is bad",
            "this is terrible",
            "how am i supposed",
            "seriously",
            "excuse me",
            "what the hell",
            "wtf",
            "not acceptable",
            "this is not okay",
            "not okay",
        ]
        if any(phrase in text for phrase in emotional_phrases):
            return True
        tokens = re.findall(r"[a-z0-9]+", text)
        return len(tokens) <= 4 and any(word in text for word in ["wow", "seriously", "really"])

    @staticmethod
    def _has_concrete_issue_signal(text: str) -> bool:
        if not text:
            return False
        concrete_keywords = [
            "cold",
            "hot",
            "late",
            "delay",
            "delayed",
            "missing",
            "wrong",
            "spilled",
            "spill",
            "leak",
            "leaked",
            "damaged",
            "broken",
            "plastic",
            "glass",
            "hair",
            "stone",
            "bug",
            "insect",
            "portion",
            "quantity",
            "small",
            "taste",
            "burnt",
            "raw",
            "soggy",
            "stale",
            "uncooked",
            "undercooked",
            "overcooked",
        ]
        return any(keyword in text for keyword in concrete_keywords)

    @staticmethod
    def _has_strong_new_issue_signal(text: str, current_issue_type: str) -> bool:
        if not text:
            return False
        detected = Rules._strong_text_issue_override(text, Rules._detect_issue_type(text))
        if detected in {"info_query", "other"}:
            return False
        if detected == current_issue_type:
            return False
        if current_issue_type == "temperature" and detected == "delay":
            return False
        if Rules._is_followup_or_evidence_turn(text):
            return False
        return Rules._has_concrete_issue_signal(text)

    @staticmethod
    def _is_followup_or_evidence_turn(text: str) -> bool:
        if not text:
            return False
        followup_phrases = [
            "photo",
            "video",
            "attached",
            "upload",
            "proof",
            "review",
            "escalate",
            "supervisor",
            "update",
            "app",
            "what happens now",
            "next step",
            "confirm",
            "noted",
            "explain this again",
            "keep it practical",
            "closed without resolution",
            "wait for the update",
            "order context",
            "feedback",
            "safety concern",
            "safety issue",
            "safety",
            "serious for me",
            "serious",
            "same issue",
            "matlab",
            "regular customer",
            "trust",
            "veg item",
            "order kiya tha",
            "chahiye tha",
            "same item",
            "otherwise",
            "reopen",
            "start again",
            "resolution chahiye",
            "resolution",
            "mere items",
            "my items",
            "baaki items",
        ]
        if any(phrase in text for phrase in followup_phrases):
            return True
        tokens = re.findall(r"[a-z0-9]+", text)
        return len(tokens) <= 5 and any(token in text for token in ["okay", "fine", "thanks", "yes", "haan"])

    @staticmethod
    def _is_non_delivery_signal(text: str) -> bool:
        if not text:
            return False
        delivered_not_received = (
            ("delivered" in text or "deliver" in text or "app" in text)
            and any(phrase in text for phrase in ["receive nahi", "not received", "did not receive", "didn't receive", "nahi mila", "not got"])
        )
        rider_problem = any(phrase in text for phrase in ["rider", "delivery partner", "partner", "driver"]) and any(
            phrase in text for phrase in ["item nahi", "receive nahi", "not received", "delivered dikha", "answer nahi", "call"]
        )
        return delivered_not_received or rider_problem or "order receive nahi hua" in text

    @staticmethod
    def _is_wrong_order_signal(text: str) -> bool:
        if not text:
            return False
        direct_patterns = [
            "wrong item",
            "different item",
            "different items",
            "got something else",
            "not what i ordered",
            "order hi nahi",
            "not my order",
            "kisi aur ka naam",
            "someone else",
        ]
        if any(pattern in text for pattern in direct_patterns):
            return True
        return bool(re.search(r"\b(order(?:ed)?|order kiya tha|manga tha).{0,60}\b(but|par|lekin).{0,60}\b(aa gaya|aaya|got|received)\b", text))

    @staticmethod
    def _is_spill_contamination_signal(text: str) -> bool:
        if not text:
            return False
        spillable = ["sharbat", "coffee", "shake", "drink", "sauce", "gravy", "curry"]
        contaminated = ["box", "bag", "container", "food", "item", "pasta", "bowl"]
        return any(term in text for term in spillable) and any(term in text for term in contaminated) and any(
            phrase in text for phrase in ["lag gaya", "lag gya", "spread", "soaked", "wet"]
        )

    @staticmethod
    def _is_temperature_signal(text: str) -> bool:
        if not text:
            return False
        if "cold coffee" in text and not any(phrase in text for phrase in ["warm", "not cold", "should be cold", "chilled nahi"]):
            return False
        return any(word in text for word in ["not hot", "warm", "chilled", "cold aa", "cold aaya", "cold aya", "bilkul cold", "garam hona", "thanda"])

    @staticmethod
    def _is_payment_or_billing_query(text: str) -> bool:
        if not text:
            return False
        payment_terms = ["payment", "upi", "debit", "debited", "transaction", "amount cut", "cut gaya", "billing", "charged"]
        order_failure_terms = ["order fail", "failed order", "order failed", "fail ho gaya", "refund timeline"]
        if any(term in text for term in payment_terms):
            return True
        return any(term in text for term in order_failure_terms)

    @staticmethod
    def _should_inherit_case_issue_type(
        text: str,
        state: Dict[str, Any],
        issue_type: str,
        wants: str,
        info_query: str,
        turn_act: str,
    ) -> bool:
        case_issue_type = state.get("case_issue_type")
        if not case_issue_type:
            return False
        if state.get("last_action") == "escalate":
            return True
        if info_query != "none" or issue_type == "info_query":
            return False
        sticky_types = {
            "missing_item",
            "wrong_item",
            "spill_leak",
            "damaged",
            "foreign_object",
            "portion_size",
            "temperature",
            "delay",
        }
        if case_issue_type in sticky_types and Rules._is_followup_or_evidence_turn(text):
            return not Rules._has_strong_new_issue_signal(text, case_issue_type)
        if wants in {"refund", "replacement", "coupon", "credit"}:
            return not Rules._has_strong_new_issue_signal(text, case_issue_type)
        if turn_act not in {"none", "clarify"}:
            return False
        if Rules._has_concrete_issue_signal(text):
            return False
        return Rules._is_emotional_followup(text)

    @staticmethod
    def _detect_info_query(complaint: str) -> str:
        text = _lower(complaint)
        item_patterns = [
            "what were the items",
            "what are the items",
            "what items",
            "items in this order",
            "show items",
            "what did i order",
            "what was in this order",
        ]
        total_patterns = [
            "how much was this order",
            "what was the total",
            "order total",
            "how much did i pay",
        ]
        status_patterns = [
            "where is my order",
            "what is the status",
            "status batao",
            "status btao",
            "status kya hai",
            "order status",
            "delivered dikha",
            "delivered dikha raha",
            "dikha raha hai",
            "when was it delivered",
            "how long",
            "eta",
            "when will it arrive",
            "when will i get it",
            "how long will it take",
            "in how long",
        ]
        if any(pattern in text for pattern in item_patterns):
            return "items"
        if any(pattern in text for pattern in total_patterns):
            return "total"
        if any(pattern in text for pattern in status_patterns):
            return "status"
        return "none"

    @staticmethod
    def _detect_assurance_query(complaint: str) -> bool:
        text = _lower(complaint)
        patterns = [
            "are you sure",
            "will it be cold",
            "will it be hot",
            "this time",
            "sure it will",
        ]
        return any(pattern in text for pattern in patterns)

    @staticmethod
    def _mentions_refund(text: str) -> bool:
        if Rules._negates_resolution(text, "refund"):
            return False
        return any(word in text for word in ["refund", "money back", "my money", "cash back"]) or Rules._contains_fuzzy_keyword(
            text, ["refund"]
        )

    @staticmethod
    def _mentions_replacement(text: str) -> bool:
        if Rules._negates_resolution(text, "replacement"):
            return False
        return any(word in text for word in ["replacement", "replace", "another one", "send another", "get me another", "fresh order", "re-deliver", "redeliver"]) or Rules._contains_fuzzy_keyword(
            text, ["replacement", "replace", "redeliver"]
        )

    @staticmethod
    def _negates_resolution(text: str, resolution: str) -> bool:
        if not text:
            return False
        if resolution == "refund":
            patterns = [
                r"\brefund\s+(nahi|nahin|not)\b",
                r"\b(no|not|dont|don't|do not)\s+(want\s+)?refund\b",
                r"\brefund\s+nahi\s+chahiye\b",
            ]
        else:
            patterns = [
                r"\b(replacement|replace|redelivery|re-delivery)\s+(nahi|nahin|not)\b",
                r"\b(no|not|dont|don't|do not)\s+(want\s+)?(replacement|replace|redelivery|re-delivery)\b",
                r"\b(replacement|redelivery|re-delivery)\s+nahi\s+chahiye\b",
            ]
        return any(re.search(pattern, text) for pattern in patterns)

    @staticmethod
    def _contains_fuzzy_keyword(text: str, keywords: List[str], threshold: float = 0.78) -> bool:
        words = re.findall(r"[a-z0-9]+", _lower(text))
        for word in words:
            if len(word) < 4:
                continue
            for keyword in keywords:
                if SequenceMatcher(None, word, keyword).ratio() >= threshold:
                    return True
        return False

    @staticmethod
    def _match_item(order_items: Dict[str, Any], complaint: str) -> Dict[str, Any]:
        items = order_items.get("items", []) if isinstance(order_items, dict) else []
        if not items:
            return {}

        complaint_lower = _lower(complaint)
        scored: List[tuple[int, Dict[str, Any]]] = []
        for item in items:
            name = _lower(item.get("name"))
            score = 0
            for token in re.findall(r"[a-z0-9]+", name):
                if token and token in complaint_lower:
                    score += len(token)
                else:
                    for word in re.findall(r"[a-z0-9]+", complaint_lower):
                        if len(token) >= 4 and SequenceMatcher(None, token, word).ratio() >= 0.82:
                            score += len(token)
                            break
            scored.append((score, item))

        scored.sort(key=lambda entry: entry[0], reverse=True)
        return scored[0][1] if scored and scored[0][0] > 0 else {}

    @staticmethod
    def _find_item_by_name(order_items: Dict[str, Any], item_name: str) -> Dict[str, Any]:
        items = order_items.get("items", []) if isinstance(order_items, dict) else []
        target = _lower(item_name)
        best_match = {}
        best_score = 0.0
        for item in items:
            name = _lower(item.get("name"))
            if not name:
                continue
            score = SequenceMatcher(None, name, target).ratio()
            if target in name:
                score += 0.2
            if score > best_score:
                best_score = score
                best_match = item
        return best_match if best_score >= 0.6 else {}

    @staticmethod
    def _complaint_mentions_item(complaint: str, item: Dict[str, Any]) -> bool:
        complaint_lower = _lower(complaint)
        name = _lower(item.get("name"))
        if not name:
            return False
        for token in re.findall(r"[a-z0-9]+", name):
            if len(token) >= 4 and token in complaint_lower:
                return True
        return False

    @staticmethod
    def _infer_fault(kitchen: Dict[str, Any], fleet: Dict[str, Any], issue_type: str) -> str:
        quality_out = _lower(kitchen.get("quality_out"))
        temp = _lower(kitchen.get("temperature_check"))
        prep_time = kitchen.get("prep_time_mins")
        delay = fleet.get("delay_mins") or 0

        if issue_type == "delay":
            return "delivery"
        if issue_type in {"wrong_item", "missing_item", "foreign_object"}:
            return "kitchen"
        if issue_type == "spill_leak":
            if quality_out == "bad":
                return "kitchen"
            if delay and delay >= 5:
                return "delivery"
            return "unclear"
        if issue_type == "damaged":
            if quality_out in {"bad", "fair"}:
                return "kitchen"
            if delay and delay >= 10:
                return "delivery"
            return "unclear"
        if issue_type == "portion_size":
            return "unclear"
        if issue_type == "temperature":
            if quality_out == "good" and delay and delay > 10:
                return "delivery"
            if quality_out == "fair" or temp in {"warm", "cold"}:
                return "kitchen"
            return "unclear"
        if quality_out == "bad":
            return "kitchen"
        if quality_out == "fair" or temp in {"warm", "cold"}:
            return "kitchen"
        if isinstance(prep_time, (int, float)) and prep_time > 0 and prep_time < 5:
            return "kitchen"
        if delay and delay > 10:
            return "delivery"
        return "unclear"

    @staticmethod
    def _coupon_amount(order_value: float, item_price: Optional[float]) -> float:
        base = item_price if isinstance(item_price, (int, float)) and item_price > 0 else order_value
        if base <= 0:
            return float(Rules.STANDARD_COUPON_AMOUNT)
        return float(max(30, min(100, round(base * 0.3))))

    @staticmethod
    def _extract_refund_percentage(text: str) -> Optional[float]:
        lowered = _lower(text)
        if any(word in lowered for word in ["full", "100%", "hundred"]):
            return 1.0
        if "75%" in lowered:
            return 0.75
        if "50%" in lowered or "half" in lowered:
            return 0.5
        if "25%" in lowered or "quarter" in lowered:
            return 0.25
        match = re.search(r"\b(25|50|75|100)\b", lowered)
        if match:
            value = int(match.group(1))
            return value / 100.0
        return None

    @staticmethod
    def _accepted(text: str) -> bool:
        strong_phrases = [
            "yes",
            "yeah",
            "yep",
            "yess",
            "yesss",
            "ok",
            "okay",
            "sure",
            "do it",
            "go ahead",
            "same items",
            "that works",
            "works for me",
            "sounds good",
        ]
        return any(re.search(rf"\b{re.escape(phrase)}\b", text) for phrase in strong_phrases)

    @staticmethod
    def _rejected(text: str) -> bool:
        return any(
            phrase in text
            for phrase in ["no", "nah", "nope", "don't want", "do not want", "instead", "not enough"]
        )

    @staticmethod
    def _is_abusive(text: str) -> bool:
        lowered = _lower(text)
        return any(word in lowered for word in ["bitch", "fuck you", "motherf", "chutiya", "madarch"])

    @staticmethod
    def _detect_compensation_request(history: List[Dict[str, str]]) -> bool:
        user_messages = [msg.get("content", "") for msg in history if msg.get("role") == "user"]
        if not user_messages:
            return False
        return Rules._detect_requested_resolution(user_messages[-1], {}) != "none"

    @staticmethod
    def _detect_confirmation(history: List[Dict[str, str]], photo_url: Optional[str] = None, photo_in_session: bool = False) -> bool:
        last_bot = next((msg.get("content", "") for msg in reversed(history) if msg.get("role") == "bot"), "")
        last_user = next((msg.get("content", "") for msg in reversed(history) if msg.get("role") == "user"), "")
        if not last_bot or not last_user:
            return False
        if "photo" in last_bot.lower() and not photo_url and not photo_in_session:
            return False
        return Rules._accepted(_lower(last_user)) or Rules._extract_refund_percentage(last_user) is not None

    @staticmethod
    def _photo_message(order_value: float, issue_type: str) -> str:
        if issue_type == "missing_item":
            return "Can you send a quick photo of what arrived? That helps me verify the missing item fast."
        return "Can you send a quick photo of the food? That helps me sort this faster."

    @staticmethod
    def _info_message(
        item_name: str,
        issue_type: str,
        fault: str,
        kitchen: Dict[str, Any],
        fleet: Dict[str, Any],
        trust: Dict[str, Any],
        last_bot_msg: str,
    ) -> str:
        prefix = ""
        if issue_type in {"foreign_object", "wrong_item", "missing_item", "damaged", "spill_leak"}:
            prefix = (
                Rules._pick_opening(
                    [
                        "That shouldn't have happened.",
                        "That’s not what we want reaching you.",
                        "That’s not good enough from our side.",
                    ],
                    last_bot_msg,
                )
                + " "
            )

        if issue_type == "delay":
            delay = fleet.get("delay_mins")
            if delay:
                return f"{prefix}Your {item_name} is running about {delay} mins behind and this looks like a delivery-side delay."
            return f"{prefix}I'm seeing a delivery delay on your {item_name}."
        if issue_type == "wrong_item":
            return f"{prefix}This looks like the wrong item was packed before dispatch, so that points back to our packing side."
        if issue_type == "missing_item":
            return f"{prefix}It looks like part of the order may not have made it into the bag before dispatch."
        if issue_type == "foreign_object":
            return f"{prefix}This looks like a kitchen-side safety miss, so I'm noting it seriously."
        if issue_type == "spill_leak":
            delay = fleet.get("delay_mins")
            if fault == "delivery" and delay:
                return f"{prefix}The {item_name} was marked okay at dispatch, so this may have spilled in transit, especially with the {delay}-minute delay."
            if fault == "kitchen":
                return f"{prefix}This looks more like a sealing or packing miss before the {item_name} left the kitchen."
            return f"{prefix}I can see the spill on the {item_name}, but the logs don't cleanly show whether it happened while packing or during delivery."
        if issue_type == "damaged":
            if fault == "delivery":
                return f"{prefix}The {item_name} seems to have left the kitchen okay, so the damage may have happened in transit."
            if fault == "kitchen":
                return f"{prefix}This looks more like a packing-side issue before the {item_name} went out."
            return f"{prefix}I can see the damage on the {item_name}, but the logs don't show clearly whether it happened while packing or on the way."
        if issue_type == "temperature":
            delay = fleet.get("delay_mins")
            if fault == "delivery" and delay:
                return f"{prefix}The {item_name} seems to have left in okay shape, but the {delay}-minute delivery delay could have affected the temperature."
            if fault == "kitchen":
                return f"{prefix}The kitchen-side checks on the {item_name} weren't strong enough before dispatch, so that lines up more with prep than delivery."
            return f"{prefix}I can see the temperature issue on the {item_name}, but the logs don't clearly show whether it shifted in prep or during delivery."
        if issue_type == "portion_size":
            return f"{prefix}I can't verify portion size reliably from the logs after delivery, but I'm logging this against the kitchen for the {item_name} because it sounds light for what you paid."

        if fault == "kitchen":
            quality = kitchen.get("quality_out") or "fair"
            return f"{prefix}The kitchen log on the {item_name} suggests it wasn't at its best when it went out. The recorded quality check was {quality}."
        if fault == "delivery":
            delay = fleet.get("delay_mins") or "a few"
            return f"{prefix}The {item_name} looks okay from the kitchen side, but the delivery leg picked up about a {delay}-minute delay."
        return f"{prefix}The logs don't point to one clean miss on either kitchen or delivery."

    @staticmethod
    def _followup_info_message(
        item_name: str,
        issue_type: str,
        fault: str,
        kitchen: Dict[str, Any],
        fleet: Dict[str, Any],
        last_bot_msg: str,
    ) -> str:
        if issue_type == "delay":
            delay = fleet.get("delay_mins")
            if delay:
                return f"I'm seeing about a {delay}-minute delivery delay on the {item_name}."
            return f"I'm seeing a delivery delay on the {item_name}."
        if issue_type == "wrong_item":
            return "This still looks like a packing mix-up before dispatch."
        if issue_type == "missing_item":
            return "This still looks like one part of the order never made it into the bag."
        if issue_type == "foreign_object":
            return "This points back to a kitchen-side safety issue, not something that should have reached you."
        if issue_type == "spill_leak":
            delay = fleet.get("delay_mins")
            if fault == "delivery" and delay:
                return f"The {item_name} seems to have gone wrong on the way, not at prep, especially with that {delay}-minute delay."
            if fault == "kitchen":
                return f"This still looks more like the {item_name} wasn't sealed or packed properly before dispatch."
            return f"I can see the spill issue, but the logs still don't prove whether it happened while packing or in transit."
        if issue_type == "damaged":
            if fault == "delivery":
                return f"The {item_name} seems to have taken the hit in transit rather than at prep."
            if fault == "kitchen":
                return f"This still looks more like a packing-side issue before the {item_name} went out."
            return f"I can see the damage, but the logs still don't clearly place it on kitchen or delivery."
        if issue_type == "temperature":
            delay = fleet.get("delay_mins")
            if fault == "delivery" and delay:
                return f"The {item_name} seems to have lost temperature during the delivery leg, especially with that {delay}-minute delay."
            if fault == "kitchen":
                return f"The kitchen checks on the {item_name} don't look strong enough before dispatch."
            return f"I can see the temperature issue, but the logs don't cleanly pin it on prep or delivery."
        if issue_type == "portion_size":
            return f"I still can't verify portion size reliably after delivery, but I've noted it as kitchen feedback on the {item_name}."

        if fault == "kitchen":
            return f"The kitchen log on the {item_name} suggests it wasn't at its best when it went out."
        if fault == "delivery":
            return f"The {item_name} looks okay from the kitchen side, and the delivery leg is the part that looks weaker here."
        return "The logs still don't point to one clean cause."

    @staticmethod
    def _info_query_message(
        info_query: str,
        order_details: Dict[str, Any],
        order_items: Dict[str, Any],
        fleet: Dict[str, Any],
        state: Dict[str, Any],
        last_bot_msg: str,
    ) -> str:
        if info_query == "items":
            items = order_items.get("items", []) if isinstance(order_items, dict) else []
            if not items:
                return "I’m not seeing the item list properly right now, but I can still help if you tell me what you need from the order."
            names = [item.get("name", "item") for item in items[:3]]
            summary = ", ".join(names[:-1]) + f" and {names[-1]}" if len(names) > 1 else names[0]
            if len(items) > 3:
                summary += f", plus {len(items) - 3} more item{'s' if len(items) - 3 != 1 else ''}"
            lead = Rules._pick_opening(["This order had", "You had", "Looks like this one had"], last_bot_msg)
            return f"{lead} {summary}."
        if info_query == "total":
            total = order_details.get("total_amount")
            if total:
                lead = Rules._pick_opening(["This order total was", "You paid", "The total on this one was"], last_bot_msg)
                return f"{lead} ₹{float(total):.0f}."
            return "I’m not getting the total cleanly right now, but I can still help with the order."
        if info_query == "status":
            if state.get("last_action") == "replacement":
                item_name = state.get("last_item_name") or state.get("active_item_name") or "replacement"
                return f"The fresh {item_name} has been approved. I don't have a live ETA here yet, but these usually go out in around 15 to 20 mins and you'll see the update in-app."
            delivered = order_details.get("delivered_at")
            status = order_details.get("status", "unknown")
            delay = fleet.get("delay_mins")
            if delivered:
                return f"This order is marked {status} and it shows as delivered at {delivered}."
            if delay:
                return f"It’s still in progress and running about {delay} mins behind right now."
            return f"This order is marked {status} right now."
        return "Tell me what you want to know about the order and I’ll pull that up."

    @staticmethod
    def _assurance_message(state: Dict[str, Any], issue_type: str, fault: str) -> str:
        item_name = state.get("last_item_name") or state.get("active_item_name") or "item"
        if issue_type == "temperature" or "cold" in _lower(item_name):
            return f"I've flagged this as a fresh cold-item remake for the kitchen. It should leave cold this time, but I don't want to promise what delivery time does after pickup."
        if fault == "delivery":
            return f"I've flagged the {item_name} remake already. Kitchen will send a fresh one, but I can't promise the delivery leg won't affect it again."
        return f"I've flagged the {item_name} remake already, so kitchen will make it fresh again. I just don't want to overpromise beyond that."

    @staticmethod
    def _coupon_offer_message(
        coupon_amount: float,
        issue_type: str,
        issue_severity: str,
        desired_resolution: str,
        evidence_strength: str,
        economic_preference: Optional[str],
        tone_guardrail: str,
        negotiation_allowed: bool,
        negotiation_strength: str,
        order_value: float,
        item_price: Optional[float],
        trust_score: float,
        item_name: str,
        last_bot_msg: str,
    ) -> str:
        amount = int(coupon_amount)
        frame = Rules._issue_negotiation_frame(issue_type, desired_resolution, evidence_strength)
        if desired_resolution == "replacement" and evidence_strength != "strong":
            return (
                f"I want to keep this moving for you. Since I can't verify enough for a remake yet, I can add a ₹{amount} coupon right now. "
                f"Want me to put that through?"
            )
        if desired_resolution == "replacement" and Rules._replacement_negotiation_turn_limit(
            order_value=order_value,
            item_price=item_price,
            coupon_amount=coupon_amount,
            issue_severity=issue_severity,
            evidence_strength=evidence_strength,
            economic_preference=economic_preference,
        ) > 0:
            if tone_guardrail == "sensitive" or negotiation_strength == "light":
                return (
                    f"I can put through a ₹{amount} coupon right away for this. "
                    f"If that still doesn't work for you, we can take the next step."
                )
            return (
                f"I can put through a ₹{amount} coupon right away for this, and that's the quickest fix I can lock in immediately. "
                f"Want me to add that?"
            )
        if desired_resolution == "replacement":
            if not negotiation_allowed:
                return f"I can get a fresh {item_name} remade for you instead. Want me to go ahead with that?"
            return (
                f"I can sort this fastest with a ₹{amount} coupon right away since {frame}. "
                f"If that still doesn't work for you, we can look at a fresh {item_name}."
            )
        if Rules._refund_hard_block(order_value, trust_score):
            return f"I can add a ₹{amount} coupon right away here. If that still doesn't land right, I'll take you through the next option."
        if issue_type == "delay":
            return f"I can offer a ₹{amount} coupon for the delay right away if that works for you."
        if issue_type == "portion_size":
            return f"I can add a ₹{amount} coupon right away for this since it felt short for what you paid. Want me to put that through?"
        if issue_type == "foreign_object":
            if tone_guardrail == "sensitive":
                return f"I can put through a ₹{amount} coupon right away while I keep this moving for you. If that still doesn't feel right, we can take the next step."
            return f"I can put through a ₹{amount} coupon right away while I keep this moving for you. If that doesn't land right, we can go to the next step."
        return f"I can put through a ₹{amount} coupon right away if that works for you."

    @staticmethod
    def _store_terminal_state(state: Dict[str, Any]) -> None:
        state["pending"] = None
        state["desired_resolution"] = None
        state["coupon_push_count"] = 0

    @staticmethod
    def _mark_terminal_action(state: Dict[str, Any], response: Dict[str, Any], item_name: str) -> None:
        action = response.get("action")
        if action not in {"refund", "replacement", "escalate"}:
            return
        Rules._store_terminal_state(state)
        state["last_action"] = action
        if action == "replacement":
            state["last_item_name"] = item_name
        if action == "refund":
            state["last_amount"] = response.get("amount", 0.0)

    @staticmethod
    def _contains_false_promise(text: str) -> bool:
        patterns = [
            r"\b(i'll|i will)\s+(check|see|arrange|get|send|call|contact|follow|reach|look|find)",
            r"\b(i'll|i will)\s+(remake|replace|refund|credit|coupon|compensate|approve)",
            r"\b(i'll|i will)\s+pass\s+this\s+to\s+the\s+team",
            r"\b(i'll|i will)\s+flag\s+this\s+with\s+the\s+team",
            r"\blet me\s+(check|see|arrange|get|send|call|contact|follow|reach|look|find)",
            r"\b(we'll|we will)\s+(check|see|arrange|get|send|call|contact|follow|reach|look|find)",
            r"\bi'm going to\s+(check|see|arrange|get|send|call|contact|follow|reach|look|find)",
            r"\b(hang tight|hold on|give me a (moment|second|minute)|bear with me)",
            r"\bsee (if|how) (we|i) can",
            r"\b(i'll|i will)\s+(keep an eye|track|watch)",
        ]
        lowered = _lower(text)
        return any(re.search(pattern, lowered) for pattern in patterns)

    @staticmethod
    def _remove_false_promises(text: str) -> str:
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        clean = [sentence for sentence in sentences if sentence and not Rules._contains_false_promise(sentence)]
        result = " ".join(clean).strip()
        return result if len(result) >= 15 else "Got it."

    @staticmethod
    def _enforce_content(response: Dict[str, Any]) -> Dict[str, Any]:
        message = response.get("message", "").strip()
        if Rules._contains_false_promise(message):
            message = Rules._remove_false_promises(message)

        lowered = message.lower()
        for phrase in Rules.BANNED_PHRASES:
            if phrase in lowered:
                message = re.sub(re.escape(phrase), "", message, flags=re.IGNORECASE).strip()
                lowered = message.lower()

        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", message) if part.strip()]
        if len(sentences) > 3:
            message = " ".join(sentences[:3])

        response["message"] = message if message else "Got it."
        return response


def _evict_expired_sessions() -> None:
    return None


def get_session(session_id: str) -> List[Dict[str, str]]:
    return session_store.get_session(session_id)


def mark_photo_provided(session_id: str) -> None:
    session_store.mark_photo_provided(session_id)


def session_has_photo(session_id: str) -> bool:
    return session_store.session_has_photo(session_id)


def get_session_state(session_id: Optional[str]) -> Dict[str, Any]:
    return session_store.get_state(session_id)


def clear_session(session_id: str) -> None:
    session_store.clear(session_id)
