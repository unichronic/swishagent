"""
Fleet Service API
Tracks delivery partner and delivery status
"""

from fastapi import FastAPI, HTTPException
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

def get_db_connection():
    return psycopg2.connect(os.getenv("DB_URL", "postgresql://postgres:postgres@localhost:5432/swishagent"), cursor_factory=RealDictCursor)


@app.get("/fleet/status/{order_id}")
def get_fleet_status(order_id: str):
    """Get delivery fleet status for an order"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT order_id, within_geofence, delay_mins, traffic_flag,
                       delivered, pickup_time, delivery_time, distance_km, notes
                FROM fleet_status WHERE order_id = %s
            """, (order_id,))
            status = cur.fetchone()
            if not status:
                raise HTTPException(status_code=404, detail="Fleet status not found")
            return dict(status)
    finally:
        conn.close()


@app.get("/health")
def health():
    try:
        conn = get_db_connection()
        conn.close()
        return {"status": "ok", "service": "fleet-service", "database": "connected"}
    except Exception as e:
        return {"status": "error", "service": "fleet-service", "database": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8082)
