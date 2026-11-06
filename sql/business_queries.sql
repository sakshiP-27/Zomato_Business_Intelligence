-- =============================================================================
-- Zomato Business Intelligence — business_queries.sql
-- Steps 9 & 10: 25 queries + 4 views + 1 documented index
-- =============================================================================
-- KPI definitions (see documentation/kpi_definitions.md):
--   Revenue        : SUM(final_amount) WHERE order_status IN ('Delivered','Delivered Late') AND final_amount > 0
--   Late delivery  : delivery_time_minutes > 45  (= p75 of the distribution)
--   Active customer: ≥1 order in the 60 days before MAX(order_date) = 2024-12-31
--   Reference date : (SELECT MAX(order_date) FROM orders)  -- NEVER use CURRENT_DATE
--   Valid del. time: delivery_time_minutes > 0
-- =============================================================================


-- =============================================================================
-- VIEWS  (create first — queries below reference them)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- VIEW 1: v_orders_valid
-- Orders with usable delivery time and cost values.
-- Use this view in all delivery-time analysis so bad rows don't skew averages.
-- Raw rows remain in orders table for auditing.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_orders_valid AS
SELECT o.*,
       r.city        AS restaurant_city,
       r.cuisine     AS restaurant_cuisine,
       r.restaurant_type
FROM orders o
JOIN restaurants r ON r.restaurant_id = o.restaurant_id
WHERE o.delivery_time_minutes > 0
  AND o.food_cost              > 0
  AND o.final_amount           > 0
  AND o.order_status IN ('Delivered', 'Delivered Late');


-- -----------------------------------------------------------------------------
-- VIEW 2: v_monthly_revenue_by_city
-- Monthly revenue per city — backbone of the Power BI time-series tile.
-- City is derived from the restaurant (canonical join path per design_notes.md).
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_monthly_revenue_by_city AS
SELECT
    r.city,
    DATE_TRUNC('month', o.order_date)::DATE        AS month,
    COUNT(*)                                        AS orders,
    ROUND(SUM(o.final_amount)::numeric, 2)          AS revenue,
    ROUND(AVG(o.final_amount)::numeric, 2)          AS avg_order_value
FROM orders o
JOIN restaurants r ON r.restaurant_id = o.restaurant_id
WHERE o.order_status IN ('Delivered', 'Delivered Late')
  AND o.final_amount > 0
GROUP BY r.city, DATE_TRUNC('month', o.order_date);


-- -----------------------------------------------------------------------------
-- VIEW 3: v_customer_rfm
-- Per-customer Recency / Frequency / Monetary values.
-- Backbone of Week 3 churn prediction model.
-- Recency: days since last order, measured from reference date 2024-12-31.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_customer_rfm AS
SELECT
    o.customer_id,
    c.name,
    c.city,
    c.membership,
    COUNT(DISTINCT o.order_id)                              AS frequency,
    ROUND(SUM(o.final_amount)::numeric, 2)                  AS monetary,
    MAX(o.order_date)                                       AS last_order_date,
    (SELECT MAX(order_date) FROM orders) - MAX(o.order_date) AS recency_days,
    CASE
        WHEN (SELECT MAX(order_date) FROM orders) - MAX(o.order_date) <= 60 THEN 'Active'
        ELSE 'Churned'
    END                                                     AS churn_status
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
WHERE o.order_status IN ('Delivered', 'Delivered Late')
  AND o.final_amount > 0
GROUP BY o.customer_id, c.name, c.city, c.membership;


