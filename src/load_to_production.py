"""
src/load_to_production.py
-------------------------
Step 6: Move data from staging → production tables.

Applies only the cleaning needed to load successfully:
  • TRIM() all text columns
  • parse_mixed_date() / parse_ddmmyyyy() for date columns
  • to_num() for numeric columns
  • city_aliases lookup for FK city columns
  • ROW_NUMBER() OVER (PARTITION BY pk) = 1 to deduplicate
  • EXISTS checks to keep only rows whose FK parents exist
  • Quarantine tables for every rejected row (with reason)
  • Reconciliation view: raw_rows = loaded + quarantined + duplicates

Load order (parents before children, required for FKs):
  1. cities
  2. customers, restaurants, delivery_partners, promotions, weather, traffic
  3. menu
  4. orders
  5. order_items, payments, customer_feedback

Usage:
    python src/load_to_production.py
"""

import os
import sys
from pathlib import Path
from datetime import datetime

import psycopg2
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    sys.exit("ERROR: DATABASE_URL not found in .env")


# ---------------------------------------------------------------------------
# SQL statements — one per table, in load order
# ---------------------------------------------------------------------------

# Each entry: (label, sql_string)
# quarantine tables are created after their parent production table is loaded.

LOAD_STATEMENTS = [

    # =========================================================================
    # 1. CITIES  (root table — no FKs)
    # =========================================================================
    ("cities", """
    INSERT INTO cities (city_id, city, population, region, average_income)
    SELECT DISTINCT
        to_num(s.city_id)::INT,
        TRIM(s.city),
        to_num(s.population)::BIGINT,
        NULLIF(TRIM(s.region), ''),
        to_num(s.average_income)
    FROM staging.cities s
    WHERE TRIM(s.city_id) ~ '^[0-9]+$'
      AND TRIM(s.city) != ''
    ON CONFLICT (city_id) DO NOTHING;
    """),

    # =========================================================================
    # 2. CUSTOMERS
    # Duplicates: all 180 are exact copies — keep first occurrence per customer_id
    # city: map via city_aliases, fallback to INITCAP of raw value
    # registration_date: uses parse_ddmmyyyy() — file has DD/MM/YYYY + DD Mon YYYY
    # =========================================================================
    ("customers", """
    INSERT INTO customers (customer_id, name, age, gender, phone, email,
                           city, state, pincode, registration_date,
                           membership, total_orders, preferred_cuisine)
    SELECT customer_id, name, age, gender, phone, email,
           city, state, pincode, registration_date,
           membership, total_orders, preferred_cuisine
    FROM (
        SELECT
            to_num(s.customer_id)::INT                                  AS customer_id,
            NULLIF(TRIM(s.name), '')                                    AS name,
            CASE WHEN TRIM(s.age) ~ '^[0-9]+(\\.[0-9]+)?$'
                 THEN TRIM(s.age)::NUMERIC::INT END                     AS age,
            NULLIF(INITCAP(TRIM(s.gender)), '')                         AS gender,
            NULLIF(TRIM(s.phone), '')                                   AS phone,
            NULLIF(TRIM(s.email), '')                                   AS email,
            COALESCE(a.canonical, INITCAP(TRIM(s.city)))                AS city,
            NULLIF(TRIM(s.state), '')                                   AS state,
            NULLIF(TRIM(s.pincode), '')                                 AS pincode,
            parse_ddmmyyyy(s.registration_date)                         AS registration_date,
            NULLIF(INITCAP(TRIM(s.membership)), '')                     AS membership,
            to_num(s.total_orders)::INT                                 AS total_orders,
            NULLIF(TRIM(s.preferred_cuisine), '')                       AS preferred_cuisine,
            ROW_NUMBER() OVER (PARTITION BY TRIM(s.customer_id)
                               ORDER BY s.customer_id)                  AS rn
        FROM staging.customers s
        LEFT JOIN city_aliases a ON a.alias = LOWER(TRIM(s.city))
        WHERE TRIM(s.customer_id) ~ '^[0-9]+'
    ) x
    WHERE rn = 1
    ON CONFLICT (customer_id) DO NOTHING;
    """),

    # =========================================================================
    # 3. RESTAURANTS
    # =========================================================================
    ("restaurants", """
    INSERT INTO restaurants (restaurant_id, restaurant_name, cuisine, city, area,
                             opening_time, closing_time, rating, average_cost,
                             owner_name, restaurant_type, latitude, longitude)
    SELECT restaurant_id, restaurant_name, cuisine, city, area,
           opening_time, closing_time, rating, average_cost,
           owner_name, restaurant_type, latitude, longitude
    FROM (
        SELECT
            to_num(s.restaurant_id)::INT                                AS restaurant_id,
            NULLIF(TRIM(s.restaurant_name), '')                         AS restaurant_name,
            NULLIF(TRIM(s.cuisine), '')                                 AS cuisine,
            COALESCE(a.canonical, INITCAP(TRIM(s.city)))                AS city,
            NULLIF(TRIM(s.area), '')                                    AS area,
            CASE WHEN TRIM(s.opening_time) ~ '^[0-9]{1,2}:[0-9]{2}'
                 THEN TRIM(s.opening_time)::TIME END                    AS opening_time,
            CASE WHEN TRIM(s.closing_time) ~ '^[0-9]{1,2}:[0-9]{2}'
                 THEN TRIM(s.closing_time)::TIME END                    AS closing_time,
            to_num(s.rating)                                            AS rating,
            to_num(s.average_cost)                                      AS average_cost,
            NULLIF(TRIM(s.owner_name), '')                              AS owner_name,
            NULLIF(TRIM(s.restaurant_type), '')                         AS restaurant_type,
            to_num(s.latitude)                                          AS latitude,
            to_num(s.longitude)                                         AS longitude,
            ROW_NUMBER() OVER (PARTITION BY TRIM(s.restaurant_id)
                               ORDER BY s.restaurant_id)                AS rn
        FROM staging.restaurants s
        LEFT JOIN city_aliases a ON a.alias = LOWER(TRIM(s.city))
        WHERE TRIM(s.restaurant_id) ~ '^[0-9]+'
    ) x
    WHERE rn = 1
    ON CONFLICT (restaurant_id) DO NOTHING;
    """),

    # =========================================================================
    # 4. DELIVERY_PARTNERS
    # joining_date: DD/MM/YYYY + DD Mon YYYY → parse_ddmmyyyy()
    # =========================================================================
    ("delivery_partners", """
    INSERT INTO delivery_partners (delivery_partner_id, name, age, gender,
                                   vehicle_type, joining_date, city, rating,
                                   completed_deliveries, average_delivery_time)
    SELECT delivery_partner_id, name, age, gender,
           vehicle_type, joining_date, city, rating,
           completed_deliveries, average_delivery_time
    FROM (
        SELECT
            to_num(s.delivery_partner_id)::INT                          AS delivery_partner_id,
            NULLIF(TRIM(s.name), '')                                    AS name,
            CASE WHEN TRIM(s.age) ~ '^[0-9]+(\\.[0-9]+)?$'
                 THEN TRIM(s.age)::NUMERIC::INT END                     AS age,
            NULLIF(INITCAP(TRIM(s.gender)), '')                         AS gender,
            NULLIF(TRIM(s.vehicle_type), '')                            AS vehicle_type,
            parse_ddmmyyyy(s.joining_date)                              AS joining_date,
            COALESCE(a.canonical, INITCAP(TRIM(s.city)))                AS city,
            to_num(s.rating)                                            AS rating,
            to_num(s.completed_deliveries)::INT                         AS completed_deliveries,
            to_num(s.average_delivery_time)                             AS average_delivery_time,
            ROW_NUMBER() OVER (PARTITION BY TRIM(s.delivery_partner_id)
                               ORDER BY s.delivery_partner_id)          AS rn
        FROM staging.delivery_partners s
        LEFT JOIN city_aliases a ON a.alias = LOWER(TRIM(s.city))
        WHERE TRIM(s.delivery_partner_id) ~ '^[0-9]+'
    ) x
    WHERE rn = 1
    ON CONFLICT (delivery_partner_id) DO NOTHING;
    """),

    # =========================================================================
    # 5. PROMOTIONS
    # coupon_code must be UNIQUE — confirmed 300 distinct codes in staging
    # start_date / end_date: MM/DD/YYYY dominant → parse_mixed_date()
    # =========================================================================
    ("promotions", """
    INSERT INTO promotions (promotion_id, coupon_code, discount_percentage,
                            campaign_name, start_date, end_date)
    SELECT promotion_id, coupon_code, discount_percentage,
           campaign_name, start_date, end_date
    FROM (
        SELECT
            to_num(s.promotion_id)::INT                                 AS promotion_id,
            UPPER(TRIM(s.coupon_code))                                  AS coupon_code,
            to_num(s.discount_percentage)::SMALLINT                     AS discount_percentage,
            NULLIF(TRIM(s.campaign_name), '')                           AS campaign_name,
            parse_mixed_date(s.start_date)                              AS start_date,
            parse_mixed_date(s.end_date)                                AS end_date,
            ROW_NUMBER() OVER (PARTITION BY UPPER(TRIM(s.coupon_code))
                               ORDER BY s.promotion_id)                 AS rn
        FROM staging.promotions s
        WHERE TRIM(s.coupon_code) != ''
    ) x
    WHERE rn = 1
    ON CONFLICT (promotion_id) DO NOTHING;
    """),

    # =========================================================================
    # 6. WEATHER
    # 91 rows have blank city — excluded (no FK target)
    # date: MM/DD/YYYY dominant → parse_mixed_date()
    # =========================================================================
    ("weather", """
    INSERT INTO weather (weather_id, city, date, temperature,
                         rainfall, humidity, weather_condition)
    SELECT weather_id, city, date, temperature,
           rainfall, humidity, weather_condition
    FROM (
        SELECT
            to_num(s.weather_id)::INT                                   AS weather_id,
            COALESCE(a.canonical, INITCAP(TRIM(s.city)))                AS city,
            parse_mixed_date(s.date)                                    AS date,
            to_num(s.temperature)                                       AS temperature,
            to_num(s.rainfall)                                          AS rainfall,
            to_num(s.humidity)::SMALLINT                                AS humidity,
            NULLIF(TRIM(s.weather_condition), '')                       AS weather_condition,
            ROW_NUMBER() OVER (PARTITION BY TRIM(s.weather_id)
                               ORDER BY s.weather_id)                   AS rn
        FROM staging.weather s
        LEFT JOIN city_aliases a ON a.alias = LOWER(TRIM(s.city))
        WHERE TRIM(s.city) != ''
          AND TRIM(s.weather_id) ~ '^[0-9]+'
    ) x
    WHERE rn = 1
      AND city IN (SELECT city FROM cities)
    ON CONFLICT (weather_id) DO NOTHING;
    """),

    # quarantine for weather rows with missing/unmappable city
    ("quarantine_weather", """
    CREATE TABLE IF NOT EXISTS quarantine_weather AS
    SELECT s.*, 'blank or unmappable city' AS quarantine_reason
    FROM staging.weather s
    LEFT JOIN city_aliases a ON a.alias = LOWER(TRIM(s.city))
    WHERE TRIM(s.city) = ''
       OR COALESCE(a.canonical, INITCAP(TRIM(s.city))) NOT IN (SELECT city FROM cities);
    """),

    # =========================================================================
    # 7. TRAFFIC
    # date: MM/DD/YYYY dominant → parse_mixed_date()
    # =========================================================================
    ("traffic", """
    INSERT INTO traffic (traffic_id, city, date, time, traffic_level, average_speed)
    SELECT traffic_id, city, date, time, traffic_level, average_speed
    FROM (
        SELECT
            to_num(s.traffic_id)::INT                                   AS traffic_id,
            COALESCE(a.canonical, INITCAP(TRIM(s.city)))                AS city,
            parse_mixed_date(s.date)                                    AS date,
            CASE WHEN TRIM(s.time) ~ '^[0-9]{1,2}:[0-9]{2}'
                 THEN TRIM(s.time)::TIME END                            AS time,
            NULLIF(TRIM(s.traffic_level), '')                           AS traffic_level,
            to_num(s.average_speed)                                     AS average_speed,
            ROW_NUMBER() OVER (PARTITION BY TRIM(s.traffic_id)
                               ORDER BY s.traffic_id)                   AS rn
        FROM staging.traffic s
        LEFT JOIN city_aliases a ON a.alias = LOWER(TRIM(s.city))
        WHERE TRIM(s.city) != ''
          AND TRIM(s.traffic_id) ~ '^[0-9]+'
    ) x
    WHERE rn = 1
      AND city IN (SELECT city FROM cities)
    ON CONFLICT (traffic_id) DO NOTHING;
    """),

    # =========================================================================
    # 8. MENU  (depends on restaurants)
    # =========================================================================
    ("menu", """
    INSERT INTO menu (food_item_id, restaurant_id, food_name, category,
                      price, preparation_time, calories, availability)
    SELECT food_item_id, restaurant_id, food_name, category,
           price, preparation_time, calories, availability
    FROM (
        SELECT
            to_num(s.food_item_id)::INT                                 AS food_item_id,
            to_num(s.restaurant_id)::INT                                AS restaurant_id,
            NULLIF(TRIM(s.food_name), '')                               AS food_name,
            NULLIF(TRIM(s.category), '')                                AS category,
            to_num(s.price)                                             AS price,
            to_num(s.preparation_time)::SMALLINT                        AS preparation_time,
            to_num(s.calories)::SMALLINT                                AS calories,
            NULLIF(TRIM(s.availability), '')                            AS availability,
            ROW_NUMBER() OVER (PARTITION BY TRIM(s.food_item_id)
                               ORDER BY s.food_item_id)                 AS rn
        FROM staging.menu s
        WHERE TRIM(s.food_item_id) ~ '^[0-9]+'
          AND TRIM(s.restaurant_id) ~ '^[0-9]+'
    ) x
    WHERE rn = 1
      AND restaurant_id IN (SELECT restaurant_id FROM restaurants)
    ON CONFLICT (food_item_id) DO NOTHING;
    """),

    ("quarantine_menu", """
    CREATE TABLE IF NOT EXISTS quarantine_menu AS
    SELECT s.*, 'unknown restaurant_id' AS quarantine_reason
    FROM staging.menu s
    WHERE to_num(s.restaurant_id)::INT NOT IN (SELECT restaurant_id FROM restaurants);
    """),

    # =========================================================================
    # 9. ORDERS  (depends on customers, restaurants, delivery_partners, promotions)
    # order_date: MM/DD/YYYY dominant → parse_mixed_date()
    # coupon_code: already UPPER in promotions; normalise here too
    # delivery_partner_id / coupon_code: nullable FKs
    # =========================================================================
    ("orders", """
    INSERT INTO orders (order_id, customer_id, restaurant_id, delivery_partner_id,
                        order_date, order_time, delivery_time_minutes,
                        food_cost, delivery_fee, discount, coupon_code,
                        gst, final_amount, order_status, payment_method)
    SELECT order_id, customer_id, restaurant_id, delivery_partner_id,
           order_date, order_time, delivery_time_minutes,
           food_cost, delivery_fee, discount, coupon_code,
           gst, final_amount, order_status, payment_method
    FROM (
        SELECT
            to_num(s.order_id)::INT                                     AS order_id,
            to_num(s.customer_id)::INT                                  AS customer_id,
            to_num(s.restaurant_id)::INT                                AS restaurant_id,
            CASE WHEN TRIM(s.delivery_partner_id) ~ '^[0-9]+'
                 THEN to_num(s.delivery_partner_id)::INT END            AS delivery_partner_id,
            parse_mixed_date(s.order_date)                              AS order_date,
            CASE WHEN TRIM(s.order_time) ~ '^[0-9]{1,2}:[0-9]{2}'
                 THEN TRIM(s.order_time)::TIME END                      AS order_time,
            to_num(s.delivery_time_minutes)                             AS delivery_time_minutes,
            to_num(s.food_cost)                                         AS food_cost,
            to_num(s.delivery_fee)                                      AS delivery_fee,
            to_num(s.discount)                                          AS discount,
            NULLIF(UPPER(TRIM(s.coupon_code)), '')                      AS coupon_code,
            to_num(s.gst)                                               AS gst,
            to_num(s.final_amount)                                      AS final_amount,
            INITCAP(TRIM(s.order_status))                               AS order_status,
            INITCAP(TRIM(s.payment_method))                             AS payment_method,
            ROW_NUMBER() OVER (PARTITION BY TRIM(s.order_id)
                               ORDER BY s.order_id)                     AS rn
        FROM staging.orders s
        WHERE TRIM(s.order_id) ~ '^[0-9]+'
    ) x
    WHERE rn = 1
      AND customer_id IN (SELECT customer_id FROM customers)
      AND restaurant_id IN (SELECT restaurant_id FROM restaurants)
      AND (delivery_partner_id IS NULL
           OR delivery_partner_id IN (SELECT delivery_partner_id FROM delivery_partners))
      AND (coupon_code IS NULL
           OR coupon_code IN (SELECT coupon_code FROM promotions))
    ON CONFLICT (order_id) DO NOTHING;
    """),

    ("quarantine_orders", """
    DROP TABLE IF EXISTS quarantine_orders;
    CREATE TABLE quarantine_orders AS
    SELECT s.*,
        CASE
            WHEN to_num(s.order_id) IS NULL                                     THEN 'invalid order_id'
            WHEN to_num(s.customer_id)::INT NOT IN
                 (SELECT customer_id FROM customers)                            THEN 'unknown customer_id'
            WHEN to_num(s.restaurant_id)::INT NOT IN
                 (SELECT restaurant_id FROM restaurants)                        THEN 'unknown restaurant_id'
            WHEN TRIM(s.delivery_partner_id) != ''
             AND to_num(s.delivery_partner_id)::INT NOT IN
                 (SELECT delivery_partner_id FROM delivery_partners)           THEN 'unknown delivery_partner_id'
            WHEN NULLIF(UPPER(TRIM(s.coupon_code)),'') IS NOT NULL
             AND UPPER(TRIM(s.coupon_code)) NOT IN
                 (SELECT coupon_code FROM promotions)                          THEN 'unknown coupon_code'
            ELSE 'duplicate order_id'
        END AS quarantine_reason
    FROM staging.orders s
    WHERE to_num(s.order_id)::TEXT NOT IN (SELECT order_id::TEXT FROM orders);
    """),

    # =========================================================================
    # 10. ORDER_ITEMS  (depends on orders and menu)
    # =========================================================================
    ("order_items", """
    INSERT INTO order_items (order_item_id, order_id, food_item_id,
                             quantity, unit_price, total_price)
    SELECT order_item_id, order_id, food_item_id,
           quantity, unit_price, total_price
    FROM (
        SELECT
            to_num(s.order_item_id)::INT                                AS order_item_id,
            to_num(s.order_id)::INT                                     AS order_id,
            to_num(s.food_item_id)::INT                                 AS food_item_id,
            to_num(s.quantity)::SMALLINT                                AS quantity,
            to_num(s.unit_price)                                        AS unit_price,
            to_num(s.total_price)                                       AS total_price,
            ROW_NUMBER() OVER (PARTITION BY TRIM(s.order_item_id)
                               ORDER BY s.order_item_id)                AS rn
        FROM staging.order_items s
        WHERE TRIM(s.order_item_id) ~ '^[0-9]+'
    ) x
    WHERE rn = 1
      AND order_id IN (SELECT order_id FROM orders)
      AND food_item_id IN (SELECT food_item_id FROM menu)
    ON CONFLICT (order_item_id) DO NOTHING;
    """),

    ("quarantine_order_items", """
    CREATE TABLE IF NOT EXISTS quarantine_order_items AS
    SELECT s.*,
        CASE
            WHEN to_num(s.order_id)::INT NOT IN (SELECT order_id FROM orders)          THEN 'unknown order_id'
            WHEN to_num(s.food_item_id)::INT NOT IN (SELECT food_item_id FROM menu)    THEN 'unknown food_item_id'
            ELSE 'duplicate order_item_id'
        END AS quarantine_reason
    FROM staging.order_items s
    WHERE to_num(s.order_item_id)::TEXT NOT IN (SELECT order_item_id::TEXT FROM order_items);
    """),

    # =========================================================================
    # 11. PAYMENTS  (depends on orders)
    # payment_date: MM/DD/YYYY dominant → parse_mixed_date()
    # =========================================================================
    ("payments", """
    INSERT INTO payments (payment_id, order_id, payment_method,
                          payment_status, transaction_id, payment_date)
    SELECT payment_id, order_id, payment_method,
           payment_status, transaction_id, payment_date
    FROM (
        SELECT
            to_num(s.payment_id)::INT                                   AS payment_id,
            to_num(s.order_id)::INT                                     AS order_id,
            NULLIF(INITCAP(TRIM(s.payment_method)), '')                 AS payment_method,
            NULLIF(INITCAP(TRIM(s.payment_status)), '')                 AS payment_status,
            NULLIF(TRIM(s.transaction_id), '')                          AS transaction_id,
            parse_mixed_date(s.payment_date)                            AS payment_date,
            ROW_NUMBER() OVER (PARTITION BY TRIM(s.payment_id)
                               ORDER BY s.payment_id)                   AS rn
        FROM staging.payments s
        WHERE TRIM(s.payment_id) ~ '^[0-9]+'
    ) x
    WHERE rn = 1
      AND order_id IN (SELECT order_id FROM orders)
    ON CONFLICT (payment_id) DO NOTHING;
    """),

    ("quarantine_payments", """
    CREATE TABLE IF NOT EXISTS quarantine_payments AS
    SELECT s.*, 'unknown order_id' AS quarantine_reason
    FROM staging.payments s
    WHERE to_num(s.order_id)::INT NOT IN (SELECT order_id FROM orders);
    """),

    # =========================================================================
    # 12. CUSTOMER_FEEDBACK  (depends on orders)
    # =========================================================================
    ("customer_feedback", """
    INSERT INTO customer_feedback (feedback_id, order_id, customer_rating,
                                   delivery_rating, food_rating, review, sentiment)
    SELECT feedback_id, order_id, customer_rating,
           delivery_rating, food_rating, review, sentiment
    FROM (
        SELECT
            to_num(s.feedback_id)::INT                                  AS feedback_id,
            to_num(s.order_id)::INT                                     AS order_id,
            to_num(s.customer_rating)::SMALLINT                         AS customer_rating,
            to_num(s.delivery_rating)::SMALLINT                         AS delivery_rating,
            to_num(s.food_rating)::SMALLINT                             AS food_rating,
            NULLIF(TRIM(s.review), '')                                  AS review,
            NULLIF(TRIM(s.sentiment), '')                               AS sentiment,
            ROW_NUMBER() OVER (PARTITION BY TRIM(s.feedback_id)
                               ORDER BY s.feedback_id)                  AS rn
        FROM staging.customer_feedback s
        WHERE TRIM(s.feedback_id) ~ '^[0-9]+'
    ) x
    WHERE rn = 1
      AND order_id IN (SELECT order_id FROM orders)
    ON CONFLICT (feedback_id) DO NOTHING;
    """),

    ("quarantine_customer_feedback", """
    CREATE TABLE IF NOT EXISTS quarantine_customer_feedback AS
    SELECT s.*, 'unknown order_id' AS quarantine_reason
    FROM staging.customer_feedback s
    WHERE to_num(s.order_id)::INT NOT IN (SELECT order_id FROM orders);
    """),

    # =========================================================================
    # 6f. RECONCILIATION TABLE  (persistent evidence — guide requirement)
    # Rule: unique_ids = loaded_rows + quarantined_rows for every table
    # =========================================================================
    ("reconciliation", """
    DROP TABLE IF EXISTS reconciliation;
    CREATE TABLE reconciliation (
        table_name        TEXT PRIMARY KEY,
        raw_rows          INT,
        unique_ids        INT,
        duplicate_rows    INT,
        loaded_rows       INT,
        quarantined_rows  INT,
        balance_check     TEXT,
        notes             TEXT
    );
    INSERT INTO reconciliation
        (table_name, raw_rows, unique_ids, duplicate_rows, loaded_rows, quarantined_rows, balance_check, notes)
    SELECT 'cities',
        (SELECT COUNT(*) FROM staging.cities),
        (SELECT COUNT(DISTINCT city_id) FROM staging.cities),
        (SELECT COUNT(*) FROM staging.cities) - (SELECT COUNT(DISTINCT city_id) FROM staging.cities),
        (SELECT COUNT(*) FROM cities),
        0,
        CASE WHEN (SELECT COUNT(DISTINCT city_id) FROM staging.cities) =
                  (SELECT COUNT(*) FROM cities) + 0
             THEN 'OK: unique = loaded + quarantined'
             ELSE 'MISMATCH' END,
        'Root table. No city variants, no duplicates.'
    UNION ALL
    SELECT 'customers',
        (SELECT COUNT(*) FROM staging.customers),
        (SELECT COUNT(DISTINCT customer_id) FROM staging.customers),
        (SELECT COUNT(*) FROM staging.customers) - (SELECT COUNT(DISTINCT customer_id) FROM staging.customers),
        (SELECT COUNT(*) FROM customers),
        0,
        CASE WHEN (SELECT COUNT(DISTINCT customer_id) FROM staging.customers) =
                  (SELECT COUNT(*) FROM customers)
             THEN 'OK: unique = loaded + quarantined'
             ELSE 'MISMATCH' END,
        '180 exact-copy duplicates removed. Rule: keep first occurrence via ROW_NUMBER().'
    UNION ALL
    SELECT 'restaurants',
        (SELECT COUNT(*) FROM staging.restaurants),
        (SELECT COUNT(DISTINCT restaurant_id) FROM staging.restaurants),
        0,
        (SELECT COUNT(*) FROM restaurants),
        0,
        CASE WHEN (SELECT COUNT(DISTINCT restaurant_id) FROM staging.restaurants) =
                  (SELECT COUNT(*) FROM restaurants)
             THEN 'OK: unique = loaded + quarantined'
             ELSE 'MISMATCH' END,
        '12 null cuisine rows loaded with NULL cuisine — logged in data_quality_log.'
    UNION ALL
    SELECT 'delivery_partners',
        (SELECT COUNT(*) FROM staging.delivery_partners),
        (SELECT COUNT(DISTINCT delivery_partner_id) FROM staging.delivery_partners),
        0,
        (SELECT COUNT(*) FROM delivery_partners),
        0,
        CASE WHEN (SELECT COUNT(DISTINCT delivery_partner_id) FROM staging.delivery_partners) =
                  (SELECT COUNT(*) FROM delivery_partners)
             THEN 'OK: unique = loaded + quarantined'
             ELSE 'MISMATCH' END,
        'joining_date used parse_ddmmyyyy() for DD/MM/YYYY + DD Mon YYYY formats.'
    UNION ALL
    SELECT 'promotions',
        (SELECT COUNT(*) FROM staging.promotions),
        (SELECT COUNT(DISTINCT promotion_id) FROM staging.promotions),
        0,
        (SELECT COUNT(*) FROM promotions),
        0,
        CASE WHEN (SELECT COUNT(DISTINCT promotion_id) FROM staging.promotions) =
                  (SELECT COUNT(*) FROM promotions)
             THEN 'OK: unique = loaded + quarantined'
             ELSE 'MISMATCH' END,
        '300 distinct coupon_codes. UPPER(TRIM()) applied for consistency with orders.'
    UNION ALL
    SELECT 'weather',
        (SELECT COUNT(*) FROM staging.weather),
        (SELECT COUNT(DISTINCT weather_id) FROM staging.weather),
        0,
        (SELECT COUNT(*) FROM weather),
        (SELECT COUNT(*) FROM quarantine_weather),
        CASE WHEN (SELECT COUNT(DISTINCT weather_id) FROM staging.weather) =
                  (SELECT COUNT(*) FROM weather) + (SELECT COUNT(*) FROM quarantine_weather)
             THEN 'OK: unique = loaded + quarantined'
             ELSE 'MISMATCH' END,
        '91 rows quarantined: blank city column — no FK target.'
    UNION ALL
    SELECT 'traffic',
        (SELECT COUNT(*) FROM staging.traffic),
        (SELECT COUNT(DISTINCT traffic_id) FROM staging.traffic),
        0,
        (SELECT COUNT(*) FROM traffic),
        0,
        CASE WHEN (SELECT COUNT(DISTINCT traffic_id) FROM staging.traffic) =
                  (SELECT COUNT(*) FROM traffic)
             THEN 'OK: unique = loaded + quarantined'
             ELSE 'MISMATCH' END,
        '147 null traffic_level rows loaded with NULL — logged in data_quality_log.'
    UNION ALL
    SELECT 'menu',
        (SELECT COUNT(*) FROM staging.menu),
        (SELECT COUNT(DISTINCT food_item_id) FROM staging.menu),
        0,
        (SELECT COUNT(*) FROM menu),
        (SELECT COUNT(*) FROM quarantine_menu),
        CASE WHEN (SELECT COUNT(DISTINCT food_item_id) FROM staging.menu) =
                  (SELECT COUNT(*) FROM menu) + (SELECT COUNT(*) FROM quarantine_menu)
             THEN 'OK: unique = loaded + quarantined'
             ELSE 'MISMATCH' END,
        'All restaurant_ids resolved. 0 orphans.'
    UNION ALL
    SELECT 'orders',
        (SELECT COUNT(*) FROM staging.orders),
        (SELECT COUNT(DISTINCT order_id) FROM staging.orders),
        (SELECT COUNT(*) FROM staging.orders) - (SELECT COUNT(DISTINCT order_id) FROM staging.orders),
        (SELECT COUNT(*) FROM orders),
        (SELECT COUNT(*) FROM quarantine_orders),
        CASE WHEN (SELECT COUNT(DISTINCT order_id) FROM staging.orders) =
                  (SELECT COUNT(*) FROM orders) + (SELECT COUNT(*) FROM quarantine_orders)
             THEN 'OK: unique = loaded + quarantined'
             ELSE 'MISMATCH' END,
        '205 exact-copy duplicates removed. 25 quarantined: 13 unknown restaurant_id, 12 unknown customer_id.'
    UNION ALL
    SELECT 'order_items',
        (SELECT COUNT(*) FROM staging.order_items),
        (SELECT COUNT(DISTINCT order_item_id) FROM staging.order_items),
        0,
        (SELECT COUNT(*) FROM order_items),
        (SELECT COUNT(*) FROM quarantine_order_items),
        CASE WHEN (SELECT COUNT(DISTINCT order_item_id) FROM staging.order_items) =
                  (SELECT COUNT(*) FROM order_items) + (SELECT COUNT(*) FROM quarantine_order_items)
             THEN 'OK: unique = loaded + quarantined'
             ELSE 'MISMATCH' END,
        '17 quarantined: order_id not in orders (those orders were quarantined).'
    UNION ALL
    SELECT 'payments',
        (SELECT COUNT(*) FROM staging.payments),
        (SELECT COUNT(DISTINCT payment_id) FROM staging.payments),
        0,
        (SELECT COUNT(*) FROM payments),
        (SELECT COUNT(*) FROM quarantine_payments),
        CASE WHEN (SELECT COUNT(DISTINCT payment_id) FROM staging.payments) =
                  (SELECT COUNT(*) FROM payments) + (SELECT COUNT(*) FROM quarantine_payments)
             THEN 'OK: unique = loaded + quarantined'
             ELSE 'MISMATCH' END,
        '24 quarantined: order_id not in orders.'
    UNION ALL
    SELECT 'customer_feedback',
        (SELECT COUNT(*) FROM staging.customer_feedback),
        (SELECT COUNT(DISTINCT feedback_id) FROM staging.customer_feedback),
        0,
        (SELECT COUNT(*) FROM customer_feedback),
        (SELECT COUNT(*) FROM quarantine_customer_feedback),
        CASE WHEN (SELECT COUNT(DISTINCT feedback_id) FROM staging.customer_feedback) =
                  (SELECT COUNT(*) FROM customer_feedback) + (SELECT COUNT(*) FROM quarantine_customer_feedback)
             THEN 'OK: unique = loaded + quarantined'
             ELSE 'MISMATCH' END,
        '20 quarantined: order_id not in orders.'
    ;
    """),

]


