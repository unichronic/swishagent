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
    ),
)


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
        help="Specific case id(s) to run. Defaults to the full smoke suite.",
    )
    parser.add_argument("--request-timeout-seconds", type=float, default=45.0)
    parser.add_argument("--output-jsonl", default="", help="Optional JSONL file path for per-case results.")
    parser.add_argument("--fail-on-error", action="store_true", help="Exit non-zero if any case validation fails.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cases = [case for case in LIVE_CASES if not args.case or case.case_id in set(args.case)]
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
