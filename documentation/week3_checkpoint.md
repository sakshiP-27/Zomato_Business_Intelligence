# Week 3 Checkpoint Self-Review

**Date:** Week 3, Day 15  
**Author:** Sakshi

---

## The Seven Questions

**1. Does every one of the 8 business questions have charts plus written takeaways, and does the register show 15+ and 15+?**

Yes.

- Matplotlib: **18 charts**, Seaborn: **20 charts**, total **38** (requirement 15 + 15)
- Every question has at least 2 charts: {'Q1': 5, 'Q2': 2, 'Q3': 12, 'Q4': 4, 'Q5': 2, 'Q6': 2, 'Q7': 9, 'Q8': 2}
- Takeaways are generated from computed statistics with significance tests (`src/eda_takeaways.py`);
  `save_fig()` refuses a chart that has no computed takeaway
- Register: `documentation/eda_chart_register.csv`
- Report: `reports/eda_report.pdf` (also `.md` and self-contained `.html`), built from the register

Corrected in this revision: five hand-written takeaways contradicted the data (traffic, stormy weather,
Cash on Delivery, membership cancellations, membership spend) and were replaced; the Q5 and Q6 charts were
mislabelled (status and payment charts) and two real Q5 charts were added; the partner chart was empty
(it filtered for partners with 50+ deliveries, the maximum is 17) and now uses 10+; two duplicate charts
were replaced.

---

**2. Did I use the test set only once for each model?**

Yes.

- Delivery model: split was `random_state=42`, preprocessing fitted only on training data, `evaluate()` called exactly once on `X_test`.
- Churn model: stratified split, threshold found from **out-of-fold predictions on training data** (not test set), `evaluate_classifier()` called exactly once.

---

**3. Are post-delivery fields (feedback ratings) excluded from the delivery-time model?**

Yes. The `EXCLUDED` dictionary in `src/model_delivery.py` lists:
- `feedback_customer_rating` — post-delivery, unknown at order time
- `feedback_delivery_rating` — post-delivery
- `feedback_food_rating` — post-delivery
- `average_rating` — post-delivery
- `sentiment`, `review` — post-delivery

These are present in the ABT for EDA and Power BI but are explicitly excluded from `NUMERIC + CATEGORICAL`.

---

**4. Are churn features built only from data on or before the cutoff?**

Yes. `build_churn_dataset()` in `src/model_churn.py`:
- Calls `build_customer_features(orders, as_of=cutoff)` — the Week 2 function that filters `order_date <= cutoff`
- Recent activity windows use `order_date > (cutoff - N days) AND order_date <= cutoff`
- Experience features aggregate `hist = orders[orders["order_date"] <= cutoff]`
- Past feedback ratings are used (legitimate — they occurred before the cutoff)
- `customers.total_orders` is NOT used (snapshot over whole period, includes future)
- The label looks only at `order_date > cutoff AND order_date <= cutoff + 60 days`

---

**5. Did I compare both models against a simple baseline?**

Yes.

| Model | Metric | Model | Baseline | Better? |
|---|---|---|---|---|
| Delivery (Random Forest) | RMSE | 9.77 min | predict the mean | No (CV RMSE equals the baseline) |
| Delivery (Random Forest) | R² | -0.002 | 0.000 | No |
| Churn (Random Forest) | F1 | 0.9326 | 0.9326 (everyone churns) | No (equal) |
| Churn (Random Forest) | ROC-AUC | 0.521 | 0.500 (random) | No meaningful gain |

---

**6. Did I state honestly whether R² ≥ 0.75, RMSE ≤ 6 min, and F1 ≥ 0.70 were met?**

Yes.

| KPI | Target | Actual | Met? | Explanation |
|---|---|---|---|---|
| Delivery R² | ≥ 0.75 | -0.002 | ⚠️ No | No feature has \|r\| above 0.05 with delivery time in this dataset. |
| Delivery RMSE | ≤ 6 min | 9.8 min | ⚠️ No | Same root cause. Meeting it needs data in which delivery time depends on the features. |
| Churn F1 | ≥ 0.70 | 0.9326 | ✅ Technically | Equals the naive baseline because 87.4% of customers churn. ROC-AUC 0.52 shows no real skill. |

---

**7. Are there plain-language explanations of the feature importances for both models?**

Yes, and they state what the data shows.

**Delivery model:** permutation importances are tiny and almost all within noise (see the table in
`documentation/delivery_model_report.md`). No feature can be named as a driver; no operational
recommendation is made.

**Churn model:** drivers are within noise and churners look like active customers (for example
`days_since_last_order` 270 vs 268 days). Risk segments do not separate churners
(actual churn 86.8% / 87.1% / 88.5% across Low / Medium / High). No retention recommendation is supported.

