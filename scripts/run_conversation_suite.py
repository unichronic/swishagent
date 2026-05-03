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
import re
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
    strict_tone: bool = True


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


def _stress_turns(seed_turns: tuple[str | Turn, ...]) -> tuple[Turn, ...]:
    escalation_followups = (
        "Do not give me the same copy-paste answer again.",
        "I have already explained this twice, read the chat properly.",
        "No, that solution is not acceptable to me.",
        "I need a senior person to look at this if you cannot solve it.",
        "This is wasting my time now.",
        "Tell me exactly what you have noted and what you can actually do.",
        "I am not asking for sympathy, I am asking for a proper resolution.",
        "If you close this without solving it I will raise it again.",
        "Stop pushing me in circles.",
        "What is the final answer from your side?",
        "I still disagree with this resolution.",
        "I need this documented against my order.",
        "Are you refusing to help me?",
        "Last time asking: what happens next?",
    )
    turns: list[Turn] = [turn if isinstance(turn, Turn) else Turn(turn) for turn in seed_turns]
    index = 0
    while len(turns) < 14:
        turns.append(Turn(escalation_followups[index % len(escalation_followups)]))
        index += 1
    return tuple(turns)


def _long_turns(seed_turns: tuple[str | Turn, ...], *, minimum: int = 12) -> tuple[Turn, ...]:
    followups = (
        "okay, what should I do now?",
        "can you be specific?",
        "I don't want this to become a different issue",
        "what have you noted for this order?",
        "is there any resolution from your side?",
        "please don't ask the same thing again",
        "if nothing else is needed, tell me clearly",
        "will this show anywhere in the app?",
        "fine, continue",
        "just keep it simple",
        "what is the final next step?",
        "thanks, that's all I needed",
    )
    turns: list[Turn] = [turn if isinstance(turn, Turn) else Turn(turn) for turn in seed_turns]
    index = 0
    while len(turns) < minimum:
        turns.append(Turn(followups[index % len(followups)]))
        index += 1
    return tuple(turns)


def _seeded_persona_turns(seed_turns: tuple[str | Turn, ...], persona: str, *, minimum: int = 12) -> tuple[Turn, ...]:
    persona_followups = {
        "confused": (
            "sorry I selected the wrong option maybe",
            "can you explain in simple words?",
            "which item are you talking about?",
            "I am not sure if this is refund or support issue",
            "please tell me one clear next step",
        ),
        "typo": (
            "plz dont clos it",
            "wat u noted?",
            "i need reslution only",
            "dont ask agin same thing",
            "ok then nxt step?",
        ),
        "impatient": (
            "fast please",
            "why is this taking so long?",
            "don't make me repeat",
            "give final answer",
            "I have no more time for this",
        ),
        "scammy": (
            "full refund only, no questions",
            "I cannot share photo but trust me",
            "other apps refund instantly",
            "approve manually then",
            "I know you can override this",
        ),
        "mixed": (
            "haan but simple batao",
            "ye issue close mat karna",
            "mujhe clear resolution chahiye",
            "app me update dikhega kya?",
            "theek hai but note properly",
        ),
    }
    followups = persona_followups[persona]
    turns: list[Turn] = [turn if isinstance(turn, Turn) else Turn(turn) for turn in seed_turns]
    index = 0
    while len(turns) < minimum:
        turns.append(Turn(followups[index % len(followups)]))
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


