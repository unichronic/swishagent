-- Order Service Database Schema and Seed Data

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

-- Seed Orders
INSERT INTO orders (order_id, user_id, status, total_amount, placed_at, delivered_at, delivery_time_mins, 
                    restaurant_id, restaurant_name, delivery_address, payment_method, 
                    delivery_partner_name, delivery_partner_phone) VALUES
-- ORD001: Butter Chicken + Fries (₹478)
('ORD001', 'USER123', 'delivered', 478, '18th Apr 2026, 01:15 pm', '18th Apr 2026, 02:00 pm', 45,
 'SWISH001', 'Swish Cloud Kitchen', '123 MG Road, Bangalore', 'UPI', 'Rahul K.', '+91-98765-43210'),

-- ORD002: Salad + Sandwich + Coffee (₹627)
('ORD002', 'USER123', 'delivered', 627, '17th Apr 2026, 08:45 pm', '17th Apr 2026, 09:23 pm', 38,
 'SWISH001', 'Swish Cloud Kitchen', '456 Indiranagar, Bangalore', 'Credit Card', 'Amit S.', '+91-98765-43211'),

-- ORD003: Vada Shots + Maggi (₹168)
('ORD003', 'USER123', 'delivered', 168, '16th Apr 2026, 02:30 pm', '16th Apr 2026, 02:55 pm', 25,
 'SWISH001', 'Swish Cloud Kitchen', '789 Koramangala, Bangalore', 'Cash on Delivery', 'Priya M.', '+91-98765-43212'),

-- ORD004: Chicken Curry + Pasta + 2 Beverages (₹756)
('ORD004', 'USER123', 'delivered', 756, '15th Apr 2026, 07:20 pm', '15th Apr 2026, 08:12 pm', 52,
 'SWISH001', 'Swish Cloud Kitchen', '321 Whitefield, Bangalore', 'Paytm', 'Vijay R.', '+91-98765-43213'),

-- ORD005: 2 Pasta + Samosa (₹437)
('ORD005', 'USER123', 'delivered', 437, '14th Apr 2026, 12:45 pm', '14th Apr 2026, 01:20 pm', 35,
 'SWISH001', 'Swish Cloud Kitchen', '555 HSR Layout, Bangalore', 'Google Pay', 'Deepak T.', '+91-98765-43214');

-- Seed Order Items
INSERT INTO order_items (order_id, item_id, name, price, quantity, description, category, quantity_detail) VALUES
-- ORD001
('ORD001', 'ITEM001', 'Butter Chicken Rice Bowl', 269, 1, 'Creamy butter chicken with jeera rice', 'Non-Veg', NULL),
('ORD001', 'ITEM002', 'Peri Peri French Fries', 209, 1, 'French fries sprinkled with peri peri masala', 'Sides', NULL),

-- ORD002
('ORD002', 'ITEM003', 'Caesar Salad (Non-Veg)', 259, 1, 'Fresh veggies & chicken with caesar dressing', 'Salads', NULL),
('ORD002', 'ITEM004', 'Grilled Paneer Club Sandwich', 219, 1, 'Paneer club sandwich, served fresh in 4 slices', 'Sandwiches', NULL),
('ORD002', 'ITEM005', 'Classic Cold Coffee', 159, 1, 'Chilled creamy coffee, as classic as it gets', 'Beverages', NULL),

-- ORD003
('ORD003', 'ITEM006', 'Batata Vada Shots', 89, 1, 'Bite-sized batata vadas served with green chutney', 'Snacks', '6 pieces'),
('ORD003', 'ITEM007', 'Classic Maggi', 79, 1, 'Your favorite noodles with the signature masala', 'Quick Bites', NULL),

-- ORD004
('ORD004', 'ITEM008', 'Dhaba Style Chicken Curry Rice Bowl', 269, 1, 'Rustic dhaba-style chicken curry with jeera rice', 'Non-Veg', NULL),
('ORD004', 'ITEM009', 'Veg Pink Sauce Pasta', 219, 1, 'Penne in creamy pink sauce with veggies and herbs', 'Pasta', NULL),
('ORD004', 'ITEM010', 'Roohafza Sharbat', 79, 1, 'Nostalgic Rooh Afza cooler (sharbat), fragrant and refreshing', 'Beverages', '450 ml'),
('ORD004', 'ITEM011', 'Dark Chocolate Oreo Shake', 189, 1, 'Creamy chocolate shake with Oreo chunks', 'Beverages', '450 ml'),

-- ORD005
('ORD005', 'ITEM012', 'Veg Alfredo Penne', 209, 1, 'Creamy penne with veggies and herbs', 'Pasta', NULL),
('ORD005', 'ITEM013', 'Egg Curry Rice Bowl', 209, 1, 'Egg curry with jeera basmati rice', 'Rice Bowls', NULL),
('ORD005', 'ITEM014', 'Mini Punjabi Aloo Samosa', 99, 1, 'As classic as samosa gets, comes with chutneys', 'Snacks', '3 pieces');

-- Seed Customizations
INSERT INTO item_customizations (order_id, item_id, customization) VALUES
('ORD002', 'ITEM003', 'Extra dressing'),
('ORD002', 'ITEM005', 'Less sugar'),
('ORD004', 'ITEM008', 'Extra spicy');

CREATE INDEX idx_orders_user_id ON orders(user_id);
CREATE INDEX idx_order_items_order_id ON order_items(order_id);
CREATE INDEX idx_item_customizations_order_id ON item_customizations(order_id);
