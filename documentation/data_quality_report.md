# Data Quality Report — Step 5 Profiling
**Generated:** 2026-11-06 10:09:37  
**Source:** staging schema (12 tables, 159,077 total rows)

---
## Summary
| Metric | Value |
|---|---|
| Tables profiled | 12 |
| Total issue rows logged | 104 |
| Issues with count > 0 | 97 |
| Issues already fixed in SQL (staging→prod load) | 48 |
| Issues deferred to Week 2 Python | 56 |

## Per-Table Findings
### cities  (25 rows)
| Column | Issue | Count | % | Example | Fix |
|--------|-------|------:|---|---------|-----|
| average_income | null or blank | 2 | 8.00% |  | Load as NULL; impute in Week 2 if needed |

### customer_feedback  (14,200 rows)
| Column | Issue | Count | % | Example | Fix |
|--------|-------|------:|---|---------|-----|
| customer_rating | null or blank | 294 | 2.07% |  | Load as NULL; impute in Week 2 if needed |
| review | null or blank | 1,058 | 7.45% |  | Load as NULL; impute in Week 2 if needed |
| sentiment | category audit (3 distinct values) | 3 | 0.02% | Positive \| Negative \| Neutral | Use exact spellings in all SQL queries and dashboa |

### customers  (12,180 rows)
| Column | Issue | Count | % | Example | Fix |
|--------|-------|------:|---|---------|-----|
| name | extra whitespace | 236 | 1.94% | ' Charles Natt  ' | TRIM() while loading to production |
| age | null or blank | 170 | 1.40% |  | Load as NULL; impute in Week 2 if needed |
| gender | null or blank | 122 | 1.00% |  | Load as NULL; impute in Week 2 if needed |
| phone | null or blank | 144 | 1.18% |  | Load as NULL; impute in Week 2 if needed |
| email | null or blank | 332 | 2.73% |  | Load as NULL; impute in Week 2 if needed |
| city | extra whitespace | 345 | 2.83% | ' Hyderabad  ' | TRIM() while loading to production |
| state | null or blank | 186 | 1.53% |  | Load as NULL; impute in Week 2 if needed |
| membership | null or blank | 120 | 0.99% |  | Load as NULL; impute in Week 2 if needed |
| preferred_cuisine | null or blank | 245 | 2.01% |  | Load as NULL; impute in Week 2 if needed |
| (all columns) | duplicate full rows | 180 | 1.48% |  | ROW_NUMBER() OVER (PARTITION BY pk) = 1 keeps firs |
| customer_id | duplicate primary key | 180 | 1.48% | 22 | Keep row with fewest NULLs; discard others; log co |
| registration_date | date format: DD-MM-YYYY | 2,021 | 16.59% | 18-02-2024 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| registration_date | date format: MM/DD/YYYY or DD/MM/YYYY | 4,034 | 33.12% | 05/17/2023 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| registration_date | date format: YYYY.MM.DD | 2,052 | 16.85% | 2022.05.16 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| registration_date | date format: YYYY-MM-DD | 2,030 | 16.67% | 2022-06-11 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| registration_date | date format: DD Mon YYYY | 2,043 | 16.77% | 28 Feb 2024 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| city | non-canonical city name | 904 | 7.42% | AHMEDABAD, BANGALORE, BENGALURU, BHOPAL, | Map via city_aliases table during staging→producti |
| phone | invalid Indian mobile number (not 10 digits / wrong prefix) | 7,451 | 61.17% | 1960013389 | Log only in Week 1; null out or fix in Week 2 Pyth |
| pincode | invalid pincode (not exactly 6 digits) | 398 | 3.27% | 85529X | Log only in Week 1; null out or fix in Week 2 Pyth |
| membership | category audit (3 distinct values) | 3 | 0.02% | Basic \| Zomato Pro \| Gold | Use exact spellings in all SQL queries and dashboa |
| gender | category audit (3 distinct values) | 3 | 0.02% | Female \| Other \| Male | Use exact spellings in all SQL queries and dashboa |

