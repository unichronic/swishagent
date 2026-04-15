-- Kitchen Service Database Schema and Seed Data
-- Minimal schema reflecting real-world kitchen data availability

CREATE TABLE IF NOT EXISTS kitchen_logs (
    id SERIAL PRIMARY KEY,
    order_id VARCHAR(50) UNIQUE NOT NULL,
    status VARCHAR(20) NOT NULL,          -- 'preparing' | 'dispatched'
    quality_out VARCHAR(20) NOT NULL,     -- 'good' | 'fair' | 'bad'
    prep_time_mins INTEGER,               -- actual prep time
    temperature_check VARCHAR(20),        -- 'hot' | 'warm' | 'cold' at dispatch
    dispatched_at TIMESTAMP,              -- when order left kitchen
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO kitchen_logs (order_id, status, quality_out, prep_time_mins, temperature_check, dispatched_at) VALUES
('ORD001', 'dispatched', 'good',  12, 'hot',  NOW() - INTERVAL '2 hours'),
('ORD002', 'dispatched', 'good',  15, 'cold', NOW() - INTERVAL '3 hours'),
('ORD003', 'dispatched', 'fair',  18, 'warm', NOW() - INTERVAL '1 hour'),
('ORD004', 'dispatched', 'good',  20, 'hot',  NOW() - INTERVAL '30 minutes'),
('ORD005', 'dispatched', 'good',  14, 'hot',  NOW() - INTERVAL '45 minutes');

CREATE INDEX idx_kitchen_logs_order_id ON kitchen_logs(order_id);