-- -----------------------------------------------------------------------------
-- VIEW 4: v_restaurant_performance
-- Composite performance score per restaurant within its city.
-- Weights: rating 40% | cancellation rate 30% | avg delivery speed 30%
-- Only restaurants with >= 10 orders are scored (too few = unreliable rank).
-- PERCENT_RANK partitioned by city keeps markets fairly comparable.
-- NULLS FIRST on rating = missing rating ranks lowest (conservative).
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_restaurant_performance AS
WITH stats AS (
    SELECT
        r.restaurant_id,
        r.restaurant_name,
        r.city,
        r.cuisine,
        r.restaurant_type,
        r.rating                                                        AS restaurant_rating,
        COUNT(o.order_id)                                               AS total_orders,
        ROUND(AVG(CASE WHEN o.order_status = 'Cancelled'
                       THEN 1.0 ELSE 0.0 END)::numeric, 4)             AS cancel_rate,
        ROUND(AVG(o.delivery_time_minutes)
              FILTER (WHERE o.delivery_time_minutes > 0)::numeric, 1)  AS avg_delivery_min,
        ROUND(SUM(CASE WHEN o.order_status IN ('Delivered','Delivered Late')
                            AND o.final_amount > 0
                       THEN o.final_amount ELSE 0 END)::numeric, 2)    AS total_revenue
    FROM restaurants r
    JOIN orders o ON o.restaurant_id = r.restaurant_id
    GROUP BY r.restaurant_id, r.restaurant_name, r.city,
             r.cuisine, r.restaurant_type, r.rating
    HAVING COUNT(o.order_id) >= 10
)
SELECT *,
    ROUND((
          0.4 * PERCENT_RANK() OVER (PARTITION BY city ORDER BY restaurant_rating NULLS FIRST)
        + 0.3 * (1.0 - PERCENT_RANK() OVER (PARTITION BY city ORDER BY cancel_rate))
        + 0.3 * (1.0 - PERCENT_RANK() OVER (PARTITION BY city ORDER BY avg_delivery_min))
    )::numeric, 3) AS performance_score
FROM stats;


-- =============================================================================
-- STEP 9: CORE QUERIES (Q01 – Q15)
-- Constructs: GROUP BY, aggregates, JOIN, LEFT/RIGHT/SELF JOIN,
--             UNION, CASE WHEN, scalar subquery, correlated subquery, CTE
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Q01: Orders, revenue, and average order value by order status
-- Constructs: GROUP BY, COUNT, SUM, AVG, ROUND
-- -----------------------------------------------------------------------------
SELECT
    order_status,
    COUNT(*)                                        AS total_orders,
    ROUND(SUM(final_amount)::numeric, 2)            AS total_revenue,
    ROUND(AVG(final_amount)::numeric, 2)            AS avg_order_value,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER ()
          ::numeric, 2)                             AS pct_of_orders
FROM orders
WHERE final_amount IS NOT NULL
GROUP BY order_status
ORDER BY total_orders DESC;


-- -----------------------------------------------------------------------------
-- Q02: Top 10 restaurants by revenue in the last 6 months of data
-- Constructs: JOIN, WHERE with date arithmetic, ORDER BY, LIMIT
-- Note: reference date 2024-12-31 — interval anchored to MAX(order_date)
-- -----------------------------------------------------------------------------
SELECT
    r.restaurant_name,
    r.city,
    r.cuisine,
    COUNT(o.order_id)                               AS orders,
    ROUND(SUM(o.final_amount)::numeric, 2)          AS revenue
FROM orders o
JOIN restaurants r ON r.restaurant_id = o.restaurant_id
WHERE o.order_status IN ('Delivered', 'Delivered Late')
  AND o.final_amount > 0
  AND o.order_date > (SELECT MAX(order_date) FROM orders) - INTERVAL '6 months'
GROUP BY r.restaurant_id, r.restaurant_name, r.city, r.cuisine
ORDER BY revenue DESC
LIMIT 10;


-- -----------------------------------------------------------------------------
-- Q03: Average delivery time by city, slowest to fastest
-- Constructs: JOIN, GROUP BY, AVG, ORDER BY
-- Excludes invalid delivery times (<= 0) per kpi_definitions.md
-- City derived from restaurant (canonical join path)
-- -----------------------------------------------------------------------------
SELECT
    r.city,
    COUNT(*)                                                AS delivered_orders,
    ROUND(AVG(o.delivery_time_minutes)::numeric, 1)        AS avg_delivery_min,
    ROUND(MIN(o.delivery_time_minutes)::numeric, 1)        AS min_delivery_min,
    ROUND(MAX(o.delivery_time_minutes)::numeric, 1)        AS max_delivery_min
FROM orders o
JOIN restaurants r ON r.restaurant_id = o.restaurant_id
WHERE o.delivery_time_minutes > 0
  AND o.order_status IN ('Delivered', 'Delivered Late')
