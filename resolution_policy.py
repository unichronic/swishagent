"""
Resolution economics for Swish support.

This module owns compensation-policy decisions that should not depend on chat
copy, raw customer phrasing, or conversation plumbing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ResolutionPolicyConfig:
    high_value_threshold: float = 500
    low_value_refund_threshold: float = 250
    refund_trust_threshold: float = 80
    standard_coupon_amount: float = 50
    estimated_replacement_overhead: float = 70
    max_coupon_reinforcement_turns: int = 2
    max_high_severity_replacement_negotiation_turns: int = 1
    min_replacement_negotiation_margin: float = 60


DEFAULT_CONFIG = ResolutionPolicyConfig()


def refund_hard_block(
    *,
    order_value: float,
    trust_score: float,
    config: ResolutionPolicyConfig = DEFAULT_CONFIG,
) -> bool:
    return order_value > config.high_value_threshold and trust_score <= config.refund_trust_threshold


def refund_allowed(
    *,
    trust_score: float,
    issue_severity: str,
    evidence_strength: str,
    config: ResolutionPolicyConfig = DEFAULT_CONFIG,
) -> bool:
    return (
        trust_score > config.refund_trust_threshold
        and issue_severity == "high"
        and evidence_strength == "strong"
    )


def preferred_refund_resolution(
    *,
    order_value: float,
    item_price: Optional[float],
    trust_score: float,
    desired_resolution: str,
    issue_type: str,
    issue_severity: str,
    evidence_strength: str,
    economic_preference: Optional[str],
    config: ResolutionPolicyConfig = DEFAULT_CONFIG,
) -> str:
    if desired_resolution != "refund":
        return desired_resolution
    if refund_hard_block(order_value=order_value, trust_score=trust_score, config=config):
        return "replacement"
    if issue_type == "delay":
        return "refund" if trust_score > config.refund_trust_threshold and evidence_strength == "strong" else "escalate"

    if economic_preference in {"refund", "replacement", "escalate"}:
        return economic_preference
    if economic_preference == "escalate":
        return "refund"

    item_cost = _item_cost(order_value, item_price)
    replacement_cost = item_cost + config.estimated_replacement_overhead
    refund_cost = float(order_value)

    if issue_type == "portion_size":
        return "refund"
    if issue_type in {"quality", "temperature"} and issue_severity != "high":
        return "escalate"
    if issue_type in {"wrong_item", "missing_item"} and evidence_strength == "strong":
        return "refund" if refund_cost <= replacement_cost else "replacement"
    if issue_type == "foreign_object" and issue_severity == "high":
        return "refund"
    if issue_type in {"spill_leak", "damaged"} and issue_severity == "high":
        return "replacement"
    if order_value <= config.low_value_refund_threshold:
        return "refund"
    if refund_cost <= replacement_cost:
        return "refund"
    return "replacement"


def choose_economic_preference(
    *,
    desired_resolution: str,
    issue_type: str,
    issue_severity: str,
    evidence_strength: str,
    order_value: float,
    item_price: Optional[float],
    trust_score: float,
    assessed_preference: Optional[str],
    assessed_confidence: Optional[float],
    config: ResolutionPolicyConfig = DEFAULT_CONFIG,
) -> str:
    default = default_economic_preference(
        desired_resolution=desired_resolution,
        issue_type=issue_type,
        issue_severity=issue_severity,
        evidence_strength=evidence_strength,
        order_value=order_value,
        item_price=item_price,
        trust_score=trust_score,
        config=config,
    )
    if not assessed_preference:
        return default
    confidence = assessed_confidence or 0.0
    if confidence < 0.6:
        return default
    if not economic_preference_allowed(
        economic_preference=assessed_preference,
        issue_type=issue_type,
        evidence_strength=evidence_strength,
        desired_resolution=desired_resolution,
    ):
        return default
    return assessed_preference


def default_economic_preference(
    *,
    desired_resolution: str,
    issue_type: str,
    issue_severity: str,
    evidence_strength: str,
    order_value: float,
    item_price: Optional[float],
    trust_score: float,
    config: ResolutionPolicyConfig = DEFAULT_CONFIG,
) -> str:
    if desired_resolution not in {"refund", "replacement"}:
        return "coupon"
    if desired_resolution == "replacement" and evidence_strength != "strong":
        return "coupon"
    if desired_resolution == "refund" and refund_hard_block(order_value=order_value, trust_score=trust_score, config=config):
        return "replacement"
    if issue_type == "delay":
        return "coupon"
    if issue_type == "portion_size":
        return "refund"
    if issue_type == "foreign_object" and issue_severity == "high":
        return "refund"
    if desired_resolution == "refund" and evidence_strength == "strong" and order_value > config.low_value_refund_threshold:
        item_cost = _item_cost(order_value, item_price)
        replacement_cost = item_cost + config.estimated_replacement_overhead
        return "replacement" if replacement_cost < float(order_value) else "refund"
    if desired_resolution == "refund" and issue_severity != "high":
        return "escalate"
    if issue_type in {"wrong_item", "missing_item"} and evidence_strength == "strong":
        return "replacement" if order_value > config.low_value_refund_threshold else "refund"
    if issue_type in {"spill_leak", "damaged"} and issue_severity == "high":
        return "replacement"
    item_cost = _item_cost(order_value, item_price)
    replacement_cost = item_cost + config.estimated_replacement_overhead
    if desired_resolution == "refund":
        return "refund" if order_value <= replacement_cost else "replacement"
    return "replacement" if evidence_strength == "strong" else "coupon"


def economic_preference_allowed(
    *,
    economic_preference: str,
    issue_type: str,
    evidence_strength: str,
    desired_resolution: str,
) -> bool:
    if economic_preference == "replacement" and evidence_strength != "strong":
        return False
    if issue_type in {"delay", "portion_size", "info_query"} and economic_preference == "replacement":
        return False
    if desired_resolution == "replacement" and economic_preference == "refund":
        return False
    return True


def adjust_coupon_amount(
    *,
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


def estimated_replacement_cost(
    *,
    order_value: float,
    item_price: Optional[float],
    config: ResolutionPolicyConfig = DEFAULT_CONFIG,
) -> float:
    item_cost = float(item_price) if isinstance(item_price, (int, float)) and item_price > 0 else float(order_value)
    return item_cost + config.estimated_replacement_overhead


def replacement_negotiation_turn_limit(
    *,
    order_value: float,
    item_price: Optional[float],
    coupon_amount: float,
    issue_severity: str,
    evidence_strength: str,
    economic_preference: Optional[str],
    config: ResolutionPolicyConfig = DEFAULT_CONFIG,
) -> int:
    if evidence_strength != "strong":
        return config.max_coupon_reinforcement_turns
    if economic_preference == "escalate":
        return 0
    if issue_severity != "high":
        return 0
    replacement_cost = estimated_replacement_cost(order_value=order_value, item_price=item_price, config=config)
    if replacement_cost - float(coupon_amount) < config.min_replacement_negotiation_margin:
        return 0
    return config.max_high_severity_replacement_negotiation_turns


def can_soft_approve_replacement(
    *,
    issue_type: str,
    order_value: float,
    item_price: Optional[float],
    trust_score: float,
    evidence_strength: str,
    economic_preference: Optional[str],
) -> bool:
    return False


def _item_cost(order_value: float, item_price: Optional[float]) -> float:
    return float(item_price) if isinstance(item_price, (int, float)) else float(order_value)