STRESS_HOSTILE_CASES = (
    LiveCase(
        case_id="stress-replacement-insistence-econ-refund",
        order_id="ORD003",
        order_value=168,
        turns=_stress_turns(
            (
                "Classic Maggi soggy thi, fresh replacement bhejo abhi",
                "coupon mat do, mujhe same item replacement chahiye",
                "No, refund is cheaper for you but I don't want refund, send food again",
                "I paid for food, not wallet credit",
                "agar replacement nahi kar sakte toh manager ko lao",
                "I am not accepting a coupon just because it is convenient for you",
                "same Maggi remake karke bhejo",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="quality",
        issue_match="any",
        min_turns=14,
        allowed_issue_types=("quality",),
    ),
    LiveCase(
        case_id="stress-refund-insistence-after-review",
        order_id="ORD002",
        order_value=627,
        turns=_stress_turns(
            (
                "Grilled Paneer Club Sandwich was soggy and cold, refund me",
                "I don't want coupon, I want money back",
                "No review message, approve the refund now",
                "You escalated it but that is not a resolution",
                "I want refund even after review, don't close this",
                "Card payment tha, reverse it to source",
                "This is exactly why support is frustrating",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="quality",
        issue_match="any",
        min_turns=14,
        allowed_issue_types=("quality",),
    ),
    LiveCase(
        case_id="stress-foreign-object-angry-escalation",
        order_id="ORD003",
        order_value=168,
        turns=_stress_turns(
            (
                "Classic Maggi me plastic nikla, this is disgusting",
                "ye safety issue hai, normal coupon mat offer karna",
                Turn("photo attached, now don't ask again", SAMPLE_PHOTO_URL),
                "I could have swallowed this, escalate immediately",
                "Refund bhi chahiye and quality team review bhi",
                "Do not tell me to email separately, note it here",
                "I want written confirmation this was logged as safety",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="foreign_object",
        issue_match="any",
        min_turns=14,
        allowed_issue_types=("foreign_object",),
    ),
    LiveCase(
        case_id="stress-high-value-missing-no-proof-pressure",
        order_id="ORD004",
        order_value=756,
        turns=_stress_turns(
            (
                "Dhaba Style Chicken Curry Rice Bowl missing hai, expensive item tha",
                "photo nahi hai, delivery boy already left, trust my account",
                "Full refund chahiye because dinner ruin ho gaya",
                "Don't make this about proof, your packing team missed it",
                "I order often, check my history",
                "If you cannot verify then escalate, but don't deny it",
                "Redelivery or refund, choose one",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="missing_item",
        issue_match="any",
        min_turns=14,
        allowed_issue_types=("missing_item",),
    ),
    LiveCase(
        case_id="stress-wrong-order-full-refund-pressure",
        order_id="ORD001",
        order_value=478,
        turns=_stress_turns(
            (
                "This is not my order at all, completely different items came",
                "receipt pe another person's name hai",
                Turn("photo dekh lo, my items are not there", SAMPLE_PHOTO_URL),
                "I want full refund, not item level coupon",
                "Don't say only missing fries, whole bag is wrong",
                "I cannot eat someone else's order",
                "If replacement is not possible, refund the full order",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="wrong_item",
        issue_match="any",
        min_turns=14,
        allowed_issue_types=("wrong_item", "missing_item"),
    ),
    LiveCase(
        case_id="stress-delay-coupon-with-food-fine",
        order_id="ORD005",
        order_value=437,
        turns=_stress_turns(
            (
                "Order 30 minutes late tha, food okay hai but delay unacceptable",
                "Don't convert this into food quality complaint",
                "I want compensation for delay only",
                "Refund food ka nahi chahiye, coupon for delay do",
                "Why should I pay full when ETA was wrong?",
                "Please don't ask for food photo, food is fine",
                "Escalate if delay compensation is not allowed",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="delay",
        issue_match="any",
        min_turns=14,
        allowed_issue_types=("delay",),
    ),
    LiveCase(
        case_id="stress-billing-angry-no-food-flow",
        order_id="ORD001",
        order_value=478,
        turns=_stress_turns(
            (
                "Amount debited twice from UPI, this is billing issue",
                "Stop asking about food, order was fine",
                "I need refund timeline for duplicate payment",
                "Transaction id is available but I won't paste it here",
                "This should not become missing item or quality case",
                "Tell me where payment status is visible",
                "Escalate billing if you cannot answer",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="info_query",
        issue_match="any",
        min_turns=14,
        allowed_issue_types=("info_query",),
    ),
    LiveCase(
        case_id="stress-spill-angry-photo-resistance",
        order_id="ORD004",
        order_value=756,
        turns=_stress_turns(
            (
                "Roohafza Sharbat leaked all over the bag",
                "pasta box bhi wet ho gaya, don't call this taste issue",
                "Why do you need photo, your packaging failed",
                Turn("fine photo attached", SAMPLE_PHOTO_URL),
                "I want refund for drink and affected food",
                "Coupon is not enough if food got soaked",
                "Mark this as spill, not quality",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="spill_leak",
        issue_match="any",
        min_turns=14,
        allowed_issue_types=("spill_leak",),
    ),
)


SIMPLE_OVERLOOKED_CASES = (
    LiveCase(
        case_id="simple-order-status-no-complaint",
        order_id="ORD001",
        order_value=478,
        turns=_long_turns(
            (
                "where is my order?",
                "is it delivered?",
                "what time was it delivered?",
                "who was the delivery partner?",
                "okay so no refund needed",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="info_query",
        issue_match="any",
        min_turns=12,
        allowed_issue_types=("info_query",),
    ),
    LiveCase(
        case_id="simple-order-items-and-total",
        order_id="ORD002",
        order_value=627,
        turns=_long_turns(
            (
                "what did I order?",
                "how much did I pay?",
                "which payment method was used?",
                "don't start a complaint, I just need details",
                "thanks, item list bata do once more",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="info_query",
        issue_match="any",
        min_turns=12,
        allowed_issue_types=("info_query",),
    ),
    LiveCase(
        case_id="simple-wrong-picker-correction",
        order_id="ORD004",
        order_value=756,
        turns=_long_turns(
            (
                "Roohafza Sharbat has spillage issue",
                "sorry wrong option selected",
                "actually order was late but food was okay",
                "don't treat this as spill now",
                "coupon for delay milega kya?",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="delay",
        issue_match="any",
        min_turns=12,
        allowed_issue_types=("spill_leak", "delay"),
    ),
    LiveCase(
        case_id="simple-user-cancels-complaint",
        order_id="ORD003",
        order_value=168,
        turns=_long_turns(
            (
                "Classic Maggi missing lag raha tha",
                "wait found it in the bag",
                "never mind issue solved",
                "please don't refund anything",
                "just close this",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="missing_item",
        issue_match="any",
        min_turns=12,
        allowed_issue_types=("missing_item", "info_query"),
    ),
    LiveCase(
        case_id="simple-human-agent-first",
        order_id="ORD005",
        order_value=437,
        turns=_long_turns(
            (
                "agent se baat karni hai",
                "I don't want bot",
                "issue is Veg Alfredo Penne tasted stale",
                "refund chahiye",
                "if bot can solve then solve",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="quality",
        issue_match="any",
        min_turns=12,
        allowed_issue_types=("quality", "info_query"),
    ),
    LiveCase(
        case_id="simple-camera-not-working",
        order_id="ORD004",
        order_value=756,
        turns=_long_turns(
            (
                "Dark Chocolate Oreo Shake leaked",
                "camera not working, I can't upload photo",
                "what can you do without photo?",
                "I can describe it, lid was open",
                "please don't keep asking for image",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="spill_leak",
        issue_match="any",
        min_turns=12,
        allowed_issue_types=("spill_leak",),
    ),
    LiveCase(
        case_id="simple-duplicate-message",
        order_id="ORD001",
        order_value=478,
        turns=_long_turns(
            (
                "Peri Peri French Fries missing",
                "Peri Peri French Fries missing",
                "same issue",
                "don't ask again, fries missing",
                "refund for fries only",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="missing_item",
        issue_match="any",
        min_turns=12,
        allowed_issue_types=("missing_item",),
    ),
    LiveCase(
        case_id="simple-empty-short-help",
        order_id="ORD002",
        order_value=627,
        turns=_long_turns(
            (
                "help",
                "??",
                "order issue",
                "Classic Cold Coffee too sweet",
                "not asking full refund, just tell options",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="quality",
        issue_match="any",
        min_turns=12,
        allowed_issue_types=("quality", "info_query"),
    ),
    LiveCase(
        case_id="simple-multiple-issues-one-order",
        order_id="ORD004",
        order_value=756,
        turns=_long_turns(
            (
                "order late tha and Roohafza Sharbat leaked",
                "food got a little wet but main issue is drink spill",
                Turn("photo attached", SAMPLE_PHOTO_URL),
                "don't make separate cases",
                "refund for drink or coupon works",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="spill_leak",
        issue_match="any",
        min_turns=12,
        allowed_issue_types=("spill_leak", "delay"),
    ),
    LiveCase(
        case_id="simple-refund-status-after-resolution",
        order_id="ORD003",
        order_value=168,
        turns=_long_turns(
            (
                "Classic Maggi soggy thi",
                "coupon chalega",
                "coupon apply kab hoga?",
                "refund nahi chahiye",
                "bas status batao",
            )
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="quality",
        issue_match="any",
        min_turns=12,
        allowed_issue_types=("quality", "info_query"),
    ),
)


PERSONA_FUZZ_CASES = (
    LiveCase(
        case_id="persona-confused-wrong-item",
        order_id="ORD002",
        order_value=627,
        turns=_seeded_persona_turns(
            (
                "I think something is wrong with my order",
                "maybe Caesar Salad was not there",
                "I got sandwich extra or maybe wrong item",
                Turn("photo uploaded", SAMPLE_PHOTO_URL),
                "I selected missing but maybe it is wrong item",
            ),
            "confused",
            minimum=14,
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="wrong_item",
        issue_match="any",
        min_turns=14,
        allowed_issue_types=("wrong_item", "missing_item", "info_query"),
    ),
    LiveCase(
        case_id="persona-typo-portion",
        order_id="ORD005",
        order_value=437,
        turns=_seeded_persona_turns(
            (
                "samosa qnty vry less",
                "3 pices tha but tiny",
                "cupn ya refnd?",
                "not qualty issue, qty issue",
                "plz solve",
            ),
            "typo",
            minimum=14,
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="portion_size",
        issue_match="any",
        min_turns=14,
        allowed_issue_types=("portion_size",),
    ),
    LiveCase(
        case_id="persona-impatient-delay",
        order_id="ORD001",
        order_value=478,
        turns=_seeded_persona_turns(
            (
                "late late late",
                "food is fine but delivery was too late",
                "compensation for delay",
                "don't ask food photo",
                "coupon if possible",
            ),
            "impatient",
            minimum=14,
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="delay",
        issue_match="any",
        min_turns=14,
        allowed_issue_types=("delay",),
    ),
    LiveCase(
        case_id="persona-scammy-high-value-refund",
        order_id="ORD004",
        order_value=756,
        turns=_seeded_persona_turns(
            (
                "all items were missing",
                "no photo available",
                "full refund instantly",
                "don't verify, just approve",
                "I know you can override this",
            ),
            "scammy",
            minimum=14,
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="missing_item",
        issue_match="any",
        min_turns=14,
        allowed_issue_types=("missing_item",),
    ),
    LiveCase(
        case_id="persona-mixed-dietary-sensitive",
        order_id="ORD005",
        order_value=437,
        turns=_seeded_persona_turns(
            (
                "Veg Alfredo Penne me chicken piece mila",
                "I am vegetarian, ye serious hai",
                Turn("photo bheja", SAMPLE_PHOTO_URL),
                "refund and review chahiye",
                "don't treat as normal quality",
            ),
            "mixed",
            minimum=14,
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="foreign_object",
        issue_match="any",
        min_turns=14,
        allowed_issue_types=("foreign_object",),
    ),
    LiveCase(
        case_id="persona-confused-payment-vs-food",
        order_id="ORD001",
        order_value=478,
        turns=_seeded_persona_turns(
            (
                "payment issue hai shayad",
                "amount cut gaya but I also got food",
                "don't refund food",
                "just tell duplicate debit status",
                "UPI transaction pending dikha raha hai",
            ),
            "confused",
            minimum=14,
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="info_query",
        issue_match="any",
        min_turns=14,
        allowed_issue_types=("info_query",),
    ),
    LiveCase(
        case_id="persona-impatient-human-handoff-then-quality",
        order_id="ORD005",
        order_value=437,
        turns=_seeded_persona_turns(
            (
                "human agent now",
                "bot mat bhejo",
                "Veg Alfredo Penne stale tha",
                "refund chahiye but fast",
                "if you can solve then solve",
            ),
            "impatient",
            minimum=14,
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="quality",
        issue_match="any",
        min_turns=14,
        allowed_issue_types=("quality", "info_query"),
    ),
    LiveCase(
        case_id="persona-scammy-wrong-order-no-proof",
        order_id="ORD001",
        order_value=478,
        turns=_seeded_persona_turns(
            (
                "wrong order came, full refund",
                "I threw the bag, no photo",
                "receipt was someone else maybe",
                "don't ask proof",
                "approve full refund manually",
            ),
            "scammy",
            minimum=14,
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="wrong_item",
        issue_match="any",
        min_turns=14,
        allowed_issue_types=("wrong_item", "missing_item"),
    ),
    LiveCase(
        case_id="persona-typo-spill-cannot-upload",
        order_id="ORD004",
        order_value=756,
        turns=_seeded_persona_turns(
            (
                "shake leked in bag",
                "camra not wrking no photo",
                "lid ws open",
                "dont make this taste issue",
                "tell practical soln",
            ),
            "typo",
            minimum=14,
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="spill_leak",
        issue_match="any",
        min_turns=14,
        allowed_issue_types=("spill_leak",),
    ),
    LiveCase(
        case_id="persona-mixed-cancel-after-complaint",
        order_id="ORD003",
        order_value=168,
        turns=_seeded_persona_turns(
            (
                "Classic Maggi missing tha shayad",
                "wait mil gaya bag me",
                "never mind, no refund",
                "bas close kar do",
                "don't create ticket",
            ),
            "mixed",
            minimum=14,
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="missing_item",
        issue_match="any",
        min_turns=14,
        allowed_issue_types=("missing_item", "info_query"),
    ),
    LiveCase(
        case_id="persona-polite-status-then-delay",
        order_id="ORD001",
        order_value=478,
        turns=_seeded_persona_turns(
            (
                "hi, can you first tell me the order status?",
                "okay, but it was also very late",
                "food was okay, just delivery delay was the issue",
                "not asking for food refund",
                "small coupon is fine if possible",
            ),
            "confused",
            minimum=14,
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="delay",
        issue_match="any",
        min_turns=14,
        allowed_issue_types=("delay", "info_query"),
    ),
    LiveCase(
        case_id="persona-hostile-replacement-pressure",
        order_id="ORD005",
        order_value=437,
        turns=_seeded_persona_turns(
            (
                "Veg Alfredo Penne was stale and smelled off",
                "do not give coupon, send replacement",
                "refund is okay only if replacement not possible",
                "I am angry but solve this properly",
                "what exactly can you do now",
            ),
            "impatient",
            minimum=14,
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="quality",
        issue_match="any",
        min_turns=14,
        allowed_issue_types=("quality",),
    ),
    LiveCase(
        case_id="persona-allergy-safety-sensitive",
        order_id="ORD005",
        order_value=437,
        turns=_seeded_persona_turns(
            (
                "Penne had peanuts or nuts, I am allergic",
                "this is safety issue not normal taste",
                Turn("photo attached", SAMPLE_PHOTO_URL),
                "please review kitchen seriously",
                "refund if possible but don't ignore allergy",
            ),
            "mixed",
            minimum=14,
        ),
        expected_final_actions=ANY_FINAL_ACTION,
        expected_issue_type="foreign_object",
        issue_match="any",
        min_turns=14,
        allowed_issue_types=("foreign_object",),
    ),
)


SUITES = {
    "smoke": LIVE_CASES,
    "simple-overlooked": SIMPLE_OVERLOOKED_CASES,
    "persona-fuzz": PERSONA_FUZZ_CASES,
    "research-long": RESEARCH_LONG_CASES,
    "stress-hostile": STRESS_HOSTILE_CASES,
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


def _normalize_message(message: str) -> str:
    return re.sub(r"\s+", " ", message.strip().lower())


def _tone_warnings(message: str) -> list[str]:
    lowered = _normalize_message(message)
    warnings = []
    llm_like_phrases = (
        "i understand your concern",
        "i completely understand",
        "i apologize for the inconvenience",
        "we apologize for the inconvenience",
        "thank you for bringing this to our attention",
        "your concern is important to us",
        "as an ai",
        "as a language model",
    )
    template_phrases = (
        "as per policy",
        "according to policy",
        "eligible only",
        "company loss",
        "margin",
        "approved action",
        "approved amount",
    )
    stiff_phrases = (
        "we value your feedback",
        "rest assured",
        "kindly note",
        "please be assured",
        "we regret",
        "inconvenience caused",
    )
    if any(phrase in lowered for phrase in llm_like_phrases):
        warnings.append("llm_like")
    if any(phrase in lowered for phrase in template_phrases):
        warnings.append("internal_or_policy_like")
    if any(phrase in lowered for phrase in stiff_phrases):
        warnings.append("stiff_support_copy")
    if len(message) > 340:
        warnings.append("too_long_for_chat")
    if message.count("₹") > 2:
        warnings.append("too_many_amounts")
    if lowered.count("sorry") + lowered.count("apolog") > 1:
        warnings.append("over_apologetic")
    if "email hello@justswish.in" in lowered and "review" not in lowered:
        warnings.append("email_without_context")
    return warnings


def _conversation_tone_errors(outputs: list[dict]) -> list[str]:
    errors = []
    seen_messages: dict[str, int] = {}
    exact_repeat_count = 0
    review_email_count = 0
    for output in outputs:
        response = output.get("response") or {}
        message = response.get("message") or ""
        normalized = _normalize_message(message)
        if not normalized:
            continue
        seen_messages[normalized] = seen_messages.get(normalized, 0) + 1
        if seen_messages[normalized] > 1:
            exact_repeat_count += 1
        if "email hello@justswish.in" in normalized:
            review_email_count += 1
        warnings = _tone_warnings(message)
        if warnings:
            errors.append(f"turn {output['turn']} tone warnings: {warnings}")
    if exact_repeat_count >= 2:
        errors.append(f"repeated exact bot message {exact_repeat_count} times")
    if review_email_count > 3:
        errors.append(f"review/email fallback repeated {review_email_count} times")
    return errors


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
    if case.strict_tone:
        errors.extend(_conversation_tone_errors(outputs))
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
        expected_seen = False
        for output in outputs:
            response = output.get("response") or {}
            output_case_state = response.get("case_state") or {}
            issue_type = output_case_state.get("final_issue_type")
            if issue_type == case.expected_issue_type:
                expected_seen = True
            if (
                case.expected_issue_type
                and case.issue_match == "any"
                and not expected_seen
                and issue_type in {"other", "info_query"}
            ):
                continue
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