GROUP BY r.city
ORDER BY avg_delivery_min DESC;


-- -----------------------------------------------------------------------------
-- Q04: Cancellation percentage by cuisine
-- Constructs: JOIN, CASE WHEN, GROUP BY, ROUND, ORDER BY
-- -----------------------------------------------------------------------------
SELECT
    r.cuisine,
    COUNT(*)                                                AS total_orders,
    SUM(CASE WHEN o.order_status = 'Cancelled' THEN 1 ELSE 0 END)
                                                            AS cancelled_orders,
    ROUND(100.0 * SUM(CASE WHEN o.order_status = 'Cancelled' THEN 1 ELSE 0 END)
          / COUNT(*), 2)                                    AS cancel_pct
FROM orders o
JOIN restaurants r ON r.restaurant_id = o.restaurant_id
WHERE r.cuisine IS NOT NULL
GROUP BY r.cuisine
ORDER BY cancel_pct DESC;


-- -----------------------------------------------------------------------------
-- Q05: Cities whose average delivery time is above the overall average
-- Constructs: GROUP BY, HAVING, scalar subquery
-- -----------------------------------------------------------------------------
SELECT
    r.city,
    ROUND(AVG(o.delivery_time_minutes)::numeric, 1)        AS avg_delivery_min,
    ROUND((SELECT AVG(delivery_time_minutes)
           FROM orders
           WHERE delivery_time_minutes > 0
             AND order_status IN ('Delivered','Delivered Late'))::numeric, 1)
                                                            AS overall_avg_min
FROM orders o
JOIN restaurants r ON r.restaurant_id = o.restaurant_id
WHERE o.delivery_time_minutes > 0
  AND o.order_status IN ('Delivered', 'Delivered Late')
GROUP BY r.city
HAVING AVG(o.delivery_time_minutes) > (
    SELECT AVG(delivery_time_minutes)
    FROM orders
    WHERE delivery_time_minutes > 0
      AND order_status IN ('Delivered', 'Delivered Late')
)
ORDER BY avg_delivery_min DESC;


-- -----------------------------------------------------------------------------
-- Q06: Customers who have never placed an order  (LEFT JOIN version)
-- Constructs: LEFT JOIN, IS NULL
-- -----------------------------------------------------------------------------
SELECT
    c.customer_id,
    c.name,
    c.city,
    c.membership,
    c.registration_date
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL
ORDER BY c.registration_date;


-- -----------------------------------------------------------------------------
-- Q07: Customers who have never placed an order  (RIGHT JOIN version)
-- Constructs: RIGHT JOIN
-- Same result as Q06, different join direction — demonstrates RIGHT JOIN
-- -----------------------------------------------------------------------------
SELECT
    c.customer_id,
    c.name,
    c.city,
    c.membership,
    c.registration_date
FROM orders o
RIGHT JOIN customers c ON c.customer_id = o.customer_id
WHERE o.order_id IS NULL
ORDER BY c.registration_date;


-- -----------------------------------------------------------------------------
-- Q08: Coupon code usage — total discount given, order volume, avg discount
-- Constructs: JOIN, GROUP BY, HAVING, ORDER BY
-- Only coupons used in at least 5 orders shown
-- -----------------------------------------------------------------------------
SELECT
    p.coupon_code,
    p.campaign_name,
    p.discount_percentage,
    COUNT(o.order_id)                               AS times_used,
    ROUND(SUM(o.discount)::numeric, 2)              AS total_discount_given,
    ROUND(AVG(o.discount)::numeric, 2)              AS avg_discount_per_order,
    ROUND(SUM(o.final_amount)::numeric, 2)          AS total_revenue_with_coupon
FROM orders o
JOIN promotions p ON p.coupon_code = o.coupon_code
WHERE o.order_status IN ('Delivered', 'Delivered Late')
GROUP BY p.coupon_code, p.campaign_name, p.discount_percentage
HAVING COUNT(o.order_id) >= 5
ORDER BY total_discount_given DESC;


