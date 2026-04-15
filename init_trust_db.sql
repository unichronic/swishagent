-- Trust Service Database Schema and Seed Data

CREATE TABLE IF NOT EXISTS user_trust (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(50) UNIQUE NOT NULL,
    score INTEGER NOT NULL CHECK (score >= 0 AND score <= 100),
    total_orders INTEGER DEFAULT 0,
    refund_requests INTEGER DEFAULT 0,
    successful_orders INTEGER DEFAULT 0,
    cancelled_orders INTEGER DEFAULT 0,
    avg_order_value DECIMAL(10, 2),
    account_age_days INTEGER,
    last_order_date VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Seed trust data for demo user
INSERT INTO user_trust (user_id, score, total_orders, refund_requests, successful_orders, cancelled_orders, avg_order_value, account_age_days, last_order_date) VALUES
('USER123', 85, 47, 3, 44, 0, 425.50, 180, '18th Apr 2026');

CREATE INDEX idx_user_trust_user_id ON user_trust(user_id);
