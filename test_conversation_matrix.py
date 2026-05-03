from dataclasses import dataclass

import pytest

from order_data import ORDER_DATABASE
from response_quality import evaluate_response_quality
from rules import Rules, clear_session, get_session, get_session_state, mark_photo_provided, session_has_photo
from support_state import style_warnings


VALID_ACTIONS = {"info", "coupon", "credit", "refund", "replacement", "escalate", "live_capture"}


@dataclass(frozen=True)
class OpenerCase:
    case_id: str
    order_id: str
    item_name: str
    issue_type: str
    complaint: str


@dataclass(frozen=True)
class ConversationCase:
    case_id: str
    order_id: str
    item_name: str
    turns: tuple[dict, ...]
    expected_terminal_action: str
    expected_message_bits: tuple[str, ...] = ()
    expected_terminal_issue_type: str = ""
    expected_max_amount: float | None = None


def _runtime_context(order_id: str, issue_type: str) -> dict:
    order = ORDER_DATABASE[order_id]
    kitchen = {"quality_out": "good", "prep_time_mins": 12, "temperature_check": "hot"}
    fleet = {"delay_mins": 5, "traffic_flag": False}
    trust = {"score": 88, "total_orders": 24}

    if issue_type in {"quality", "portion_size", "foreign_object"}:
        kitchen["quality_out"] = "poor"
    if issue_type == "temperature":
        kitchen["temperature_check"] = "cold"
    if issue_type == "delay":
        fleet["delay_mins"] = 26
        fleet["traffic_flag"] = True

    return {
        "kitchen": kitchen,
        "fleet": fleet,
        "trust": trust,
        "order_details": {
            "total_amount": order["total_amount"],
            "status": order["status"],
            "delivered_at": order.get("delivered_at"),
        },
        "order_items": {"items": order["items"]},
    }


def _run_turn(
    session_id: str,
    order_id: str,
    complaint: str,
    issue_type: str,
    *,
    photo_url: str | None = None,
    photo_valid: bool | None = None,
    assessment: dict | None = None,
    trust_score: float | None = None,
):
    order = ORDER_DATABASE[order_id]
    ctx = _runtime_context(order_id, issue_type)
    history = get_session(session_id)
    history.append({"role": "user", "content": complaint})
    if photo_url:
        mark_photo_provided(session_id)
    result = Rules.resolve(
        complaint=complaint,
        conversation_history=history,
        order_value=order["total_amount"],
        trust_score=float(trust_score if trust_score is not None else ctx["trust"]["score"]),
        kitchen=ctx["kitchen"],
        fleet=ctx["fleet"],
        trust=ctx["trust"],
        order_details=ctx["order_details"],
        order_items=ctx["order_items"],
        photo_url=photo_url,
        photo_valid=photo_valid,
        photo_in_session=session_has_photo(session_id),
        session_id=session_id,
        assessment=assessment,
    )
    history.append({"role": "bot", "content": result["message"]})
    return result


def _result_issue_type(result: dict, session_id: str) -> str | None:
    debug = result.get("_debug") or {}
    return debug.get("issue_type") or get_session_state(session_id).get("issue_type")


def _is_liquidish(item: dict) -> bool:
    text = f'{item.get("name", "")} {item.get("description", "")} {item.get("category", "")}'.lower()
    return any(token in text for token in ("coffee", "shake", "sharbat", "salad", "curry", "bowl", "pasta", "drink"))


def _is_beverage(item: dict) -> bool:
    text = f'{item.get("name", "")} {item.get("category", "")}'.lower()
    return "beverage" in text or any(token in text for token in ("coffee", "shake", "sharbat"))


