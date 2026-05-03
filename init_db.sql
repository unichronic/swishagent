-- Consolidated database schema for all services

-- Order Service Tables
CREATE TABLE IF NOT EXISTS orders (
    order_id VARCHAR(50) PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(10, 2) NOT NULL,
    placed_at VARCHAR(50) NOT NULL,
    delivered_at VARCHAR(50),
    delivery_time_mins INTEGER,
    restaurant_id VARCHAR(50) NOT NULL,
    restaurant_name VARCHAR(100) NOT NULL,
    delivery_address TEXT NOT NULL,
    payment_method VARCHAR(50) NOT NULL,
    delivery_partner_name VARCHAR(100),
    delivery_partner_phone VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS order_items (
    id SERIAL PRIMARY KEY,
    order_id VARCHAR(50) NOT NULL REFERENCES orders(order_id),
    item_id VARCHAR(50) NOT NULL,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    description TEXT,
    category VARCHAR(50),
    quantity_detail VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS item_customizations (
    id SERIAL PRIMARY KEY,
    order_id VARCHAR(50) NOT NULL,
    item_id VARCHAR(50) NOT NULL,
    customization VARCHAR(200) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

-- Kitchen Service Tables
CREATE TABLE IF NOT EXISTS kitchen_logs (
    id SERIAL PRIMARY KEY,
    order_id VARCHAR(50) UNIQUE NOT NULL,
    status VARCHAR(20) NOT NULL,
    quality_out VARCHAR(20) NOT NULL,
    prep_time_mins INTEGER,
    temperature_check VARCHAR(20),
    dispatched_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Fleet Service Tables
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

-- Trust Service Tables
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

-- Indexes
CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_item_customizations_order_id ON item_customizations(order_id);
CREATE INDEX IF NOT EXISTS idx_kitchen_logs_order_id ON kitchen_logs(order_id);
CREATE INDEX IF NOT EXISTS idx_fleet_status_order_id ON fleet_status(order_id);
CREATE INDEX IF NOT EXISTS idx_user_trust_user_id ON user_trust(user_id);

-- Seed Data: Orders
INSERT INTO orders (order_id, user_id, status, total_amount, placed_at, delivered_at, delivery_time_mins,
                    restaurant_id, restaurant_name, delivery_address, payment_method,
                    delivery_partner_name, delivery_partner_phone) VALUES
('ORD001', 'USER123', 'delivered', 478, '18th Apr 2026, 01:15 pm', '18th Apr 2026, 02:00 pm', 45,
 'SWISH001', 'Swish Cloud Kitchen', '123 MG Road, Bangalore', 'UPI', 'Rahul K.', '+91-98765-43210'),
('ORD002', 'USER123', 'delivered', 627, '17th Apr 2026, 08:45 pm', '17th Apr 2026, 09:23 pm', 38,
 'SWISH001', 'Swish Cloud Kitchen', '456 Indiranagar, Bangalore', 'Credit Card', 'Amit S.', '+91-98765-43211'),
('ORD003', 'USER123', 'delivered', 168, '16th Apr 2026, 02:30 pm', '16th Apr 2026, 02:55 pm', 25,
 'SWISH001', 'Swish Cloud Kitchen', '789 Koramangala, Bangalore', 'Cash on Delivery', 'Priya M.', '+91-98765-43212'),
('ORD004', 'USER123', 'delivered', 756, '15th Apr 2026, 07:20 pm', '15th Apr 2026, 08:12 pm', 52,
 'SWISH001', 'Swish Cloud Kitchen', '321 Whitefield, Bangalore', 'Paytm', 'Vijay R.', '+91-98765-43213'),
('ORD005', 'USER123', 'delivered', 437, '14th Apr 2026, 12:45 pm', '14th Apr 2026, 01:20 pm', 35,
 'SWISH001', 'Swish Cloud Kitchen', '555 HSR Layout, Bangalore', 'Google Pay', 'Deepak T.', '+91-98765-43214')
ON CONFLICT DO NOTHING;

-- Seed Data: Order Items
INSERT INTO order_items (order_id, item_id, name, price, quantity, description, category, quantity_detail) VALUES
('ORD001', 'ITEM001', 'Butter Chicken Rice Bowl', 269, 1, 'Creamy butter chicken with jeera rice', 'Non-Veg', NULL),
('ORD001', 'ITEM002', 'Peri Peri French Fries', 209, 1, 'French fries sprinkled with peri peri masala', 'Sides', NULL),
('ORD002', 'ITEM003', 'Caesar Salad (Non-Veg)', 259, 1, 'Fresh veggies & chicken with caesar dressing', 'Salads', NULL),
('ORD002', 'ITEM004', 'Grilled Paneer Club Sandwich', 219, 1, 'Paneer club sandwich, served fresh in 4 slices', 'Sandwiches', NULL),
('ORD002', 'ITEM005', 'Classic Cold Coffee', 159, 1, 'Chilled creamy coffee, as classic as it gets', 'Beverages', NULL),
('ORD003', 'ITEM006', 'Batata Vada Shots', 89, 1, 'Bite-sized batata vadas served with green chutney', 'Snacks', '6 pieces'),
('ORD003', 'ITEM007', 'Classic Maggi', 79, 1, 'Your favorite noodles with the signature masala', 'Quick Bites', NULL),
('ORD004', 'ITEM008', 'Dhaba Style Chicken Curry Rice Bowl', 269, 1, 'Rustic dhaba-style chicken curry with jeera rice', 'Non-Veg', NULL),
('ORD004', 'ITEM009', 'Veg Pink Sauce Pasta', 219, 1, 'Penne in creamy pink sauce with veggies and herbs', 'Pasta', NULL),
('ORD004', 'ITEM010', 'Roohafza Sharbat', 79, 1, 'Nostalgic Rooh Afza cooler (sharbat), fragrant and refreshing', 'Beverages', '450 ml'),
('ORD004', 'ITEM011', 'Dark Chocolate Oreo Shake', 189, 1, 'Creamy chocolate shake with Oreo chunks', 'Beverages', '450 ml'),
('ORD005', 'ITEM012', 'Veg Alfredo Penne', 209, 1, 'Creamy penne with veggies and herbs', 'Pasta', NULL),
('ORD005', 'ITEM013', 'Egg Curry Rice Bowl', 209, 1, 'Egg curry with jeera basmati rice', 'Rice Bowls', NULL),
('ORD005', 'ITEM014', 'Mini Punjabi Aloo Samosa', 99, 1, 'As classic as samosa gets, comes with chutneys', 'Snacks', '3 pieces')
ON CONFLICT DO NOTHING;

-- Seed Data: Customizations
INSERT INTO item_customizations (order_id, item_id, customization) VALUES
('ORD002', 'ITEM003', 'Extra dressing'),
('ORD002', 'ITEM005', 'Less sugar'),
('ORD004', 'ITEM008', 'Extra spicy')
ON CONFLICT DO NOTHING;

-- Seed Data: Kitchen Logs
INSERT INTO kitchen_logs (order_id, status, quality_out, prep_time_mins, temperature_check, dispatched_at) VALUES
('ORD001', 'dispatched', 'good',  12, 'hot',  NOW() - INTERVAL '2 hours'),
('ORD002', 'dispatched', 'good',  15, 'cold', NOW() - INTERVAL '3 hours'),
('ORD003', 'dispatched', 'fair',  18, 'warm', NOW() - INTERVAL '1 hour'),
('ORD004', 'dispatched', 'good',  20, 'hot',  NOW() - INTERVAL '30 minutes'),
('ORD005', 'dispatched', 'good',  14, 'hot',  NOW() - INTERVAL '45 minutes')
ON CONFLICT DO NOTHING;

-- Seed Data: Fleet Status
INSERT INTO fleet_status (order_id, within_geofence, delay_mins, traffic_flag, delivered, pickup_time, delivery_time, distance_km, notes) VALUES
('ORD001', true,  5,  false, true, '01:20 pm', '02:00 pm', 3.2, 'Smooth delivery, minor delay at pickup'),
('ORD002', true,  8,  true,  true, '08:55 pm', '09:23 pm', 4.5, 'Traffic on main road, driver waited at signal'),
('ORD003', true,  0,  false, true, '02:35 pm', '02:55 pm', 2.1, 'Quick delivery, no issues'),
('ORD004', false, 15, true,  true, '07:35 pm', '08:12 pm', 8.7, 'Heavy traffic to Whitefield, driver took alternate route'),
('ORD005', true,  3,  false, true, '12:52 pm', '01:20 pm', 3.8, 'Normal delivery, slight delay at restaurant')
ON CONFLICT DO NOTHING;

-- Seed Data: User Trust
INSERT INTO user_trust (user_id, score, total_orders, refund_requests, successful_orders, cancelled_orders, avg_order_value, account_age_days, last_order_date) VALUES
('USER123', 85, 47, 3, 44, 0, 425.50, 180, '18th Apr 2026')
ON CONFLICT DO NOTHING;
