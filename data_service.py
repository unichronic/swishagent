"""
Consolidated data service — order, kitchen, fleet, trust on a single process.
"""
from fastapi import FastAPI, HTTPException
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

def get_db():
    return psycopg2.connect(os.getenv("DB_URL", "postgresql://postgres:postgres@localhost:5432/swishagent"), cursor_factory=RealDictCursor)


# --- Order ---

@app.get("/order/{order_id}")
def get_order(order_id: str):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT order_id, user_id, status, total_amount, placed_at, delivered_at,
                       delivery_time_mins, restaurant_id, restaurant_name, delivery_address,
                       payment_method, delivery_partner_name, delivery_partner_phone
                FROM orders WHERE order_id = %s
            """, (order_id,))
            row = cur.fetchone()
            if not row: raise HTTPException(status_code=404, detail="Order not found")
            return dict(row)
    finally:
        conn.close()

@app.get("/order/{order_id}/items")
def get_order_items(order_id: str):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM orders WHERE order_id = %s", (order_id,))
            if not cur.fetchone(): raise HTTPException(status_code=404, detail="Order not found")
            cur.execute("""
                SELECT item_id, name, price, quantity, description, category, quantity_detail
                FROM order_items WHERE order_id = %s
            """, (order_id,))
            items = [dict(r) for r in cur.fetchall()]
            for item in items:
                cur.execute("SELECT customization FROM item_customizations WHERE order_id = %s AND item_id = %s", (order_id, item['item_id']))
                item['customizations'] = [r['customization'] for r in cur.fetchall()]
            return {"order_id": order_id, "items": items}
    finally:
        conn.close()

@app.get("/order/{order_id}/item/{item_name}")
def get_specific_item(order_id: str, item_name: str):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT item_id, name, price, quantity, description, category, quantity_detail FROM order_items WHERE order_id = %s AND LOWER(name) LIKE %s LIMIT 1", (order_id, f"%{item_name.lower()}%"))
            item = cur.fetchone()
            if not item: raise HTTPException(status_code=404, detail=f"Item '{item_name}' not found")
            item = dict(item)
            cur.execute("SELECT customization FROM item_customizations WHERE order_id = %s AND item_id = %s", (order_id, item['item_id']))
            item['customizations'] = [r['customization'] for r in cur.fetchall()]
            return item
    finally:
        conn.close()

@app.get("/order/{order_id}/total")
def get_order_total(order_id: str):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT order_id, total_amount, payment_method FROM orders WHERE order_id = %s", (order_id,))
            row = cur.fetchone()
            if not row: raise HTTPException(status_code=404, detail="Order not found")
            return dict(row)
    finally:
        conn.close()

@app.get("/order/{order_id}/delivery")
def get_delivery_info(order_id: str):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT order_id, delivery_partner_name, delivery_partner_phone, delivery_address, placed_at, delivered_at, delivery_time_mins FROM orders WHERE order_id = %s", (order_id,))
            row = cur.fetchone()
            if not row: raise HTTPException(status_code=404, detail="Order not found")
            return dict(row)
    finally:
        conn.close()


# --- Kitchen ---

@app.get("/kitchen/log/{order_id}")
def get_kitchen_log(order_id: str):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT order_id, status, quality_out, prep_time_mins, temperature_check, dispatched_at FROM kitchen_logs WHERE order_id = %s", (order_id,))
            row = cur.fetchone()
            if not row: raise HTTPException(status_code=404, detail="Kitchen log not found")
            return dict(row)
    finally:
        conn.close()


# --- Fleet ---

@app.get("/fleet/status/{order_id}")
def get_fleet_status(order_id: str):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT order_id, within_geofence, delay_mins, traffic_flag, delivered, pickup_time, delivery_time, distance_km, notes FROM fleet_status WHERE order_id = %s", (order_id,))
            row = cur.fetchone()
            if not row: raise HTTPException(status_code=404, detail="Fleet status not found")
            return dict(row)
    finally:
        conn.close()


# --- Trust ---

@app.get("/trust/{user_id}")
def get_trust_score(user_id: str):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id, score, total_orders, refund_requests, successful_orders, cancelled_orders, avg_order_value, account_age_days, last_order_date FROM user_trust WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            if not row: raise HTTPException(status_code=404, detail="User not found")
            return dict(row)
    finally:
        conn.close()


# --- Health ---

@app.get("/health")
def health():
    try:
        conn = get_db()
        conn.close()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)
