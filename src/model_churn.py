"""
src/model_churn.py
------------------
Week 3, Steps 10–13: Customer churn classification model.

Predicts whether a customer will place no order in the 60 days after
a cut-off date — built strictly in time order to prevent leakage.

Key design rules:
  • Features use only orders ON OR BEFORE the cut-off date.
  • The churn label looks at the 60 days AFTER the cut-off date.
  • do_not_use list excludes any feature derived from post-cutoff data.
  • Train/test split is by customer, stratified by churn label.
  • Test set is opened exactly once.

Usage:
    python src/model_churn.py

Outputs:
    models/churn_model.joblib
    data/cleaned/ml_model_comparison_churn.csv
    data/cleaned/churn_scores.csv
    data/cleaned/churn_scores_current.csv     (forward-looking, no ground truth)
    documentation/churn_model_report.md
    images/churn_confusion_matrix.png
    images/churn_roc_curve.png
    images/churn_feature_importance.png
    images/churn_pr_curve.png
"""

import os
import sys
import warnings
import numpy as np
import pandas as pd
import joblib
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime

from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.model_selection import (
    train_test_split, StratifiedKFold, cross_validate,
    RandomizedSearchCV, cross_val_predict,
)
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, average_precision_score,
    confusion_matrix, ConfusionMatrixDisplay, RocCurveDisplay,
    precision_recall_curve,
)
from sklearn.inspection import permutation_importance

warnings.filterwarnings("ignore")

ROOT      = Path(__file__).resolve().parent.parent
CLEAN_DIR = ROOT / "data"  / "cleaned"
MODEL_DIR = ROOT / "models"
DOC_DIR   = ROOT / "documentation"
IMG_DIR   = ROOT / "images"

# Ensure project root is on sys.path for imports
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Feature lists
# ---------------------------------------------------------------------------

CHURN_NUMERIC: list[str] = [
    # RFM — the standard churn features (recency, frequency, monetary)
    "days_since_last_order",      # Recency: days since last delivered order as of cutoff
    "orders_to_date",             # Frequency: total delivered orders up to cutoff
    "customer_lifetime_value",    # Monetary: total spend up to cutoff
    "average_basket_value",       # Average per-order spend
    "order_frequency_30d",        # Orders per 30-day window (derived from span)
    # Recent activity windows (computed inside build_churn_dataset)
    "orders_last_30d",            # Orders in last 30 days before cutoff
    "orders_last_60d",            # Orders in last 60 days before cutoff
    "orders_last_90d",            # Orders in last 90 days before cutoff
    # Experience metrics up to cutoff
    "cancel_rate",                # Fraction of orders that were cancelled
    "late_rate",                  # Fraction of delivered orders that were late (>45 min)
    "avg_delivery_time",          # Average delivery time on completed orders
    "coupon_rate",                # Fraction of orders with a coupon
    "avg_rating_given",           # Average rating given by the customer (past only)
    "n_restaurants",              # Number of distinct restaurants ordered from
    # Customer attributes (static, no leakage)
    "customer_age",               # Age at cutoff
    "tenure_days",                # Days from registration to cutoff
]

CHURN_CATEGORICAL: list[str] = [
    "membership",                 # Basic, Gold, Zomato Pro
    "customer_city",              # 25 cities
    "preferred_cuisine",          # Customer's stated preferred cuisine
    "customer_gender",            # Female, Male, Other
]

# Label
TARGET = "churned"

# KPI targets
KPI_F1      = 0.70
HORIZON     = 60   # days after cutoff that define "churned"

# ---------------------------------------------------------------------------
# Step 10: Build the churn dataset in time order
# ---------------------------------------------------------------------------

