# Zomato Business Insights Report

**Author:** Sakshi  
**Date:** 8 November 2026  
**Data:** 1 January 2023 to 31 December 2024, 20,475 cleaned orders, 25 cities  
**Sources:** `documentation/kpi_definitions.md`, `reports/eda_report.md`, the Week 3 model reports, and `data/cleaned/`

---

## 1. Executive summary

The pipeline is consistent. Python and SQL agree on row counts, revenue, and all 25 cities, and 100% of the logged data-quality issues are resolved. The business picture is less flattering than a forecasting project usually hopes.

Completed-order revenue (Delivered and Delivered Late, positive amount) is **₹52.36 lakh**. Another **₹44.06 lakh** of that is status Delivered only. Monthly delivered revenue barely moves: ₹1.60–2.06 lakh, and 2024 is **+0.4%** versus 2023. **22.3%** of orders are cancelled. There is no cancellation-reason column.

Delivery time on completed orders averages **40.1 minutes**. The 90th percentile is **61 minutes**. **24.9%** of those orders take longer than 45 minutes. The delivery model does not beat predicting the average: test **R² = −0.0022**, **RMSE = 9.774 minutes**. The targets were R² ≥ 0.75 and RMSE ≤ 6. City, traffic, rain, and hour do not show a reliable difference.

**87.4%** of customers place no order in the 60 days after 1 November 2024. The churn model’s test F1 is **0.9326**, the same as predicting that everyone churns. ROC-AUC is **0.514**. The risk bands all sit between about 86% and 89% actual churn.

**Do these three things. Do not do the other two.**

1. Review the restaurants at the bottom of `v_restaurant_performance`, starting with high cancellation, not with a city-wide staffing plan.
2. Treat 22% cancellation as the operational problem. The data cannot say why.
3. Do not buy a win-back campaign off the churn scores, and do not add riders for rain or the 7 pm peak based on this model.

---

## 2. City Operations Head — what predicts a late delivery?

**Finding:** On completed orders with a positive delivery time, the mean is 40.1 minutes and 24.9% exceed 45 minutes (Week 1 rule, `is_late` on the analytical base table). The test-set delivery model explains none of the variation (R² −0.0022, RMSE 9.8 minutes; `documentation/delivery_model_report.md`). EDA group tests for city, traffic, and weather are not significant. Traffic itself matched only 5.1% of valid deliveries.

**Implication:** A late-delivery rate near one in four is real. This dataset does not say which lever moves it. Peak hour is 19:00 and that window holds 22.2% of orders, but the late rate at peak (12.3% on the EDA delivered subset) is not distinguishable from off-peak (12.1%).

**Recommended action:** Do not move extra partners onto rainy dinner hours from this analysis. Keep the 45-minute definition, watch `Late Delivery %` on the Delivery page after the next data refresh, and only staff a city differently when a later extract shows a difference that survives a simple test.

**How to measure success:** Late delivery % on completed orders, by city and month, moving for a reason you can name. A flat line is an acceptable result.

**Confidence / caveat:** Association was tested and not found. The restaurant coordinates are not usable as distance (median about 950 km from the city’s own centre). One 24-month snapshot.

---

## 3. Restaurant Partnerships Manager — who is underperforming?

**Finding:** `v_restaurant_performance` scores restaurants with at least 10 orders inside their own city: rating 40%, cancellation 30%, speed 30%. The lowest scores on the export are Royal Grill in Delhi (0.054, cancellation 37.5%, 16 orders, ₹3,331) and Royal Kitchen in Visakhapatnam (0.084, cancellation 40%, 20 orders). Green Corner in Chandigarh is at the other end (0.988, cancellation 9.1%).

**Implication:** The weak scores are mostly cancellations, not a slow-delivery story the model can explain. Several low-score restaurants also have no rating. Ranks with 15–20 orders will move around.

**Recommended action:** Partnerships reviews the bottom of the score list city by city, confirms the cancellation count on those restaurant IDs, and asks the restaurant for an operational reason. Do not delist anyone on the score alone.

**How to measure success:** Cancellation rate and the composite score for that restaurant on the next refresh, after at least another month of orders.

**Confidence / caveat:** The score is a design choice, not a measured cause. It does not respond to the dashboard date slicer because it was calculated once for the full period. Missing ratings were a conservative input to the rank.

---

## 4. Growth Marketing Lead — who will churn in 60 days?

**Finding:** Using orders on or before 1 November 2024, 87.4% of customers place no order in the following 60 days (`documentation/churn_model_report.md`). Test F1 0.9326 equals the baseline that flags everyone. ROC-AUC is 0.514. On the 1,694 test customers the risk bands do not separate: Low 87.5% actually churned, Medium 85.9%, High 89.1%. The largest permutation importance changes ROC-AUC by under 0.02, and the direction is “no meaningful difference.”

