-- Fleet Service Database Schema and Seed Data

CREATE TABLE IF NOT EXISTS fleet_status (
    id SERIAL PRIMARY KEY,
    order_id VARCHAR(50) UNIQUE NOT NULL,
    within_geofence BOOLEAN DEFAULT TRUE,
    delay_mins INTEGER DEFAULT 0,
    traffic_flag BOOLEAN DEFAULT FALSE,
    delivered BOOLEAN DEFAULT TRUE,
    pickup_time VARCHAR(50),
    delivery_time VARCHAR(50),
    distance_km DECIMAL(5, 2),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Seed fleet status for demo orders
INSERT INTO fleet_status (order_id, within_geofence, delay_mins, traffic_flag, delivered, pickup_time, delivery_time, distance_km, notes) VALUES
-- ORD001: Butter Chicken + Fries
('ORD001', true, 5, false, true, '01:20 pm', '02:00 pm', 3.2, 'Smooth delivery, minor delay at pickup'),

-- ORD002: Salad + Sandwich + Coffee
('ORD002', true, 8, true, true, '08:55 pm', '09:23 pm', 4.5, 'Traffic on main road, driver waited at signal'),

-- ORD003: Vada Shots + Maggi
('ORD003', true, 0, false, true, '02:35 pm', '02:55 pm', 2.1, 'Quick delivery, no issues'),

-- ORD004: Chicken Curry + Pasta + 2 Beverages
('ORD004', false, 15, true, true, '07:35 pm', '08:12 pm', 8.7, 'Heavy traffic to Whitefield, driver took alternate route'),

-- ORD005: 2 Pasta + Samosa
('ORD005', true, 3, false, true, '12:52 pm', '01:20 pm', 3.8, 'Normal delivery, slight delay at restaurant');

CREATE INDEX idx_fleet_status_order_id ON fleet_status(order_id);