def build_churn_dataset(
    orders: pd.DataFrame,
    customers: pd.DataFrame,
    cutoff: pd.Timestamp,
    horizon_days: int = HORIZON,
) -> pd.DataFrame:
    """
    Build one row per customer with features from orders ≤ cutoff
    and a churn label based on the next horizon_days.

    Design decisions (documented per guide requirement):
      • Feature window: orders ON OR BEFORE cutoff.
      • Label: 1 if customer placed ZERO orders in (cutoff, cutoff + horizon_days],
               0 if they placed at least one.
      • 'Any order' counts — not just delivered — consistent with PRD
        definition of activity.
      • customers.total_orders is NOT used (snapshot includes future data).
      • Past feedback ratings ARE used for experience features — they occurred
        before the cutoff.

    Args:
        orders:       Cleaned orders DataFrame.
        customers:    Cleaned customers DataFrame.
        cutoff:       Feature/label boundary date.
        horizon_days: Days after cutoff that define the churn window.

    Returns:
        DataFrame with one row per customer who had ≥1 order before cutoff.
    """
    # Compute RFM features using only pre-cutoff history
    from src.features import build_customer_features
    feats = build_customer_features(orders, as_of=cutoff)

    # Churn label
    window_end = cutoff + pd.Timedelta(days=horizon_days)
    future_customers = set(
        orders.loc[
            (orders["order_date"] > cutoff) &
            (orders["order_date"] <= window_end),
            "customer_id",
        ]
    )
    feats["churned"] = (~feats["customer_id"].isin(future_customers)).astype(int)

    # Recent activity windows
    feats = add_recent_activity(feats, orders, cutoff)

    # Experience metrics
    feats = add_experience_features(feats, orders, cutoff)

    # Customer attributes (static, no leakage)
    cust_attrs = customers[
        ["customer_id", "age", "membership", "city",
         "preferred_cuisine", "gender", "registration_date"]
    ].copy()
    cust_attrs["registration_date"] = pd.to_datetime(cust_attrs["registration_date"], errors="coerce")
    cust_attrs["tenure_days"] = (cutoff - cust_attrs["registration_date"]).dt.days

    feats = feats.merge(
        cust_attrs.rename(columns={
            "age": "customer_age",
            "city": "customer_city",
            "gender": "customer_gender",
        })[["customer_id", "customer_age", "membership", "customer_city",
            "preferred_cuisine", "customer_gender", "tenure_days"]],
        on="customer_id", how="left",
    )

    return feats


def add_recent_activity(
    feats: pd.DataFrame,
    orders: pd.DataFrame,
    cutoff: pd.Timestamp,
) -> pd.DataFrame:
    """Count orders in the last 30/60/90 days before cutoff (any status)."""
    for days in (30, 60, 90):
        window_start = cutoff - pd.Timedelta(days=days)
        recent = orders[
            (orders["order_date"] > window_start) &
            (orders["order_date"] <= cutoff)
        ]
        counts = recent.groupby("customer_id").size()
        feats[f"orders_last_{days}d"] = (
            feats["customer_id"].map(counts).fillna(0).astype(int)
        )
    return feats


def add_experience_features(
    feats: pd.DataFrame,
    orders: pd.DataFrame,
    cutoff: pd.Timestamp,
) -> pd.DataFrame:
    """
    Add experience-based churn signals from the pre-cutoff order history.

    Using past feedback ratings is legitimate here because every rated
    order happened before the cutoff.
    """
    hist = orders[orders["order_date"] <= cutoff].copy()
    hist["delivery_time_minutes"] = pd.to_numeric(
        hist["delivery_time_minutes"], errors="coerce"
    )

    hist["is_cancelled"] = (hist["order_status"] == "Cancelled").astype(float)
    hist["is_late"]      = np.where(
        hist["delivery_time_minutes"] > 0,
        (hist["delivery_time_minutes"] > 45).astype(float),
        np.nan,
    )
    hist["has_coupon"] = hist["coupon_code"].notna().astype(float)

    exp = (hist.groupby("customer_id")
               .agg(
                   cancel_rate=("is_cancelled",  "mean"),
                   late_rate  =("is_late",        "mean"),
                   avg_delivery_time=("delivery_time_minutes", "mean"),
                   coupon_rate=("has_coupon",      "mean"),
                   n_restaurants=("restaurant_id", "nunique"),
               )
               .reset_index())

    # Average rating given (pre-cutoff feedback only)
    # Load from ABT if available; otherwise skip
    abt_path = ROOT / "data" / "cleaned" / "analytical_base_table.csv"
    if abt_path.exists():
        abt_sub = pd.read_csv(abt_path, usecols=[
            "customer_id", "order_date",
            "feedback_customer_rating", "feedback_delivery_rating", "feedback_food_rating"
        ])
        abt_sub["order_date"] = pd.to_datetime(abt_sub["order_date"], errors="coerce")
        past_feedback = abt_sub[abt_sub["order_date"] <= cutoff].copy()
        for col in ["feedback_customer_rating", "feedback_delivery_rating", "feedback_food_rating"]:
            past_feedback[col] = pd.to_numeric(past_feedback[col], errors="coerce")
        past_feedback["avg_rating_given"] = past_feedback[
            ["feedback_customer_rating", "feedback_delivery_rating", "feedback_food_rating"]
        ].mean(axis=1)
        rating_agg = (past_feedback.groupby("customer_id")["avg_rating_given"]
                      .mean().reset_index())
        exp = exp.merge(rating_agg, on="customer_id", how="left")
    else:
        exp["avg_rating_given"] = np.nan

    feats = feats.merge(exp, on="customer_id", how="left")
    return feats


