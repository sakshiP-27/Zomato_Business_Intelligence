"""
src/ingest.py
-------------
Step 4: Load all 12 raw CSVs into the 'staging' schema.

Every column is loaded as TEXT — no type conversion, no constraints,
no data loss. This preserves the raw data exactly as-is so that every
data-quality problem can be measured and logged in Step 5.

Usage:
    python src/ingest.py

Re-runnable: drops and recreates all staging tables on every run
(if_exists='replace'), so it is safe to run multiple times.

PRD requirement: FR-10 (repeatable, automated data load).
"""

import os
import re
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"

load_dotenv(ROOT / ".env")
DATABASE_URL = os.getenv("DATABASE_URL")


def sqlalchemy_url(database_url: str) -> str:
    """SQLAlchemy needs a postgresql+psycopg2:// prefix."""
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg2://", 1)
    return database_url

# Expected row counts from Step 1 inspection (used for reconciliation check)
EXPECTED_ROWS = {
    "cities":            25,
    "customers":         12180,
    "restaurants":       1200,
    "delivery_partners": 2000,
    "menu":              8997,
    "orders":            20705,
    "order_items":       42378,
    "payments":          20493,
    "customer_feedback": 14200,
    "promotions":        300,
    "weather":           18264,
    "traffic":           18335,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def to_snake(name: str) -> str:
    """
    Convert CamelCase CSV header to snake_case.
    Examples:
        OrderID              -> order_id
        DeliveryTimeMinutes  -> delivery_time_minutes
        FoodItemID           -> food_item_id
    """
    name = name.strip()
    # Insert underscore before every uppercase letter that follows a lowercase
    # letter or digit (handles ID suffix: CustomerID -> Customer_ID -> customer_id)
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    return name.lower()


def print_header(msg: str) -> None:
    print("\n" + "=" * 62)
    print(msg)
    print("=" * 62)


def print_section(msg: str) -> None:
    print("\n" + "-" * 50)
    print(msg)
    print("-" * 50)


# ---------------------------------------------------------------------------
# Week 2 — DataFrame loaders (load_raw / load_all)
# Returns DataFrames (all columns as str) for the Python cleaning pipeline.
# Separate from the staging DB loader above; both use the same to_snake().
# ---------------------------------------------------------------------------

TABLES = [
    "cities", "customers", "restaurants", "menu",
    "delivery_partners", "promotions", "orders",
    "order_items", "payments", "customer_feedback",
    "weather", "traffic",
]


def load_raw(table: str) -> pd.DataFrame:
    """
    Read one raw CSV as text (dtype=str), with snake_case column names.

    Args:
        table: Name of the CSV file without extension (e.g. 'orders').

    Returns:
        DataFrame with all columns as str and snake_case headers.

    Raises:
        FileNotFoundError: If the CSV file does not exist in data/raw/.
    """
    path = RAW_DIR / f"{table}.csv"
    try:
        df = pd.read_csv(path, dtype=str)
    except FileNotFoundError as err:
        raise FileNotFoundError(f"Raw file not found: {path}") from err
    df.columns = [to_snake(c) for c in df.columns]
    return df


def load_all() -> dict:
    """
    Load all 12 raw CSVs into a dict of DataFrames.

    Returns:
        Dict mapping table name -> DataFrame (all columns as str).
    """
    return {t: load_raw(t) for t in TABLES}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    start_time = datetime.now()

    if not DATABASE_URL:
        sys.exit("ERROR: DATABASE_URL not found in .env")
    SQLALCHEMY_URL = sqlalchemy_url(DATABASE_URL)

    print_header("Zomato BI — Step 4: Load Raw CSVs → staging schema")
    print(f"Raw data dir : {RAW_DIR.relative_to(ROOT)}")
    print(f"Target       : staging schema (Supabase / PostgreSQL)")
    print(f"Started      : {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. Discover CSV files
    csv_files = sorted(RAW_DIR.glob("*.csv"))
    if not csv_files:
        sys.exit(f"ERROR: No CSV files found in {RAW_DIR}")
    print(f"CSV files    : {len(csv_files)} found")

    # 2. Create SQLAlchemy engine (connection pool for Supabase)
    print("\nConnecting to database ...")
    try:
        engine = create_engine(
            SQLALCHEMY_URL,
            pool_pre_ping=True,      # test connection before using it
            connect_args={
                "connect_timeout": 30,
                "options": "-c statement_timeout=300000"  # 5 min per statement
            }
        )
        # Quick connectivity test
        with engine.connect() as conn:
            result = conn.execute(text("SELECT current_database(), pg_size_pretty(pg_database_size(current_database()))"))
            db_name, db_size = result.fetchone()
        print(f"Connected    : database='{db_name}', size={db_size}")
    except Exception as e:
        sys.exit(f"ERROR: Could not connect — {e}")

    # 3. Create staging schema
    print("\nCreating staging schema ...")
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS staging"))
        print("  staging schema ready ✅")
    except Exception as e:
        sys.exit(f"ERROR: Could not create staging schema — {e}")

    # 4. Load each CSV
    print_section("Loading CSVs into staging")

    results = []
    total_rows_loaded = 0

    for csv_path in csv_files:
        table_name = csv_path.stem   # e.g. "orders" from "orders.csv"
        expected = EXPECTED_ROWS.get(table_name, None)

        try:
            # Read everything as str — no type inference, no silent coercions
            df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)

            # Convert headers to snake_case to match schema.sql column names
            original_cols = list(df.columns)
            df.columns = [to_snake(c) for c in df.columns]
            snake_cols = list(df.columns)

            csv_rows = len(df)

            # Load to staging — replace on every run (idempotent)
            df.to_sql(
                name=table_name,
                con=engine,
                schema="staging",
                if_exists="replace",   # drop & recreate staging table each run
                index=False,
                chunksize=5000,
                method="multi"         # faster bulk insert via multi-row VALUES
            )

            # Verify row count from DB
            with engine.connect() as conn:
                db_count = conn.execute(
                    text(f"SELECT COUNT(*) FROM staging.{table_name}")
                ).scalar()

            count_ok = (db_count == csv_rows)
            expected_ok = (expected is None) or (csv_rows == expected)
            status = "✅" if (count_ok and expected_ok) else "⚠️ "

            total_rows_loaded += db_count

            results.append({
                "table":      table_name,
                "csv_rows":   csv_rows,
                "db_rows":    db_count,
                "count_ok":   count_ok,
                "expected":   expected,
                "expected_ok": expected_ok,
                "columns":    len(df.columns),
                "status":     status,
            })

            exp_str = f"(expected {expected:,})" if expected else ""
            print(f"  {status} staging.{table_name:<22} {db_count:>6,} rows  {exp_str}")

        except Exception as e:
            print(f"  ❌ {table_name}: FAILED — {e}")
            results.append({
                "table": table_name, "csv_rows": 0, "db_rows": 0,
                "count_ok": False, "expected": expected, "expected_ok": False,
                "columns": 0, "status": "❌",
            })

    # 5. Column name verification
    print_section("Column name spot-check (CSV header → snake_case)")

    schema_expected = {
        "cities":            ["city_id", "city", "population", "region", "average_income"],
        "customers":         ["customer_id", "name", "age", "gender", "phone", "email",
                              "city", "state", "pincode", "registration_date",
                              "membership", "total_orders", "preferred_cuisine"],
        "restaurants":       ["restaurant_id", "restaurant_name", "cuisine", "city", "area",
                              "opening_time", "closing_time", "rating", "average_cost",
                              "owner_name", "restaurant_type", "latitude", "longitude"],
        "delivery_partners": ["delivery_partner_id", "name", "age", "gender", "vehicle_type",
                              "joining_date", "city", "rating", "completed_deliveries",
                              "average_delivery_time"],
        "menu":              ["food_item_id", "restaurant_id", "food_name", "category",
                              "price", "preparation_time", "calories", "availability"],
        "orders":            ["order_id", "customer_id", "restaurant_id", "delivery_partner_id",
                              "order_date", "order_time", "delivery_time_minutes",
                              "food_cost", "delivery_fee", "discount", "coupon_code",
                              "gst", "final_amount", "order_status", "payment_method"],
        "order_items":       ["order_item_id", "order_id", "food_item_id", "quantity",
                              "unit_price", "total_price"],
        "payments":          ["payment_id", "order_id", "payment_method", "payment_status",
                              "transaction_id", "payment_date"],
        "customer_feedback": ["feedback_id", "order_id", "customer_rating", "delivery_rating",
                              "food_rating", "review", "sentiment"],
        "promotions":        ["promotion_id", "coupon_code", "discount_percentage",
                              "campaign_name", "start_date", "end_date"],
        "weather":           ["weather_id", "city", "date", "temperature", "rainfall",
                              "humidity", "weather_condition"],
        "traffic":           ["traffic_id", "city", "date", "time", "traffic_level",
                              "average_speed"],
    }

    col_mismatches = 0
    for csv_path in sorted(csv_files):
        stem = csv_path.stem
        df_cols = pd.read_csv(csv_path, dtype=str, nrows=0)
        actual_cols = [to_snake(c) for c in df_cols.columns]
        expected_cols = schema_expected.get(stem, [])

        if actual_cols == expected_cols:
            print(f"  ✅ {stem:<25} {len(actual_cols)} columns match schema")
        else:
            col_mismatches += 1
            print(f"  ❌ {stem}: COLUMN MISMATCH")
            for a, e in zip(actual_cols, expected_cols or [""]*len(actual_cols)):
                flag = "  ← MISMATCH" if a != e else ""
                print(f"       CSV:{a:<35} Schema:{e}{flag}")

    if col_mismatches == 0:
        print("\n  All 12 tables: column names match schema.sql ✅")

    # 6. Reconciliation table
    print_section("Reconciliation: CSV rows vs staging rows vs expected")
    print(f"  {'Table':<25} {'CSV':>7} {'Staging':>8} {'Expected':>9}  Match?")
    print(f"  {'-'*25} {'-'*7} {'-'*8} {'-'*9}  {'------'}")

    all_ok = True
    for r in results:
        exp_str = f"{r['expected']:>9,}" if r['expected'] else "       N/A"
        match_str = "✅" if r["count_ok"] else "❌"
        if r["expected"] and not r["expected_ok"]:
            match_str += " ⚠ expected mismatch"
        print(f"  {r['table']:<25} {r['csv_rows']:>7,} {r['db_rows']:>8,} {exp_str}  {match_str}")
        if not r["count_ok"]:
            all_ok = False

    print(f"\n  Total rows loaded into staging: {total_rows_loaded:,}")

    # 7. Verify staging schema in DB
    print_section("Staging schema: final verification")
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT table_name,
                   (SELECT COUNT(*) FROM information_schema.columns
                    WHERE table_schema = 'staging' AND table_name = t.table_name) AS col_count
            FROM information_schema.tables t
            WHERE table_schema = 'staging'
            ORDER BY table_name;
        """)).fetchall()

    print(f"  {'Table':<25} {'Columns':>7}")
    print(f"  {'-'*25} {'-'*7}")
    for tbl, cols in rows:
        print(f"  {tbl:<25} {cols:>7}")
    print(f"\n  Total staging tables: {len(rows)}")

    # 8. Final summary
    elapsed = (datetime.now() - start_time).total_seconds()
    print_header("Step 4 Summary")
    print(f"  Tables loaded     : {len([r for r in results if r['status'] == '✅'])}/{len(results)}")
    print(f"  Total rows        : {total_rows_loaded:,}")
    print(f"  Column mismatches : {col_mismatches}")
    print(f"  Time elapsed      : {elapsed:.1f}s")
    print()

    if all_ok and col_mismatches == 0 and len(rows) == 12:
        print("Step 4 COMPLETE ✅")
        print("staging schema contains all 12 tables with correct column names.")
        print("All staging row counts match their source CSVs.")
        print("\nNext: python src/profile.py   (Step 5 — data quality log)")
    else:
        print("Step 4 completed WITH WARNINGS — review output above.")

    print("=" * 62)


if __name__ == "__main__":
    main()
