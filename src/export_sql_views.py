"""
src/export_sql_views.py
-----------------------
Week 4, Step 1: exports Power BI cannot rebuild safely on its own.

  1. data/cleaned/restaurant_performance.csv
     The Week 1 view v_restaurant_performance, read from PostgreSQL so the
     dashboard uses the same scores as the SQL queries.

  2. data/cleaned/ml_test_metrics.csv
     Test-set R², RMSE, ROC-AUC, and F1 from models/model_metadata.json.
     These are single numbers, not row-level predictions.

Usage (from the project root, after the cleaning pipeline):
    python src/export_sql_views.py

Requires DATABASE_URL in .env for the restaurant view.
The metrics file is written even if the database is unreachable.
"""

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
CLEAN_DIR = ROOT / "data" / "cleaned"
MODEL_META = ROOT / "models" / "model_metadata.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")


def _sql_round(series: pd.Series, digits: int) -> pd.Series:
    """Round half away from zero, matching PostgreSQL ROUND(numeric, digits)."""
    factor = 10 ** digits
    values = pd.to_numeric(series, errors="coerce")
    rounded = np.sign(values) * np.floor(np.abs(values) * factor + 0.5) / factor
    return rounded


def _percent_rank(series: pd.Series, nulls: str) -> pd.Series:
    """
    PostgreSQL PERCENT_RANK() within one city.

    nulls='first' matches ORDER BY ... NULLS FIRST.
    nulls='last' matches the default NULLS LAST.
    A city with one restaurant scores 0, as PostgreSQL does.
    """
    n = len(series)
    if n <= 1:
        return pd.Series(0.0, index=series.index)
    na_option = "top" if nulls == "first" else "bottom"
    rank = series.rank(method="min", ascending=True, na_option=na_option)
    return (rank - 1) / (n - 1)


def restaurant_performance_from_cleaned() -> pd.DataFrame:
    """
    Same calculation as v_restaurant_performance, using the cleaned CSVs.

    Used when PostgreSQL is not configured. The formula is the Week 1 view:
    restaurants with at least 10 orders, scored within their city as
    0.4 * rating rank + 0.3 * (1 - cancellation rank) + 0.3 * (1 - speed rank).
    """
    orders = pd.read_csv(CLEAN_DIR / "orders.csv")
    restaurants = pd.read_csv(CLEAN_DIR / "restaurants.csv")
    orders["delivery_time_minutes"] = pd.to_numeric(orders["delivery_time_minutes"], errors="coerce")
    orders["final_amount"] = pd.to_numeric(orders["final_amount"], errors="coerce")

    delivered = orders["order_status"].isin(["Delivered", "Delivered Late"]) & (orders["final_amount"] > 0)
    valid_time = orders["delivery_time_minutes"] > 0
    work = orders.assign(
        is_cancelled=(orders["order_status"] == "Cancelled").astype(float),
        revenue=np.where(delivered, orders["final_amount"], 0.0),
        valid_delivery_time=np.where(valid_time, orders["delivery_time_minutes"], np.nan),
    )
    stats = (work.groupby("restaurant_id", as_index=False)
                 .agg(total_orders=("order_id", "count"),
                      cancel_rate=("is_cancelled", "mean"),
                      avg_delivery_min=("valid_delivery_time", "mean"),
                      total_revenue=("revenue", "sum")))
    stats = stats[stats["total_orders"] >= 10].copy()

    keep = ["restaurant_id", "restaurant_name", "city", "cuisine",
            "restaurant_type", "rating"]
    stats = stats.merge(restaurants[keep], on="restaurant_id", how="left", validate="m:1")
    stats = stats.rename(columns={"rating": "restaurant_rating"})
    stats["cancel_rate"] = _sql_round(stats["cancel_rate"], 4)
    stats["avg_delivery_min"] = _sql_round(stats["avg_delivery_min"], 1)
    stats["total_revenue"] = _sql_round(stats["total_revenue"], 2)

    grouped = stats.groupby("city", dropna=False)
    stats["performance_score"] = _sql_round(
        0.4 * grouped["restaurant_rating"].transform(lambda s: _percent_rank(s, "first"))
        + 0.3 * (1.0 - grouped["cancel_rate"].transform(lambda s: _percent_rank(s, "last")))
        + 0.3 * (1.0 - grouped["avg_delivery_min"].transform(lambda s: _percent_rank(s, "last"))),
        3,
    )
    columns = [
        "restaurant_id", "restaurant_name", "city", "cuisine", "restaurant_type",
        "restaurant_rating", "total_orders", "cancel_rate", "avg_delivery_min",
        "total_revenue", "performance_score",
    ]
    return stats[columns].sort_values(["city", "performance_score"], ascending=[True, False])


def export_restaurant_performance() -> Path:
    """
    Save v_restaurant_performance next to the cleaned CSVs.

    Reads the live view when DATABASE_URL is set. Otherwise applies the
    view's formula to the cleaned orders and restaurants.
    """
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        url = database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
        elif url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg2://", 1)
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            frame = pd.read_sql(text("SELECT * FROM v_restaurant_performance"), conn)
        source = "PostgreSQL view v_restaurant_performance"
    else:
        frame = restaurant_performance_from_cleaned()
        source = (
            "cleaned CSVs, using the v_restaurant_performance formula "
            "(no DATABASE_URL in .env, so the live view was not queried)"
        )

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    path = CLEAN_DIR / "restaurant_performance.csv"
    frame.to_csv(path, index=False)
    print(f"  restaurant_performance.csv  ({len(frame):,} rows) — {source}")
    return path


def export_ml_test_metrics() -> Path:
    """
    Write the four test metrics the ML page cannot calculate in DAX.

    Values come from the saved model metadata, which records the one time
    the test set was opened.
    """
    meta = json.loads(MODEL_META.read_text(encoding="utf-8"))
    delivery = meta["delivery_model"]["test_metrics"]
    churn = meta["churn_model"]["test_metrics"]
    frame = pd.DataFrame([
        {"model": "delivery", "metric": "r2", "value": delivery["R2"]},
        {"model": "delivery", "metric": "rmse", "value": delivery["RMSE"]},
        {"model": "churn", "metric": "roc_auc", "value": churn["roc_auc"]},
        {"model": "churn", "metric": "f1", "value": churn["f1"]},
    ])
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    path = CLEAN_DIR / "ml_test_metrics.csv"
    frame.to_csv(path, index=False)
    print("  ml_test_metrics.csv")
    print(frame.to_string(index=False))
    return path


def main() -> None:
    print("=" * 64)
    print("Zomato BI — Week 4 Step 1 exports")
    print("=" * 64)
    export_ml_test_metrics()
    print()
    try:
        export_restaurant_performance()
    except Exception as exc:
        print(f"  restaurant_performance.csv was NOT written: {exc}")
        raise SystemExit(1) from exc
    print("=" * 64)


if __name__ == "__main__":
    main()
