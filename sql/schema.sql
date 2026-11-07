-- =============================================================================
-- Zomato Business Intelligence & Delivery Time Prediction
-- Database Schema (DDL)
-- Target engine : PostgreSQL 14+
-- =============================================================================
-- Column naming : snake_case throughout (PostgreSQL lowercases unquoted names
--                 so CamelCase causes silent bugs — avoid it).
--
-- Load order (parents before children, required for FK constraints):
--   1. cities
--   2. customers, restaurants, delivery_partners, promotions, weather, traffic
--   3. menu
--   4. orders
--   5. order_items, payments, customer_feedback
--
-- Workflow:
--   Raw CSVs → staging schema (all TEXT, no constraints) via src/ingest.py
--   staging  → these tables with light cleaning via src/load_to_production.sql
--
-- Design decision logged in documentation/design_notes.md:
--   cities.city is declared UNIQUE NOT NULL so FK from child tables can
--   reference cities(city) instead of cities(city_id).  This matches the
--   raw CSV data (which stores city names, not integer IDs) and keeps
--   queries readable.
-- =============================================================================


-- =============================================================================
-- DROP ORDER: children first, then parents
-- =============================================================================
DROP TABLE IF EXISTS customer_feedback  CASCADE;
DROP TABLE IF EXISTS payments           CASCADE;
DROP TABLE IF EXISTS order_items        CASCADE;
DROP TABLE IF EXISTS orders             CASCADE;
DROP TABLE IF EXISTS menu               CASCADE;
DROP TABLE IF EXISTS delivery_partners  CASCADE;
DROP TABLE IF EXISTS restaurants        CASCADE;
DROP TABLE IF EXISTS customers          CASCADE;
DROP TABLE IF EXISTS promotions         CASCADE;
DROP TABLE IF EXISTS weather            CASCADE;
DROP TABLE IF EXISTS traffic            CASCADE;
DROP TABLE IF EXISTS cities             CASCADE;
DROP TABLE IF EXISTS city_aliases       CASCADE;


-- =============================================================================
-- HELPER: city_aliases
-- Maps every spelling variant found in the raw CSVs to the canonical city name
-- stored in cities.city.  Used during staging → production load.
-- =============================================================================
CREATE TABLE city_aliases (
    alias     TEXT PRIMARY KEY,   -- lowercase, trimmed variant
    canonical TEXT NOT NULL       -- exact spelling in cities.city
);

INSERT INTO city_aliases (alias, canonical) VALUES
    ('bangalore',     'Bengaluru'),
    ('bengaluru',     'Bengaluru'),
    ('bombay',        'Mumbai'),
    ('mumbai',        'Mumbai'),
    ('calcutta',      'Kolkata'),
    ('kolkata',       'Kolkata'),
    ('madras',        'Chennai'),
    ('chennai',       'Chennai'),
    ('new delhi',     'Delhi'),
    ('delhi',         'Delhi'),
    ('baroda',        'Vadodara'),
    ('vadodara',      'Vadodara'),
    ('ahmedabad',     'Ahmedabad'),
    ('bhopal',        'Bhopal'),
    ('bhubaneswar',   'Bhubaneswar'),
    ('chandigarh',    'Chandigarh'),
    ('coimbatore',    'Coimbatore'),
    ('guwahati',      'Guwahati'),
    ('hyderabad',     'Hyderabad'),
    ('indore',        'Indore'),
    ('jaipur',        'Jaipur'),
    ('kochi',         'Kochi'),
    ('lucknow',       'Lucknow'),
    ('ludhiana',      'Ludhiana'),
    ('nagpur',        'Nagpur'),
    ('nashik',        'Nashik'),
    ('patna',         'Patna'),
    ('pune',          'Pune'),
    ('raipur',        'Raipur'),
    ('surat',         'Surat'),
    ('visakhapatnam', 'Visakhapatnam');


-- =============================================================================
-- HELPER FUNCTIONS
-- Created once; used in the staging → production INSERT statements.
-- =============================================================================

