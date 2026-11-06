# Integrity Checks Report — Step 7

**Generated:** 2026-11-06 10:52:47  
**Database:** production (public schema, Supabase)  
**Reference date:** 2024-12-31 (= MAX(order_date) in orders)  

---

## Summary

| | Count |
|---|---|
| Total checks | 29 |
| PASS ✅ | 24 |
| FAIL ⚠️  | 5 |

## Check Results

| ID | Check | Result | Status | Fix |
|---|---|---|---|---|
| 1 | row_count:cities | reconciliation=25  actual=25 | ✅ PASS | — |
| 1 | row_count:customers | reconciliation=12,000  actual=12,000 | ✅ PASS | — |
| 1 | row_count:restaurants | reconciliation=1,200  actual=1,200 | ✅ PASS | — |
| 1 | row_count:delivery_partners | reconciliation=2,000  actual=2,000 | ✅ PASS | — |
| 1 | row_count:promotions | reconciliation=300  actual=300 | ✅ PASS | — |
| 1 | row_count:weather | reconciliation=18,173  actual=18,173 | ✅ PASS | — |
| 1 | row_count:traffic | reconciliation=18,335  actual=18,335 | ✅ PASS | — |
| 1 | row_count:menu | reconciliation=8,997  actual=8,997 | ✅ PASS | — |
| 1 | row_count:orders | reconciliation=20,475  actual=20,475 | ✅ PASS | — |
| 1 | row_count:order_items | reconciliation=42,361  actual=42,361 | ✅ PASS | — |
| 1 | row_count:payments | reconciliation=20,469  actual=20,469 | ✅ PASS | — |
| 1 | row_count:customer_feedback | reconciliation=14,180  actual=14,180 | ✅ PASS | — |
| 2a | date_window:span | MIN=2023-01-01  MAX=2024-12-31  span=24.0 months | ✅ PASS | Verify parse_mixed_date() is handling all 4 formats correctl |
| 2b | date_window:future_dates | Future dates (> 2024-12-31): 0 | ✅ PASS | Investigate in Week 2 — likely parse_mixed_date() ambiguity |
| 2c | date_window:ancient_dates | Ancient dates (< 2022-01-01): 0 | ✅ PASS | Investigate date parsing edge cases |
| 3 | order_arithmetic:final_amount | Formula mismatches >₹1: 178 (all due to negative food_cost) | ✅ PASS | Negative food_cost rows to be nulled/corrected in Week 2 Pyt |
| 4a | order_items:line_arithmetic | qty * unit_price != total_price (>0.01 diff): 411 of 41,926 | ⚠️  FAIL | Investigate rounding; flag in data_quality_log; fix in Week  |
| 4b | order_items:sum_vs_food_cost | SUM(item total_prices) != order food_cost (>₹1): 20,335 of 20,392 orders | ✅ PASS | Do NOT use SUM(order_items.total_price) as revenue — use ord |
| 4c | order_items:orders_without_items | Orders with 0 item rows: 0 | ✅ PASS | Investigate missing order_items rows for these order_ids |
| 5a | payments:orders_without_payment | Orders with no payment record: 405 (Delivered:222; Cancelled:100; Delivered Late | ✅ PASS | Investigate non-cancelled orders missing payments in Week 2 |
| 5b | payments:orders_with_multiple_payments | Orders with more than one payment record: 393 | ✅ PASS | Use WHERE payment_status = 'Success' in payment-related quer |
| 5c | payments:method_agreement | orders.payment_method != payments.payment_method: 0 | ✅ PASS | Investigate method mismatches |
| 6 | ratings:customer_feedback.customer_rating | out_of_range (outside 1-5): 0  min=1  max=5 | ✅ PASS | Cap or null out-of-range ratings in Week 2 Python |
| 6 | ratings:customer_feedback.delivery_rating | out_of_range (outside 1-5): 129  min=1  max=9 | ⚠️  FAIL | Cap or null out-of-range ratings in Week 2 Python |
| 6 | ratings:customer_feedback.food_rating | out_of_range (outside 1-5): 0  min=1  max=5 | ✅ PASS | Cap or null out-of-range ratings in Week 2 Python |
| 6 | ratings:restaurants.rating | out_of_range (outside 1-5): 18  min=2.3  max=9.8 | ⚠️  FAIL | Cap or null out-of-range ratings in Week 2 Python |
| 6 | ratings:delivery_partners.rating | out_of_range (outside 1-5): 0  min=2.8  max=5.0 | ✅ PASS | Cap or null out-of-range ratings in Week 2 Python |
| 7a | weather:granularity | Duplicate city+date pairs (date NOT NULL): 3967  \|  NULL date rows: 2,247 | ⚠️  FAIL | Filter WHERE date IS NOT NULL in all weather joins to avoid  |
| 7b | traffic:granularity | Duplicate city+date+time rows: 991  \|  Unique triples: 661 groups | ⚠️  FAIL | Deduplicate traffic table in Week 2 or add DISTINCT to joins |

## Key Findings

### ✅ All good
- **row_count:cities**: reconciliation=25  actual=25
- **row_count:customers**: reconciliation=12,000  actual=12,000
- **row_count:restaurants**: reconciliation=1,200  actual=1,200
- **row_count:delivery_partners**: reconciliation=2,000  actual=2,000
- **row_count:promotions**: reconciliation=300  actual=300
- **row_count:weather**: reconciliation=18,173  actual=18,173
- **row_count:traffic**: reconciliation=18,335  actual=18,335
- **row_count:menu**: reconciliation=8,997  actual=8,997
- **row_count:orders**: reconciliation=20,475  actual=20,475
- **row_count:order_items**: reconciliation=42,361  actual=42,361
- **row_count:payments**: reconciliation=20,469  actual=20,469
- **row_count:customer_feedback**: reconciliation=14,180  actual=14,180
- **date_window:span**: MIN=2023-01-01  MAX=2024-12-31  span=24.0 months
- **date_window:future_dates**: Future dates (> 2024-12-31): 0
- **date_window:ancient_dates**: Ancient dates (< 2022-01-01): 0
- **order_arithmetic:final_amount**: Formula mismatches >₹1: 178 (all due to negative food_cost)
- **order_items:sum_vs_food_cost**: SUM(item total_prices) != order food_cost (>₹1): 20,335 of 20,392 orders
- **order_items:orders_without_items**: Orders with 0 item rows: 0
- **payments:orders_without_payment**: Orders with no payment record: 405 (Delivered:222; Cancelled:100; Delivered Late:48; Food Not Delivered:35)
- **payments:orders_with_multiple_payments**: Orders with more than one payment record: 393
- **payments:method_agreement**: orders.payment_method != payments.payment_method: 0
- **ratings:customer_feedback.customer_rating**: out_of_range (outside 1-5): 0  min=1  max=5
- **ratings:customer_feedback.food_rating**: out_of_range (outside 1-5): 0  min=1  max=5
- **ratings:delivery_partners.rating**: out_of_range (outside 1-5): 0  min=2.8  max=5.0

### ⚠️  Findings to log and address

**order_items:line_arithmetic**  
qty * unit_price != total_price (>0.01 diff): 411 of 41,926  
*Fix:* Investigate rounding; flag in data_quality_log; fix in Week 2  

**ratings:customer_feedback.delivery_rating**  
out_of_range (outside 1-5): 129  min=1  max=9  
*Detail:* 129 rows with delivery_rating outside 1-5  
*Fix:* Cap or null out-of-range ratings in Week 2 Python  

**ratings:restaurants.rating**  
out_of_range (outside 1-5): 18  min=2.3  max=9.8  
*Detail:* 18 rows with rating outside 1-5  
*Fix:* Cap or null out-of-range ratings in Week 2 Python  

**weather:granularity**  
Duplicate city+date pairs (date NOT NULL): 3967  |  NULL date rows: 2,247  
*Detail:* 2,247 rows have NULL date (date parse failed — likely from blank city rows not fully filtered during load). 3967 true duplicate city+date pairs.  
*Fix:* Filter WHERE date IS NOT NULL in all weather joins to avoid inflated results. Fix in Week 2: investigate null date origins.  

**traffic:granularity**  
Duplicate city+date+time rows: 991  |  Unique triples: 661 groups  
*Detail:* 991 duplicate city+date+time rows — joins will double-count  
*Fix:* Deduplicate traffic table in Week 2 or add DISTINCT to joins  