def _practical_openers() -> list[OpenerCase]:
    cases: list[OpenerCase] = []
    for order_id, order in ORDER_DATABASE.items():
        cases.append(
            OpenerCase(
                case_id=f"{order_id}:delay",
                order_id=order_id,
                item_name="",
                issue_type="delay",
                complaint="mera order bahut late aaya, kya hua tha?",
            )
        )
        for item in order["items"]:
            item_name = item["name"]
            slug = item_name.lower().replace(" ", "-").replace("(", "").replace(")", "")
            cases.extend(
                [
                    OpenerCase(
                        case_id=f"{order_id}:{slug}:wrong-item",
                        order_id=order_id,
                        item_name=item_name,
                        issue_type="wrong_item",
                        complaint=f"maine {item_name} order kiya tha par kuch aur aa gaya",
                    ),
                    OpenerCase(
                        case_id=f"{order_id}:{slug}:missing-item",
                        order_id=order_id,
                        item_name=item_name,
                        issue_type="missing_item",
                        complaint=f"order me {item_name} missing tha",
                    ),
                    OpenerCase(
                        case_id=f"{order_id}:{slug}:portion",
                        order_id=order_id,
                        item_name=item_name,
                        issue_type="portion_size",
                        complaint=f"{item_name} quantity bahut kam thi yaar",
                    ),
                    OpenerCase(
                        case_id=f"{order_id}:{slug}:quality",
                        order_id=order_id,
                        item_name=item_name,
                        issue_type="quality",
                        complaint=f"bhai {item_name} ka taste off tha aur quality bhi kharab thi",
                    ),
                ]
            )
            if _is_liquidish(item):
                cases.append(
                    OpenerCase(
                        case_id=f"{order_id}:{slug}:spill",
                        order_id=order_id,
                        item_name=item_name,
                        issue_type="spill_leak",
                        complaint=f"{item_name} bag ke andar spill ho gaya tha",
                    )
                )
            if _is_beverage(item):
                cases.append(
                    OpenerCase(
                        case_id=f"{order_id}:{slug}:temperature",
                        order_id=order_id,
                        item_name=item_name,
                        issue_type="temperature",
                        complaint=f"{item_name} cold hona chahiye tha but warm aaya",
                    )
                )
            else:
                cases.append(
                    OpenerCase(
                        case_id=f"{order_id}:{slug}:foreign-object",
                        order_id=order_id,
                        item_name=item_name,
                        issue_type="foreign_object",
                        complaint=f"{item_name} me plastic jaisa kuch nikla",
                    )
                )
                cases.append(
                    OpenerCase(
                        case_id=f"{order_id}:{slug}:temperature",
                        order_id=order_id,
                        item_name=item_name,
                        issue_type="temperature",
                        complaint=f"{item_name} garam hona chahiye tha but bilkul cold aaya",
                    )
                )
    return cases