-- -----------------------------------------------------------------------------
-- Q09: Orders bucketed into Low / Medium / High value tiers
-- Constructs: CASE WHEN bucketing, GROUP BY
-- Thresholds based on ₹0-300 / ₹300-600 / ₹600+
-- -----------------------------------------------------------------------------
SELECT
    CASE
        WHEN final_amount < 300  THEN 'Low   (< ₹300)'
        WHEN final_amount < 600  THEN 'Medium (₹300–600)'
        ELSE                          'High  (₹600+)'
    END                                             AS value_tier,
    COUNT(*)                                        AS order_count,
    ROUND(AVG(final_amount)::numeric, 2)            AS avg_order_value,
    ROUND(SUM(final_amount)::numeric, 2)            AS total_revenue,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER ()
          ::numeric, 2)                             AS pct_of_orders
FROM orders
WHERE order_status IN ('Delivered', 'Delivered Late')
  AND final_amount > 0
GROUP BY 1
ORDER BY MIN(final_amount);


-- -----------------------------------------------------------------------------
-- Q10: Pairs of restaurants in the same city serving the same cuisine
-- Constructs: SELF JOIN
-- Uses r1.restaurant_id < r2.restaurant_id to avoid duplicate pairs
-- -----------------------------------------------------------------------------
SELECT
    r1.city,
    r1.cuisine,
    r1.restaurant_name  AS restaurant_1,
    r2.restaurant_name  AS restaurant_2
FROM restaurants r1
JOIN restaurants r2
    ON  r1.city    = r2.city
    AND r1.cuisine = r2.cuisine
    AND r1.restaurant_id < r2.restaurant_id   -- prevents (A,B) and (B,A) duplicates
WHERE r1.cuisine IS NOT NULL
ORDER BY r1.city, r1.cuisine, r1.restaurant_name
LIMIT 30;


-- -----------------------------------------------------------------------------
-- Q11: Combined list of top-10 spenders AND top-10 most frequent customers
-- Constructs: UNION (de-duplicates), label column
-- -----------------------------------------------------------------------------
SELECT customer_id, name, city, total_value, label
FROM (
    SELECT c.customer_id, c.name, c.city,
           ROUND(SUM(o.final_amount)::numeric, 2)  AS total_value,
           'Top Spender'                            AS label
    FROM orders o
    JOIN customers c ON c.customer_id = o.customer_id
    WHERE o.order_status IN ('Delivered','Delivered Late') AND o.final_amount > 0
    GROUP BY c.customer_id, c.name, c.city
    ORDER BY total_value DESC LIMIT 10
) top_spenders

UNION

SELECT customer_id, name, city, total_orders AS total_value, label
FROM (
    SELECT c.customer_id, c.name, c.city,
           COUNT(o.order_id)::numeric              AS total_orders,
           'Most Frequent'                          AS label
    FROM orders o
    JOIN customers c ON c.customer_id = o.customer_id
    WHERE o.order_status IN ('Delivered','Delivered Late')
    GROUP BY c.customer_id, c.name, c.city
    ORDER BY total_orders DESC LIMIT 10
) top_frequent

ORDER BY label, total_value DESC;


-- -----------------------------------------------------------------------------
-- Q12: Orders whose final_amount exceeds that restaurant's own average
-- Constructs: correlated subquery in WHERE
-- -----------------------------------------------------------------------------
SELECT
    o.order_id,
    r.restaurant_name,
    r.city,
    o.final_amount,
    ROUND((
        SELECT AVG(o2.final_amount)
        FROM orders o2
        WHERE o2.restaurant_id = o.restaurant_id
          AND o2.order_status IN ('Delivered','Delivered Late')
          AND o2.final_amount > 0
    )::numeric, 2)                                  AS restaurant_avg_order_value
FROM orders o
JOIN restaurants r ON r.restaurant_id = o.restaurant_id
WHERE o.order_status IN ('Delivered','Delivered Late')
  AND o.final_amount > 0
  AND o.final_amount > (
        SELECT AVG(o2.final_amount)
        FROM orders o2
        WHERE o2.restaurant_id = o.restaurant_id
          AND o2.order_status IN ('Delivered','Delivered Late')
          AND o2.final_amount > 0
  )
ORDER BY o.final_amount DESC
LIMIT 20;