**Implication:** Almost everyone looks like a churner because most customers already order rarely (mean 1.80 non-cancelled orders; 47.9% order once). A model that matches “flag all” is not a target list.

**Recommended action:** Do not email the High band. If marketing spends anything, spend it on the 479 customers labelled Repeat on `dim_customers_enriched.csv` (ordered in the last 30 days, and not new). Measure whether they order again. Leave the 7,979 At-risk customers out of a paid campaign until a model beats the baseline.

**How to measure success:** Repeat purchase rate among the contacted Repeat segment, versus a holdout that is not contacted. F1 is the wrong success metric here.

**Confidence / caveat:** The 60-day label matches the active-customer window. The dashboard segment At-risk starts at 30 days of silence, which is earlier than churn. Segments are as of 31 December 2024 and do not follow the date slicer.

---

## 5. Finance Analyst — city revenue

**Finding:** Delivered-only revenue is ₹44.06 lakh. Kolkata is the largest city at ₹2.02 lakh; the top three cities are 14% of delivered revenue; the largest city is 1.57 times the smallest (Nagpur). South Indian is the largest cuisine at ₹3.07 lakh, 34% above the tenth cuisine. The last six months average +1.6% versus the first six. 2024 is +0.4% versus 2023. Completed-order revenue including Delivered Late is ₹52.36 lakh across 13,351 orders, about ₹392 per order.

**Implication:** There is no growth story and no collapse. City mix is wide but not a one-city business. Payment methods are almost even (about 16–17% each). Failed payments are 1,655 of 20,469 (8.1%).

**How to measure success:** Monthly completed revenue by city on the Sales page, next to the SQL view `v_monthly_revenue_by_city`. A gap between those two numbers is a bug.

**Recommended action:** Plan next quarter off the flat trend. Investigate failed payments as a cash-collection issue, not as a demand issue. Do not reallocate budget toward a “fastest growing city”; the series does not support one.

**Confidence / caveat:** 3,222 orders have ambiguous slash dates and were read as month/day. That can move a day across a month boundary. It does not create a trend that is not there, but a single month’s rank can be slightly off.

---

## 6. Limitations

- No cancellation reason, so cancellation findings are patterns.
- No usable distance. Customer coordinates do not exist, and restaurant coordinates do not sit in their cities.
- Traffic is missing for most orders. Weather is missing for about 38% of valid deliveries.
- Both models were trained on this fixed snapshot. They are not a production scoring service.
- The churn label is harsh because ordering is infrequent. A 60-day silence is the rule we chose, and it makes “churn” the normal state.
- Dashboard scores for restaurants and the customer segments are point-in-time. They will not change when someone moves the date slicer.
- Power BI numbers below were computed with the same rules as the DAX. They have not yet been read back from a refreshed Desktop file. That check is still open.

## 7. KPI reconciliation (no slicers)

These are the Python figures the DAX is written to match. SQL matched Python on revenue, row counts, and cities in `documentation/validation_report.md`.

| KPI | Python (DAX rule) | SQL | Match |
|---|---:|---:|---|
| Completed revenue (Delivered + Delivered Late, amount > 0) | ₹52,36,335.60 | Same rule in Week 1; Delivered-only ₹44,06,359.55 matched SQL exactly | Delivered-only matched; combined figure follows the KPI doc |
| Delivered-only revenue | ₹44,06,359.55 | ₹44,06,359.55 | Yes |
| Delivered Late revenue | ₹8,29,976.05 | ₹8,29,976.05 | Yes |
| Total orders | 20,475 | 20,475 | Yes |
| Cancellation rate | 22.3% (4,569 / 20,475) | 4,569 cancelled | Yes |
| Avg delivery time, completed and time > 0 | 40.1 min | Week 1 distribution mean 40.1 min | Yes |
| Late, completed and time > 0 | 24.9% | Week 1 threshold is the 75th percentile, 45 min | Consistent with the rule |
| Late, `is_late` over every usable time | 20.7% (4,187 / 20,268) | Not a separate SQL KPI; this is the dashboard card | By construction of the column |
| Active customers, order after 2024-11-01 | 1,550 | Same date rule | Recompute in SQL when the dashboard is open |
| Registered customers | 12,000 | 12,000 | Yes |

Two cities: Kolkata is the delivered-revenue leader at ₹2.02 lakh in both SQL and Python. All 25 restaurant cities match on order counts. One month: there is no month with a break in the series; the range is ₹1.60–2.06 lakh of delivered revenue.