# ---------------------------------------------------------------------------
# Reconciliation query — run after all tables loaded
# ---------------------------------------------------------------------------
RECONCILIATION_SQL = """
SELECT
    'cities'            AS table_name,
    (SELECT COUNT(*)                       FROM staging.cities)           AS raw_rows,
    (SELECT COUNT(DISTINCT city_id)        FROM staging.cities)           AS unique_ids,
    (SELECT COUNT(*)                       FROM cities)                   AS loaded_rows,
    0                                                                      AS quarantined_rows
UNION ALL SELECT
    'customers',
    (SELECT COUNT(*)                       FROM staging.customers),
    (SELECT COUNT(DISTINCT customer_id)    FROM staging.customers),
    (SELECT COUNT(*)                       FROM customers),
    0
UNION ALL SELECT
    'restaurants',
    (SELECT COUNT(*)                       FROM staging.restaurants),
    (SELECT COUNT(DISTINCT restaurant_id)  FROM staging.restaurants),
    (SELECT COUNT(*)                       FROM restaurants),
    0
UNION ALL SELECT
    'delivery_partners',
    (SELECT COUNT(*)                       FROM staging.delivery_partners),
    (SELECT COUNT(DISTINCT delivery_partner_id) FROM staging.delivery_partners),
    (SELECT COUNT(*)                       FROM delivery_partners),
    0
UNION ALL SELECT
    'promotions',
    (SELECT COUNT(*)                       FROM staging.promotions),
    (SELECT COUNT(DISTINCT promotion_id)   FROM staging.promotions),
    (SELECT COUNT(*)                       FROM promotions),
    0
UNION ALL SELECT
    'weather',
    (SELECT COUNT(*)                       FROM staging.weather),
    (SELECT COUNT(DISTINCT weather_id)     FROM staging.weather),
    (SELECT COUNT(*)                       FROM weather),
    (SELECT COUNT(*)                       FROM quarantine_weather)
UNION ALL SELECT
    'traffic',
    (SELECT COUNT(*)                       FROM staging.traffic),
    (SELECT COUNT(DISTINCT traffic_id)     FROM staging.traffic),
    (SELECT COUNT(*)                       FROM traffic),
    0
UNION ALL SELECT
    'menu',
    (SELECT COUNT(*)                       FROM staging.menu),
    (SELECT COUNT(DISTINCT food_item_id)   FROM staging.menu),
    (SELECT COUNT(*)                       FROM menu),
    (SELECT COUNT(*)                       FROM quarantine_menu)
UNION ALL SELECT
    'orders',
    (SELECT COUNT(*)                       FROM staging.orders),
    (SELECT COUNT(DISTINCT order_id)       FROM staging.orders),
    (SELECT COUNT(*)                       FROM orders),
    (SELECT COUNT(*)                       FROM quarantine_orders)
UNION ALL SELECT
    'order_items',
    (SELECT COUNT(*)                       FROM staging.order_items),
    (SELECT COUNT(DISTINCT order_item_id)  FROM staging.order_items),
    (SELECT COUNT(*)                       FROM order_items),
    (SELECT COUNT(*)                       FROM quarantine_order_items)
UNION ALL SELECT
    'payments',
    (SELECT COUNT(*)                       FROM staging.payments),
    (SELECT COUNT(DISTINCT payment_id)     FROM staging.payments),
    (SELECT COUNT(*)                       FROM payments),
    (SELECT COUNT(*)                       FROM quarantine_payments)
UNION ALL SELECT
    'customer_feedback',
    (SELECT COUNT(*)                       FROM staging.customer_feedback),
    (SELECT COUNT(DISTINCT feedback_id)    FROM staging.customer_feedback),
    (SELECT COUNT(*)                       FROM customer_feedback),
    (SELECT COUNT(*)                       FROM quarantine_customer_feedback)
ORDER BY table_name;
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(cur, label: str, sql: str) -> int:
    """Execute a SQL statement and return rowcount. Strips blank lines."""
    # Split multi-statement blocks (quarantine tables sometimes have DROP + CREATE)
    parts = [s.strip() for s in sql.split(";") if s.strip()]
    total = 0
    for part in parts:
        cur.execute(part)
        if cur.rowcount and cur.rowcount > 0:
            total += cur.rowcount
    return total


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    start = datetime.now()
    print("=" * 64)
    print("Zomato BI — Step 6: Load Staging → Production")
    print("=" * 64)
    print(f"Started : {start.strftime('%Y-%m-%d %H:%M:%S')}\n")

    conn = psycopg2.connect(DATABASE_URL, connect_timeout=30,
                            options="-c statement_timeout=120000")
    conn.autocommit = False
    cur = conn.cursor()

    # Drop quarantine and reconciliation tables from any prior run
    print("Dropping old quarantine / reconciliation tables ...")
    for qt in [
        "quarantine_weather", "quarantine_menu", "quarantine_orders",
        "quarantine_order_items", "quarantine_payments", "quarantine_customer_feedback",
        "reconciliation",
    ]:
        cur.execute(f"DROP TABLE IF EXISTS {qt}")
    conn.commit()
    print("  done\n")

    # Execute each load statement in order
    print(f"{'Step':<35} {'Rows':>8}  Status")
    print("-" * 64)
    errors = []

    for label, sql in LOAD_STATEMENTS:
        try:
            rows = run(cur, label, sql)
            conn.commit()
            tag = "quarantine" if label.startswith("quarantine") else "loaded"
            print(f"  {label:<33} {rows:>8,}  ✅  ({tag})")
        except Exception as e:
            conn.rollback()
            errors.append((label, str(e)))
            print(f"  {label:<33} {'ERR':>8}  ❌  {e}")
            # Re-connect after rollback to keep going with remaining tables
            conn = psycopg2.connect(DATABASE_URL, connect_timeout=30,
                                    options="-c statement_timeout=120000")
            conn.autocommit = False
            cur = conn.cursor()

    # Reconciliation
    print("\n" + "=" * 64)
    print("Reconciliation")
    print("=" * 64)
    print(f"\n  {'Table':<22} {'Raw':>7} {'Unique':>7} {'Loaded':>8} {'Quar':>7}  Check")
    print(f"  {'-'*22} {'-'*7} {'-'*7} {'-'*8} {'-'*7}  {'-----'}")

    try:
        cur.execute(RECONCILIATION_SQL)
        rec_rows = cur.fetchall()
        all_balanced = True
        for table_name, raw, unique, loaded, quarantined in rec_rows:
            dups = raw - unique
            # Rule: unique_ids = loaded + quarantined
            balanced = (unique == loaded + quarantined)
            icon = "✅" if balanced else "⚠️ "
            if not balanced:
                all_balanced = False
            print(f"  {table_name:<22} {raw:>7,} {unique:>7,} {loaded:>8,} {quarantined:>7,}  {icon}")

        print(f"\n  Legend: Raw = CSV rows  |  Unique = distinct PKs  |  Loaded = in production")
        print(f"          Quar = quarantined  |  ✅ Unique = Loaded + Quarantined")
        if all_balanced:
            print("\n  All tables balanced — no rows silently lost ✅")
        else:
            print("\n  ⚠️  Some tables don't balance — investigate above")
    except Exception as e:
        print(f"  Reconciliation query failed: {e}")

    # Date range check on orders
    print("\n" + "=" * 64)
    print("Date Range Verification")
    print("=" * 64)
    try:
        cur.execute("SELECT MIN(order_date), MAX(order_date) FROM orders;")
        min_d, max_d = cur.fetchone()
        if min_d and max_d:
            span_days = (max_d - min_d).days
            span_months = round(span_days / 30.44, 1)
            print(f"\n  orders.order_date  MIN={min_d}  MAX={max_d}")
            print(f"  Span: ~{span_months} months ({span_days} days)")
            if 18 <= span_months <= 30:
                print("  ✅ Spans ~24 months as expected")
            else:
                print(f"  ⚠️  Expected ~24 months — investigate date parsing")
    except Exception as e:
        print(f"  Date check failed: {e}")

    # Final production counts
    print("\n" + "=" * 64)
    print("Production Table Counts")
    print("=" * 64)
    prod_tables = ["cities", "customers", "restaurants", "delivery_partners",
                   "promotions", "weather", "traffic", "menu", "orders",
                   "order_items", "payments", "customer_feedback"]
    total_prod = 0
    for t in prod_tables:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        cnt = cur.fetchone()[0]
        total_prod += cnt
        print(f"  {t:<25} {cnt:>8,}")
    print(f"  {'TOTAL':<25} {total_prod:>8,}")

    elapsed = (datetime.now() - start).total_seconds()
    print("\n" + "=" * 64)
    if not errors:
        print(f"Step 6 COMPLETE ✅  ({elapsed:.1f}s)")
        print("All 12 production tables populated.")
        print("Quarantine tables created for rejected rows.")
        print("\nNext: verify integrity checks (Step 7)")
    else:
        print(f"Step 6 completed with {len(errors)} error(s) — review above.")
    print("=" * 64)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
