"""
Kitchen Service API
Tracks food preparation and quality checks
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


@app.get("/kitchen/log/{order_id}")
def get_kitchen_log(order_id: str):
    """Get kitchen preparation log for an order"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT order_id, status, quality_out,
                       prep_time_mins, temperature_check, dispatched_at
                FROM kitchen_logs WHERE order_id = %s
            """, (order_id,))
            log = cur.fetchone()
            if not log:
                raise HTTPException(status_code=404, detail="Kitchen log not found")
            return dict(log)
    finally:
        conn.close()


@app.get("/health")
def health():
    try:
        conn = get_db_connection()
        conn.close()
        return {"status": "ok", "service": "kitchen-service", "database": "connected"}
    except Exception as e:
        return {"status": "error", "service": "kitchen-service", "database": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)
