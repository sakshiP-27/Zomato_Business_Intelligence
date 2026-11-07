# KPI Definitions — Zomato BI Project

**Author:** Sakshi  
**Date defined:** Week 1, Day 4  
**Reference:** These definitions must be used identically in Weeks 2 (Python), 3 (ML), and 4 (Power BI).  
Changing them mid-project would make week-over-week numbers incomparable.

---

## 1. Reference Date

```sql
SELECT MAX(order_date) FROM orders;  -- returns 2024-12-31
```

**Definition:** `2024-12-31` — the latest order date in the dataset.  
**Rule:** Never use `CURRENT_DATE` or `NOW()`. The data is a fixed 24-month snapshot  
(Jan 2023 – Dec 2024). Using today's date returns zero or wrong results.

---

## 2. Revenue

**Definition:** `SUM(final_amount)` for orders where:
- `order_status IN ('Delivered', 'Delivered Late')` — only completed orders count
- `final_amount > 0` — excludes the 327 NULL and negative anomalies logged in data_quality_log.csv

**Rationale:** Cancelled orders (`22.32%` of all orders) and `Food Not Delivered` orders  
(`11.54%`) should never contribute to revenue. `Delivered Late` orders (`10.52%`) were  
received by the customer and are legitimate revenue.

**Total revenue in dataset:** ₹5,236,335.60 across 13,544 qualifying orders.

```sql
-- Standard revenue filter used in all queries
WHERE order_status IN ('Delivered', 'Delivered Late')
  AND final_amount > 0
```

---

## 3. Late Delivery

**Definition:** A delivery is **late** if `delivery_time_minutes > 45`.

**Data-driven justification:**  
Delivery time distribution for valid completed orders (`delivery_time_minutes > 0`,  
`order_status IN ('Delivered', 'Delivered Late')`, n = 13,408):

| Percentile | Minutes |
|---|---|
| Median (p50) | 36 min |
| p75 | 45 min |
| p90 | 61 min |
| p95 | 72 min |
| p99 | 91 min |
| Max | 399 min |
| Mean | 40.1 min |

**Choice:** The **75th percentile = 45 minutes** is used as the threshold.  
- It is a natural breakpoint in the distribution — the top 25% of delivery times.
- It aligns with the industry standard of "45-minute delivery" used in Zomato's own marketing.
- The `Delivered Late` status in the data (`10.52%` of orders) likely uses a similar internal rule.
- Using p75 keeps the "late" label meaningful — not so strict that half of orders are "late".

**Valid delivery time:** `delivery_time_minutes > 0`  
An upper cap (for outlier exclusion) will be decided in Week 2 after box-plot analysis.  
The current max of 399 minutes is suspicious but kept for now.

```sql
-- Late delivery flag used in all queries
CASE WHEN delivery_time_minutes > 45 AND delivery_time_minutes > 0
     THEN 'Late' ELSE 'On Time' END AS delivery_status
```

---

## 4. Active Customer

**Definition:** A customer who placed **at least one order in the 60 days before the reference date** —  
i.e. between `2024-11-01` and `2024-12-31`.

**Count:** 1,379 active customers as of the reference date.

**Rationale:** 60 days matches the churn horizon used in the Week 3 ML model  
(a customer not ordering in 60 days is at churn risk). Using the same window keeps  
Week 1 SQL, Week 3 features, and Week 4 dashboards consistent.

```sql
-- Active customer filter
WHERE order_date > (SELECT MAX(order_date) FROM orders) - INTERVAL '60 days'
```

---

## 5. Top Restaurant

**Definition:** A restaurant's performance score is a weighted composite of three metrics,  
ranked within each city (not globally — comparing Mumbai restaurants to Raipur restaurants  
is unfair given market size differences):

```
performance_score = 0.4 × PERCENT_RANK(rating)
                  + 0.3 × (1 − PERCENT_RANK(cancellation_rate))
                  + 0.3 × (1 − PERCENT_RANK(avg_delivery_time))
```

**Weights rationale:**
- Rating (40%) is given the largest weight as the most direct measure of customer satisfaction (a design choice, not a measured result).
- Cancellation rate (30%) directly impacts revenue and customer trust.
- Average delivery time (30%) is the core operational KPI of this project.

**Minimum order threshold:** 10 orders (restaurants with fewer cannot be reliably ranked).

This is implemented as `v_restaurant_performance` view in `business_queries.sql`.

---

## 6. Valid Order (for delivery time analysis)

**Definition:** An order is valid for delivery time analysis if:
- `delivery_time_minutes > 0` (excludes the 209 negative and zero values logged in data_quality_log.csv)
- `order_status IN ('Delivered', 'Delivered Late')` (only orders that were actually delivered)

The `v_orders_valid` view in `business_queries.sql` encapsulates this filter.

---

## 7. "Last N Months" Date Arithmetic

Always anchor to the reference date, never `CURRENT_DATE`:

```sql
-- Last 6 months of data
order_date > (SELECT MAX(order_date) FROM orders) - INTERVAL '6 months'

-- Last 3 months
order_date > (SELECT MAX(order_date) FROM orders) - INTERVAL '3 months'
```

---

## Summary Table

| Term | Definition | SQL anchor |
|---|---|---|
| Reference date | `MAX(order_date)` = 2024-12-31 | `(SELECT MAX(order_date) FROM orders)` |
| Revenue | `SUM(final_amount)` for Delivered/Delivered Late, final_amount > 0 | `order_status IN ('Delivered','Delivered Late') AND final_amount > 0` |
| Late delivery | `delivery_time_minutes > 45` | `CASE WHEN delivery_time_minutes > 45 ...` |
| Valid delivery time | `delivery_time_minutes > 0` | `delivery_time_minutes > 0` |
| Active customer | ≥1 order in last 60 days before reference date | `order_date > ref_date - INTERVAL '60 days'` |
| Top restaurant | Highest weighted score (rating 40%, cancel 30%, speed 30%) within city | `v_restaurant_performance` view |