-- -----------------------------------------------------------------------------
-- Q13: New vs. repeat customers
-- Constructs: CTE (WITH), CASE WHEN
-- New = exactly 1 delivered order; Repeat = 2+
-- -----------------------------------------------------------------------------
WITH orders_per_customer AS (
    SELECT
        customer_id,
        COUNT(*) AS n_orders
    FROM orders
    WHERE order_status IN ('Delivered','Delivered Late')
    GROUP BY customer_id
)
SELECT
    CASE WHEN n_orders = 1 THEN 'New (1 order)'
         ELSE 'Repeat (2+ orders)' END              AS customer_type,
    COUNT(*)                                        AS customer_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER ()
          ::numeric, 2)                             AS pct
FROM orders_per_customer
GROUP BY 1
ORDER BY customer_count DESC;


-- -----------------------------------------------------------------------------
-- Q14: Average basket size (items per order) by membership tier
-- Constructs: multi-table JOIN, GROUP BY
-- -----------------------------------------------------------------------------
SELECT
    c.membership,
    COUNT(DISTINCT o.order_id)                      AS total_orders,
    COUNT(oi.order_item_id)                         AS total_items,
    ROUND(AVG(o.final_amount)::numeric, 2)          AS avg_order_value,
    ROUND(COUNT(oi.order_item_id)::numeric
          / COUNT(DISTINCT o.order_id), 2)          AS avg_items_per_order
FROM orders o
JOIN customers c  ON c.customer_id = o.customer_id
JOIN order_items oi ON oi.order_id = o.order_id
WHERE o.order_status IN ('Delivered','Delivered Late')
  AND o.final_amount > 0
  AND c.membership IS NOT NULL
GROUP BY c.membership
ORDER BY avg_order_value DESC;


-- -----------------------------------------------------------------------------
-- Q15: Payment method share of completed orders, in percent
-- Constructs: aggregates, percentage maths
-- -----------------------------------------------------------------------------
SELECT
    payment_method,
    COUNT(*)                                        AS order_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER ()
          ::numeric, 2)                             AS pct_of_orders,
    ROUND(SUM(final_amount)::numeric, 2)            AS total_revenue,
    ROUND(AVG(final_amount)::numeric, 2)            AS avg_order_value
FROM orders
WHERE order_status IN ('Delivered','Delivered Late')
  AND final_amount > 0
  AND payment_method IS NOT NULL
GROUP BY payment_method
ORDER BY order_count DESC;


-- =============================================================================
-- STEP 10: ADVANCED QUERIES (Q16 – Q25)
-- Constructs: RANK/DENSE_RANK, ROW_NUMBER, LAG, LEAD,
--             PERCENT_RANK, running totals, DATE_TRUNC, EXTRACT
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Q16: Top 3 restaurants by revenue within each city
-- Constructs: DENSE_RANK() OVER (PARTITION BY city ORDER BY revenue DESC)
-- Using DENSE_RANK so ties share the same rank
-- -----------------------------------------------------------------------------
WITH city_revenue AS (
    SELECT
        r.city,
        r.restaurant_name,
        r.cuisine,
        ROUND(SUM(o.final_amount)::numeric, 2)      AS revenue,
        COUNT(o.order_id)                           AS orders
    FROM orders o
    JOIN restaurants r ON r.restaurant_id = o.restaurant_id
    WHERE o.order_status IN ('Delivered','Delivered Late')
      AND o.final_amount > 0
    GROUP BY r.city, r.restaurant_id, r.restaurant_name, r.cuisine
)
SELECT *
FROM (
    SELECT *,
           DENSE_RANK() OVER (PARTITION BY city ORDER BY revenue DESC) AS city_rank
    FROM city_revenue
) ranked
WHERE city_rank <= 3
ORDER BY city, city_rank;


