from dataclasses import dataclass

import pytest

from order_data import ORDER_DATABASE
from rules import Rules, clear_session, get_session, mark_photo_provided, session_has_photo


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
        trust_score=float(ctx["trust"]["score"]),
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
            expected_terminal_action="info",
            expected_message_bits=("fresh classic cold coffee",),
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
    for turn in case.turns:
        result = _run_turn(
            session_id,
            case.order_id,
            turn["complaint"],
            turn["issue_type"],
            photo_url=turn.get("photo_url"),
            photo_valid=turn.get("photo_valid"),
            assessment=turn.get("assessment"),
        )

    assert result is not None
    assert result["action"] == case.expected_terminal_action
    for bit in case.expected_message_bits:
        assert bit.lower() in result["message"].lower()


@pytest.mark.parametrize("order_id", sorted(ORDER_DATABASE.keys()))
def test_order_level_info_queries_work_for_every_order(order_id: str):
    session_id = f"qa:{order_id}:info"
    clear_session(session_id)

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

    order = ORDER_DATABASE[order_id]
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
        assert result["_debug"]["active_item_name"] == item_name