### delivery_partners  (2,000 rows)
| Column | Issue | Count | % | Example | Fix |
|--------|-------|------:|---|---------|-----|
| name | extra whitespace | 31 | 1.55% | ' Dalaja Yogi  ' | TRIM() while loading to production |
| city | extra whitespace | 53 | 2.65% | ' Nagpur  ' | TRIM() while loading to production |
| rating | null or blank | 34 | 1.70% |  | Load as NULL; impute in Week 2 if needed |
| joining_date | date format: DD-MM-YYYY | 327 | 16.35% | 25-08-2021 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| joining_date | date format: MM/DD/YYYY or DD/MM/YYYY | 657 | 32.85% | 22/10/2024 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| joining_date | date format: YYYY.MM.DD | 346 | 17.30% | 2022.11.13 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| joining_date | date format: YYYY-MM-DD | 329 | 16.45% | 2023-10-23 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| joining_date | date format: DD Mon YYYY | 341 | 17.05% | 19 Jul 2021 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| city | non-canonical city name | 128 | 6.40% | AHMEDABAD, BANGALORE, BENGALURU, BHUBANE | Map via city_aliases table during staging→producti |
| average_delivery_time | negative value | 27 | 1.35% | -35.7 | Keep and study; exclude via view in business queri |
| average_delivery_time | potential outlier (> p99=55 min) | 19 | 0.95% | p50=32 p75=38 p90=44 p99=55 max=64 | Log only; decide cap threshold after EDA in Week 2 |
| vehicle_type | category audit (4 distinct values) | 4 | 0.20% | Bike \| Scooter \| Bicycle \| Car | Use exact spellings in all SQL queries and dashboa |
| gender | category audit (2 distinct values) | 2 | 0.10% | Male \| Female | Use exact spellings in all SQL queries and dashboa |

### menu  (8,997 rows)
| Column | Issue | Count | % | Example | Fix |
|--------|-------|------:|---|---------|-----|
| food_name | extra whitespace | 155 | 1.72% | ' Cold Coffee  ' | TRIM() while loading to production |
| calories | null or blank | 132 | 1.47% |  | Load as NULL; impute in Week 2 if needed |
| price | negative value | 90 | 1.00% | -274 | Keep and study; exclude via view in business queri |
| availability | category audit (2 distinct values) | 2 | 0.02% | Yes \| No | Use exact spellings in all SQL queries and dashboa |

### order_items  (42,378 rows)
| Column | Issue | Count | % | Example | Fix |
|--------|-------|------:|---|---------|-----|
| total_price | null or blank | 435 | 1.03% |  | Load as NULL; impute in Week 2 if needed |
| quantity | negative value | 417 | 0.98% | -2 | Keep and study; exclude via view in business queri |

### orders  (20,705 rows)
| Column | Issue | Count | % | Example | Fix |
|--------|-------|------:|---|---------|-----|
| coupon_code | null or blank | 13,421 | 64.82% |  | Load as NULL; impute in Week 2 if needed |
| final_amount | null or blank | 327 | 1.58% |  | Load as NULL; impute in Week 2 if needed |
| (all columns) | duplicate full rows | 205 | 0.99% |  | ROW_NUMBER() OVER (PARTITION BY pk) = 1 keeps firs |
| order_id | duplicate primary key | 205 | 0.99% | 100146 | Keep row with fewest NULLs; discard others; log co |
| order_date | date format: DD-MM-YYYY | 4,187 | 20.22% | 22-06-2024 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| order_date | date format: MM/DD/YYYY or DD/MM/YYYY | 8,218 | 39.69% | 17/03/2024 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| order_date | date format: YYYY.MM.DD | 4,191 | 20.24% | 2023.06.17 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| order_date | date format: YYYY-MM-DD | 4,109 | 19.85% | 2023-05-09 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| delivery_time_minutes | negative value | 209 | 1.01% | -41 | Keep and study; exclude via view in business queri |
| food_cost | negative value | 182 | 0.88% | -292 | Keep and study; exclude via view in business queri |
| delivery_fee | zero value | 3,429 | 16.56% | 0 | Keep and study; flag in business queries; decide f |
| discount | zero value | 13,421 | 64.82% | 0 | Keep and study; flag in business queries; decide f |
| delivery_time_minutes | potential outlier (> p99=89 min) | 207 | 1.00% | p50=35 p75=43 p90=55 p99=89 max=399 | Log only; decide cap threshold after EDA in Week 2 |
| order_status | category audit (4 distinct values) | 4 | 0.02% | Delivered \| Cancelled \| Food Not Deliver | Use exact spellings in all SQL queries and dashboa |
| payment_method | category audit (6 distinct values) | 6 | 0.03% | Debit Card \| Net Banking \| Cash on Deliv | Use exact spellings in all SQL queries and dashboa |
| customer_id | orphaned FK → staging.customers(customer_id) | 12 | 0.06% | 12254 | Move orphan rows to quarantine table during stagin |
| restaurant_id | orphaned FK → staging.restaurants(restaurant_id) | 13 | 0.06% | 1317 | Move orphan rows to quarantine table during stagin |

