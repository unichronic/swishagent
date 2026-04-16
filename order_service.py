"""
Order Service API
Manages order data with PostgreSQL database
"""

from fastapi import FastAPI, HTTPException
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

def get_db_connection():
    """Get database connection"""
    return psycopg2.connect(os.getenv("DB_URL", "postgresql://postgres:postgres@localhost:5432/swishagent"), cursor_factory=RealDictCursor)


@app.get("/order/{order_id}")
def get_order(order_id: str):
    """Get basic order information"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT order_id, user_id, status, total_amount, placed_at, delivered_at,
                       delivery_time_mins, restaurant_id, restaurant_name, delivery_address,
                       payment_method, delivery_partner_name, delivery_partner_phone
                FROM orders WHERE order_id = %s
            """, (order_id,))
            order = cur.fetchone()
            if not order:
                raise HTTPException(status_code=404, detail="Order not found")
            return dict(order)
    finally:
        conn.close()


@app.get("/order/{order_id}/items")
def get_order_items(order_id: str):
    """Get all items in an order with customizations"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Check if order exists
            cur.execute("SELECT 1 FROM orders WHERE order_id = %s", (order_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Order not found")
            
            # Get items
            cur.execute("""
                SELECT item_id, name, price, quantity, description, category, quantity_detail
                FROM order_items WHERE order_id = %s
            """, (order_id,))
            items = [dict(row) for row in cur.fetchall()]
            
            # Get customizations for each item
            for item in items:
                cur.execute("""
                    SELECT customization FROM item_customizations
                    WHERE order_id = %s AND item_id = %s
                """, (order_id, item['item_id']))
                item['customizations'] = [row['customization'] for row in cur.fetchall()]
            
            return {"order_id": order_id, "items": items}
    finally:
        conn.close()


@app.get("/order/{order_id}/item/{item_name}")
def get_specific_item(order_id: str, item_name: str):
    """Get details of a specific item in an order"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT item_id, name, price, quantity, description, category, quantity_detail
                FROM order_items 
                WHERE order_id = %s AND LOWER(name) LIKE %s
                LIMIT 1
            """, (order_id, f"%{item_name.lower()}%"))
            item = cur.fetchone()
            
            if not item:
                raise HTTPException(status_code=404, detail=f"Item '{item_name}' not found in order")
            
            item = dict(item)
            
            # Get customizations
            cur.execute("""
                SELECT customization FROM item_customizations
                WHERE order_id = %s AND item_id = %s
            """, (order_id, item['item_id']))
            item['customizations'] = [row['customization'] for row in cur.fetchall()]
            
            return item
    finally:
        conn.close()


@app.get("/order/{order_id}/total")
def get_order_total(order_id: str):
    """Get order total amount"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT order_id, total_amount, payment_method
                FROM orders WHERE order_id = %s
            """, (order_id,))
            result = cur.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Order not found")
            return dict(result)
    finally:
        conn.close()


@app.get("/order/{order_id}/delivery")
def get_delivery_info(order_id: str):
    """Get delivery information for an order"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT order_id, delivery_partner_name, delivery_partner_phone,
                       delivery_address, placed_at, delivered_at, delivery_time_mins
                FROM orders WHERE order_id = %s
            """, (order_id,))
            result = cur.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Order not found")
            return dict(result)
    finally:
        conn.close()


@app.get("/health")
def health():
    """Health check endpoint"""
    try:
        conn = get_db_connection()
        conn.close()
        return {"status": "ok", "service": "order-service", "database": "connected"}
    except Exception as e:
        return {"status": "error", "service": "order-service", "database": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8084)

