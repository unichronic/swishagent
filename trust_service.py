"""
Trust Service API
Manages user trust scores and fraud detection
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


@app.get("/trust/{user_id}")
def get_trust_score(user_id: str):
    """Get trust score and order history for a user"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT user_id, score, total_orders, refund_requests,
                       successful_orders, cancelled_orders, avg_order_value,
                       account_age_days, last_order_date
                FROM user_trust WHERE user_id = %s
            """, (user_id,))
            trust = cur.fetchone()
            if not trust:
                raise HTTPException(status_code=404, detail="User not found")
            return dict(trust)
    finally:
        conn.close()


@app.get("/health")
def health():
    try:
        conn = get_db_connection()
        conn.close()
        return {"status": "ok", "service": "trust-service", "database": "connected"}
    except Exception as e:
        return {"status": "error", "service": "trust-service", "database": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8083)
