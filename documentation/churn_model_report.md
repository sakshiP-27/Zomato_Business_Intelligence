# Churn Classification Model Report — Week 3

**Generated:** 2026-11-07 23:16  
**Target:** `churned` (1 = no order in 60 days after cutoff)  
**KPI target:** F1 ≥ 0.7  

---

## Dataset Design

| | |
|---|---|
| Feature window | all orders on or before 2024-11-01 |
| Label window | 2024-11-01 → 2024-12-31 |
| Train customers | 6,773 |
| Test customers | 1,694 |
| Churn rate | 87.4% |
| Naive baseline F1 (predict all churn) | 0.9326 |

**Design decisions:**
- Cutoff = MAX(order_date) − 60 days = `2024-11-01`
- Label = 1 if customer placed NO order in the following 60 days
- Any order status counts as 'activity' for the label
- `customers.total_orders` excluded — it is a snapshot over the whole period
- Past feedback ratings ARE used — they occurred before the cutoff

## Class Imbalance Handling

Churn rate is 87.4% — highly imbalanced.  
Strategy used: `class_weight='balanced'` on all classifiers.  
This makes errors on the minority class (non-churners) cost proportionally more.  
SMOTE was not used to avoid introducing synthetic samples in a one-hot encoded space.  

## Cross-Validation Comparison (training set, 5-fold stratified)

| Model | CV F1 | CV Precision | CV Recall | CV ROC-AUC | CV PR-AUC |
|---|---|---|---|---|---|
| Baseline (predict majority) | 0.9327 | 0.8739 | 1.0 | 0.5 | 0.8739 |
| Random Forest | 0.9321 | 0.8739 | 0.9986 | 0.4916 | 0.871 |
| Gradient Boosting | 0.8712 | 0.8745 | 0.8681 | 0.5029 | 0.8721 |
| Logistic Regression | 0.6843 | 0.8798 | 0.5602 | 0.5131 | 0.8738 |
| Decision Tree | 0.5961 | 0.8725 | 0.4654 | 0.5106 | 0.8767 |

## Hyperparameter Tuning

### Random Forest

- Before: CV F1 = 0.9321
- After:  CV F1 = 0.9313
- Best params: `{'model__n_estimators': 100, 'model__min_samples_leaf': 1, 'model__max_features': 'sqrt', 'model__max_depth': None}`

### Gradient Boosting

- Before: CV F1 = 0.8712
- After:  CV F1 = 0.8958
- Best params: `{'model__min_samples_leaf': 30, 'model__max_iter': 300, 'model__max_depth': 7, 'model__learning_rate': 0.1, 'model__l2_regularization': 0.1}`


## Test Set Results

**Winner: Random Forest**  
**Decision threshold: 0.420** (F1-maximising, chosen on OOF predictions)  

| Metric | Value | Baseline (predict all churn) | KPI | Status |
|---|---|---|---|---|
| F1 | 0.9326 | 0.9326 | ≥0.7 | ✅ PASS |
| Precision | 0.8737 | — | — | — |
| Recall | 1.0 | — | — | — |
| ROC-AUC | 0.5207 | 0.50 (random) | — | ⚠️ |
| PR-AUC | 0.8746 | 0.8739 (naive) | — | — |
| Accuracy | 0.8737 | 0.8739 | — | — |

## Interpretation

The churn rate is 87.4% — the majority of customers placed only 1–2 orders.  
The naive baseline (predict everyone churns) already achieves F1=0.9326.  

The model achieves F1=0.9326 vs baseline F1=0.9326.
ROC-AUC=0.5207 (above 0.5=random, below 0.95=no suspicious leakage).  

**In plain English:** the model's precision and recall trade-off is tuned at the  
F1-maximising threshold (0.42). Of every 100 customers the model  
flags as high-risk, approximately 87 have actually churned.  
It catches approximately 100% of customers who will churn.  

**Key churn drivers** (from permutation importance):
- `tenure_days`: importance = 0.0245
- `customer_lifetime_value`: importance = 0.0165
- `average_basket_value`: importance = 0.0117
- `customer_gender`: importance = 0.0111
- `days_since_last_order`: importance = 0.0100

**Recommendations:** only act on a risk segment if `src/churn_analysis.py` shows its actual  
churn rate differs from the other segments (`data/cleaned/ml_churn_segment_check.csv`).  

## Steps 11-13 Addendum (computed by src/churn_analysis.py)

**Imbalance experiment (training CV, `data/cleaned/ml_churn_imbalance_experiment.csv`):**

| Model | Option | F1 | ROC-AUC | PR-AUC |
|---|---|---|---|---|
| Logistic Regression | (a) no handling | 0.9327 | 0.5156 | 0.8746 |
| Logistic Regression | (b) class_weight=balanced | 0.6843 | 0.5131 | 0.8738 |
| Random Forest | (a) no handling | 0.9327 | 0.499 | 0.8723 |
| Random Forest | (b) class_weight=balanced | 0.932 | 0.4884 | 0.8699 |

Accuracy would mislead here: predicting churn for everyone is 87.4% accurate. `class_weight=balanced` is the documented default.

**Threshold in plain words:** the F1-maximising threshold (0.420) flags 1694 of 1694 test customers (100.0%); of those, 87.4% actually churned, against an overall churn rate of 87.4%.

**Risk segments:** band edges are terciles of the training out-of-fold probabilities (Low < 0.720, Medium 0.720-0.790, High >= 0.790). Actual churn rate per segment on the test set: Low 86.8%, Medium 87.1%, High 88.5%. The segments do not separate churners, so they should not be used to target offers.

**Drivers:** 2 of 20 features have permutation importance clearly above noise (tenure_days, customer_lifetime_value); measured directions are in `ml_churn_feature_importance.csv`.

**Conclusion:** test ROC-AUC is 0.52. The churn label is not predictable from the available features in this dataset; the F1 KPI is met only because most customers churn, and no retention recommendation is supported.

## Saved Artefacts

- `models/churn_model.joblib`
- `data/cleaned/ml_model_comparison_churn.csv`
- `data/cleaned/churn_scores.csv`
- `data/cleaned/churn_scores_current.csv` (forward-looking, no ground truth)
- `images/churn_confusion_matrix.png`
- `images/churn_roc_curve.png`
- `images/churn_pr_curve.png`
- `images/churn_feature_importance.png`