-- parse_mixed_date(text) → DATE
-- Handles the five date formats found across the raw CSVs:
--   DD-MM-YYYY  |  DD/MM/YYYY  |  MM/DD/YYYY  |  YYYY.MM.DD  |  YYYY-MM-DD  |  DD Mon YYYY
-- Returns NULL instead of crashing on unparseable values.
CREATE OR REPLACE FUNCTION parse_mixed_date(s TEXT)
RETURNS DATE
LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
    s := NULLIF(TRIM(s), '');
    IF s IS NULL THEN RETURN NULL; END IF;

    -- YYYY-MM-DD (ISO — most unambiguous, check first)
    IF s ~ '^\d{4}-\d{2}-\d{2}$' THEN
        RETURN s::DATE;
    -- YYYY.MM.DD
    ELSIF s ~ '^\d{4}\.\d{2}\.\d{2}$' THEN
        RETURN TO_DATE(s, 'YYYY.MM.DD');
    -- DD-MM-YYYY
    ELSIF s ~ '^\d{2}-\d{2}-\d{4}$' THEN
        RETURN TO_DATE(s, 'DD-MM-YYYY');
    -- DD/MM/YYYY  (customers & delivery_partners — separator / but day ≤ 12 is ambiguous)
    -- MM/DD/YYYY  (orders, payments, weather, traffic — same separator)
    -- Strategy: use DD/MM/YYYY for customers & delivery_partners; MM/DD/YYYY elsewhere.
    -- The calling INSERT passes a second argument to signal which to use.
    ELSIF s ~ '^\d{2}/\d{2}/\d{4}$' THEN
        -- First part above 12 can only be a day -> DD/MM; otherwise MM/DD
        RETURN CASE WHEN split_part(s, '/', 1)::INT > 12
                    THEN TO_DATE(s, 'DD/MM/YYYY') ELSE TO_DATE(s, 'MM/DD/YYYY') END;
    -- DD Mon YYYY  (e.g. "28 Feb 2024") — only in customers & delivery_partners
    ELSIF s ~ '^\d{1,2} [A-Za-z]{3} \d{4}$' THEN
        RETURN TO_DATE(s, 'DD Mon YYYY');
    ELSE
        RETURN NULL;
    END IF;
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END;
$$;


-- parse_ddmmyyyy(text) → DATE
-- Dedicated parser for customers.registration_date and delivery_partners.joining_date
-- which use DD/MM/YYYY (not MM/DD/YYYY like the other tables).
CREATE OR REPLACE FUNCTION parse_ddmmyyyy(s TEXT)
RETURNS DATE
LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
    s := NULLIF(TRIM(s), '');
    IF s IS NULL THEN RETURN NULL; END IF;

    IF    s ~ '^\d{4}-\d{2}-\d{2}$'        THEN RETURN s::DATE;
    ELSIF s ~ '^\d{4}\.\d{2}\.\d{2}$'      THEN RETURN TO_DATE(s, 'YYYY.MM.DD');
    ELSIF s ~ '^\d{2}-\d{2}-\d{4}$'        THEN RETURN TO_DATE(s, 'DD-MM-YYYY');
    ELSIF s ~ '^\d{2}/\d{2}/\d{4}$'        THEN
        -- Second part above 12 can only be a day -> MM/DD; otherwise DD/MM
        RETURN CASE WHEN split_part(s, '/', 2)::INT > 12
                    THEN TO_DATE(s, 'MM/DD/YYYY') ELSE TO_DATE(s, 'DD/MM/YYYY') END;
    ELSIF s ~ '^\d{1,2} [A-Za-z]{3} \d{4}$' THEN RETURN TO_DATE(s, 'DD Mon YYYY');
    ELSE RETURN NULL;
    END IF;
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END;
$$;


-- to_num(text) → NUMERIC
-- Converts a text value to NUMERIC; returns NULL for blanks, 'N/A', etc.
CREATE OR REPLACE FUNCTION to_num(s TEXT)
RETURNS NUMERIC
LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
    RETURN NULLIF(TRIM(s), '')::NUMERIC;
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END;
$$;