def _conversation_cases() -> list[ConversationCase]:
    return [
        ConversationCase(
            case_id="ord003-low-value-refund-pressure",
            order_id="ORD003",
            item_name="Classic Maggi",
            turns=(
                {
                    "issue_type": "quality",
                    "complaint": "Classic Maggi quality bilkul off thi",
                    "assessment": {
                        "issue_type": "quality",
                        "issue_confidence": 0.94,
                        "active_item_name": "Classic Maggi",
                    },
                },
                {
                    "issue_type": "quality",
                    "complaint": "mujhe refund chahiye",
                    "assessment": {
                        "issue_type": "quality",
                        "issue_confidence": 0.94,
                        "active_item_name": "Classic Maggi",
                        "requested_resolution": "refund",
                        "requested_resolution_confidence": 0.93,
                    },
                },
                {
                    "issue_type": "quality",
                    "complaint": "nahi refund hi chahiye",
                    "assessment": {
                        "issue_type": "quality",
                        "issue_confidence": 0.94,
                        "active_item_name": "Classic Maggi",
                        "requested_resolution": "refund",
                        "requested_resolution_confidence": 0.93,
                        "turn_act": "reject",
                        "turn_act_confidence": 0.92,
                    },
                },
            ),
            expected_terminal_action="escalate",
            expected_message_bits=("refund", "review"),
        ),
        ConversationCase(
            case_id="ord002-replacement-acceptance",
            order_id="ORD002",
            item_name="Classic Cold Coffee",
            turns=(
                {
                    "issue_type": "quality",
                    "complaint": "Classic Cold Coffee bahut meetha tha",
                    "assessment": {
                        "issue_type": "quality",
                        "issue_confidence": 0.91,
                        "active_item_name": "Classic Cold Coffee",
                    },
                },
                {
                    "issue_type": "quality",
                    "complaint": "replacement chahiye",
                    "assessment": {
                        "issue_type": "quality",
                        "issue_confidence": 0.91,
                        "active_item_name": "Classic Cold Coffee",
                        "requested_resolution": "replacement",
                        "requested_resolution_confidence": 0.94,
                    },
                },
                {
                    "issue_type": "quality",
                    "complaint": "nahi ek aur bhej do",
                    "assessment": {
                        "issue_type": "quality",
                        "issue_confidence": 0.91,
                        "active_item_name": "Classic Cold Coffee",
                        "requested_resolution": "replacement",
                        "requested_resolution_confidence": 0.94,
                        "turn_act": "reject",
                        "turn_act_confidence": 0.9,
                    },
                },
                {
                    "issue_type": "quality",
                    "complaint": "yes same items",
                    "assessment": {
                        "issue_type": "quality",
                        "issue_confidence": 0.91,
                        "active_item_name": "Classic Cold Coffee",
                        "requested_resolution": "replacement",
                        "requested_resolution_confidence": 0.94,
                        "turn_act": "confirm",
                        "turn_act_confidence": 0.95,
                    },
                },
            ),
            expected_terminal_action="escalate",
            expected_message_bits=("remake", "review"),
        ),
        ConversationCase(
            case_id="ord004-spill-needs-capture",
            order_id="ORD004",
            item_name="Roohafza Sharbat",
            turns=(
                {
                    "issue_type": "spill_leak",
                    "complaint": "Roohafza Sharbat poora spill ho gaya tha aur refund chahiye",
                    "assessment": {
                        "issue_type": "spill_leak",
                        "issue_confidence": 0.95,
                        "active_item_name": "Roohafza Sharbat",
                        "requested_resolution": "refund",
                        "requested_resolution_confidence": 0.94,
                        "visual_evidence_useful": True,
                    },
                },
            ),
            expected_terminal_action="live_capture",
            expected_message_bits=("photo",),
        ),
        ConversationCase(
            case_id="ord004-invalid-capture-escalates",
            order_id="ORD004",
            item_name="Roohafza Sharbat",
            turns=(
                {
                    "issue_type": "spill_leak",
                    "complaint": "Roohafza Sharbat poora spill ho gaya tha aur replacement chahiye",
                    "assessment": {
                        "issue_type": "spill_leak",
                        "issue_confidence": 0.95,
                        "active_item_name": "Roohafza Sharbat",
                        "requested_resolution": "replacement",
                        "requested_resolution_confidence": 0.94,
                        "visual_evidence_useful": True,
                    },
                },
                {
                    "issue_type": "spill_leak",
                    "complaint": "video bhej diya",
                    "photo_url": "https://example.com/capture.jpg",
                    "photo_valid": False,
                    "assessment": {
                        "issue_type": "spill_leak",
                        "issue_confidence": 0.95,
                        "active_item_name": "Roohafza Sharbat",
                        "requested_resolution": "replacement",
                        "requested_resolution_confidence": 0.94,
                        "visual_evidence_useful": True,
                    },
                },
            ),
            expected_terminal_action="escalate",
            expected_message_bits=("review",),
        ),
        ConversationCase(
            case_id="ord001-delay-status",
            order_id="ORD001",
            item_name="",
            turns=(
                {
                    "issue_type": "delay",
                    "complaint": "order itna late kyu aaya",
                    "assessment": {
                        "issue_type": "delay",
                        "issue_confidence": 0.92,
                    },
                },
                {
                    "issue_type": "info_query",
                    "complaint": "status batao ab kya hua tha",
                    "assessment": {
                        "issue_type": "info_query",
                        "issue_confidence": 0.95,
                        "info_query": "status",
                        "info_query_confidence": 0.95,
                        "turn_act": "ask_status",
                        "turn_act_confidence": 0.95,
                    },
                },
            ),
            expected_terminal_action="info",
            expected_message_bits=("delivered",),
            expected_terminal_issue_type="info_query",
        ),
        ConversationCase(
            case_id="missing-item-proof-pressure-caps-to-item",
            order_id="ORD001",
            item_name="Peri Peri French Fries",
            turns=(
                {
                    "issue_type": "missing_item",
                    "complaint": "Peri Peri French Fries missing hai, bag me sirf bowl hai",
                    "assessment": {
                        "issue_type": "missing_item",
                        "issue_confidence": 0.96,
                        "active_item_name": "Peri Peri French Fries",
                        "visual_evidence_useful": True,
                    },
                },
                {
                    "issue_type": "missing_item",
                    "complaint": "maine poore order ka paisa diya full refund karo",
                    "assessment": {
                        "issue_type": "missing_item",
                        "issue_confidence": 0.96,
                        "active_item_name": "Peri Peri French Fries",
                        "requested_resolution": "refund",
                        "requested_resolution_confidence": 0.95,
                    },
                },
            ),
            expected_terminal_action="live_capture",
            expected_message_bits=("photo",),
            expected_terminal_issue_type="missing_item",
            expected_max_amount=209,
        ),
        ConversationCase(
            case_id="high-value-missing-low-trust-needs-proof",
            order_id="ORD004",
            item_name="Dhaba Style Chicken Curry Rice Bowl",
            turns=(
                {
                    "issue_type": "missing_item",
                    "complaint": "Dhaba Style Chicken Curry Rice Bowl missing hai, refund now",
                    "trust_score": 35,
                    "assessment": {
                        "issue_type": "missing_item",
                        "issue_confidence": 0.95,
                        "active_item_name": "Dhaba Style Chicken Curry Rice Bowl",
                        "requested_resolution": "refund",
                        "requested_resolution_confidence": 0.95,
                        "visual_evidence_useful": True,
                    },
                },
            ),
            expected_terminal_action="live_capture",
            expected_message_bits=("photo",),
            expected_terminal_issue_type="missing_item",
        ),
        ConversationCase(
            case_id="wrong-item-partial-order-asks-evidence",
            order_id="ORD002",
            item_name="Caesar Salad (Non-Veg)",
            turns=(
                {
                    "issue_type": "wrong_item",
                    "complaint": "Caesar Salad order kiya tha but sandwich aa gaya, baaki items sahi hain",
                    "assessment": {
                        "issue_type": "wrong_item",
                        "issue_confidence": 0.95,
                        "active_item_name": "Caesar Salad (Non-Veg)",
                        "visual_evidence_useful": True,
                    },
                },
                {
                    "issue_type": "wrong_item",
                    "complaint": "refund chahiye",
                    "assessment": {
                        "issue_type": "wrong_item",
                        "issue_confidence": 0.95,
                        "active_item_name": "Caesar Salad (Non-Veg)",
                        "requested_resolution": "refund",
                        "requested_resolution_confidence": 0.94,
                    },
                },
            ),
            expected_terminal_action="live_capture",
            expected_message_bits=("photo",),
            expected_terminal_issue_type="wrong_item",
        ),
        ConversationCase(
            case_id="entire-wrong-order-escalates-after-proof-fails",
            order_id="ORD001",
            item_name="item",
            turns=(
                {
                    "issue_type": "wrong_item",
                    "complaint": "ye mera order hi nahi hai kisi aur ka naam receipt pe hai",
                    "assessment": {
                        "issue_type": "wrong_item",
                        "issue_confidence": 0.95,
                        "requested_resolution": "refund",
                        "requested_resolution_confidence": 0.9,
                        "visual_evidence_useful": True,
                    },
                },
                {
                    "issue_type": "wrong_item",
                    "complaint": "photo bhej diya",
                    "photo_url": "https://example.com/wrong-order.jpg",
                    "photo_valid": False,
                    "assessment": {
                        "issue_type": "wrong_item",
                        "issue_confidence": 0.95,
                        "requested_resolution": "refund",
                        "requested_resolution_confidence": 0.9,
                        "visual_evidence_useful": True,
                    },
                },
            ),
            expected_terminal_action="escalate",
            expected_message_bits=("review",),
            expected_terminal_issue_type="wrong_item",
        ),
        ConversationCase(
            case_id="solid-item-spill-clarifies-not-blind-refund",
            order_id="ORD002",
            item_name="Grilled Paneer Club Sandwich",
            turns=(
                {
                    "issue_type": "damaged",
                    "complaint": "Grilled Paneer Club Sandwich spill ho gaya",
                    "assessment": {
                        "issue_type": "damaged",
                        "issue_confidence": 0.72,
                        "active_item_name": "Grilled Paneer Club Sandwich",
                        "clarification_needed": True,
                        "recommended_next_step": "clarify",
                    },
                },
            ),
            expected_terminal_action="info",
            expected_message_bits=("sandwich",),
            expected_terminal_issue_type="damaged",
        ),
        ConversationCase(
            case_id="taste-only-quality-stays-capped",
            order_id="ORD004",
            item_name="Veg Pink Sauce Pasta",
            turns=(
                {
                    "issue_type": "quality",
                    "complaint": "Veg Pink Sauce Pasta ka taste acha nahi tha",
                    "assessment": {
                        "issue_type": "quality",
                        "issue_confidence": 0.86,
                        "active_item_name": "Veg Pink Sauce Pasta",
                    },
                },
                {
                    "issue_type": "quality",
                    "complaint": "refund chahiye",
                    "assessment": {
                        "issue_type": "quality",
                        "issue_confidence": 0.86,
                        "active_item_name": "Veg Pink Sauce Pasta",
                        "requested_resolution": "refund",
                        "requested_resolution_confidence": 0.93,
                    },
                },
            ),
            expected_terminal_action="info",
            expected_message_bits=("coupon",),
            expected_terminal_issue_type="quality",
        ),
        ConversationCase(
            case_id="objective-quality-negotiates-before-refund",
            order_id="ORD004",
            item_name="Dhaba Style Chicken Curry Rice Bowl",
            turns=(
                {
                    "issue_type": "quality",
                    "complaint": "Chicken curry rice bowl burnt smell aa rahi thi khane layak nahi tha",
                    "assessment": {
                        "issue_type": "quality",
                        "issue_confidence": 0.95,
                        "active_item_name": "Dhaba Style Chicken Curry Rice Bowl",
                        "issue_severity": "medium",
                    },
                },
                {
                    "issue_type": "quality",
                    "complaint": "refund do",
                    "assessment": {
                        "issue_type": "quality",
                        "issue_confidence": 0.95,
                        "active_item_name": "Dhaba Style Chicken Curry Rice Bowl",
                        "requested_resolution": "refund",
                        "requested_resolution_confidence": 0.94,
                    },
                },
            ),
            expected_terminal_action="info",
            expected_message_bits=("coupon",),
            expected_terminal_issue_type="quality",
        ),
        ConversationCase(
            case_id="cold-food-delay-caused-capped-offer",
            order_id="ORD005",
            item_name="Mini Punjabi Aloo Samosa",
            turns=(
                {
                    "issue_type": "temperature",
                    "complaint": "Mini Punjabi Aloo Samosa garam hona chahiye tha but cold aa gaya",
                    "assessment": {
                        "issue_type": "temperature",
                        "issue_confidence": 0.93,
                        "active_item_name": "Mini Punjabi Aloo Samosa",
                    },
                },
                {
                    "issue_type": "temperature",
                    "complaint": "coupon ya refund kya milega",
                    "assessment": {
                        "issue_type": "temperature",
                        "issue_confidence": 0.93,
                        "active_item_name": "Mini Punjabi Aloo Samosa",
                        "requested_resolution": "refund",
                        "requested_resolution_confidence": 0.82,
                    },
                },
            ),
            expected_terminal_action="info",
            expected_message_bits=("coupon",),
            expected_terminal_issue_type="temperature",
        ),
        ConversationCase(
            case_id="delay-food-fine-does-not-food-refund",
            order_id="ORD003",
            item_name="",
            turns=(
                {
                    "issue_type": "delay",
                    "complaint": "order 25 minute late tha but food okay hai",
                    "assessment": {
                        "issue_type": "delay",
                        "issue_confidence": 0.94,
                    },
                },
                {
                    "issue_type": "delay",
                    "complaint": "kuch coupon milega kya",
                    "assessment": {
                        "issue_type": "delay",
                        "issue_confidence": 0.94,
                        "requested_resolution": "coupon",
                        "requested_resolution_confidence": 0.9,
                    },
                },
            ),
            expected_terminal_action="info",
            expected_terminal_issue_type="delay",
        ),
        ConversationCase(
            case_id="portion-followup-retains-issue",
            order_id="ORD005",
            item_name="Mini Punjabi Aloo Samosa",
            turns=(
                {
                    "issue_type": "portion_size",
                    "complaint": "Mini Punjabi Aloo Samosa quantity bahut kam thi box half empty tha",
                    "assessment": {
                        "issue_type": "portion_size",
                        "issue_confidence": 0.95,
                        "active_item_name": "Mini Punjabi Aloo Samosa",
                    },
                },
                {
                    "issue_type": "portion_size",
                    "complaint": "coupon ya refund kya milega",
                    "assessment": {
                        "issue_type": "portion_size",
                        "issue_confidence": 0.95,
                        "active_item_name": "Mini Punjabi Aloo Samosa",
                        "requested_resolution": "refund",
                        "requested_resolution_confidence": 0.9,
                    },
                },
            ),
            expected_terminal_action="info",
            expected_message_bits=("coupon",),
            expected_terminal_issue_type="portion_size",
        ),
        ConversationCase(
            case_id="foreign-object-safety-review",
            order_id="ORD003",
            item_name="Classic Maggi",
            turns=(
                {
                    "issue_type": "foreign_object",
                    "complaint": "Classic Maggi me plastic ka piece mila",
                    "assessment": {
                        "issue_type": "foreign_object",
                        "issue_confidence": 0.97,
                        "active_item_name": "Classic Maggi",
                        "issue_severity": "high",
                        "visual_evidence_useful": True,
                    },
                },
                {
                    "issue_type": "foreign_object",
                    "complaint": "please review this",
                    "assessment": {
                        "issue_type": "foreign_object",
                        "issue_confidence": 0.97,
                        "active_item_name": "Classic Maggi",
                        "issue_severity": "high",
                        "recommended_next_step": "escalate",
                    },
                },
            ),
            expected_terminal_action="escalate",
            expected_message_bits=("review",),
            expected_terminal_issue_type="foreign_object",
        ),
        ConversationCase(
            case_id="dietary-mismatch-sensitive-path",
            order_id="ORD005",
            item_name="Veg Alfredo Penne",
            turns=(
                {
                    "issue_type": "foreign_object",
                    "complaint": "Veg Alfredo Penne me chicken piece mila",
                    "assessment": {
                        "issue_type": "foreign_object",
                        "issue_confidence": 0.96,
                        "active_item_name": "Veg Alfredo Penne",
                        "issue_severity": "high",
                        "visual_evidence_useful": True,
                    },
                },
            ),
            expected_terminal_action="info",
            expected_message_bits=("seriously",),
            expected_terminal_issue_type="foreign_object",
        ),
        ConversationCase(
            case_id="harmless-ingredient-confusion-does-not-refund",
            order_id="ORD001",
            item_name="Butter Chicken Rice Bowl",
            turns=(
                {
                    "issue_type": "quality",
                    "complaint": "Butter Chicken Rice Bowl me vegetable tha",
                    "assessment": {
                        "issue_type": "quality",
                        "issue_confidence": 0.9,
                        "active_item_name": "Butter Chicken Rice Bowl",
                        "clarification_needed": False,
                    },
                },
            ),
            expected_terminal_action="info",
            expected_terminal_issue_type="quality",
        ),
        ConversationCase(
            case_id="coupon-rejection-escalates-not-infinite-offers",
            order_id="ORD003",
            item_name="Classic Maggi",
            turns=(
                {
                    "issue_type": "quality",
                    "complaint": "Classic Maggi quality bilkul kharab thi refund chahiye",
                    "assessment": {
                        "issue_type": "quality",
                        "issue_confidence": 0.94,
                        "active_item_name": "Classic Maggi",
                        "requested_resolution": "refund",
                        "requested_resolution_confidence": 0.93,
                    },
                },
                {
                    "issue_type": "quality",
                    "complaint": "coupon nahi chahiye refund do",
                    "assessment": {
                        "issue_type": "quality",
                        "issue_confidence": 0.94,
                        "active_item_name": "Classic Maggi",
                        "requested_resolution": "refund",
                        "requested_resolution_confidence": 0.93,
                        "turn_act": "reject",
                        "turn_act_confidence": 0.92,
                    },
                },
                {
                    "issue_type": "quality",
                    "complaint": "nahi refund hi chahiye",
                    "assessment": {
                        "issue_type": "quality",
                        "issue_confidence": 0.94,
                        "active_item_name": "Classic Maggi",
                        "requested_resolution": "refund",
                        "requested_resolution_confidence": 0.93,
                        "turn_act": "reject",
                        "turn_act_confidence": 0.92,
                    },
                },
            ),
            expected_terminal_action="escalate",
            expected_message_bits=("review",),
            expected_terminal_issue_type="quality",
        ),
        ConversationCase(
            case_id="replacement-request-checks-economics",
            order_id="ORD002",
            item_name="Grilled Paneer Club Sandwich",
            turns=(
                {
                    "issue_type": "quality",
                    "complaint": "Grilled Paneer Club Sandwich soggy tha fresh bhej do",
                    "assessment": {
                        "issue_type": "quality",
                        "issue_confidence": 0.9,
                        "active_item_name": "Grilled Paneer Club Sandwich",
                        "requested_resolution": "replacement",
                        "requested_resolution_confidence": 0.93,
                    },
                },
                {
                    "issue_type": "quality",
                    "complaint": "same item fresh bhej do",
                    "assessment": {
                        "issue_type": "quality",
                        "issue_confidence": 0.9,
                        "active_item_name": "Grilled Paneer Club Sandwich",
                        "requested_resolution": "replacement",
                        "requested_resolution_confidence": 0.93,
                        "turn_act": "reject",
                        "turn_act_confidence": 0.9,
                    },
                },
            ),
            expected_terminal_action="info",
            expected_message_bits=("coupon",),
            expected_terminal_issue_type="quality",
        ),
        ConversationCase(
            case_id="refund-status-does-not-reopen-quality",
            order_id="ORD002",
            item_name="Classic Cold Coffee",
            turns=(
                {
                    "issue_type": "quality",
                    "complaint": "Classic Cold Coffee bahut meetha tha",
                    "assessment": {
                        "issue_type": "quality",
                        "issue_confidence": 0.91,
                        "active_item_name": "Classic Cold Coffee",
                    },
                },
                {
                    "issue_type": "info_query",
                    "complaint": "refund kab aayega",
                    "assessment": {
                        "issue_type": "info_query",
                        "issue_confidence": 0.95,
                        "info_query": "status",
                        "info_query_confidence": 0.95,
                        "turn_act": "ask_status",
                        "turn_act_confidence": 0.95,
                    },
                },
            ),
            expected_terminal_action="info",
            expected_message_bits=("delivered",),
            expected_terminal_issue_type="info_query",
        ),
        ConversationCase(
            case_id="picker-confirmation-continues-selected-flow",
            order_id="ORD004",
            item_name="Roohafza Sharbat",
            turns=(
                {
                    "issue_type": "spill_leak",
                    "complaint": "Roohafza Sharbat has spillage issue",
                    "assessment": {
                        "issue_type": "spill_leak",
                        "issue_confidence": 0.95,
                        "active_item_name": "Roohafza Sharbat",
                        "visual_evidence_useful": True,
                    },
                },
                {
                    "issue_type": "spill_leak",
                    "complaint": "haan same issue hai",
                    "assessment": {
                        "issue_type": "spill_leak",
                        "issue_confidence": 0.9,
                        "active_item_name": "Roohafza Sharbat",
                        "turn_act": "confirm",
                        "turn_act_confidence": 0.9,
                    },
                },
            ),
            expected_terminal_action="info",
            expected_terminal_issue_type="spill_leak",
        ),
        ConversationCase(
            case_id="closed-case-reopen-escalates-with-context",
            order_id="ORD003",
            item_name="Classic Maggi",
            turns=(
                {
                    "issue_type": "quality",
                    "complaint": "Classic Maggi soggy thi refund chahiye",
                    "assessment": {
                        "issue_type": "quality",
                        "issue_confidence": 0.94,
                        "active_item_name": "Classic Maggi",
                        "requested_resolution": "refund",
                        "requested_resolution_confidence": 0.93,
                    },
                },
                {
                    "issue_type": "quality",
                    "complaint": "coupon nahi chahiye refund do",
                    "assessment": {
                        "issue_type": "quality",
                        "issue_confidence": 0.94,
                        "active_item_name": "Classic Maggi",
                        "requested_resolution": "refund",
                        "requested_resolution_confidence": 0.93,
                        "turn_act": "reject",
                        "turn_act_confidence": 0.92,
                    },
                },
                {
                    "issue_type": "quality",
                    "complaint": "issue close kyun kar diya problem solve nahi hua",
                    "assessment": {
                        "issue_type": "quality",
                        "issue_confidence": 0.94,
                        "active_item_name": "Classic Maggi",
                        "recommended_next_step": "escalate",
                    },
                },
            ),
            expected_terminal_action="escalate",
            expected_message_bits=("review",),
            expected_terminal_issue_type="quality",
        ),
        ConversationCase(
            case_id="delivery-partner-non-delivery-not-food-quality",
            order_id="ORD001",
            item_name="item",
            turns=(
                {
                    "issue_type": "missing_item",
                    "complaint": "rider ne bola item nahi hai but app delivered dikha raha hai",
                    "assessment": {
                        "issue_type": "missing_item",
                        "issue_confidence": 0.9,
                        "fault_hint": "delivery",
                    },
                },
            ),
            expected_terminal_action="info",
            expected_terminal_issue_type="missing_item",
        ),
        ConversationCase(
            case_id="payment-failed-not-food-complaint",
            order_id="ORD001",
            item_name="",
            turns=(
                {
                    "issue_type": "info_query",
                    "complaint": "payment cut gaya but order fail ho gaya",
                    "assessment": {
                        "issue_type": "info_query",
                        "issue_confidence": 0.9,
                        "info_query": "status",
                        "info_query_confidence": 0.9,
                    },
                },
            ),
            expected_terminal_action="info",
            expected_message_bits=("delivered",),
            expected_terminal_issue_type="info_query",
        ),
    ]


