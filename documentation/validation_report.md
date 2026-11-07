# Validation Report — Step 11

**Generated:** 2026-11-07 23:10:23  
**SQL source:** Supabase (production schema, Week 1)  
**Python source:** `data/cleaned/` (Week 2 pipeline)  

---

## Summary

| | Value |
|---|---|
| Total checks | 15 |
| All match | ✅ Yes |
| Data Cleaning Completeness | 100.0% (target ≥ 95%) ✅ |

## Check Results

| Check | SQL value | Python value | Match | Explanation |
|-------|-----------|--------------|-------|-------------|
| orders: row count | 20475 | 20475 | ✅ OK | Should match — same dedup and orphan rules applied in both Week 1 SQL and Python |
| customers: row count | 12000 | 12000 | ✅ OK | Should match — 180 exact-copy duplicates removed in both |
| restaurants: row count | 1200 | 1200 | ✅ OK | No duplicates in either |
| delivery_partners: row count | 2000 | 2000 | ✅ OK | No duplicates in either |
| payments: row count | 20469 | 20469 | ✅ OK | Same orphan rows quarantined in both |
| customer_feedback: row count | 14180 | 14180 | ✅ OK | Same orphan rows quarantined in both |
| orders: Delivered revenue (₹) | 4406359.55 | 4406359.55 | ✅ OK | Revenue computed using same filter: Delivered + final_amount > 0 |
| orders: Delivered Late revenue (₹) | 829976.05 | 829976.05 | ✅ OK | Same filter applied both sides |
| orders: avg delivery time (valid, mins) | 38.5923 | 38.5923 | ✅ OK | Same filter: delivery_time_minutes > 0 |
| orders: min order_date | 2023-01-01 | 2023-01-01 | ✅ OK | Both span Jan 2023 – Dec 2024 |
| orders: max order_date | 2024-12-31 | 2024-12-31 | ✅ OK | Reference date matches |
| orders: Cancelled count | 4569 | 4569 | ✅ OK | Same status values after .str.title() in Python |
| orders: Delivered count | 11390 | 11390 | ✅ OK | Same status values |
| orders: Food Not Delivered count | 2362 | 2362 | ✅ OK | Same status values |
| orders: per-city distribution (all 25 cities) | see breakdown | see breakdown | ✅ OK | Orders grouped by restaurant.city, compared city by city |

## Data Quality Log Status

| Status | Count | % |
|---|---|---|
| fixed in Python | 53 | 48.2% |
| fixed in SQL | 48 | 43.6% |
| verified | 9 | 8.2% |

**% resolved (fixed in SQL + fixed in Python + verified):** 100.0%

## Why Differences Are Expected

Both pipelines apply the same rules:
- Deduplication: keep first per PK (same rule)
- Orphans: quarantined with reason (same FK checks)
- City names: same alias dict from Week 1
- Date parsing: same format logic

Python also applies additional cleaning SQL did not:
- Rating out-of-range → NaN (SQL loaded them as-is)
- Age imputation with group median (SQL left NaN)
- Phone/pincode validity flags (SQL left NaN)
- `has_review` flag, `age_was_missing` flag (new columns)

These are Python-only enrichments, not disagreements.

## Distance Limitation

`customers.csv` has no latitude/longitude columns (verified in Step 9).  
The PRD's 'restaurant-to-customer distance' feature was replaced with an honest proxy:  
`distance_to_city_centre_km` = haversine distance from the restaurant to the mean  
latitude/longitude of all restaurants in its city.  
This is documented here and in `documentation/kpi_definitions.md`.
