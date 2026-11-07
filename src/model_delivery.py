"""
src/model_delivery.py
---------------------
Week 3, Steps 6–9: Delivery time regression model.

Builds, compares, tunes, evaluates, and saves a model that predicts
delivery_time_minutes from facts known when the order is placed.

Key design rules:
  • Only pre-delivery features are used as inputs (no feedback ratings,
    no order_status, no ID columns treated as numbers).
  • The 80/20 train/test split is done BEFORE any preprocessing.
  • Preprocessing is fitted ONLY on training data (inside a Pipeline).
  • The test set is opened ONCE, at the very end.

Usage:
    python src/model_delivery.py

Outputs:
    models/delivery_time_model.joblib          best tuned model
    data/cleaned/ml_model_comparison_delivery.csv
    data/cleaned/ml_delivery_test_results.csv
    documentation/delivery_model_report.md
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
    train_test_split, KFold, cross_validate, RandomizedSearchCV
)
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.tree import DecisionTreeRegressor
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

warnings.filterwarnings("ignore")

ROOT      = Path(__file__).resolve().parent.parent
CLEAN_DIR = ROOT / "data" / "cleaned"
MODEL_DIR = ROOT / "models"
DOC_DIR   = ROOT / "documentation"
IMG_DIR   = ROOT / "images"

# ---------------------------------------------------------------------------
# Feature lists — everything known when the order is placed
# ---------------------------------------------------------------------------

NUMERIC: list[str] = [
    # Time features
    "order_hour",           # Hour of day (0-23)
    "order_dayofweek",      # Day of week (0=Mon … 6=Sun)
    "peak_hour",            # Binary: 1 if lunch(12-14) or dinner(19-22)
    "weekend_order",        # Binary: 1 if Saturday or Sunday
    # Order content
    "n_items",              # Number of items in order
    "avg_prep_time",        # Mean preparation time across items (min)
    "max_prep_time",        # Max preparation time across items (min)
    "basket_value",         # SUM of item total_prices
    "discount_pct",         # discount / food_cost
    "coupon_used",          # Binary: 1 if coupon applied
    # Restaurant
    "restaurant_rating",    # Restaurant star rating (1-5)
    "restaurant_popularity_rank",  # Dense rank within city by order count
    # Partner
    "partner_rating",       # Partner star rating (1-5)
    "delivery_efficiency",  # Partner avg_delivery_time / city average
    "partner_avg_delivery_time",  # Partner's average delivery time (min)
    "completed_deliveries", # Partner's career completed deliveries
    # Distance
    "is_cross_city",        # Binary: 1 if customer city ≠ restaurant city
    # Customer
    "customer_tenure_days", # Days from registration to order
    # Context (weather + traffic — mostly null but imputed by median)
    "rainfall",             # mm — from weather join
    "temperature",          # °C
    "humidity",             # %
    "traffic_score",        # 1=Low … 4=Severe
    # Interaction features
    "is_peak_and_rain",     # peak_hour AND moderate/heavy rain
]

CATEGORICAL: list[str] = [
    "restaurant_city",      # 25 cities
    "restaurant_cuisine",   # 19 cuisines
    "vehicle_type",         # Bike, Scooter, Bicycle, Car
    "weather_condition",    # Clear, Cloudy, Rainy, etc.
    "membership",           # Basic, Gold, Zomato Pro
    "payment_method",       # 6 methods
]

# Columns explicitly excluded and reasons:
EXCLUDED = {
    "feedback_customer_rating": "post-delivery — unknown at order time",
    "feedback_delivery_rating": "post-delivery — unknown at order time",
    "feedback_food_rating":     "post-delivery — unknown at order time",
    "average_rating":           "post-delivery — unknown at order time",
    "sentiment":                "post-delivery — unknown at order time",
    "review":                   "post-delivery — free text",
    "order_status":             "every row is 'Delivered'; zero variance",
    "order_id":                 "identifier — not a predictor",
    "customer_id":              "identifier — use customer attributes instead",
    "restaurant_id":            "identifier — use restaurant attributes instead",
    "delivery_partner_id":      "identifier — use partner attributes instead",
    "final_amount":             "future value: depends on delivery completing",
    "distance_to_city_centre_km": "restaurant coordinates do not sit in their cities (median ~950 km from centre)",
}

TARGET = "delivery_time_minutes"

# KPI targets from the guide
KPI_R2   = 0.75
KPI_RMSE = 6.0   # minutes


# ---------------------------------------------------------------------------
# Preprocessing pipeline factory
# ---------------------------------------------------------------------------

def make_preprocessor(scale: bool = False) -> ColumnTransformer:
    """
    Build a ColumnTransformer that:
      - Numeric: median-impute, then optionally StandardScaler
      - Categorical: most-frequent impute + OneHotEncoder(handle_unknown='ignore')

    Args:
        scale: If True, apply StandardScaler after imputation (for linear models).

    Returns:
        ColumnTransformer ready to be embedded in a Pipeline.
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
            ("num", Pipeline(num_steps),                 NUMERIC),
            ("cat", Pipeline(cat_steps),                 CATEGORICAL),
        ],
        remainder="drop",
    )


# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

MODELS: dict[str, tuple] = {
    "Baseline (predict mean)":   (DummyRegressor(strategy="mean"),          True),
    "Ridge Regression":          (Ridge(alpha=1.0),                         True),
    "Decision Tree (depth=8)":   (DecisionTreeRegressor(
                                     max_depth=8, random_state=42),         False),
    "Random Forest":             (RandomForestRegressor(
                                     n_estimators=200, n_jobs=-1,
                                     random_state=42),                       False),
    "Gradient Boosting":         (GradientBoostingRegressor(
                                     n_estimators=200, learning_rate=0.1,
                                     max_depth=4, random_state=42),          False),
}


# ---------------------------------------------------------------------------
# Step 6: Build the modelling dataset
# ---------------------------------------------------------------------------

def build_model_dataset(abt: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """
    Filter and select the modelling dataset from the ABT.

    Rows: Delivered orders with valid delivery time and no outlier flag.
    Columns: NUMERIC + CATEGORICAL features only (no post-delivery or ID cols).

    Args:
        abt: Analytical base table.

    Returns:
        Tuple of (X, y).
    """
    model_df = abt[
        (abt["order_status"] == "Delivered") &
        (abt["delivery_time_minutes"] > 0)   &
        (abt["dt_outlier_flag"] == 0)
    ].copy()

    # Parse numeric columns that may have come in as strings
    for col in NUMERIC:
        if col in model_df.columns:
            model_df[col] = pd.to_numeric(model_df[col], errors="coerce")

    available_num = [c for c in NUMERIC      if c in model_df.columns]
    available_cat = [c for c in CATEGORICAL  if c in model_df.columns]

    missing_num = [c for c in NUMERIC      if c not in model_df.columns]
    missing_cat = [c for c in CATEGORICAL  if c not in model_df.columns]
    if missing_num or missing_cat:
        print(f"  [WARN] Missing numeric features: {missing_num}")
        print(f"  [WARN] Missing categorical features: {missing_cat}")

    X = model_df[available_num + available_cat]
    y = model_df[TARGET]

    return X, y


# ---------------------------------------------------------------------------
# Step 7: Cross-validate all models
# ---------------------------------------------------------------------------

def compare_models(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    cv: KFold,
) -> pd.DataFrame:
    """
    Cross-validate every model on the TRAINING data.

    Args:
        X_train: Training features.
        y_train: Training target.
        cv:      KFold cross-validator.

    Returns:
        DataFrame sorted by cv_rmse (best first), with one row per model.
    """
    rows = []
    for name, (model, scale) in MODELS.items():
        pipe = Pipeline([
            ("prep",  make_preprocessor(scale)),
            ("model", model),
        ])
        try:
            res = cross_validate(
                pipe, X_train, y_train, cv=cv, n_jobs=-1,
                scoring={
                    "mae":  "neg_mean_absolute_error",
                    "rmse": "neg_root_mean_squared_error",
                    "r2":   "r2",
                },
            )
        except Exception as err:
            print(f"  [ERROR] {name}: {err}")
            continue

        rows.append({
            "model":       name,
            "cv_mae":      round(-res["test_mae"].mean(),   3),
            "cv_rmse":     round(-res["test_rmse"].mean(),  3),
            "cv_rmse_std": round( res["test_rmse"].std(),   3),
            "cv_r2":       round( res["test_r2"].mean(),    4),
        })
        print(f"    {name:<35} RMSE={rows[-1]['cv_rmse']:.2f}  "
              f"R²={rows[-1]['cv_r2']:.4f}")

    return (pd.DataFrame(rows)
              .sort_values("cv_rmse")
              .reset_index(drop=True))


# ---------------------------------------------------------------------------
# Step 8: Hyperparameter tuning
# ---------------------------------------------------------------------------

def tune_model(
    name: str,
    model,
    param_grid: dict,
    X_train: pd.DataFrame,
    y_train: pd.Series,
    cv: KFold,
    n_iter: int = 20,
) -> tuple:
    """
    Run RandomizedSearchCV for one model on the training set.

    Args:
        name:       Human-readable model name.
        model:      Estimator (not yet in a pipeline).
        param_grid: Dict of param_distributions (use 'model__' prefix).
        X_train:    Training features.
        y_train:    Training target.
        cv:         Cross-validator.
        n_iter:     Number of random combinations to try.

    Returns:
        Tuple of (best_estimator, best_params, best_cv_rmse).
    """
    pipe = Pipeline([
        ("prep",  make_preprocessor(False)),
        ("model", model),
    ])
    search = RandomizedSearchCV(
        pipe,
        param_distributions=param_grid,
        n_iter=n_iter,
        cv=cv,
        scoring="neg_root_mean_squared_error",
        n_jobs=-1,
        random_state=42,
        refit=True,
    )
    search.fit(X_train, y_train)
    best_rmse = round(-search.best_score_, 3)
    print(f"  {name}: best CV RMSE = {best_rmse:.3f}")
    print(f"    params: {search.best_params_}")
    return search.best_estimator_, search.best_params_, best_rmse


# ---------------------------------------------------------------------------
# Step 9: Final evaluation (test set — opened once)
# ---------------------------------------------------------------------------

def evaluate(model, X_test: pd.DataFrame, y_test: pd.Series) -> tuple:
    """
    Score a fitted pipeline on the held-out test set.

    Args:
        model:  Fitted sklearn Pipeline.
        X_test: Test features.
        y_test: True target values.

    Returns:
        Tuple of (metrics_dict, predictions_array).
    """
    pred = model.predict(X_test)
    mse = mean_squared_error(y_test, pred)
    metrics = {
        "MAE":  round(mean_absolute_error(y_test, pred), 3),
        "MSE":  round(mse, 3),
        "RMSE": round(float(np.sqrt(mse)), 3),
        "R2":   round(r2_score(y_test, pred), 4),
    }
    return metrics, pred


def plot_residuals(y_test: pd.Series, pred: np.ndarray, model_name: str) -> None:
    """Save residual analysis plots to images/."""
    resid = y_test.values - pred

    fig, axes = plt.subplots(1, 3, figsize=(15, 4))

    # 1. Actual vs Predicted
    axes[0].scatter(y_test, pred, alpha=0.3, s=10, color="steelblue")
    _min, _max = min(y_test.min(), pred.min()), max(y_test.max(), pred.max())
    axes[0].plot([_min, _max], [_min, _max], "r--", lw=2)
    axes[0].set_title("Actual vs Predicted")
    axes[0].set_xlabel("Actual (min)"); axes[0].set_ylabel("Predicted (min)")

    # 2. Residual vs Predicted
    axes[1].scatter(pred, resid, alpha=0.3, s=10, color="darkorange")
    axes[1].axhline(0, color="red", linestyle="--", lw=2)
    axes[1].set_title("Residuals vs Predicted")
    axes[1].set_xlabel("Predicted (min)"); axes[1].set_ylabel("Residual (min)")

    # 3. Residual histogram
    axes[2].hist(resid, bins=40, color="steelblue", edgecolor="white", alpha=0.8)
    axes[2].axvline(0, color="red", linestyle="--")
    axes[2].set_title("Residual Distribution")
    axes[2].set_xlabel("Residual (min)"); axes[2].set_ylabel("Count")

    plt.suptitle(f"Residual Analysis — {model_name}", fontsize=13)
    plt.tight_layout()
    IMG_DIR.mkdir(exist_ok=True)
    plt.savefig(IMG_DIR / "delivery_residuals.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  → images/delivery_residuals.png saved")


def plot_feature_importance(model, X: pd.DataFrame, y: pd.Series,
                            model_name: str, n_top: int = 10) -> pd.DataFrame:
    """
    Permutation importance on the whole pipeline (one bar per original feature, so a
    category such as cuisine is one bar, not 20 one-hot bars), measured on the given
    test data. Saves the top-n chart to images/ and the full table, with measured
    direction and a noise flag, to data/cleaned/ml_delivery_feature_importance.csv.
    """
    from sklearn.inspection import permutation_importance
    imp = permutation_importance(model, X, y, n_repeats=10, random_state=42,
                                 scoring="neg_root_mean_squared_error", n_jobs=-1)
    df = pd.DataFrame({"feature": X.columns, "importance": imp.importances_mean,
                       "std": imp.importances_std})

    def direction(f: str) -> str:
        if f in CATEGORICAL:
            return "categorical - no single direction"
        r = pd.to_numeric(X[f], errors="coerce").corr(y)
        if pd.isna(r) or abs(r) < 0.02:
            return f"no meaningful relationship (r={r:.3f})"
        return f"higher values go with {'longer' if r > 0 else 'shorter'} delivery (r={r:.3f})"

    df["direction"] = df["feature"].map(direction)
    df["distinguishable_from_noise"] = (df["importance"] > 2 * df["std"]).map({True: "yes", False: "no"})
    df = df.sort_values("importance", ascending=False).reset_index(drop=True)
    df.to_csv(CLEAN_DIR / "ml_delivery_feature_importance.csv", index=False)

    top = df.head(n_top).iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(top["feature"], top["importance"], xerr=top["std"],
            color=["steelblue" if s == "yes" else "lightgray" for s in top["distinguishable_from_noise"]])
    ax.axvline(0, color="black", lw=0.8)
    ax.set_title(f"Top {n_top} Features by Permutation Importance — {model_name}")
    ax.set_xlabel("Increase in test RMSE when the feature is shuffled (minutes); grey = within noise")
    plt.tight_layout()
    IMG_DIR.mkdir(exist_ok=True)
    plt.savefig(IMG_DIR / "delivery_feature_importance.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  → images/delivery_feature_importance.png + ml_delivery_feature_importance.csv saved")
    return df


def save_prediction_export(abt: pd.DataFrame, X_test: pd.DataFrame,
                           y_test: pd.Series, pred: np.ndarray) -> None:
    """Power BI export: test-set predictions with columns for slicing."""
    cols = ["order_id", "restaurant_city", "peak_hour", "weather_condition", "order_status",
            "restaurant_cuisine", "membership", "vehicle_type"]
    out = abt.loc[X_test.index, [c for c in cols if c in abt.columns]].copy()
    out.insert(1, "actual_minutes", y_test.values)
    out.insert(2, "predicted_minutes", np.round(pred, 1))
    out.insert(3, "residual", np.round(y_test.values - pred, 1))
    out.insert(4, "abs_error", np.round(np.abs(y_test.values - pred), 1))
    out.to_csv(CLEAN_DIR / "ml_delivery_predictions.csv", index=False)
    print("  → data/cleaned/ml_delivery_predictions.csv saved")


def interpretation_section(met: dict) -> str:
    """Markdown interpretation, error analysis and importance table, all computed."""
    from scipy import stats
    pr = pd.read_csv(CLEAN_DIR / "ml_delivery_predictions.csv")
    imp = pd.read_csv(CLEAN_DIR / "ml_delivery_feature_importance.csv")

    def kruskal(col: str) -> float:
        g = [x["abs_error"].to_numpy() for _, x in pr.groupby(col) if len(x) >= 5]
        return stats.kruskal(*g).pvalue if len(g) >= 2 else float("nan")

    out = ["## Interpretation\n\n",
           f"On the test set the model is off by **{met['MAE']:.1f} minutes** on average (MAE), "
           f"RMSE is **{met['RMSE']:.1f} min** ({'meets' if met['RMSE'] <= KPI_RMSE else 'does not meet'} "
           f"the ≤{KPI_RMSE}-minute target) and it explains **{met['R2']:.1%}** of the variation (R²). "]
    if met["R2"] < 0.1:
        out.append("It does not beat the predict-the-mean baseline, so it has found no usable structure, "
                   "linear or non-linear. Its predictions cluster around the mean (standard deviation "
                   f"{pr['predicted_minutes'].std():.1f} min, versus {pr['actual_minutes'].std():.1f} min "
                   "for actual delivery times).")
    out.append("\n\n### Error analysis (test set)\n\n"
               "| Segment | Mean absolute error by group (min) | Difference between groups |\n|---|---|---|\n")
    for col in ["peak_hour", "vehicle_type", "weather_condition", "restaurant_city"]:
        g = pr.groupby(col)["abs_error"].mean().sort_values()
        p = kruskal(col)
        sig = f"significant (p={p:.3f})" if p < 0.05 else f"not significant (p={p:.2f})"
        desc = (f"{g.index[0]} {g.iloc[0]:.1f} (best) to {g.index[-1]} {g.iloc[-1]:.1f} (worst)"
                if col == "restaurant_city" else ", ".join(f"{k}: {x:.1f}" for k, x in g.items()))
        out.append(f"| {col} | {desc} | {sig} |\n")
    out.append(f"\nThe largest 5% of errors exceed {pr['abs_error'].quantile(0.95):.0f} minutes. They come from "
               "deliveries far from the mean, which a model that predicts close to the mean misses.\n\n")
    out.append("### Feature importance (permutation, test set)\n\n"
               "| Feature | Importance (RMSE min) | ± std | Direction | Beyond noise? |\n|---|---|---|---|---|\n")
    for r in imp.head(10).itertuples():
        out.append(f"| {r.feature} | {r.importance:.4f} | {r.std:.4f} | {r.direction} | "
                   f"{r.distinguishable_from_noise} |\n")
    n_sig = int((imp["distinguishable_from_noise"] == "yes").sum())
    out.append(f"\nIn plain language: shuffling any single feature changes test RMSE by at most "
               f"{imp['importance'].max():.3f} minutes, and only {n_sig} of {len(imp)} features rise above noise. "
               + ("No feature can be named as a driver of delivery time on this dataset, so no operational "
                  "recommendation is made from this model.\n\n" if met["R2"] < 0.1 else
                  "See the table for which features matter and in which direction.\n\n"))
    return "".join(out)


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def write_model_report(
    cv_table: pd.DataFrame,
    tune_results: dict,
    test_metrics: dict,
    model_name: str,
    n_train: int,
    n_test: int,
) -> None:
    """Write delivery_model_report.md."""
    lines = [
        "# Delivery Time Model Report — Week 3\n\n",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  \n",
        f"**Target:** `delivery_time_minutes`  \n",
        f"**KPI targets:** R² ≥ {KPI_R2}  |  RMSE ≤ {KPI_RMSE} min  \n\n---\n\n",
        "## Dataset\n\n",
        f"| | |\n|---|---|\n",
        f"| Rows (model_df) | {n_train + n_test:,} |\n",
        f"| Train (80%) | {n_train:,} |\n",
        f"| Test  (20%) | {n_test:,} |\n",
        f"| Numeric features | {len([c for c in NUMERIC if c in cv_table.columns or True])} |\n",
        f"| Categorical features | {len(CATEGORICAL)} |\n\n",
        "## Feature List\n\n",
        "**Numeric:**  \n",
        ", ".join(f"`{c}`" for c in NUMERIC) + "\n\n",
        "**Categorical:**  \n",
        ", ".join(f"`{c}`" for c in CATEGORICAL) + "\n\n",
        "**Excluded (with reasons):**  \n",
    ]
    for col, reason in EXCLUDED.items():
        lines.append(f"- `{col}`: {reason}\n")

    lines += [
        "\n## Cross-Validation Comparison (training set, 5-fold)\n\n",
        "| Model | CV MAE | CV RMSE | CV RMSE std | CV R² |\n",
        "|---|---|---|---|---|\n",
    ]
    for _, row in cv_table.iterrows():
        lines.append(
            f"| {row['model']} | {row['cv_mae']} | {row['cv_rmse']} | "
            f"{row['cv_rmse_std']} | {row['cv_r2']} |\n"
        )

    lines += ["\n## Hyperparameter Tuning\n\n"]
    for mname, result in tune_results.items():
        lines += [
            f"### {mname}\n\n",
            f"- Before tuning: CV RMSE = {result['before_rmse']:.3f}\n",
            f"- After tuning:  CV RMSE = {result['after_rmse']:.3f}\n",
            f"- Best params: `{result['best_params']}`\n\n",
        ]

    met = test_metrics
    r2_ok   = "✅" if met["R2"]   >= KPI_R2   else "⚠️ below target"
    rmse_ok = "✅" if met["RMSE"] <= KPI_RMSE else "⚠️ below target"

    lines += [
        "\n## Test Set Results\n\n",
        f"**Winner: {model_name}**  \n\n",
        "| Metric | Value | KPI Target | Status |\n",
        "|---|---|---|---|\n",
        f"| MAE | {met['MAE']} min | — | On average prediction is off by {met['MAE']:.1f} min |\n",
        f"| RMSE | {met['RMSE']} min | ≤ {KPI_RMSE} min | {rmse_ok} |\n",
        f"| R² | {met['R2']} | ≥ {KPI_R2} | {r2_ok} |\n\n",
        interpretation_section(met),
        "## Saved artefacts\n\n",
        "- `models/delivery_time_model.joblib`\n",
        "- `data/cleaned/ml_model_comparison_delivery.csv`\n",
        "- `data/cleaned/ml_delivery_test_results.csv`\n",
        "- `images/delivery_residuals.png`\n",
        "- `images/delivery_feature_importance.png`\n",
    ]

    out = DOC_DIR / "delivery_model_report.md"
    out.write_text("".join(lines), encoding="utf-8")
    print(f"  → {out.relative_to(ROOT)} written")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    start = datetime.now()
    print("=" * 64)
    print("Zomato BI — Week 3 Steps 6–9: Delivery Time Model")
    print("=" * 64)

    MODEL_DIR.mkdir(exist_ok=True)

    # ── Load ABT ──────────────────────────────────────────────────────────
    print("\n[1] Loading ABT ...")
    abt = pd.read_csv(CLEAN_DIR / "analytical_base_table.csv")
    print(f"    ABT: {len(abt):,} rows × {len(abt.columns)} cols")

    # ── Step 6: Build dataset ─────────────────────────────────────────────
    print("\n[2] Building model dataset (Step 6) ...")
    X, y = build_model_dataset(abt)
    print(f"    model_df rows: {len(X):,}")
    print(f"    Numeric features:     {len([c for c in NUMERIC if c in X.columns])}")
    print(f"    Categorical features: {len([c for c in CATEGORICAL if c in X.columns])}")
    print(f"    Target mean:  {y.mean():.1f} min")
    print(f"    Target std:   {y.std():.1f} min")
    print(f"    Target range: {y.min():.0f} – {y.max():.0f} min")

    # ── Step 7: Split ─────────────────────────────────────────────────────
    print("\n[3] Splitting 80/20 (Step 7) ...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    cv = KFold(n_splits=5, shuffle=True, random_state=42)
    print(f"    Train: {len(X_train):,}  Test: {len(X_test):,}")

    # ── Step 7: Cross-validate ────────────────────────────────────────────
    print("\n[4] Cross-validating models (Step 7) ...")
    cv_table = compare_models(X_train, y_train, cv)
    print("\n    Cross-validation results:")
    print(cv_table.to_string(index=False))

    cv_table.to_csv(CLEAN_DIR / "ml_model_comparison_delivery.csv", index=False)
    print(f"\n    → data/cleaned/ml_model_comparison_delivery.csv saved")

    # ── Step 8: Tune top 2 ────────────────────────────────────────────────
    print("\n[5] Tuning top 2 models (Step 8) ...")
    best_names = cv_table[~cv_table["model"].str.contains("Baseline|Ridge")]["model"]
    top2 = best_names.head(2).tolist()
    print(f"    Tuning: {top2}")

    tune_results = {}
    best_estimator = None
    best_cv_rmse   = float("inf")

    # Param grids
    param_grids = {
        "Random Forest": {
            "model__n_estimators":    [100, 200, 300],
            "model__max_depth":       [None, 8, 12, 16],
            "model__min_samples_leaf":[1, 3, 5],
            "model__max_features":    ["sqrt", 0.5, 0.7],
        },
        "Gradient Boosting": {
            "model__n_estimators":    [100, 200, 400],
            "model__learning_rate":   [0.03, 0.05, 0.1],
            "model__max_depth":       [3, 4, 5],
            "model__subsample":       [0.7, 0.85, 1.0],
            "model__min_samples_leaf":[1, 5, 10],
        },
        "Decision Tree (depth=8)": {
            "model__max_depth":       [4, 6, 8, 10, None],
            "model__min_samples_leaf":[1, 5, 10, 20],
            "model__min_samples_split":[2, 10, 20],
        },
    }

    for mname in top2:
        model_obj = MODELS[mname][0]
        grid = param_grids.get(mname, {})
        before_rmse = cv_table.loc[cv_table["model"] == mname, "cv_rmse"].iloc[0]

        if not grid:
            print(f"    {mname}: no tuning grid, skipping")
            tune_results[mname] = {
                "before_rmse": before_rmse,
                "after_rmse": before_rmse,
                "best_params": {},
            }
            continue

        # Build a fresh estimator (same class, default params)
        fresh_model = model_obj.__class__(**{k: v for k, v in model_obj.get_params().items()
                                              if k in ["random_state","n_jobs"]})
        tuned, best_params, after_rmse = tune_model(
            mname, fresh_model, grid, X_train, y_train, cv, n_iter=20
        )
        tune_results[mname] = {
            "before_rmse": before_rmse,
            "after_rmse":  after_rmse,
            "best_params": best_params,
        }
        if after_rmse < best_cv_rmse:
            best_cv_rmse   = after_rmse
            best_estimator = tuned
            winner_name    = mname

    if best_estimator is None:
        # Fallback: use best model from CV without tuning
        winner_name   = top2[0]
        model_obj, scale = MODELS[winner_name]
        best_estimator = Pipeline([
            ("prep",  make_preprocessor(scale)),
            ("model", model_obj),
        ])
        best_estimator.fit(X_train, y_train)

    print(f"\n    Winner: {winner_name}  (CV RMSE = {best_cv_rmse:.3f})")

    # ── Step 9: Final evaluation ──────────────────────────────────────────
    print("\n[6] Final test-set evaluation (Step 9, test opened ONCE) ...")
    test_metrics, pred = evaluate(best_estimator, X_test, y_test)
    print(f"    MAE : {test_metrics['MAE']:.3f} min")
    print(f"    RMSE: {test_metrics['RMSE']:.3f} min  (KPI: ≤{KPI_RMSE} min)")
    print(f"    R²  : {test_metrics['R2']:.4f}        (KPI: ≥{KPI_R2})")

    r2_ok   = test_metrics["R2"]   >= KPI_R2
    rmse_ok = test_metrics["RMSE"] <= KPI_RMSE
    print(f"    R² KPI:   {'✅ PASS' if r2_ok   else '⚠️ BELOW TARGET'}")
    print(f"    RMSE KPI: {'✅ PASS' if rmse_ok else '⚠️ BELOW TARGET'}")

    # ── Residual + importance plots ───────────────────────────────────────
    print("\n[7] Saving residual and importance plots ...")
    plot_residuals(y_test, pred, winner_name)
    save_prediction_export(abt, X_test, y_test, pred)
    plot_feature_importance(best_estimator, X_test, y_test, winner_name)

    # ── Save artefacts ────────────────────────────────────────────────────
    print("\n[8] Saving artefacts ...")
    model_path = MODEL_DIR / "delivery_time_model.joblib"
    joblib.dump(best_estimator, model_path)
    joblib.dump(best_estimator, MODEL_DIR / "delivery_time_best_model.pkl")
    import json, sklearn
    meta_path = MODEL_DIR / "model_metadata.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    meta["delivery_model"] = {
        "target": TARGET, "model": winner_name, "model_file": "delivery_time_best_model.pkl",
        "sklearn_version": sklearn.__version__, "trained_on": str(pd.Timestamp.today().date()),
        "test_metrics": test_metrics, "kpi_r2_target": KPI_R2, "kpi_rmse_target_min": KPI_RMSE,
        "features": {"numeric": NUMERIC, "categorical": CATEGORICAL},
    }
    meta_path.write_text(json.dumps(meta, indent=2, default=float))
    print(f"    → {model_path.relative_to(ROOT)}")

    # Test predictions CSV
    test_df = pd.DataFrame({
        "actual_minutes":    y_test.values,
        "predicted_minutes": pred.round(1),
        "residual":          (y_test.values - pred).round(1),
    })
    test_df.to_csv(CLEAN_DIR / "ml_delivery_test_results.csv", index=False)
    print(f"    → data/cleaned/ml_delivery_test_results.csv")

    # Model report
    write_model_report(
        cv_table, tune_results, test_metrics,
        winner_name, len(X_train), len(X_test),
    )

    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n{'='*64}")
    print(f"Steps 6–9 COMPLETE ✅  ({elapsed:.0f}s)")
    print(f"  CV comparison  → data/cleaned/ml_model_comparison_delivery.csv")
    print(f"  Best model     → models/delivery_time_model.joblib")
    print(f"  Test results   → data/cleaned/ml_delivery_test_results.csv")
    print(f"  Report         → documentation/delivery_model_report.md")
    print(f"{'='*64}")


if __name__ == "__main__":
    main()