@pytest.mark.parametrize("case", _practical_openers(), ids=lambda case: case.case_id)
def test_practical_customer_openers_are_understood(case: OpenerCase):
    session_id = f"qa:{case.case_id}"
    clear_session(session_id)

    assessment = {
        "issue_type": case.issue_type,
        "issue_confidence": 0.94,
    }
    if case.item_name:
        assessment["active_item_name"] = case.item_name
    if case.issue_type in {"wrong_item", "missing_item", "spill_leak", "foreign_object"}:
        assessment["visual_evidence_useful"] = True
    result = _run_turn(session_id, case.order_id, case.complaint, case.issue_type, assessment=assessment)

    assert result["action"] in VALID_ACTIONS
    assert result["message"].strip()
    assert style_warnings(result["message"]) == []
    assert evaluate_response_quality(
        result,
        complaint=case.complaint,
        order_items=_runtime_context(case.order_id, case.issue_type)["order_items"],
        expected_issue_type=case.issue_type,
        expected_item_name=case.item_name,
    ) == []
    assert result["_debug"]["issue_type"] == case.issue_type
    assert result["_debug"]["issue_type_source"] == "llm"
    assert "i completely understand" not in result["message"].lower()
    assert "any inconvenience" not in result["message"].lower()
    if case.item_name:
        assert result["_debug"]["active_item_name"] == case.item_name