---

## Deliverables Checklist

### EDA
| Item | Status |
|---|---|
| EDA notebook (`02_eda.ipynb`) with chart register | ✅ |
| 18 Matplotlib charts (bar, line, scatter, histogram, pie, stacked bar, area, box) | ✅ |
| 20 Seaborn charts (heatmap, pairplot, countplot, violin, strip, boxplot, regplot, KDE) | ✅ |
| All 8 questions answered with title + labels + units + takeaway | ✅ |
| Pairplot on seeded sample (n=1000); cross-checks against SQL | ✅ |
| EDA report (`reports/eda_report.pdf`, plus `.md` and `.html`) | ✅ |

### Delivery time regression
| Item | Status |
|---|---|
| Model dataset: Delivered + dt>0 + outlier flag=0; no post-delivery features | ✅ |
| 80/20 split before preprocessing; Pipeline with imputation + scaling + one-hot | ✅ |
| Baseline + 4 models CV-compared; top 2 tuned with RandomizedSearchCV | ✅ |
| Test MAE/MSE/RMSE/R² reported once; KPI comparison honest | ✅ |
| Residuals plot + actual vs predicted + residual histogram | ✅ |
| Feature importance + plain-language explanation | ✅ |
| Notebook (`04_delivery_time_model.ipynb`) runs top-to-bottom | ✅ |

### Churn classification
| Item | Status |
|---|---|
| Cutoff chosen; features before it, label after it; rules written | ✅ |
| Churn rate (87.4%) and naive baseline F1 (0.9326) recorded | ✅ |
| Stratified split by customer; `class_weight="balanced"` on all classifiers | ✅ |
| 4 classifiers + baseline CV-compared; top 2 tuned | ✅ |
| Threshold chosen from OOF predictions (training set only) | ✅ |
| Confusion matrix, ROC curve, PR curve | ✅ |
| Top-10 drivers with measured direction and noise flag (no recommendation supported) | ✅ |
| Risk segments (Low/Medium/High) + current forward-looking scores | ✅ |
| Notebook (`05_churn_model.ipynb`) runs top-to-bottom | ✅ |

### Wrap-up
| Item | Status |
|---|---|
| Both models saved as `.pkl` + `model_metadata.json` | ✅ |
| Reload tested in fresh session (5 predictions each) | ✅ |
| 6 Power BI export CSVs with stable filenames | ✅ |
| `src/model_delivery.py` and `src/model_churn.py` documented with docstrings | ✅ |
| All random steps use `random_state=42` | ✅ |
| `requirements.txt` updated | ✅ |

---

## Files Summary

| Path | Purpose |
|---|---|
| `notebooks/02_eda.ipynb` | EDA — 38 charts, 8 questions |
| `notebooks/04_delivery_time_model.ipynb` | Delivery model notebook |
| `notebooks/05_churn_model.ipynb` | Churn model notebook |
| `models/delivery_time_best_model.pkl` | Delivery model (Random Forest, 1.3 MB) |
| `models/churn_best_model.pkl` | Churn model (Random Forest, 16 MB) |
| `models/model_metadata.json` | Versions, thresholds, KPI results |
| `data/cleaned/ml_delivery_predictions.csv` | Test set predictions for Power BI |
| `data/cleaned/ml_delivery_feature_importance.csv` | Feature importances for Power BI |
| `data/cleaned/ml_model_comparison_delivery.csv` | CV comparison table |
| `data/cleaned/ml_churn_scores_test.csv` | Churn scores + risk segments |
| `data/cleaned/ml_churn_feature_importance.csv` | Churn drivers for Power BI |
| `data/cleaned/ml_model_comparison_churn.csv` | CV comparison table |
| `reports/eda_report.pdf` | EDA report (PDF, also .md and .html) |
| `documentation/delivery_model_report.md` | Delivery model report |
| `documentation/churn_model_report.md` | Churn model report |

---

## Fixed in this revision: date parsing (Weeks 1-3 rebuilt)

Raw dates written with `/` mix DD/MM and MM/DD. Both parsers (`parse_mixed_date()` in `sql/schema.sql`
and `parse_mixed_dates()` / `parse_ddmmyyyy_dates()` in `src/clean.py`) now read a part above 12 as the
day. Previously 2,430 orders (11.9%) and 2,247 weather rows had no date; now none do. 3,222 orders with
both parts at 12 or under remain ambiguous and are read as MM/DD (logged in `cleaning_log.csv`).
Weeks 1-3 were re-run from scratch; Python and SQL still match on all 15 validation checks.

The broken distance feature (restaurants sit a median ~950 km from their own city's centre) was removed
from the delivery model.
