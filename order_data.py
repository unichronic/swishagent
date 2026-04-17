"""
Order data for demo/testing
Contains realistic order details that the agent can reference
"""

ORDER_DATABASE = {
    "ORD001": {
        "order_id": "ORD001",
        "status": "delivered",
        "total_amount": 478,
        "placed_at": "18th Apr 2026, 01:15 pm",
        "delivered_at": "18th Apr 2026, 02:00 pm",
        "delivery_time": "45 mins",
        "restaurant": "Fulfilling Dinner",
        "delivery_address": "123 MG Road, Bangalore",
        "payment_method": "UPI",
        "items": [
            {
                "name": "Butter Chicken Rice Bowl",
                "price": 269,
                "quantity": 1,
                "description": "Creamy butter chicken with jeera rice",
                "category": "Non-Veg",
                "customizations": []
            },
            {
                "name": "Peri Peri French Fries",
                "price": 209,
                "quantity": 1,
                "description": "French fries sprinkled with peri peri masala",
                "category": "Sides",
                "customizations": []
            }
        ],
        "delivery_partner": "Rahul K.",
        "delivery_partner_phone": "+91-98765-43210"
    },
    "ORD002": {
        "order_id": "ORD002",
        "status": "delivered",
        "total_amount": 627,
        "placed_at": "17th Apr 2026, 08:45 pm",
        "delivered_at": "17th Apr 2026, 09:23 pm",
        "delivery_time": "38 mins",
        "restaurant": "Fulfilling Dinner",
        "delivery_address": "456 Indiranagar, Bangalore",
        "payment_method": "Credit Card",
        "items": [
            {
                "name": "Caesar Salad (Non-Veg)",
                "price": 259,
                "quantity": 1,
                "description": "Fresh veggies & chicken with caesar dressing",
                "category": "Salads",
                "customizations": ["Extra dressing"]
            },
            {
                "name": "Grilled Paneer Club Sandwich",
                "price": 219,
                "quantity": 1,
                "description": "Paneer club sandwich, served fresh in 4 slices",
                "category": "Sandwiches",
                "customizations": []
            },
            {
                "name": "Classic Cold Coffee",
                "price": 159,
                "quantity": 1,
                "description": "Chilled creamy coffee, as classic as it gets",
                "category": "Beverages",
                "customizations": ["Less sugar"]
            }
        ],
        "delivery_partner": "Amit S.",
        "delivery_partner_phone": "+91-98765-43211"
    },
    "ORD003": {
        "order_id": "ORD003",
        "status": "delivered",
        "total_amount": 168,
        "placed_at": "16th Apr 2026, 02:30 pm",
        "delivered_at": "16th Apr 2026, 02:55 pm",
        "delivery_time": "25 mins",
        "restaurant": "Under ₹99",
        "delivery_address": "789 Koramangala, Bangalore",
        "payment_method": "Cash on Delivery",
        "items": [
            {
                "name": "Batata Vada Shots",
                "price": 89,
                "quantity": 1,
                "description": "Bite-sized batata vadas served with green chutney",
                "category": "Snacks",
                "customizations": [],
                "quantity_detail": "6 pieces"
            },
            {
                "name": "Classic Maggi",
                "price": 79,
                "quantity": 1,
                "description": "Your favorite noodles with the signature masala",
                "category": "Quick Bites",
                "customizations": []
            }
        ],
        "delivery_partner": "Priya M.",
        "delivery_partner_phone": "+91-98765-43212"
    },
    "ORD004": {
        "order_id": "ORD004",
        "status": "delivered",
        "total_amount": 756,
        "placed_at": "15th Apr 2026, 07:20 pm",
        "delivered_at": "15th Apr 2026, 08:12 pm",
        "delivery_time": "52 mins",
        "restaurant": "Fulfilling Dinner",
        "delivery_address": "321 Whitefield, Bangalore",
        "payment_method": "Paytm",
        "items": [
            {
                "name": "Dhaba Style Chicken Curry Rice Bowl",
                "price": 269,
                "quantity": 1,
                "description": "Rustic dhaba-style chicken curry with jeera rice",
                "category": "Non-Veg",
                "customizations": ["Extra spicy"]
            },
            {
                "name": "Veg Pink Sauce Pasta",
                "price": 219,
                "quantity": 1,
                "description": "Penne in creamy pink sauce with veggies and herbs",
                "category": "Pasta",
                "customizations": []
            },
            {
                "name": "Roohafza Sharbat",
                "price": 79,
                "quantity": 1,
                "description": "Nostalgic Rooh Afza cooler (sharbat), fragrant and refreshing",
                "category": "Beverages",
                "customizations": [],
                "quantity_detail": "450 ml"
            },
            {
                "name": "Dark Chocolate Oreo Shake",
                "price": 189,
                "quantity": 1,
                "description": "Creamy chocolate shake with Oreo chunks",
                "category": "Beverages",
                "customizations": [],
                "quantity_detail": "450 ml"
            }
        ],
        "delivery_partner": "Vijay R.",
        "delivery_partner_phone": "+91-98765-43213"
    },
    "ORD005": {
        "order_id": "ORD005",
        "status": "delivered",
        "total_amount": 437,
        "placed_at": "14th Apr 2026, 12:45 pm",
        "delivered_at": "14th Apr 2026, 01:20 pm",
        "delivery_time": "35 mins",
        "restaurant": "Fulfilling Dinner",
        "delivery_address": "555 HSR Layout, Bangalore",
        "payment_method": "Google Pay",
        "items": [
            {
                "name": "Veg Alfredo Penne",
                "price": 209,
                "quantity": 1,
                "description": "Creamy penne with veggies and herbs",
                "category": "Pasta",
                "customizations": []
            },
            {
                "name": "Egg Curry Rice Bowl",
                "price": 209,
                "quantity": 1,
                "description": "Egg curry with jeera basmati rice",
                "category": "Rice Bowls",
                "customizations": []
            },
            {
                "name": "Mini Punjabi Aloo Samosa",
                "price": 99,
                "quantity": 1,
                "description": "As classic as samosa gets, comes with chutneys",
                "category": "Snacks",
                "customizations": [],
                "quantity_detail": "3 pieces"
            }
        ],
        "delivery_partner": "Deepak T.",
        "delivery_partner_phone": "+91-98765-43214"
    }
}


def get_order_details(order_id: str) -> dict:
    """Get order details for a given order ID"""
    return ORDER_DATABASE.get(order_id)


def format_order_context(order_id: str) -> str:
    """Format order details for agent context"""
    order = get_order_details(order_id)
    if not order:
        return f"Order {order_id} not found in system."
    
    items_text = "\n".join([
        f"  - {item['name']} (₹{item['price']}) x{item['quantity']}"
        + (f" - {item['quantity_detail']}" if 'quantity_detail' in item else "")
        + (f"\n    Customizations: {', '.join(item['customizations'])}" if item['customizations'] else "")
        for item in order['items']
    ])
    
    return f"""ORDER DETAILS FOR {order_id}:
Restaurant: {order['restaurant']}
Total: ₹{order['total_amount']}
Placed: {order['placed_at']}
Delivered: {order['delivered_at']} (took {order['delivery_time']})
Payment: {order['payment_method']}
Delivery Address: {order['delivery_address']}
Delivery Partner: {order['delivery_partner']} ({order['delivery_partner_phone']})

ITEMS ORDERED:
{items_text}

Status: {order['status']}"""