-- =============================================================================
-- 1. CITIES
-- Root / reference table — no foreign keys.
-- city is UNIQUE NOT NULL so child tables can FK reference cities(city).
-- =============================================================================
CREATE TABLE cities (
    city_id        INT             PRIMARY KEY,
    city           VARCHAR(60)     NOT NULL UNIQUE,
    population     BIGINT,
    region         VARCHAR(40),
    average_income NUMERIC(12,2)
);


-- =============================================================================
-- 2. CUSTOMERS
-- =============================================================================
CREATE TABLE customers (
    customer_id       INT          PRIMARY KEY,
    name              VARCHAR(100),
    age               SMALLINT,
    gender            VARCHAR(20),
    phone             VARCHAR(20),       -- TEXT-type: leading digits must be kept
    email             VARCHAR(120),
    city              VARCHAR(60)        REFERENCES cities(city),
    state             VARCHAR(60),
    pincode           VARCHAR(10),       -- TEXT-type: leading zeros must be kept
    registration_date DATE,
    membership        VARCHAR(30),
    total_orders      INT,
    preferred_cuisine VARCHAR(60)
);


-- =============================================================================
-- 3. RESTAURANTS
-- =============================================================================
CREATE TABLE restaurants (
    restaurant_id   INT          PRIMARY KEY,
    restaurant_name VARCHAR(150),
    cuisine         VARCHAR(50),
    city            VARCHAR(60)        REFERENCES cities(city),
    area            VARCHAR(100),
    opening_time    TIME,
    closing_time    TIME,
    rating          NUMERIC(2,1),
    average_cost    NUMERIC(10,2),
    owner_name      VARCHAR(150),
    restaurant_type VARCHAR(50),
    latitude        NUMERIC(9,6),
    longitude       NUMERIC(9,6)
);


-- =============================================================================
-- 4. DELIVERY_PARTNERS
-- =============================================================================
CREATE TABLE delivery_partners (
    delivery_partner_id   INT         PRIMARY KEY,
    name                  VARCHAR(100),
    age                   SMALLINT,
    gender                VARCHAR(20),
    vehicle_type          VARCHAR(30),
    joining_date          DATE,
    city                  VARCHAR(60)  REFERENCES cities(city),
    rating                NUMERIC(2,1),
    completed_deliveries  INT,
    average_delivery_time NUMERIC(6,2)
);


-- =============================================================================
-- 5. PROMOTIONS
-- coupon_code is UNIQUE so orders.coupon_code can FK reference it.
-- =============================================================================
CREATE TABLE promotions (
    promotion_id          INT         PRIMARY KEY,
    coupon_code           VARCHAR(30) NOT NULL UNIQUE,
    discount_percentage   SMALLINT,
    campaign_name         VARCHAR(150),
    start_date            DATE,
    end_date              DATE
);


-- =============================================================================
-- 6. WEATHER
-- =============================================================================
CREATE TABLE weather (
    weather_id        INT         PRIMARY KEY,
    city              VARCHAR(60) REFERENCES cities(city),
    date              DATE,
    temperature       NUMERIC(5,2),
    rainfall          NUMERIC(6,2),
    humidity          SMALLINT,
    weather_condition VARCHAR(30)
);


-- =============================================================================
-- 7. TRAFFIC
-- =============================================================================
CREATE TABLE traffic (
    traffic_id    INT         PRIMARY KEY,
    city          VARCHAR(60) REFERENCES cities(city),
    date          DATE,
    time          TIME,
    traffic_level VARCHAR(20),
    average_speed NUMERIC(5,2)
);


-- =============================================================================
-- 8. MENU  (depends on restaurants)
-- =============================================================================
CREATE TABLE menu (
    food_item_id     INT          PRIMARY KEY,
    restaurant_id    INT          NOT NULL REFERENCES restaurants(restaurant_id),
    food_name        VARCHAR(150),
    category         VARCHAR(50),
    price            NUMERIC(10,2),
    preparation_time SMALLINT,
    calories         SMALLINT,
    availability     VARCHAR(5)
);