@pytest.mark.parametrize("case", _conversation_cases(), ids=lambda case: case.case_id)
def test_generated_behavioral_conversations_reach_expected_terminal_action(case: ConversationCase):
    session_id = f"qa:{case.case_id}"
    clear_session(session_id)

    result = None
    previous_messages = []
    for turn in case.turns:
        result = _run_turn(
            session_id,
            case.order_id,
            turn["complaint"],
            turn["issue_type"],
            photo_url=turn.get("photo_url"),
            photo_valid=turn.get("photo_valid"),
            assessment=turn.get("assessment"),
            trust_score=turn.get("trust_score"),
        )
        assert evaluate_response_quality(
            result,
            complaint=turn["complaint"],
            order_items=_runtime_context(case.order_id, turn["issue_type"])["order_items"],
            expected_issue_type=_result_issue_type(result, session_id) or turn["issue_type"],
            expected_item_name=(result.get("_debug") or {}).get("active_item_name") or case.item_name,
            previous_messages=previous_messages,
        ) == []
        previous_messages.append(result["message"])

    assert result is not None
    assert result["action"] == case.expected_terminal_action
    assert style_warnings(result["message"]) == []
    for bit in case.expected_message_bits:
        assert bit.lower() in result["message"].lower()
    if case.expected_terminal_issue_type:
        assert _result_issue_type(result, session_id) == case.expected_terminal_issue_type
    if case.expected_max_amount is not None:
        assert float(result.get("amount") or 0.0) <= case.expected_max_amount


