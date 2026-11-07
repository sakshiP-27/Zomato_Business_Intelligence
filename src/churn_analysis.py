"""
src/churn_analysis.py
---------------------
Week 3, Steps 11-13 (churn): finishing work on top of the saved churn model.

  Step 11: imbalance experiment (no handling vs class_weight='balanced')
  Step 12: plain-words threshold interpretation
  Step 13: data-driven driver direction + risk segments whose band edges
           come from the TRAINING out-of-fold probability distribution,
           plus a check that the segments actually separate churners.

Uses the already-trained models/churn_best_model.pkl. The test set is only
used for reporting, never for choosing thresholds or band edges.

Usage:
    python src/churn_analysis.py
"""

import sys
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import (
    StratifiedKFold, cross_val_predict, cross_validate, train_test_split,
)
from sklearn.pipeline import Pipeline

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.model_churn import (  # noqa: E402
    CHURN_CATEGORICAL, CHURN_NUMERIC, HORIZON,
    build_churn_dataset, make_churn_preprocessor,
)

CLEAN = ROOT / "data" / "cleaned"
MODELS = ROOT / "models"
DOC = ROOT / "documentation"


def load_inputs():
    """Load cleaned orders/customers and build the time-ordered churn dataset."""
    orders = pd.read_csv(CLEAN / "orders.csv")
    customers = pd.read_csv(CLEAN / "customers.csv")
    orders["order_date"] = pd.to_datetime(orders["order_date"], errors="coerce")
    orders["final_amount"] = pd.to_numeric(orders["final_amount"], errors="coerce")
    orders["delivery_time_minutes"] = pd.to_numeric(orders["delivery_time_minutes"], errors="coerce")
    ref_date = orders["order_date"].max()
    cutoff = ref_date - pd.Timedelta(days=HORIZON)
    churn_df = build_churn_dataset(orders, customers, cutoff, HORIZON)
    return orders, customers, ref_date, cutoff, churn_df


def imbalance_experiment(X_train, y_train, cv) -> pd.DataFrame:
    """Compare no handling vs class_weight='balanced' (CV on training data only)."""
    rows = []
    configs = [
        ("Logistic Regression", True,
         lambda cw: LogisticRegression(max_iter=1000, class_weight=cw, random_state=42)),
        ("Random Forest", False,
         lambda cw: RandomForestClassifier(n_estimators=200, class_weight=cw,
                                           n_jobs=-1, random_state=42)),
    ]
    for name, scale, make in configs:
        for label, cw in [("(a) no handling", None), ("(b) class_weight=balanced", "balanced")]:
            pipe = Pipeline([("prep", make_churn_preprocessor(scale)), ("model", make(cw))])
            res = cross_validate(
                pipe, X_train, y_train, cv=cv, n_jobs=-1,
                scoring={"f1": "f1", "precision": "precision", "recall": "recall",
                         "roc_auc": "roc_auc", "pr_auc": "average_precision"},
            )
            rows.append({
                "model": name, "imbalance_option": label,
                "cv_f1": round(res["test_f1"].mean(), 4),
                "cv_precision": round(res["test_precision"].mean(), 4),
                "cv_recall": round(res["test_recall"].mean(), 4),
                "cv_roc_auc": round(res["test_roc_auc"].mean(), 4),
                "cv_pr_auc": round(res["test_pr_auc"].mean(), 4),
            })
    return pd.DataFrame(rows)


def driver_directions(churn_df, features) -> pd.DataFrame:
    """
    Data-driven direction: standardized difference in means (churned - active).
    Positive = higher values go with churn; |d| < 0.05 is treated as no real difference.
    """
    out = []
    for col in features:
        a = churn_df.loc[churn_df["churned"] == 1, col]
        b = churn_df.loc[churn_df["churned"] == 0, col]
        pooled = np.sqrt((a.var() + b.var()) / 2)
        d = (a.mean() - b.mean()) / pooled if pooled and not np.isnan(pooled) else np.nan
        if np.isnan(d) or abs(d) < 0.05:
            direction = "no meaningful difference"
        elif d > 0:
            direction = "higher values go with churn"
        else:
            direction = "higher values go with staying"
        out.append({"feature": col, "mean_churned": round(a.mean(), 3),
                    "mean_active": round(b.mean(), 3),
                    "std_diff": round(d, 3) if not np.isnan(d) else np.nan,
                    "direction": direction})
    return pd.DataFrame(out)