### payments  (20,493 rows)
| Column | Issue | Count | % | Example | Fix |
|--------|-------|------:|---|---------|-----|
| transaction_id | null or blank | 183 | 0.89% |  | Load as NULL; impute in Week 2 if needed |
| payment_date | date format: DD-MM-YYYY | 4,169 | 20.34% | 23-01-2023 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| payment_date | date format: MM/DD/YYYY or DD/MM/YYYY | 8,163 | 39.83% | 01/01/2023 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| payment_date | date format: YYYY.MM.DD | 4,136 | 20.18% | 2023.12.06 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| payment_date | date format: YYYY-MM-DD | 4,025 | 19.64% | 2023-01-24 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| payment_method | category audit (6 distinct values) | 6 | 0.03% | Debit Card \| Net Banking \| Cash on Deliv | Use exact spellings in all SQL queries and dashboa |
| payment_status | category audit (4 distinct values) | 4 | 0.02% | Success \| Failed \| Refunded \| Pending | Use exact spellings in all SQL queries and dashboa |

### promotions  (300 rows)
| Column | Issue | Count | % | Example | Fix |
|--------|-------|------:|---|---------|-----|
| start_date | date format: DD-MM-YYYY | 61 | 20.33% | 12-11-2023 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| start_date | date format: MM/DD/YYYY or DD/MM/YYYY | 117 | 39.00% | 06/28/2023 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| start_date | date format: YYYY.MM.DD | 59 | 19.67% | 2024.03.26 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| start_date | date format: YYYY-MM-DD | 63 | 21.00% | 2024-02-13 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| end_date | date format: DD-MM-YYYY | 61 | 20.33% | 06-12-2023 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| end_date | date format: MM/DD/YYYY or DD/MM/YYYY | 118 | 39.33% | 07/31/2023 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| end_date | date format: YYYY.MM.DD | 51 | 17.00% | 2024.05.09 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| end_date | date format: YYYY-MM-DD | 70 | 23.33% | 2024-02-09 | parse_mixed_date() / parse_ddmmyyyy() while loadin |

### restaurants  (1,200 rows)
| Column | Issue | Count | % | Example | Fix |
|--------|-------|------:|---|---------|-----|
| restaurant_name | extra whitespace | 17 | 1.42% | ' Golden Hub  ' | TRIM() while loading to production |
| cuisine | null or blank | 12 | 1.00% |  | Load as NULL; impute in Week 2 if needed |
| city | extra whitespace | 37 | 3.08% | ' Patna  ' | TRIM() while loading to production |
| rating | null or blank | 22 | 1.83% |  | Load as NULL; impute in Week 2 if needed |
| city | non-canonical city name | 83 | 6.92% | AHMEDABAD, BANGALORE, BENGALURU, BHUBANE | Map via city_aliases table during staging→producti |
| average_cost | negative value | 15 | 1.25% | -355 | Keep and study; exclude via view in business queri |
| restaurant_type | category audit (5 distinct values) | 5 | 0.42% | Cloud Kitchen \| Dine-in \| Delivery Only  | Use exact spellings in all SQL queries and dashboa |
| cuisine | category audit (19 distinct values) | 19 | 1.58% | South Indian \| Fast Food \| Healthy Food  | Use exact spellings in all SQL queries and dashboa |

### traffic  (18,335 rows)
| Column | Issue | Count | % | Example | Fix |
|--------|-------|------:|---|---------|-----|
| traffic_level | null or blank | 147 | 0.80% |  | Load as NULL; impute in Week 2 if needed |
| date | date format: DD-MM-YYYY | 3,664 | 19.98% | 18-11-2023 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| date | date format: MM/DD/YYYY or DD/MM/YYYY | 7,240 | 39.49% | 01/09/2023 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| date | date format: YYYY.MM.DD | 3,793 | 20.69% | 2023.01.07 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| date | date format: YYYY-MM-DD | 3,638 | 19.84% | 2024-12-29 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| traffic_level | category audit (4 distinct values) | 4 | 0.02% | Moderate \| High \| Low \| Severe | Use exact spellings in all SQL queries and dashboa |

### weather  (18,264 rows)
| Column | Issue | Count | % | Example | Fix |
|--------|-------|------:|---|---------|-----|
| city | null or blank | 91 | 0.50% |  | Load as NULL; impute in Week 2 if needed |
| rainfall | null or blank | 269 | 1.47% |  | Load as NULL; impute in Week 2 if needed |
| date | date format: DD-MM-YYYY | 3,674 | 20.12% | 19-08-2024 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| date | date format: MM/DD/YYYY or DD/MM/YYYY | 7,337 | 40.17% | 12/28/2024 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| date | date format: YYYY.MM.DD | 3,645 | 19.96% | 2024.08.30 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| date | date format: YYYY-MM-DD | 3,608 | 19.75% | 2023-08-24 | parse_mixed_date() / parse_ddmmyyyy() while loadin |
| weather_condition | category audit (6 distinct values) | 6 | 0.03% | Clear \| Cloudy \| Humid \| Rainy \| Foggy | Use exact spellings in all SQL queries and dashboa |

---

## Data Quality Log Columns

The full machine-readable log is in `documentation/data_quality_log.csv`.  
Status values: `found` → `fixed in SQL` → `fixed in Python` → `verified`