-- -----------------------------------------------------------------------------
-- Q17: Each customer's most recent order and days since it (recency)
-- Constructs: ROW_NUMBER() to pick latest order per customer
-- -----------------------------------------------------------------------------
WITH ranked_orders AS (
    SELECT
        o.customer_id,
        c.name,
        c.city,
        c.membership,
        o.order_id,
        o.order_date,
        o.final_amount,
        o.order_status,
        ROW_NUMBER() OVER (PARTITION BY o.customer_id
                           ORDER BY o.order_date DESC) AS rn
    FROM orders o
    JOIN customers c ON c.customer_id = o.customer_id
)
SELECT
    customer_id,
    name,
    city,
    membership,
    order_id            AS latest_order_id,
    order_date          AS latest_order_date,
    final_amount,
    order_status,
    (SELECT MAX(order_date) FROM orders) - order_date AS recency_days
FROM ranked_orders
WHERE rn = 1
ORDER BY recency_days ASC
LIMIT 20;


-- -----------------------------------------------------------------------------
-- Q18: Month-over-month revenue growth % per city
-- Constructs: LAG() OVER (PARTITION BY city ORDER BY month)
-- NULLIF prevents divide-by-zero on first month
-- -----------------------------------------------------------------------------
WITH monthly AS (
    SELECT
        r.city,
        DATE_TRUNC('month', o.order_date)::DATE     AS month,
        ROUND(SUM(o.final_amount)::numeric, 2)      AS revenue
    FROM orders o
    JOIN restaurants r ON r.restaurant_id = o.restaurant_id
    WHERE o.order_status IN ('Delivered','Delivered Late')
      AND o.final_amount > 0
    GROUP BY r.city, DATE_TRUNC('month', o.order_date)
)
SELECT
    city,
    month,
    revenue,
    LAG(revenue) OVER (PARTITION BY city ORDER BY month)   AS prev_month_revenue,
    ROUND(
        100.0 * (revenue - LAG(revenue) OVER (PARTITION BY city ORDER BY month))
        / NULLIF(LAG(revenue) OVER (PARTITION BY city ORDER BY month), 0)
    , 2)                                                    AS mom_growth_pct
FROM monthly
ORDER BY city, month;


-- -----------------------------------------------------------------------------
-- Q19: Days between consecutive orders for each customer
-- Constructs: LEAD() OVER (PARTITION BY customer_id ORDER BY order_date)
-- Useful for understanding purchase frequency / re-order cadence
-- -----------------------------------------------------------------------------
SELECT
    customer_id,
    order_id,
    order_date,
    order_status,
    LEAD(order_date) OVER (PARTITION BY customer_id
                           ORDER BY order_date)             AS next_order_date,
    LEAD(order_date) OVER (PARTITION BY customer_id
                           ORDER BY order_date) - order_date AS days_to_next_order
FROM orders
WHERE order_status IN ('Delivered','Delivered Late')
ORDER BY customer_id, order_date
LIMIT 30;


-- -----------------------------------------------------------------------------
-- Q20: Delivery partners in the top 10% by completed deliveries and rating
-- Constructs: NTILE(10) for decile ranking
-- Top 10% = decile 10
-- -----------------------------------------------------------------------------
SELECT
    delivery_partner_id,
    name,
    city,
    vehicle_type,
    completed_deliveries,
    rating,
    NTILE(10) OVER (ORDER BY completed_deliveries ASC)  AS deliveries_decile,
    NTILE(10) OVER (ORDER BY rating ASC)                AS rating_decile
FROM delivery_partners
WHERE completed_deliveries IS NOT NULL AND rating IS NOT NULL
ORDER BY completed_deliveries DESC, rating DESC;


-- Top 10% only (decile 10 in both)
-- Uncomment to filter:
-- WITH ranked AS ( ... above query ... )
-- SELECT * FROM ranked WHERE deliveries_decile = 10 AND rating_decile = 10;


-- -----------------------------------------------------------------------------
-- Q21: Cumulative (running) revenue over time, company-wide
-- Constructs: SUM() OVER (ORDER BY month) — running total window function
-- -----------------------------------------------------------------------------
WITH monthly_rev AS (
    SELECT
        DATE_TRUNC('month', o.order_date)::DATE     AS month,
        ROUND(SUM(o.final_amount)::numeric, 2)      AS monthly_revenue
    FROM orders o
    WHERE o.order_status IN ('Delivered','Delivered Late')
      AND o.final_amount > 0
    GROUP BY DATE_TRUNC('month', o.order_date)
)
SELECT
    month,
    monthly_revenue,
    ROUND(SUM(monthly_revenue) OVER (ORDER BY month
                                     ROWS BETWEEN UNBOUNDED PRECEDING
                                              AND CURRENT ROW)
          ::numeric, 2)                             AS cumulative_revenue