# ---------------------------------------------------------------------------
# Preprocessing factory
# ---------------------------------------------------------------------------

def make_churn_preprocessor(scale: bool = False) -> ColumnTransformer:
    """
    Median-impute numerics (+ StandardScaler for linear models),
    most-frequent impute + OneHotEncoder for categoricals.
    """
    num_steps = [("impute", SimpleImputer(strategy="median"))]
    if scale:
        num_steps.append(("scale", StandardScaler()))

    cat_steps = [
        ("impute", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ]

    return ColumnTransformer(
        [
            ("num", Pipeline(num_steps),  CHURN_NUMERIC),
            ("cat", Pipeline(cat_steps),  CHURN_CATEGORICAL),
        ],
        remainder="drop",
    )


# ---------------------------------------------------------------------------
# Classifier registry
# ---------------------------------------------------------------------------

CLASSIFIERS: dict[str, tuple] = {
    "Baseline (predict majority)": (
        DummyClassifier(strategy="most_frequent"), True
    ),
    "Logistic Regression": (
        LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42),
        True,
    ),
    "Decision Tree": (
        DecisionTreeClassifier(max_depth=6, class_weight="balanced", random_state=42),
        False,
    ),
    "Random Forest": (
        RandomForestClassifier(
            n_estimators=300, class_weight="balanced",
            n_jobs=-1, random_state=42
        ),
        False,
    ),
    "Gradient Boosting": (
        HistGradientBoostingClassifier(
            class_weight="balanced", random_state=42
        ),
        False,
    ),
}


# ---------------------------------------------------------------------------
# Step 11: Cross-validate classifiers
# ---------------------------------------------------------------------------

def compare_classifiers(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    cv: StratifiedKFold,
) -> pd.DataFrame:
    """
    Cross-validate all classifiers on training data.
    Returns a DataFrame sorted by F1 score (best first).
    """
    rows = []
    for name, (clf, scale) in CLASSIFIERS.items():
        pipe = Pipeline([
            ("prep",  make_churn_preprocessor(scale)),
            ("model", clf),
        ])
        try:
            res = cross_validate(
                pipe, X_train, y_train, cv=cv, n_jobs=-1,
                scoring={
                    "f1":        "f1",
                    "precision": "precision",
                    "recall":    "recall",
                    "roc_auc":   "roc_auc",
                    "pr_auc":    "average_precision",
                },
            )
        except Exception as err:
            print(f"  [ERROR] {name}: {err}")
            continue

        rows.append({
            "model":       name,
            "cv_f1":       round( res["test_f1"].mean(),        4),
            "cv_precision":round( res["test_precision"].mean(),  4),
            "cv_recall":   round( res["test_recall"].mean(),     4),
            "cv_roc_auc":  round( res["test_roc_auc"].mean(),    4),
            "cv_pr_auc":   round( res["test_pr_auc"].mean(),     4),
        })
        print(f"    {name:<37} F1={rows[-1]['cv_f1']:.4f}  "
              f"ROC-AUC={rows[-1]['cv_roc_auc']:.4f}  "
              f"PR-AUC={rows[-1]['cv_pr_auc']:.4f}")

    return (pd.DataFrame(rows)
              .sort_values("cv_f1", ascending=False)
              .reset_index(drop=True))


# ---------------------------------------------------------------------------
# Step 12: Threshold tuning via out-of-fold predictions
# ---------------------------------------------------------------------------

def find_best_threshold(
    model: Pipeline,
    X_train: pd.DataFrame,
    y_train: pd.Series,
    cv: StratifiedKFold,
) -> float:
    """
    Find the F1-maximising decision threshold using out-of-fold predictions
    on the training set (test set is never touched for this step).

    Args:
        model:   Fitted or unfitted Pipeline.
        X_train: Training features.
        y_train: Training labels.
        cv:      Stratified cross-validator.

    Returns:
        Best threshold (float between 0 and 1).
    """
    oof_proba = cross_val_predict(
        model, X_train, y_train, cv=cv, method="predict_proba"
    )[:, 1]
    prec, rec, thr = precision_recall_curve(y_train, oof_proba)
    f1_scores = 2 * prec * rec / (prec + rec + 1e-12)
    best_idx = int(np.argmax(f1_scores[:-1]))
    best_thr = float(thr[best_idx])
    print(f"  Optimal threshold (F1-maximising, OOF): {best_thr:.3f}")
    print(f"  OOF F1 at threshold: {f1_scores[best_idx]:.4f}")
    return best_thr


# ---------------------------------------------------------------------------
# Step 12: Final evaluation on test set
# ---------------------------------------------------------------------------

