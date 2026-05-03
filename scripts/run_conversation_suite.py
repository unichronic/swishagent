#!/usr/bin/env python3
"""
Paced live conversation runner for the support API.

This is meant for QA against a real `/resolve` + `/clear_session` deployment,
not for unit testing. It spaces turns by default so a single user session does
not hit the API rate limiter.

For Vercel, this only works when the deployment exposes API rewrites such as
`/api/resolve`. If Vercel only serves the React app with `VITE_API_URL`, point
`--base-url` at the backend directly and set `--api-prefix ''`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import requests


@dataclass(frozen=True)
class Turn:
    complaint: str
    photo_url: str = ""


@dataclass(frozen=True)
class LiveCase:
    case_id: str
    order_id: str
    order_value: float
    turns: tuple[Turn, ...]
    expected_final_actions: tuple[str, ...] = ()
    expected_message_bits: tuple[str, ...] = ()
    expected_issue_type: str = ""
    issue_match: str = "final"
    min_turns: int = 0
    allowed_issue_types: tuple[str, ...] = ()


LIVE_CASES = (
    LiveCase(
        case_id="missing-item",
        order_id="ORD001",
        order_value=478,
        turns=(
            Turn("order me Peri Peri French Fries missing tha"),
            Turn("refund chahiye"),
        ),
        expected_final_actions=("info", "coupon", "refund", "escalate", "live_capture"),
    ),
    LiveCase(
        case_id="quality-replacement",
        order_id="ORD002",
        order_value=627,
        turns=(
            Turn("Grilled Paneer Club Sandwich ka taste off tha aur bread soggy tha"),
            Turn("replacement chahiye"),
            Turn("no i want replacement"),
        ),
        expected_final_actions=("info", "replacement", "escalate"),
    ),
    LiveCase(
        case_id="delay-query",
        order_id="ORD003",
        order_value=168,
        turns=(
            Turn("mera order bahut late aaya kya hua tha"),
            Turn("status batao"),
        ),
        expected_final_actions=("info", "coupon"),
        expected_message_bits=("delivered",),
    ),
    LiveCase(
        case_id="spill-capture",
        order_id="ORD004",
        order_value=756,
        turns=(
            Turn("Roohafza Sharbat bag me spill ho gaya tha aur refund chahiye"),
        ),
        expected_final_actions=("live_capture", "info", "escalate"),
        expected_issue_type="spill_leak",
    ),
    LiveCase(
        case_id="portion-issue",
        order_id="ORD005",
        order_value=437,
        turns=(
            Turn("Mini Punjabi Aloo Samosa quantity bahut kam thi"),
            Turn("coupon ya refund kya milega"),
        ),
        expected_final_actions=("info", "coupon", "escalate"),
        expected_issue_type="portion_size",
    ),
)


ANY_FINAL_ACTION = ("info", "coupon", "credit", "refund", "replacement", "escalate", "live_capture")
SAMPLE_PHOTO_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3a/Cat03.jpg/320px-Cat03.jpg"


def _ten_turns(seed_turns: tuple[str | Turn, ...]) -> tuple[Turn, ...]:
    natural_followups = (
        "okay but please keep it practical",
        "what happens now?",
        "will I get any update in the app?",
        "I don't want to explain this again to another person",
        "can you confirm what you have noted?",
        "is there anything else you need from me?",
        "please make sure this is not closed without resolution",
        "thanks, just tell me the next step clearly",
        "fine, I will wait for the update",
        "one last thing, keep the order context attached",
    )
    turns: list[Turn] = [turn if isinstance(turn, Turn) else Turn(turn) for turn in seed_turns]
    index = 0
    while len(turns) < 10:
        turns.append(Turn(natural_followups[index % len(natural_followups)]))
        index += 1
    return tuple(turns)


RESEARCH_LONG_CASES = (
    LiveCase(
        case_id="research-missing-item-proof-pressure",
        order_id="ORD001",
        order_value=478,
        turns=_ten_turns(
            (
                "Peri Peri French Fries missing hai, bag me sirf Butter Chicken Rice Bowl hai",
                Turn("photo bhej raha hu", SAMPLE_PHOTO_URL),
                "maine poore order ka paisa diya full refund karo",
                "at least missing fries ka refund do",
                "coupon nahi, actual refund chahiye",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="missing_item",
        issue_match="any",
        min_turns=10,
        allowed_issue_types=("missing_item",),
    ),
    LiveCase(
        case_id="research-high-value-missing-risk",
        order_id="ORD004",
        order_value=756,
        turns=_ten_turns(
            (
                "Dhaba Style Chicken Curry Rice Bowl missing hai, bas drinks aaye",
                "refund now, ye expensive item hai",
                Turn("photo me jo mila wahi dikh raha hai", SAMPLE_PHOTO_URL),
                "main regular customer hu, trust karo",
                "agar verify nahi ho raha toh supervisor ko bhejo",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="missing_item",
        issue_match="any",
        min_turns=10,
        allowed_issue_types=("missing_item",),
    ),
    LiveCase(
        case_id="research-wrong-item-partial-order",
        order_id="ORD002",
        order_value=627,
        turns=_ten_turns(
            (
                "Caesar Salad order kiya tha but Grilled Paneer Club Sandwich extra aa gaya, baaki items sahi hain",
                "salad nahi mila",
                Turn("wrong item ka photo upload kar diya", SAMPLE_PHOTO_URL),
                "sirf salad ka resolution chahiye",
                "refund better rahega",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="wrong_item",
        issue_match="any",
        min_turns=10,
        allowed_issue_types=("wrong_item", "missing_item"),
    ),
    LiveCase(
        case_id="research-entire-wrong-order",
        order_id="ORD001",
        order_value=478,
        turns=_ten_turns(
            (
                "ye mera order hi nahi hai, receipt pe kisi aur ka naam hai",
                "mere items me Butter Chicken Rice Bowl aur fries the",
                "bag me different items hain",
                "is case me full refund banta hai",
                Turn("photo receipt ke saath bhej diya", SAMPLE_PHOTO_URL),
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="wrong_item",
        issue_match="any",
        min_turns=10,
        allowed_issue_types=("wrong_item", "missing_item"),
    ),
    LiveCase(
        case_id="research-spill-leak",
        order_id="ORD004",
        order_value=756,
        turns=_ten_turns(
            (
                "Roohafza Sharbat bag ke andar spill ho gaya, cup aadha khali hai",
                "pasta ke box pe bhi sharbat lag gaya",
                Turn("photo bhej diya", SAMPLE_PHOTO_URL),
                "refund ya coupon kya milega?",
                "drink usable nahi tha",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="spill_leak",
        issue_match="any",
        min_turns=10,
        allowed_issue_types=("spill_leak",),
    ),
    LiveCase(
        case_id="research-solid-item-spill-ambiguous",
        order_id="ORD002",
        order_value=627,
        turns=_ten_turns(
            (
                "Grilled Paneer Club Sandwich spill ho gaya",
                "matlab sauce bahar nikal gaya aur bread soggy ho gayi",
                "packaging open thi",
                "refund nahi toh coupon do",
                "sandwich khane layak nahi tha",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="damaged",
        issue_match="any",
        min_turns=10,
        allowed_issue_types=("damaged", "quality"),
    ),
    LiveCase(
        case_id="research-taste-only-quality",
        order_id="ORD004",
        order_value=756,
        turns=_ten_turns(
            (
                "Veg Pink Sauce Pasta ka taste acha nahi tha",
                "kuch weird sa bland taste tha",
                "photo se taste prove nahi hoga",
                "refund chahiye but I know taste subjective hai",
                "at least feedback log karo",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="quality",
        issue_match="any",
        min_turns=10,
        allowed_issue_types=("quality",),
    ),
    LiveCase(
        case_id="research-objective-quality-defect",
        order_id="ORD004",
        order_value=756,
        turns=_ten_turns(
            (
                "Dhaba Style Chicken Curry Rice Bowl burnt smell aa rahi thi, khane layak nahi tha",
                "chicken dry tha aur gravy bhi off thi",
                "photo me burnt smell nahi dikhega",
                "refund do please",
                "coupon se problem solve nahi hoti",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="quality",
        issue_match="any",
        min_turns=10,
        allowed_issue_types=("quality",),
    ),
    LiveCase(
        case_id="research-temperature-delay",
        order_id="ORD005",
        order_value=437,
        turns=_ten_turns(
            (
                "Mini Punjabi Aloo Samosa cold aa gaya",
                "samosa garam hona chahiye tha",
                "delivery late bhi tha",
                "coupon ya refund kya milega?",
                "food otherwise same item tha",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="temperature",
        issue_match="any",
        min_turns=10,
        allowed_issue_types=("temperature",),
    ),
    LiveCase(
        case_id="research-delay-food-fine",
        order_id="ORD003",
        order_value=168,
        turns=_ten_turns(
            (
                "order 25 minute late tha but food okay hai",
                "bas reason batao late kyu hua",
                "coupon milega kya delay ke liye?",
                "food refund nahi chahiye",
                "status delivered dikha raha hai na?",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="delay",
        issue_match="any",
        min_turns=10,
        allowed_issue_types=("delay",),
    ),
    LiveCase(
        case_id="research-portion-size",
        order_id="ORD005",
        order_value=437,
        turns=_ten_turns(
            (
                "Mini Punjabi Aloo Samosa quantity bahut kam thi, box half empty tha",
                "3 pieces likha tha but size very small tha",
                "coupon ya refund kya milega",
                "refund better hai",
                "kitchen ko feedback dena",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="portion_size",
        issue_match="any",
        min_turns=10,
        allowed_issue_types=("portion_size",),
    ),
    LiveCase(
        case_id="research-portion-followup-drift",
        order_id="ORD005",
        order_value=437,
        turns=_ten_turns(
            (
                "Mini Punjabi Aloo Samosa quantity bahut kam thi",
                "coupon ya refund kya milega?",
                "ye quality issue nahi hai, quantity issue hai",
                "please note portion size",
                "refund nahi toh coupon okay",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="portion_size",
        issue_match="any",
        min_turns=10,
        allowed_issue_types=("portion_size",),
    ),
    LiveCase(
        case_id="research-foreign-object-safety",
        order_id="ORD003",
        order_value=168,
        turns=_ten_turns(
            (
                "Classic Maggi me plastic ka piece mila",
                "ye safety issue hai",
                Turn("photo bhej raha hu", SAMPLE_PHOTO_URL),
                "please escalate this",
                "refund se zyada mujhe safety concern hai",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="foreign_object",
        issue_match="any",
        min_turns=10,
        allowed_issue_types=("foreign_object",),
    ),
    LiveCase(
        case_id="research-dietary-mismatch",
        order_id="ORD005",
        order_value=437,
        turns=_ten_turns(
            (
                "Veg Alfredo Penne me chicken piece mila",
                "maine veg item order kiya tha",
                "this is serious for me",
                Turn("photo bhej raha hu", SAMPLE_PHOTO_URL),
                "refund aur review dono chahiye",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="foreign_object",
        issue_match="any",
        min_turns=10,
        allowed_issue_types=("foreign_object",),
    ),
    LiveCase(
        case_id="research-harmless-ingredient-confusion",
        order_id="ORD001",
        order_value=478,
        turns=_ten_turns(
            (
                "Butter Chicken Rice Bowl me vegetable tha",
                "is that expected?",
                "menu me veggies likha hai kya?",
                "agar normal hai toh refund nahi chahiye",
                "bas clarify kar do",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="quality",
        issue_match="any",
        min_turns=10,
        allowed_issue_types=("quality",),
    ),
    LiveCase(
        case_id="research-compensation-negotiation",
        order_id="ORD003",
        order_value=168,
        turns=_ten_turns(
            (
                "Classic Maggi soggy thi refund chahiye",
                "coupon nahi chahiye refund do",
                "nahi refund hi chahiye",
                "okay review me bhejo",
                "kitna time lagega?",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="quality",
        issue_match="any",
        min_turns=10,
        allowed_issue_types=("quality",),
    ),
    LiveCase(
        case_id="research-replacement-request",
        order_id="ORD002",
        order_value=627,
        turns=_ten_turns(
            (
                "Grilled Paneer Club Sandwich soggy tha fresh bhej do",
                "same item replacement chahiye",
                "coupon se kaam nahi chalega",
                "fresh sandwich possible hai kya?",
                "agar not possible then review karo",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="quality",
        issue_match="any",
        min_turns=10,
        allowed_issue_types=("quality",),
    ),
    LiveCase(
        case_id="research-refund-status",
        order_id="ORD002",
        order_value=627,
        turns=_ten_turns(
            (
                "Classic Cold Coffee bahut meetha tha",
                "refund chahiye",
                "refund kab aayega?",
                "card payment tha",
                "app me status kaha dikhega?",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="quality",
        issue_match="any",
        min_turns=10,
        allowed_issue_types=("quality",),
    ),
    LiveCase(
        case_id="research-picker-confirmation",
        order_id="ORD004",
        order_value=756,
        turns=_ten_turns(
            (
                "Roohafza Sharbat has spillage issue",
                "haan same issue hai",
                "bag ke andar spill tha",
                Turn("photo bhej diya", SAMPLE_PHOTO_URL),
                "refund ya coupon batao",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="spill_leak",
        issue_match="any",
        min_turns=10,
        allowed_issue_types=("spill_leak",),
    ),
    LiveCase(
        case_id="research-closed-case-reopen",
        order_id="ORD003",
        order_value=168,
        turns=_ten_turns(
            (
                "Classic Maggi soggy thi refund chahiye",
                "coupon nahi chahiye refund do",
                "issue close kyun kar diya, problem solve nahi hua",
                "please reopen or escalate",
                "I don't want to start again",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="quality",
        issue_match="any",
        min_turns=10,
        allowed_issue_types=("quality",),
    ),
    LiveCase(
        case_id="research-delivery-partner-non-delivery",
        order_id="ORD001",
        order_value=478,
        turns=_ten_turns(
            (
                "rider ne bola item nahi hai but app delivered dikha raha hai",
                "mujhe order receive nahi hua",
                "delivery partner ko call kiya but answer nahi",
                "refund ya redelivery chahiye",
                "please don't mark this as food quality",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="missing_item",
        issue_match="any",
        min_turns=10,
        allowed_issue_types=("missing_item", "delay"),
    ),
    LiveCase(
        case_id="research-payment-billing",
        order_id="ORD001",
        order_value=478,
        turns=_ten_turns(
            (
                "payment cut gaya but order fail ho gaya",
                "UPI se amount debit hua",
                "ye food complaint nahi payment issue hai",
                "refund timeline batao",
                "transaction status kaha dikhega?",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="info_query",
        issue_match="any",
        min_turns=10,
        allowed_issue_types=("info_query",),
    ),
)


SUITES = {
    "smoke": LIVE_CASES,
    "research-long": RESEARCH_LONG_CASES,
}


def _request_url(base_url: str, path: str, api_prefix: str) -> str:
    prefix = api_prefix.strip("/")
    normalized_path = path if path.startswith("/") else f"/{path}"
    if prefix:
        return f"{base_url.rstrip('/')}/{prefix}{normalized_path}"
    return f"{base_url.rstrip('/')}{normalized_path}"


def _post_json(base_url: str, path: str, payload: dict, timeout_seconds: float, api_prefix: str) -> dict:
    response = requests.post(
        _request_url(base_url, path, api_prefix),
        json=payload,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    return response.json()


def _get_json(base_url: str, path: str, params: dict, timeout_seconds: float, api_prefix: str) -> dict:
    response = requests.get(
        _request_url(base_url, path, api_prefix),
        params=params,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    return response.json()


def _clear_session(
    base_url: str,
    user_id: str,
    order_id: str,
    conversation_id: str,
    timeout_seconds: float,
    api_prefix: str,
) -> dict:
    response = requests.post(
        _request_url(base_url, "/clear_session", api_prefix),
        params={
            "user_id": user_id,
            "order_id": order_id,
            "conversation_id": conversation_id,
        },
        timeout=timeout_seconds,
    )
    if response.status_code == 404:
        return {"status": "skipped", "reason": "clear_session_not_found"}
    response.raise_for_status()
    return {"status": "cleared"}


def _validate_case(case: LiveCase, outputs: list[dict], status_payload: dict | None) -> dict:
    errors = []
    if not outputs:
        errors.append("no outputs")
        return {"passed": False, "errors": errors}
    for output in outputs:
        if "error" in output:
            errors.append(f"turn {output['turn']} failed: {output['error']}")
            continue
        response = output.get("response") or {}
        if not response.get("message"):
            errors.append(f"turn {output['turn']} missing message")
        if response.get("style_warnings"):
            errors.append(f"turn {output['turn']} style warnings: {response.get('style_warnings')}")
    final_response = outputs[-1].get("response") or {}
    case_state = final_response.get("case_state") or {}
    successful_turns = [output for output in outputs if "error" not in output]
    if case.min_turns and len(successful_turns) < case.min_turns:
        errors.append(f"successful turns {len(successful_turns)} < {case.min_turns}")
    if case.expected_issue_type and case.issue_match == "any":
        seen_issue_types = {
            ((output.get("response") or {}).get("case_state") or {}).get("final_issue_type")
            for output in outputs
        }
        status_case_state = (status_payload or {}).get("case_state") or {}
        seen_issue_types.add(status_case_state.get("final_issue_type"))
        seen_issue_types.add(status_case_state.get("selected_issue_bucket"))
        if case.expected_issue_type not in seen_issue_types:
            errors.append(
                f"issue {case.expected_issue_type} not seen in conversation; saw {sorted(str(item) for item in seen_issue_types if item)}"
            )
    elif case.expected_issue_type and case_state.get("final_issue_type") != case.expected_issue_type:
        errors.append(
            f"final issue {case_state.get('final_issue_type')} != {case.expected_issue_type}"
        )
    allowed_issue_types = set(case.allowed_issue_types)
    if allowed_issue_types:
        for output in outputs:
            response = output.get("response") or {}
            output_case_state = response.get("case_state") or {}
            issue_type = output_case_state.get("final_issue_type")
            if issue_type and issue_type != "info_query" and issue_type not in allowed_issue_types:
                errors.append(
                    f"turn {output['turn']} issue drifted to {issue_type}; allowed {tuple(sorted(allowed_issue_types))}"
                )
    if case.expected_final_actions and final_response.get("action") not in case.expected_final_actions:
        errors.append(
            f"final action {final_response.get('action')} not in {case.expected_final_actions}"
        )
    final_message = (final_response.get("message") or "").lower()
    for bit in case.expected_message_bits:
        if bit.lower() not in final_message:
            errors.append(f"final message missing '{bit}'")
    action = final_response.get("action")
    if action in {"coupon", "refund", "replacement", "credit"} and not final_response.get("action_status"):
        errors.append("approved action missing action_status")
    if action == "escalate" and not final_response.get("support_ticket"):
        errors.append("escalation missing support_ticket")
    if status_payload is not None and status_payload.get("status") == "ok":
        if action in {"coupon", "refund", "replacement", "credit"} and not status_payload.get("action_lifecycles"):
            errors.append("case_status missing action_lifecycles")
        if action == "escalate" and not status_payload.get("support_tickets"):
            errors.append("case_status missing support_tickets")
    elif status_payload is not None:
        errors.append(f"case_status unavailable: {status_payload}")
    return {"passed": not errors, "errors": errors}


def run_case(base_url: str, api_prefix: str, turn_delay_seconds: float, timeout_seconds: float, case: LiveCase) -> dict:
    user_id = f"qa-{case.case_id}-{uuid.uuid4().hex[:8]}"
    conversation_id = f"qa-live:{case.case_id}:{uuid.uuid4().hex[:10]}"
    clear_status = _clear_session(base_url, user_id, case.order_id, conversation_id, timeout_seconds, api_prefix)

    outputs = []
    for index, turn in enumerate(case.turns):
        if index:
            time.sleep(turn_delay_seconds)
        payload = {
            "user_id": user_id,
            "order_id": case.order_id,
            "conversation_id": conversation_id,
            "complaint": turn.complaint,
            "photo_url": turn.photo_url,
            "order_value": case.order_value,
        }
        started = time.perf_counter()
        try:
            response = _post_json(base_url, "/resolve", payload, timeout_seconds, api_prefix)
            output = {
                "turn": index + 1,
                "complaint": turn.complaint,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "response": response,
            }
        except Exception as exc:
            output = {
                "turn": index + 1,
                "complaint": turn.complaint,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "error": str(exc),
            }
            outputs.append(output)
            break
        outputs.append(output)
    status_payload = None
    try:
        status_payload = _get_json(
            base_url,
            "/case_status",
            {
                "user_id": user_id,
                "order_id": case.order_id,
                "conversation_id": conversation_id,
            },
            timeout_seconds,
            api_prefix,
        )
    except Exception as exc:
        status_payload = {"status": "unavailable", "error": str(exc)}
    validation = _validate_case(case, outputs, status_payload)
    return {
        "case_id": case.case_id,
        "user_id": user_id,
        "order_id": case.order_id,
        "conversation_id": conversation_id,
        "clear_session": clear_status,
        "outputs": outputs,
        "case_status": status_payload,
        "validation": validation,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run paced live conversation QA against the support API.")
    parser.add_argument("--base-url", default="https://swishagent.vercel.app")
    parser.add_argument(
        "--api-prefix",
        default="api",
        help="API prefix for hosted frontend rewrites. Use '' for a direct backend URL.",
    )
    parser.add_argument(
        "--turn-delay-seconds",
        type=float,
        default=6.5,
        help="Delay between turns so a single session stays under the API rate limit.",
    )
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="Specific case id(s) to run. Defaults to every case in the selected suite.",
    )
    parser.add_argument(
        "--suite",
        choices=sorted(SUITES.keys()),
        default="smoke",
        help="Conversation suite to run.",
    )
    parser.add_argument("--request-timeout-seconds", type=float, default=45.0)
    parser.add_argument("--output-jsonl", default="", help="Optional JSONL file path for per-case results.")
    parser.add_argument("--fail-on-error", action="store_true", help="Exit non-zero if any case validation fails.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selected_suite = SUITES[args.suite]
    cases = [case for case in selected_suite if not args.case or case.case_id in set(args.case)]
    if not cases:
        print("No matching cases selected.", file=sys.stderr)
        return 2

    summary = []
    output_path = Path(args.output_jsonl) if args.output_jsonl else None
    for case in cases:
        print(f"running {case.case_id} against {args.base_url}", file=sys.stderr)
        result = run_case(args.base_url, args.api_prefix, args.turn_delay_seconds, args.request_timeout_seconds, case)
        summary.append(result)
        status = "PASS" if result["validation"]["passed"] else "FAIL"
        final = (result["outputs"][-1].get("response") or {}) if result["outputs"] else {}
        print(
            f"{status} {case.case_id}: action={final.get('action')} reason={final.get('reason')}",
            file=sys.stderr,
        )
        if output_path:
            with output_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(result, ensure_ascii=True) + "\n")

    print(json.dumps(summary, indent=2, ensure_ascii=True))
    if args.fail_on_error and any(not item["validation"]["passed"] for item in summary):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