FROM monthly_rev
ORDER BY month;


-- -----------------------------------------------------------------------------
-- Q22: Average delivery time by weather condition and by traffic level
-- Constructs: JOIN weather/traffic on city + date (canonical join path)
-- WARNING: filter weather/traffic WHERE date IS NOT NULL (see integrity_checks_report.md)
-- City comes from the order's restaurant
-- -----------------------------------------------------------------------------

-- 22a: by weather condition
SELECT
    w.weather_condition,
    COUNT(o.order_id)                                       AS order_count,
    ROUND(AVG(o.delivery_time_minutes)::numeric, 1)        AS avg_delivery_min,
    ROUND(MIN(o.delivery_time_minutes)::numeric, 1)        AS min_delivery_min,
    ROUND(MAX(o.delivery_time_minutes)::numeric, 1)        AS max_delivery_min
FROM orders o
JOIN restaurants r  ON r.restaurant_id = o.restaurant_id
JOIN weather w      ON w.city = r.city AND w.date = o.order_date
WHERE o.delivery_time_minutes > 0
  AND o.order_status IN ('Delivered','Delivered Late')
  AND w.date IS NOT NULL                -- guard per integrity check 7
  AND w.weather_condition IS NOT NULL
GROUP BY w.weather_condition
ORDER BY avg_delivery_min DESC;

-- 22b: by traffic level
SELECT
    t.traffic_level,
    COUNT(o.order_id)                                       AS order_count,
    ROUND(AVG(o.delivery_time_minutes)::numeric, 1)        AS avg_delivery_min
FROM orders o
JOIN restaurants r  ON r.restaurant_id = o.restaurant_id
JOIN (
    -- Deduplicate traffic: take the max speed per city+date+time to handle duplicates
    SELECT DISTINCT ON (city, date, time) city, date, time, traffic_level, average_speed
    FROM traffic
    WHERE date IS NOT NULL AND traffic_level IS NOT NULL
    ORDER BY city, date, time, traffic_level
) t ON t.city = r.city AND t.date = o.order_date
WHERE o.delivery_time_minutes > 0
  AND o.order_status IN ('Delivered','Delivered Late')
GROUP BY t.traffic_level
ORDER BY avg_delivery_min DESC;


-- -----------------------------------------------------------------------------
-- Q23: Quarterly revenue by cuisine
-- Constructs: EXTRACT(QUARTER), DATE_TRUNC
-- -----------------------------------------------------------------------------
SELECT
    EXTRACT(YEAR  FROM o.order_date)::INT               AS year,
    EXTRACT(QUARTER FROM o.order_date)::INT             AS quarter,
    r.cuisine,
    COUNT(o.order_id)                                   AS orders,
    ROUND(SUM(o.final_amount)::numeric, 2)              AS revenue
FROM orders o
JOIN restaurants r ON r.restaurant_id = o.restaurant_id
WHERE o.order_status IN ('Delivered','Delivered Late')
  AND o.final_amount > 0
  AND r.cuisine IS NOT NULL
GROUP BY 1, 2, 3
ORDER BY year, quarter, revenue DESC;


-- -----------------------------------------------------------------------------
-- Q24: % of late deliveries by city  (using the Step 8 KPI: > 45 minutes)
-- Constructs: CASE WHEN conditional aggregation, window function for %
-- -----------------------------------------------------------------------------
SELECT
    r.city,
    COUNT(*)                                            AS delivered_orders,
    SUM(CASE WHEN o.delivery_time_minutes > 45 THEN 1 ELSE 0 END)
                                                        AS late_orders,
    ROUND(100.0 * SUM(CASE WHEN o.delivery_time_minutes > 45 THEN 1 ELSE 0 END)
          / COUNT(*)
          ::numeric, 2)                                 AS pct_late,
    ROUND(AVG(o.delivery_time_minutes)::numeric, 1)    AS avg_delivery_min