def main() -> None:
    orders, customers, ref_date, cutoff, churn_df = load_inputs()
    num = [c for c in CHURN_NUMERIC if c in churn_df.columns]
    cat = [c for c in CHURN_CATEGORICAL if c in churn_df.columns]
    X, y = churn_df[num + cat], churn_df["churned"]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    # ---------------- Step 11: imbalance experiment ----------------
    print("[Step 11] Imbalance experiment (training CV) ...")
    imb = imbalance_experiment(X_train, y_train, cv)
    imb.to_csv(CLEAN / "ml_churn_imbalance_experiment.csv", index=False)
    print(imb.to_string(index=False))

    # ---------------- Step 12: threshold in plain words ----------------
    model = joblib.load(MODELS / "churn_best_model.pkl")
    proba_test = model.predict_proba(X_test)[:, 1]
    meta_path = MODELS / "model_metadata.json"
    import json
    meta = json.loads(meta_path.read_text())
    thr = meta["churn_model"]["churn_threshold"]
    pred = (proba_test >= thr).astype(int)
    flagged = int(pred.sum())
    print(f"\n[Step 12] Threshold {thr:.3f}: flags {flagged}/{len(pred)} test customers "
          f"({flagged/len(pred):.1%}); of those, {y_test[pred == 1].mean():.1%} really churned "
          f"(overall churn rate {y_test.mean():.1%}).")

    # ---------------- Step 13: risk bands from TRAINING OOF probabilities ----------------
    print("\n[Step 13] Computing band edges from training out-of-fold probabilities ...")
    oof = cross_val_predict(model, X_train, y_train, cv=cv, method="predict_proba")[:, 1]
    low_edge, high_edge = np.percentile(oof, [33.3, 66.7])
    edges = [0.0, float(low_edge), float(high_edge), 1.0]
    print(f"  Low < {low_edge:.3f} <= Medium < {high_edge:.3f} <= High")

    def segment(p):
        return pd.cut(p, bins=edges, labels=["Low", "Medium", "High"], include_lowest=True)

    cust_info = customers[["customer_id", "city", "membership"]].rename(
        columns={"city": "customer_city"})

    scores = pd.DataFrame({
        "customer_id": churn_df.loc[X_test.index, "customer_id"].values,
        "churn_probability": proba_test.round(4),
        "predicted_label": pred,
        "actual_label": y_test.values,
    })
    scores["risk_segment"] = segment(scores["churn_probability"])
    scores.drop(columns=[]).to_csv(CLEAN / "churn_scores.csv", index=False)
    scores.merge(cust_info, on="customer_id", how="left").to_csv(
        CLEAN / "ml_churn_scores_test.csv", index=False)

    seg_check = (scores.groupby("risk_segment", observed=True)
                 .agg(customers=("customer_id", "count"),
                      actual_churn_rate=("actual_label", "mean")).round(4))
    print("\n  Do the segments separate churners? (test set, reporting only)")
    print(seg_check.to_string())
    seg_check.reset_index().to_csv(CLEAN / "ml_churn_segment_check.csv", index=False)

    # Forward-looking scores for every customer as of the latest date
    cur = build_churn_dataset(orders, customers, ref_date, HORIZON)
    Xc = cur[[c for c in num + cat if c in cur.columns]]
    pc = model.predict_proba(Xc)[:, 1]
    cur_scores = pd.DataFrame({"customer_id": cur["customer_id"].values,
                               "churn_probability": pc.round(4),
                               "predicted_label": (pc >= thr).astype(int)})
    cur_scores["risk_segment"] = segment(cur_scores["churn_probability"])
    cur_scores.to_csv(CLEAN / "churn_scores_current.csv", index=False)
    print(f"\n  Current (forward-looking) segments: "
          f"{cur_scores['risk_segment'].value_counts().to_dict()}")

    # Data-driven driver directions merged into the importance export
    dirs = driver_directions(churn_df, num)
    from sklearn.inspection import permutation_importance
    pi = permutation_importance(model, X_test, y_test, n_repeats=10, random_state=42,
                                scoring="roc_auc", n_jobs=-1)
    imp = pd.DataFrame({"feature": X_test.columns, "importance": pi.importances_mean,
                        "std": pi.importances_std})
    imp = imp.merge(dirs[["feature", "std_diff", "direction"]], on="feature", how="left")
    imp["direction"] = imp["direction"].fillna("categorical - see model report")
    imp["distinguishable_from_noise"] = (imp["importance"] > 2 * imp["std"]).map(
        {True: "yes", False: "no"})
    imp = imp.sort_values("importance", ascending=False)
    imp.to_csv(CLEAN / "ml_churn_feature_importance.csv", index=False)
    print("\n  Top 10 drivers (permutation importance, with measured direction):")
    print(imp.head(10)[["feature", "importance", "std", "direction",
                        "distinguishable_from_noise"]].to_string(index=False))

    # Keep metadata in sync with the bands actually used
    meta["churn_model"]["risk_bands"] = {
        "Low": [0.0, round(float(low_edge), 3)],
        "Medium": [round(float(low_edge), 3), round(float(high_edge), 3)],
        "High": [round(float(high_edge), 3), 1.0],
        "method": "terciles of training out-of-fold probabilities",
    }
    meta_path.write_text(json.dumps(meta, indent=2))
    print("\n  models/model_metadata.json updated with the real band edges")
    write_addendum(imb, thr, flagged, len(pred), y_test, pred, low_edge, high_edge, seg_check, imp, churn_df)