-- =============================================================================
-- 9. ORDERS  (depends on customers, restaurants, delivery_partners, promotions)
-- delivery_partner_id is nullable: cancelled orders may have no assigned partner.
-- coupon_code        is nullable: most orders have no coupon.
-- No CHECK (value > 0) constraints — negatives/zeroes are data-quality findings
-- to be logged and studied, not silently rejected.
-- =============================================================================
CREATE TABLE orders (
    order_id              INT         PRIMARY KEY,
    customer_id           INT         NOT NULL REFERENCES customers(customer_id),
    restaurant_id         INT         NOT NULL REFERENCES restaurants(restaurant_id),
    delivery_partner_id   INT                  REFERENCES delivery_partners(delivery_partner_id),
    order_date            DATE,
    order_time            TIME,
    delivery_time_minutes NUMERIC(8,1),
    food_cost             NUMERIC(10,2),
    delivery_fee          NUMERIC(10,2),
    discount              NUMERIC(10,2),
    coupon_code           VARCHAR(30)          REFERENCES promotions(coupon_code),
    gst                   NUMERIC(10,2),
    final_amount          NUMERIC(10,2),
    order_status          VARCHAR(30),
    payment_method        VARCHAR(30)
);


-- =============================================================================
-- 10. ORDER_ITEMS  (depends on orders and menu)
-- =============================================================================
CREATE TABLE order_items (
    order_item_id INT          PRIMARY KEY,
    order_id      INT          NOT NULL REFERENCES orders(order_id),
    food_item_id  INT          NOT NULL REFERENCES menu(food_item_id),
    quantity      SMALLINT,
    unit_price    NUMERIC(10,2),
    total_price   NUMERIC(10,2)
);


-- =============================================================================
-- 11. PAYMENTS  (depends on orders)
-- =============================================================================
CREATE TABLE payments (
    payment_id     INT         PRIMARY KEY,
    order_id       INT         NOT NULL REFERENCES orders(order_id),
    payment_method VARCHAR(30),
    payment_status VARCHAR(20),
    transaction_id VARCHAR(30),
    payment_date   DATE
);


-- =============================================================================
-- 12. CUSTOMER_FEEDBACK  (depends on orders)
-- =============================================================================
CREATE TABLE customer_feedback (
    feedback_id     INT       PRIMARY KEY,
    order_id        INT       NOT NULL REFERENCES orders(order_id),
    customer_rating SMALLINT,
    delivery_rating SMALLINT,
    food_rating     SMALLINT,
    review          TEXT,
    sentiment       VARCHAR(20)
);


-- =============================================================================
-- INDEXES
-- PostgreSQL automatically indexes PK and UNIQUE columns.
-- These additional indexes target the most common analytical join/filter patterns.
-- =============================================================================

-- Orders by customer + date — the most common WHERE/JOIN pattern
CREATE INDEX idx_orders_customer_date   ON orders(customer_id, order_date);

-- Restaurant-level rollups (revenue, ratings, cancellation %)
CREATE INDEX idx_orders_restaurant      ON orders(restaurant_id);

-- Delivery-partner performance reports
CREATE INDEX idx_orders_delivery_partner ON orders(delivery_partner_id);

-- Order status filter (used in virtually every business query)
CREATE INDEX idx_orders_status          ON orders(order_status);

-- Weather/traffic joins to orders by city + date
CREATE INDEX idx_weather_city_date      ON weather(city, date);
CREATE INDEX idx_traffic_city_date      ON traffic(city, date);

-- Order items lookup by order
CREATE INDEX idx_order_items_order      ON order_items(order_id);

-- Payment lookup by order
CREATE INDEX idx_payments_order         ON payments(order_id);

-- Feedback lookup by order
CREATE INDEX idx_feedback_order         ON customer_feedback(order_id);


-- =============================================================================
-- NOTES FOR RUNNING THIS FILE
-- =============================================================================
-- 1. Create the database first:
--      CREATE DATABASE zomato;
--      \c zomato
--
-- 2. Run this file:
--      \i sql/schema.sql
--
-- 3. Load staging data (all raw CSVs as TEXT, no constraints):
--      python src/ingest.py
--
-- 4. Load production data (cleaned, with FK resolution):
--      \i src/load_to_production.sql
--
-- To reload from scratch: just re-run this file — the DROP ... CASCADE at
-- the top wipes everything cleanly.
-- =============================================================================