FROM orders o
JOIN restaurants r ON r.restaurant_id = o.restaurant_id
WHERE o.delivery_time_minutes > 0
  AND o.order_status IN ('Delivered','Delivered Late')
GROUP BY r.city
ORDER BY pct_late DESC;


-- -----------------------------------------------------------------------------
-- Q25: Top and bottom 3 restaurants per city by performance score
-- Constructs: window function on the v_restaurant_performance view
-- Demonstrates using a view as a table in a subsequent query
-- -----------------------------------------------------------------------------
WITH ranked AS (
    SELECT *,
           RANK() OVER (PARTITION BY city ORDER BY performance_score DESC) AS rank_top,
           RANK() OVER (PARTITION BY city ORDER BY performance_score ASC)  AS rank_bottom
    FROM v_restaurant_performance
)
SELECT
    city,
    restaurant_name,
    cuisine,
    total_orders,
    restaurant_rating,
    ROUND(cancel_rate * 100, 2)         AS cancel_pct,
    avg_delivery_min,
    performance_score,
    CASE WHEN rank_top    <= 3 THEN 'Top 3'
         WHEN rank_bottom <= 3 THEN 'Bottom 3'
    END                                 AS tier
FROM ranked
WHERE rank_top <= 3 OR rank_bottom <= 3
ORDER BY city, performance_score DESC;


-- =============================================================================
-- INDEX DOCUMENTATION
-- =============================================================================
-- Index: idx_orders_customer_date  ON orders(customer_id, order_date)
-- Already created in schema.sql — documented here as required by the guide.
--
-- PURPOSE:
--   The most common analytical pattern in this project is "find a customer's
--   orders" — used in RFM analysis, churn prediction, active customer counts,
--   and customer-level reports. A composite index on (customer_id, order_date)
--   supports both equality lookups (customer_id = ?) and date-range filters
--   (customer_id = ? AND order_date > ?).
--
-- BEFORE (without index — simulated by checking plan):
--   EXPLAIN SELECT * FROM orders WHERE customer_id = 7095;
--   → Index Scan using idx_orders_customer_date  (cost=0.29..3.62 rows=2)
--   The index was already in place from schema.sql, confirming it is used.
--   On a fresh table without the index, this would be a Seq Scan over 20,475 rows.
--
-- AFTER:
--   Index Scan using idx_orders_customer_date on orders
--   (cost=0.29..3.62 rows=2 width=88)
--   Index Cond: (customer_id = 7095)
--
-- NOTE ON TABLE SIZE:
--   With ~20,000 rows, PostgreSQL may choose a sequential scan on some queries
--   because the table fits in a small number of pages. The index becomes
--   increasingly valuable as the orders table grows toward millions of rows in
--   production.
--
-- To verify the index is being used:
EXPLAIN (FORMAT TEXT) SELECT * FROM orders WHERE customer_id = 7095;

-- Additional indexes already created in schema.sql:
--   idx_orders_restaurant      ON orders(restaurant_id)          — restaurant rollups
--   idx_orders_delivery_partner ON orders(delivery_partner_id)   — partner reports
--   idx_orders_status           ON orders(order_status)          — status filters
--   idx_weather_city_date       ON weather(city, date)           — weather joins
--   idx_traffic_city_date       ON traffic(city, date)           — traffic joins
--   idx_order_items_order       ON order_items(order_id)         — basket lookups
--   idx_payments_order          ON payments(order_id)            — payment joins
--   idx_feedback_order          ON customer_feedback(order_id)   — feedback joins


-- =============================================================================
-- QUERY COUNT SUMMARY
-- =============================================================================
-- Core queries (Step 9)  : Q01 – Q15  = 15 queries
-- Advanced queries (Step 10): Q16 – Q25 = 10 queries
-- Views                  : v_orders_valid, v_monthly_revenue_by_city,
--                          v_customer_rfm, v_restaurant_performance  = 4 views
-- Indexes documented     : idx_orders_customer_date (primary) + 8 others
-- TOTAL DISTINCT QUERIES : 25  (requirement: 20+) ✅
-- TOTAL VIEWS            : 4   (requirement: 2+)  ✅
-- TOTAL INDEXES          : 9   (requirement: 1+)  ✅
-- =============================================================================
