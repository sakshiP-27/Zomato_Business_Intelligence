# Week 2 Checkpoint Self-Review

**Date:** Week 2, Day 10  
**Pipeline entry point:** `python src/run_pipeline.py`

---

## The Six Questions

**1. Can she delete `data/cleaned/` and rebuild everything with one command?**

Yes.

```bash
rm -rf data/cleaned
python src/run_pipeline.py
```

Runs in ~3.5 seconds. Produces 12 cleaned CSVs, `analytical_base_table.csv`,
`customer_features.csv`, `cleaning_log.csv`, and 4 quarantine files.
Also run `python src/validate.py` to regenerate `validation_report.md`.

---

**2. Does the base table have one row per order?**

Yes. `analytical_base_table.csv` has **20,475 rows** and 85 columns.
Every merge uses `validate="m:1"` with a row-count assertion after each join.
All 10 assertions pass.

---

**3. Is the target column untouched by imputation?**

Yes. `delivery_time_minutes` is never imputed:
- Values ≤0 are set to NaN (and logged)
- NaN rows are kept in the ABT for completeness
- They are excluded from model training in Week 3 via `WHERE delivery_time_minutes > 0`
- 207 nulls remain (1.0% of orders)

---

**4. Are feedback ratings kept out of the delivery-time feature list?**

Yes. `feedback_customer_rating`, `feedback_delivery_rating`, `feedback_food_rating`,
and `average_rating` are in the ABT but clearly marked as post-delivery fields.
They must not be used as inputs for the delivery-time prediction model.
They are available for EDA and Power BI dashboards.

---

**5. Does every difference between Python and SQL have an explanation?**

Yes. `src/validate.py` runs 15 checks — all pass (100% match).
`documentation/validation_report.md` documents each check and explains why
Python-only enrichments (age imputation, rating cap, validity flags) do not
create disagreements — they are additive, not contradictory.

---

**6. Is the distance limitation written down?**

Yes.
- `documentation/kpi_definitions.md` — distance proxy section
- `documentation/validation_report.md` — "Distance Limitation" section
- `notebooks/03_feature_engineering.ipynb` — Cell 11
- `src/features.py` — docstring of `add_features()`

`customers.csv` has no latitude/longitude. The proxy used is:
`distance_to_city_centre_km` = haversine distance from the restaurant
to the mean lat/lon of all restaurants in that city.

---

## Deliverables Checklist

| Item | Status |
|---|---|
| Loader: `load_raw()` + `load_all()` in `src/ingest.py` | ✅ |
| `CleaningLog` + `DataCleaner` with all 12 methods in `src/clean.py` | ✅ |
| City names canonical in all 5 tables | ✅ |
| Category spellings match SQL exactly (8 columns) | ✅ |
| Mixed dates parsed (5 formats); all date cols are datetime64 | ✅ |
| Phone repaired (133) → invalid → NaN; `phone_valid` flag | ✅ |
| Pincode invalid → NaN; `pincode_valid` flag | ✅ |
| Email invalid → NaN; `email_valid` flag | ✅ |
| Missing value strategy for every PRD-flagged column | ✅ |
| delivery_time_minutes NOT imputed | ✅ |
| Negative values handled (food_cost, delivery_time, delivery_fee, avg_delivery_time) | ✅ |
| `dt_outlier_flag` added (IQR k=3.0, flagged not capped) | ✅ |
| Duplicates removed: customers 180, orders 205 (same rule as SQL) | ✅ |
| Orphans quarantined: 25 orders + 17 OI + 24 payments + 20 feedback | ✅ |
| `python src/run_pipeline.py` → 12 cleaned CSVs + ABT + log in 3.5s | ✅ |
| ABT: one row per order, 85 cols, all 10 merges asserted | ✅ |
| 11 PRD features + 4 extras engineered | ✅ |
| `build_customer_features(orders, as_of)` with cut-off date | ✅ |
| `customer_features.csv` (8,252 rows, 8 cols) | ✅ |
| SQL vs Python validation: 15/15 checks pass | ✅ |
| Data Cleaning Completeness: **100%** (target ≥ 95%) | ✅ |
| `documentation/validation_report.md` | ✅ |
| `documentation/cleaning_log.csv` (28 entries) | ✅ |
| `documentation/data_quality_log.csv` — all statuses updated | ✅ |
| `notebooks/01_data_cleaning.ipynb` | ✅ |
| `notebooks/03_feature_engineering.ipynb` | ✅ |
| No hard-coded passwords; all use `.env` | ✅ |
| All functions have docstrings | ✅ |
| `requirements.txt` covers all dependencies | ✅ |
