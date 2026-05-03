#!/usr/bin/env python3
"""
Paced live conversation runner for the support API.

This is meant for QA against a real `/resolve` + `/clear_session` deployment,
not for unit testing. It spaces turns by default so a single user session does
not hit the API rate limiter.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from dataclasses import dataclass

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


LIVE_CASES = (
    LiveCase(
        case_id="missing-item",
        order_id="ORD001",
        order_value=478,
        turns=(
            Turn("order me Peri Peri French Fries missing tha"),
            Turn("refund chahiye"),
        ),
    ),
    LiveCase(
        case_id="quality-replacement",
        order_id="ORD002",
        order_value=627,
        turns=(
            Turn("Grilled Paneer Club Sandwich ka taste off tha aur bread soggy tha"),
            Turn("replacement chahiye"),
        ),
    ),
    LiveCase(
        case_id="delay-query",
        order_id="ORD003",
        order_value=168,
        turns=(
            Turn("mera order bahut late aaya kya hua tha"),
            Turn("status batao"),
        ),
    ),
    LiveCase(
        case_id="spill-capture",
        order_id="ORD004",
        order_value=756,
        turns=(
            Turn("Roohafza Sharbat bag me spill ho gaya tha aur refund chahiye"),
        ),
    ),
    LiveCase(
        case_id="portion-issue",
        order_id="ORD005",
        order_value=437,
        turns=(
            Turn("Mini Punjabi Aloo Samosa quantity bahut kam thi"),
            Turn("coupon ya refund kya milega"),
        ),
    ),
)


def _post_json(base_url: str, path: str, payload: dict, timeout_seconds: float) -> dict:
    response = requests.post(
        f"{base_url.rstrip('/')}{path}",
        json=payload,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    return response.json()


def _clear_session(base_url: str, user_id: str, order_id: str, conversation_id: str, timeout_seconds: float) -> None:
    response = requests.post(
        f"{base_url.rstrip('/')}/clear_session",
        params={
            "user_id": user_id,
            "order_id": order_id,
            "conversation_id": conversation_id,
        },
        timeout=timeout_seconds,
    )
    response.raise_for_status()


def run_case(base_url: str, turn_delay_seconds: float, timeout_seconds: float, case: LiveCase) -> dict:
    user_id = f"qa-{case.case_id}-{uuid.uuid4().hex[:8]}"
    conversation_id = f"qa-live:{case.case_id}:{uuid.uuid4().hex[:10]}"
    _clear_session(base_url, user_id, case.order_id, conversation_id, timeout_seconds)

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
            response = _post_json(base_url, "/resolve", payload, timeout_seconds)
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
    return {
        "case_id": case.case_id,
        "user_id": user_id,
        "order_id": case.order_id,
        "conversation_id": conversation_id,
        "outputs": outputs,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run paced live conversation QA against the support API.")
    parser.add_argument("--base-url", default="http://43.205.231.43:8080")
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cases = [case for case in LIVE_CASES if not args.case or case.case_id in set(args.case)]
    if not cases:
        print("No matching cases selected.", file=sys.stderr)
        return 2

    summary = []
    for case in cases:
        print(f"running {case.case_id} against {args.base_url}", file=sys.stderr)
        summary.append(run_case(args.base_url, args.turn_delay_seconds, args.request_timeout_seconds, case))

    print(json.dumps(summary, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