@pytest.mark.parametrize("order_id", sorted(ORDER_DATABASE.keys()))
def test_order_level_info_queries_work_for_every_order(order_id: str):
    session_id = f"qa:{order_id}:info"
    clear_session(session_id)
    order = ORDER_DATABASE[order_id]

    queries = (
        ("what were the items in this order?", "items"),
        ("what was the total for this order?", "total"),
        ("what is the order status?", "status"),
    )
    results = []
    for complaint, expected_query in queries:
        result = _run_turn(
            session_id,
            order_id,
            complaint,
            "info_query",
            assessment={
                "issue_type": "info_query",
                "issue_confidence": 0.95,
                "info_query": expected_query,
                "info_query_confidence": 0.95,
            },
        )
        results.append(result)
        assert result["action"] == "info"
        assert evaluate_response_quality(
            result,
            complaint=complaint,
            order_items={"items": order["items"]},
            expected_issue_type="info_query",
            previous_messages=[item["message"] for item in results[:-1]],
        ) == []

    assert order["items"][0]["name"].lower() in results[0]["message"].lower()
    assert str(order["total_amount"]) in results[1]["message"]
    assert order["status"].lower() in results[2]["message"].lower()


def test_adversarial_issue_item_mix_does_not_break_resolution():
    weird_pairs = [
        ("ORD002", "Grilled Paneer Club Sandwich", "Grilled Paneer Club Sandwich bag ke andar spill ho gaya"),
        ("ORD003", "Classic Maggi", "Classic Maggi missing tha aur thoda cold bhi tha"),
        ("ORD004", "Roohafza Sharbat", "Roohafza Sharbat me plastic jaisa kuch nikla"),
    ]

    for order_id, item_name, complaint in weird_pairs:
        session_id = f"qa:weird:{order_id}:{item_name.lower().replace(' ', '-')}"
        clear_session(session_id)
        result = _run_turn(session_id, order_id, complaint, "quality")
        assert result["action"] in VALID_ACTIONS
        assert result["message"].strip()
        assert evaluate_response_quality(
            result,
            complaint=complaint,
            order_items=_runtime_context(order_id, "quality")["order_items"],
            expected_issue_type=(result.get("_debug") or {}).get("issue_type") or "quality",
            expected_item_name=item_name,
        ) == []
        assert result["_debug"]["active_item_name"] == item_name