def evaluate_classifier(
    model: Pipeline,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    threshold: float = 0.5,
) -> tuple[dict, np.ndarray, np.ndarray]:
    """
    Score a fitted pipeline on the held-out test set.

    Args:
        model:     Fitted Pipeline.
        X_test:    Test features.
        y_test:    True labels.
        threshold: Decision threshold for binary prediction.

    Returns:
        Tuple of (metrics_dict, probabilities, binary_predictions).
    """
    proba = model.predict_proba(X_test)[:, 1]
    pred  = (proba >= threshold).astype(int)

    metrics = {
        "accuracy":  round(accuracy_score(y_test, pred),              4),
        "precision": round(precision_score(y_test, pred,  zero_division=0), 4),
        "recall":    round(recall_score(y_test, pred,     zero_division=0), 4),
        "f1":        round(f1_score(y_test, pred,          zero_division=0), 4),
        "roc_auc":   round(roc_auc_score(y_test, proba),               4),
        "pr_auc":    round(average_precision_score(y_test, proba),     4),
        "threshold": round(threshold, 3),
    }
    return metrics, proba, pred


# ---------------------------------------------------------------------------
# Plotting helpers
# ---------------------------------------------------------------------------

def plot_confusion_matrix(y_test, pred, model_name: str) -> None:
    fig, ax = plt.subplots(figsize=(5, 4))
    ConfusionMatrixDisplay.from_predictions(
        y_test, pred, display_labels=["Active (0)", "Churned (1)"],
        cmap="Blues", ax=ax,
    )
    ax.set_title(f"Confusion Matrix — {model_name}")
    plt.tight_layout()
    plt.savefig(IMG_DIR / "churn_confusion_matrix.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  → images/churn_confusion_matrix.png")


def plot_roc_curve(y_test, proba, model_name: str) -> None:
    fig, ax = plt.subplots(figsize=(6, 5))
    RocCurveDisplay.from_predictions(y_test, proba, ax=ax, name=model_name)
    ax.plot([0, 1], [0, 1], "k--", label="Random classifier")
    ax.set_title("ROC Curve — Churn Model")
    ax.legend()
    plt.tight_layout()
    plt.savefig(IMG_DIR / "churn_roc_curve.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  → images/churn_roc_curve.png")


def plot_pr_curve(y_test, proba, model_name: str) -> None:
    prec, rec, _ = precision_recall_curve(y_test, proba)
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.plot(rec, prec, lw=2, color="darkorange")
    ax.set_xlabel("Recall"); ax.set_ylabel("Precision")
    ax.set_title(f"Precision-Recall Curve — {model_name}")
    baseline = y_test.mean()
    ax.axhline(baseline, color="grey", linestyle="--",
               label=f"Baseline (always predict churn, precision={baseline:.2f})")
    ax.legend()
    plt.tight_layout()
    plt.savefig(IMG_DIR / "churn_pr_curve.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  → images/churn_pr_curve.png")