def write_addendum(imb, thr, flagged, n, y_test, pred, low_edge, high_edge, seg_check, imp, churn_df):
    """Replace the Steps 11-13 section of churn_model_report.md with computed text."""
    from sklearn.metrics import roc_auc_score
    s = pd.read_csv(CLEAN / "ml_churn_scores_test.csv")
    auc = roc_auc_score(s["actual_label"], s["churn_probability"])
    rates = seg_check["actual_churn_rate"]
    separates = rates.max() - rates.min() >= 0.05
    noise_ok = imp[imp["distinguishable_from_noise"] == "yes"]["feature"].tolist()
    lines = ["## Steps 11-13 Addendum (computed by src/churn_analysis.py)\n\n",
             "**Imbalance experiment (training CV, `data/cleaned/ml_churn_imbalance_experiment.csv`):**\n\n",
             "| Model | Option | F1 | ROC-AUC | PR-AUC |\n|---|---|---|---|---|\n"]
    lines += [f"| {r.model} | {r.imbalance_option} | {r.cv_f1} | {r.cv_roc_auc} | {r.cv_pr_auc} |\n"
              for r in imb.itertuples()]
    lines += [f"\nAccuracy would mislead here: predicting churn for everyone is {y_test.mean():.1%} accurate. "
              "`class_weight=balanced` is the documented default.\n\n",
              f"**Threshold in plain words:** the F1-maximising threshold ({thr:.3f}) flags {flagged} of {n} "
              f"test customers ({flagged / n:.1%}); of those, {y_test[pred == 1].mean():.1%} actually churned, "
              f"against an overall churn rate of {y_test.mean():.1%}.\n\n",
              f"**Risk segments:** band edges are terciles of the training out-of-fold probabilities "
              f"(Low < {low_edge:.3f}, Medium {low_edge:.3f}-{high_edge:.3f}, High >= {high_edge:.3f}). "
              "Actual churn rate per segment on the test set: "
              + ", ".join(f"{k} {v:.1%}" for k, v in rates.items())
              + (". The segments separate churners and can be used to prioritise offers.\n\n" if separates else
                 ". The segments do not separate churners, so they should not be used to target offers.\n\n"),
              f"**Drivers:** {len(noise_ok)} of {len(imp)} features have permutation importance clearly above "
              f"noise ({', '.join(noise_ok) if noise_ok else 'none'}); measured directions are in "
              "`ml_churn_feature_importance.csv`.\n\n",
              f"**Conclusion:** test ROC-AUC is {auc:.2f}. "
              + ("The churn label is not predictable from the available features in this dataset; the F1 KPI is "
                 "met only because most customers churn, and no retention recommendation is supported.\n\n"
                 if auc < 0.6 else "The model ranks customers better than chance; see the segments above.\n\n")]
    rp = DOC / "churn_model_report.md"
    t = rp.read_text()
    if "## Steps 11-13 Addendum" in t:
        t = t[:t.index("## Steps 11-13 Addendum")] + t[t.index("## Saved Artefacts"):]
    t = t.replace("## Saved Artefacts", "".join(lines) + "## Saved Artefacts", 1)
    rp.write_text(t)
    print("  documentation/churn_model_report.md addendum written")


if __name__ == "__main__":
    main()