def plot_churn_feature_importance(
    model: Pipeline,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    model_name: str,
    n_top: int = 15,
) -> None:
    """Permutation importance on the whole pipeline — one bar per real feature."""
    try:
        imp = permutation_importance(
            model, X_test, y_test,
            n_repeats=10, random_state=42,
            scoring="roc_auc", n_jobs=-1,
        )
        feat_names = [c for c in CHURN_NUMERIC if c in X_test.columns] + \
                     [c for c in CHURN_CATEGORICAL if c in X_test.columns]
        imp_df = (pd.DataFrame({
                      "feature":    feat_names[:len(imp.importances_mean)],
                      "importance": imp.importances_mean,
                  })
                  .sort_values("importance", ascending=False)
                  .head(n_top))

        fig, ax = plt.subplots(figsize=(9, 6))
        ax.barh(imp_df["feature"][::-1], imp_df["importance"][::-1],
                color="steelblue", edgecolor="white")
        ax.set_title(f"Top {n_top} Feature Importances (Permutation) — {model_name}")
        ax.set_xlabel("Mean decrease in ROC-AUC")
        plt.tight_layout()
        plt.savefig(IMG_DIR / "churn_feature_importance.png", dpi=150, bbox_inches="tight")
        plt.close()
        print("  → images/churn_feature_importance.png")
        return imp_df
    except Exception as e:
        print(f"  [WARN] Feature importance failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Step 13: Risk segments
# ---------------------------------------------------------------------------

def build_risk_segments(
    churn_df: pd.DataFrame,
    model: Pipeline,
    X: pd.DataFrame,
    threshold: float,
    label: str = "test",
) -> pd.DataFrame:
    """
    Add churn probability and risk segment to every row.

    Risk segments (band edges chosen to align with the threshold):
      Low    : probability < 0.4
      Medium : 0.4 ≤ probability < threshold
      High   : probability ≥ threshold

    Args:
        churn_df: Full churn dataset (with customer_id column).
        model:    Fitted pipeline.
        X:        Features (same rows as churn_df, aligned by index).
        threshold: Decision threshold.
        label:    Tag added to the 'split' column ("test" or "current").

    Returns:
        DataFrame with customer_id, churn_probability, predicted_label,
        risk_segment columns.
    """
    proba = model.predict_proba(X)[:, 1]
    pred  = (proba >= threshold).astype(int)

    scores = pd.DataFrame({
        "customer_id":       churn_df.loc[X.index, "customer_id"].values,
        "churn_probability": proba.round(4),
        "predicted_label":   pred,
        "split":             label,
    })

    # Band edges are terciles of the predicted probabilities (not tied to the
    # threshold: when a model has no skill the threshold can sit below every
    # probability, which puts everyone in "High"). For reporting, src/churn_analysis.py
    # computes the edges from TRAINING out-of-fold probabilities instead.
    low_edge, high_edge = np.percentile(proba, [33.3, 66.7])
    scores["risk_segment"] = pd.cut(
        scores["churn_probability"],
        bins=[0.0, low_edge, high_edge, 1.0],
        labels=["Low", "Medium", "High"],
        include_lowest=True,
    )
    return scores


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def write_churn_report(
    cutoff: pd.Timestamp,
    churn_rate: float,
    cv_table: pd.DataFrame,
    tune_results: dict,
    test_metrics: dict,
    baseline_f1: float,
    winner_name: str,
    threshold: float,
    n_train: int,
    n_test: int,
    imp_df=None,
) -> None:
    """Write documentation/churn_model_report.md."""
    f1_ok   = test_metrics["f1"]      >= KPI_F1
    roc_ok  = test_metrics["roc_auc"] >= 0.60

    lines = [
        "# Churn Classification Model Report — Week 3\n\n",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  \n",
        f"**Target:** `churned` (1 = no order in {HORIZON} days after cutoff)  \n",
        f"**KPI target:** F1 ≥ {KPI_F1}  \n\n---\n\n",
        "## Dataset Design\n\n",
        f"| | |\n|---|---|\n",
        f"| Feature window | all orders on or before {cutoff.date()} |\n",
        f"| Label window | {cutoff.date()} → {(cutoff + pd.Timedelta(days=HORIZON)).date()} |\n",
        f"| Train customers | {n_train:,} |\n",
        f"| Test customers | {n_test:,} |\n",
        f"| Churn rate | {churn_rate*100:.1f}% |\n",
        f"| Naive baseline F1 (predict all churn) | {baseline_f1:.4f} |\n\n",
        "**Design decisions:**\n",
        f"- Cutoff = MAX(order_date) − {HORIZON} days = `{cutoff.date()}`\n",
        "- Label = 1 if customer placed NO order in the following 60 days\n",
        "- Any order status counts as 'activity' for the label\n",
        "- `customers.total_orders` excluded — it is a snapshot over the whole period\n",
        "- Past feedback ratings ARE used — they occurred before the cutoff\n\n",
        "## Class Imbalance Handling\n\n",
        f"Churn rate is {churn_rate*100:.1f}% — highly imbalanced.  \n",
        "Strategy used: `class_weight='balanced'` on all classifiers.  \n",
        "This makes errors on the minority class (non-churners) cost proportionally more.  \n",
        "SMOTE was not used to avoid introducing synthetic samples in a one-hot encoded space.  \n\n",
        "## Cross-Validation Comparison (training set, 5-fold stratified)\n\n",
        "| Model | CV F1 | CV Precision | CV Recall | CV ROC-AUC | CV PR-AUC |\n",
        "|---|---|---|---|---|---|\n",
    ]
    for _, row in cv_table.iterrows():
        lines.append(
            f"| {row['model']} | {row['cv_f1']} | {row['cv_precision']} | "
            f"{row['cv_recall']} | {row['cv_roc_auc']} | {row['cv_pr_auc']} |\n"
        )

    lines += ["\n## Hyperparameter Tuning\n\n"]
    for mname, result in tune_results.items():
        lines += [
            f"### {mname}\n\n",
            f"- Before: CV F1 = {result['before_f1']:.4f}\n",
            f"- After:  CV F1 = {result['after_f1']:.4f}\n",
            f"- Best params: `{result['best_params']}`\n\n",
        ]

    met = test_metrics
    f1_status  = "✅ PASS" if f1_ok  else f"⚠️ below target (target: ≥{KPI_F1})"
    roc_status = "✅" if roc_ok else "⚠️"

    lines += [
        "\n## Test Set Results\n\n",
        f"**Winner: {winner_name}**  \n",
        f"**Decision threshold: {threshold:.3f}** (F1-maximising, chosen on OOF predictions)  \n\n",
        "| Metric | Value | Baseline (predict all churn) | KPI | Status |\n",
        "|---|---|---|---|---|\n",
        f"| F1 | {met['f1']} | {baseline_f1:.4f} | ≥{KPI_F1} | {f1_status} |\n",
        f"| Precision | {met['precision']} | — | — | — |\n",
        f"| Recall | {met['recall']} | — | — | — |\n",
        f"| ROC-AUC | {met['roc_auc']} | 0.50 (random) | — | {roc_status} |\n",
        f"| PR-AUC | {met['pr_auc']} | {churn_rate:.4f} (naive) | — | — |\n",
        f"| Accuracy | {met['accuracy']} | {churn_rate:.4f} | — | — |\n\n",
        "## Interpretation\n\n",
        f"The churn rate is {churn_rate*100:.1f}% — the majority of customers placed only 1–2 orders.  \n",
        f"The naive baseline (predict everyone churns) already achieves F1={baseline_f1:.4f}.  \n\n",
        f"The model achieves F1={met['f1']:.4f} vs baseline F1={baseline_f1:.4f}.\n",
        f"ROC-AUC={met['roc_auc']:.4f} (above 0.5=random, below 0.95=no suspicious leakage).  \n\n",
        "**In plain English:** the model's precision and recall trade-off is tuned at the  \n",
        f"F1-maximising threshold ({threshold:.2f}). Of every 100 customers the model  \n",
        f"flags as high-risk, approximately {int(met['precision']*100)} have actually churned.  \n",
        f"It catches approximately {int(met['recall']*100)}% of customers who will churn.  \n\n",
        "**Key churn drivers** (from permutation importance):\n",
    ]
    if imp_df is not None:
        for _, row in imp_df.head(5).iterrows():
            lines.append(f"- `{row['feature']}`: importance = {row['importance']:.4f}\n")
    lines += [
        "\n",
        "**Recommendations:** only act on a risk segment if `src/churn_analysis.py` shows its actual  \n",
        "churn rate differs from the other segments (`data/cleaned/ml_churn_segment_check.csv`).  \n\n",
        "## Saved Artefacts\n\n",
        "- `models/churn_model.joblib`\n",
        "- `data/cleaned/ml_model_comparison_churn.csv`\n",
        "- `data/cleaned/churn_scores.csv`\n",
        "- `data/cleaned/churn_scores_current.csv` (forward-looking, no ground truth)\n",
        "- `images/churn_confusion_matrix.png`\n",
        "- `images/churn_roc_curve.png`\n",
        "- `images/churn_pr_curve.png`\n",
        "- `images/churn_feature_importance.png`\n",
    ]

    out = DOC_DIR / "churn_model_report.md"
    out.write_text("".join(lines), encoding="utf-8")
    print(f"  → {out.relative_to(ROOT)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    start = datetime.now()
    print("=" * 64)
    print("Zomato BI — Week 3 Steps 10–13: Churn Classification Model")
    print("=" * 64)

    MODEL_DIR.mkdir(exist_ok=True)

    # ── Load data ─────────────────────────────────────────────────────────
    print("\n[1] Loading data ...")
    orders = pd.read_csv(CLEAN_DIR / "orders.csv")
    cust   = pd.read_csv(CLEAN_DIR / "customers.csv")
    orders["order_date"]    = pd.to_datetime(orders["order_date"],    errors="coerce")
    orders["final_amount"]  = pd.to_numeric(orders["final_amount"],   errors="coerce")
    orders["delivery_time_minutes"] = pd.to_numeric(orders["delivery_time_minutes"], errors="coerce")
    print(f"    orders: {len(orders):,}  customers: {len(cust):,}")

    # ── Step 10: Build churn dataset ──────────────────────────────────────
    print("\n[2] Building churn dataset (Step 10) ...")
    ref_date = orders["order_date"].max()
    cutoff   = ref_date - pd.Timedelta(days=HORIZON)
    print(f"    ref_date : {ref_date.date()}")
    print(f"    cutoff   : {cutoff.date()}")
    print(f"    label window: {cutoff.date()} → {ref_date.date()}")

    churn_df = build_churn_dataset(orders, cust, cutoff, HORIZON)
    churn_rate = churn_df["churned"].mean()
    print(f"    Customers: {len(churn_df):,}")
    print(f"    Churn rate: {churn_rate*100:.1f}%  ({churn_df['churned'].sum():,} churned)")
    print(f"    Class distribution: {churn_df['churned'].value_counts().to_dict()}")

    # ── Step 11: Split ────────────────────────────────────────────────────
    print("\n[3] Splitting 80/20 stratified (Step 11) ...")
    available_num = [c for c in CHURN_NUMERIC     if c in churn_df.columns]
    available_cat = [c for c in CHURN_CATEGORICAL if c in churn_df.columns]
    X = churn_df[available_num + available_cat]
    y = churn_df["churned"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    print(f"    Train: {len(X_train):,}  Test: {len(X_test):,}")
    print(f"    Train churn rate: {y_train.mean()*100:.1f}%  "
          f"Test churn rate: {y_test.mean()*100:.1f}%")

    # Naive baseline F1
    baseline_f1 = f1_score(y_test, np.ones(len(y_test), dtype=int), zero_division=0)
    print(f"    Naive baseline F1 (predict all churn): {baseline_f1:.4f}")

    # ── Step 11: Compare classifiers ──────────────────────────────────────
    print("\n[4] Cross-validating classifiers (Step 11) ...")
    cv_table = compare_classifiers(X_train, y_train, cv)
    print("\n    CV results:")
    print(cv_table.to_string(index=False))
    cv_table.to_csv(CLEAN_DIR / "ml_model_comparison_churn.csv", index=False)
    print("\n    → data/cleaned/ml_model_comparison_churn.csv")

    # ── Step 12: Tune top 2 ───────────────────────────────────────────────
    print("\n[5] Tuning top 2 models (Step 12) ...")
    top2 = cv_table[~cv_table["model"].str.contains("Baseline")]["model"].head(2).tolist()
    print(f"    Tuning: {top2}")

    param_grids = {
        "Random Forest": {
            "model__n_estimators":    [100, 200, 300],
            "model__max_depth":       [None, 6, 10, 16],
            "model__min_samples_leaf":[1, 3, 5],
            "model__max_features":    ["sqrt", 0.5],
        },
        "Gradient Boosting": {
            "model__learning_rate":        [0.03, 0.05, 0.1],
            "model__max_iter":             [100, 200, 300],
            "model__max_depth":            [3, 5, 7],
            "model__min_samples_leaf":     [10, 20, 30],
            "model__l2_regularization":    [0.0, 0.1, 1.0],
        },
        "Logistic Regression": {
            "model__C":                [0.01, 0.1, 1.0, 10.0],
            "model__solver":           ["lbfgs", "liblinear"],
        },
        "Decision Tree": {
            "model__max_depth":        [4, 6, 8, None],
            "model__min_samples_leaf": [1, 5, 10],
        },
    }

    tune_results = {}
    best_estimator = None
    best_cv_f1     = -1.0
    winner_name    = top2[0]

    for mname in top2:
        clf, scale = CLASSIFIERS[mname]
        grid = param_grids.get(mname, {})
        before_f1 = cv_table.loc[cv_table["model"]==mname, "cv_f1"].iloc[0]

        if not grid:
            print(f"    {mname}: no tuning grid — using default")
            pipe = Pipeline([
                ("prep",  make_churn_preprocessor(scale)),
                ("model", clf),
            ])
            pipe.fit(X_train, y_train)
            tune_results[mname] = {
                "before_f1": before_f1,
                "after_f1":  before_f1,
                "best_params": {},
            }
            if before_f1 > best_cv_f1:
                best_cv_f1   = before_f1
                best_estimator = pipe
                winner_name  = mname
            continue

        fresh_clf = clf.__class__(**{
            k: v for k, v in clf.get_params().items()
            if k in ["class_weight", "random_state", "n_jobs", "max_iter"]
        })
        pipe = Pipeline([
            ("prep",  make_churn_preprocessor(scale)),
            ("model", fresh_clf),
        ])
        search = RandomizedSearchCV(
            pipe,
            param_distributions=grid,
            n_iter=20, cv=cv,
            scoring="f1",
            n_jobs=-1, random_state=42, refit=True,
        )
        search.fit(X_train, y_train)
        after_f1   = round(search.best_score_, 4)
        best_params = search.best_params_
        print(f"    {mname}: before F1={before_f1:.4f}  after F1={after_f1:.4f}")
        print(f"      params: {best_params}")

        tune_results[mname] = {
            "before_f1":   before_f1,
            "after_f1":    after_f1,
            "best_params": best_params,
        }
        if after_f1 > best_cv_f1:
            best_cv_f1     = after_f1
            best_estimator = search.best_estimator_
            winner_name    = mname

    if best_estimator is None:
        clf, scale = CLASSIFIERS[top2[0]]
        best_estimator = Pipeline([
            ("prep",  make_churn_preprocessor(scale)),
            ("model", clf),
        ])
        best_estimator.fit(X_train, y_train)

    print(f"\n    Winner: {winner_name}  (CV F1={best_cv_f1:.4f})")

    # ── Step 12: Threshold selection ──────────────────────────────────────
    print("\n[6] Finding optimal decision threshold (Step 12) ...")
    threshold = find_best_threshold(best_estimator, X_train, y_train, cv)

    # ── Step 12: Final test evaluation ────────────────────────────────────
    print("\n[7] Final test-set evaluation (test opened ONCE) ...")
    test_metrics, proba, pred = evaluate_classifier(
        best_estimator, X_test, y_test, threshold
    )
    print(f"    F1       : {test_metrics['f1']}  (KPI: ≥{KPI_F1})")
    print(f"    ROC-AUC  : {test_metrics['roc_auc']}")
    print(f"    PR-AUC   : {test_metrics['pr_auc']}")
    print(f"    Precision: {test_metrics['precision']}")
    print(f"    Recall   : {test_metrics['recall']}")
    print(f"    Baseline F1 (all churn): {baseline_f1:.4f}")

    f1_ok = test_metrics["f1"] >= KPI_F1
    print(f"    F1 KPI: {'✅ PASS' if f1_ok else '⚠️ BELOW TARGET'}")

    # ── Step 13: Plots ────────────────────────────────────────────────────
    print("\n[8] Saving plots (Step 13) ...")
    plot_confusion_matrix(y_test, pred, winner_name)
    plot_roc_curve(y_test, proba, winner_name)
    plot_pr_curve(y_test, proba, winner_name)
    imp_df = plot_churn_feature_importance(best_estimator, X_test, y_test, winner_name)

    # ── Step 13: Risk segments ────────────────────────────────────────────
    print("\n[9] Building risk segments (Step 13) ...")
    scores_test = build_risk_segments(
        churn_df, best_estimator, X_test, threshold, label="test"
    )
    if y_test is not None:
        scores_test["actual_label"] = y_test.values
    scores_test.to_csv(CLEAN_DIR / "churn_scores.csv", index=False)
    print(f"    Test risk segments:")
    print("   ", scores_test["risk_segment"].value_counts().to_dict())

    # Forward-looking: score ALL customers as of the latest date
    print("\n    Forward-looking scores (all customers, as of ref_date) ...")
    churn_df_current = build_churn_dataset(orders, cust, ref_date, HORIZON)
    available_num_c = [c for c in CHURN_NUMERIC     if c in churn_df_current.columns]
    available_cat_c = [c for c in CHURN_CATEGORICAL if c in churn_df_current.columns]
    X_current = churn_df_current[available_num_c + available_cat_c]

    scores_current = build_risk_segments(
        churn_df_current, best_estimator, X_current, threshold, label="current"
    )
    scores_current.to_csv(CLEAN_DIR / "churn_scores_current.csv", index=False)
    high_risk = (scores_current["risk_segment"] == "High").sum()
    print(f"    Current high-risk customers: {high_risk:,} (forward-looking — no ground truth)")

    # ── Save model ────────────────────────────────────────────────────────
    print("\n[10] Saving artefacts ...")
    joblib.dump(best_estimator, MODEL_DIR / "churn_model.joblib")
    joblib.dump(best_estimator, MODEL_DIR / "churn_best_model.pkl")
    import json, sklearn
    meta_path = MODEL_DIR / "model_metadata.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    meta["churn_model"] = {
        "target": TARGET, "model": winner_name, "model_file": "churn_best_model.pkl",
        "cutoff_date": str(cutoff.date()), "horizon_days": HORIZON, "churn_rate": round(churn_rate, 4),
        "churn_threshold": round(threshold, 3), "naive_baseline_f1": round(baseline_f1, 4),
        "test_metrics": test_metrics, "kpi_f1_target": KPI_F1,
        "sklearn_version": sklearn.__version__, "trained_on": str(pd.Timestamp.today().date()),
    }
    meta_path.write_text(json.dumps(meta, indent=2, default=float))
    print(f"    → models/churn_model.joblib")

    write_churn_report(
        cutoff, churn_rate, cv_table, tune_results, test_metrics,
        baseline_f1, winner_name, threshold,
        len(X_train), len(X_test), imp_df,
    )

    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n{'='*64}")
    print(f"Steps 10–13 COMPLETE ✅  ({elapsed:.0f}s)")
    print(f"  Model         → models/churn_model.joblib")
    print(f"  CV table      → data/cleaned/ml_model_comparison_churn.csv")
    print(f"  Test scores   → data/cleaned/churn_scores.csv")
    print(f"  Current scores→ data/cleaned/churn_scores_current.csv")
    print(f"  Report        → documentation/churn_model_report.md")
    print(f"{'='*64}")


if __name__ == "__main__":
    main()
