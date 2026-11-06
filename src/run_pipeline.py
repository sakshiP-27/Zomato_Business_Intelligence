"""
src/run_pipeline.py
-------------------
Week 2, Step 7: One-command reproducible pipeline.

Loads raw CSVs → cleans all 12 tables → saves cleaned CSVs → builds the
analytical base table → saves cleaning log. Fully idempotent.

Usage:
    python -m src.run_pipeline

Or from the project root:
    python src/run_pipeline.py
"""

import sys
import time
from pathlib import Path
from datetime import datetime

# Ensure project root is on the path when run as a script
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ingest import load_all
from src.clean import CleaningLog, DataCleaner, CITY_ALIASES
from src.features import build_analytical_base_table, add_features, build_customer_features

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CLEAN_DIR = ROOT / "data" / "cleaned"
DOC_DIR   = ROOT / "documentation"
LOG_PATH  = DOC_DIR / "cleaning_log.csv"
ABT_PATH  = CLEAN_DIR / "analytical_base_table.csv"

# Tables to save as individual cleaned CSVs
TABLES = [
    "cities", "customers", "restaurants", "delivery_partners",
    "promotions", "weather", "traffic", "menu",
    "orders", "order_items", "payments", "customer_feedback",
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    start = datetime.now()
    print("=" * 64)
    print("Zomato BI — Week 2 Pipeline: Raw → Cleaned → ABT")
    print("=" * 64)
    print(f"Started : {start.strftime('%Y-%m-%d %H:%M:%S')}\n")

    # 1. Ensure output directories exist
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    DOC_DIR.mkdir(parents=True, exist_ok=True)

    # 2. Load raw CSVs
    print("Step 1: Loading raw CSVs ...")
    t0 = time.time()
    raw = load_all()
    total_raw = sum(len(df) for df in raw.values())
    print(f"  Loaded {len(raw)} tables, {total_raw:,} total rows  ({time.time()-t0:.1f}s)\n")

    # 3. Clean all tables
    print("Step 2: Cleaning all 12 tables ...")
    t0 = time.time()
    cities_list = raw["cities"]["city"].dropna().str.strip().tolist()
    log = CleaningLog()
    cleaner = DataCleaner(cities_list, CITY_ALIASES, log)
    cleaned = cleaner.clean_all(raw)
    total_clean = sum(len(df) for df in cleaned.values())
    print(f"  Cleaned {len(cleaned)} tables, {total_clean:,} total rows  ({time.time()-t0:.1f}s)")

    # Print row-count comparison
    print(f"\n  {'Table':<25} {'Raw':>7} {'Cleaned':>8} {'Δ':>6}")
    print(f"  {'-'*25} {'-'*7} {'-'*8} {'-'*6}")
    for table in TABLES:
        raw_n = len(raw.get(table, []))
        clean_n = len(cleaned.get(table, []))
        delta = clean_n - raw_n
        print(f"  {table:<25} {raw_n:>7,} {clean_n:>8,} {delta:>+6,}")

    # 4. Save cleaned CSVs
    print(f"\nStep 3: Saving cleaned CSVs to {CLEAN_DIR.relative_to(ROOT)}/ ...")
    t0 = time.time()
    for table in TABLES:
        if table in cleaned:
            path = CLEAN_DIR / f"{table}.csv"
            cleaned[table].to_csv(path, index=False)
            print(f"  ✅ {table}.csv  ({len(cleaned[table]):,} rows)")
    print(f"  ({time.time()-t0:.1f}s)\n")

    # 5. Build analytical base table
    print("Step 4: Building analytical base table ...")
    t0 = time.time()
    abt = build_analytical_base_table(cleaned)
    print(f"  ABT built: {len(abt):,} rows, {len(abt.columns)} cols")

    # 6. Engineer features (Step 9)
    print("Step 5: Engineering features ...")
    abt = add_features(abt)
    abt.to_csv(ABT_PATH, index=False)
    print(f"  ✅ analytical_base_table.csv  ({len(abt):,} rows, {len(abt.columns)} cols)")
    print(f"  ({time.time()-t0:.1f}s)\n")

    # 7. Build customer features as-of reference date (Step 10)
    print("Step 6: Building customer features (as-of reference date) ...")
    t0 = time.time()
    import pandas as pd
    orders_clean = cleaned["orders"].copy()
    orders_clean["order_date"] = pd.to_datetime(orders_clean["order_date"], errors="coerce")
    orders_clean["final_amount"] = pd.to_numeric(orders_clean["final_amount"], errors="coerce")
    ref_date = orders_clean["order_date"].max()
    cust_features = build_customer_features(orders_clean, as_of=ref_date)
    cust_features_path = CLEAN_DIR / "customer_features.csv"
    cust_features.to_csv(cust_features_path, index=False)
    print(f"  Reference date  : {ref_date.date()}")
    print(f"  ✅ customer_features.csv  ({len(cust_features):,} rows, {len(cust_features.columns)} cols)")
    print(f"  ({time.time()-t0:.1f}s)\n")

    # 8. Save cleaning log
    print("Step 7: Saving cleaning log ...")
    log.save(str(LOG_PATH))
    print(f"  ✅ cleaning_log.csv  ({len(log.rows)} entries)")
    print(f"  → {LOG_PATH.relative_to(ROOT)}\n")

    # 9. Summary
    elapsed = (datetime.now() - start).total_seconds()
    print("=" * 64)
    print(f"Pipeline COMPLETE ✅  ({elapsed:.1f}s)")
    print(f"  12 cleaned CSVs       → {CLEAN_DIR.relative_to(ROOT)}/")
    print(f"  analytical_base_table → {ABT_PATH.relative_to(ROOT)}")
    print(f"  customer_features     → {cust_features_path.relative_to(ROOT)}")
    print(f"  cleaning_log          → {LOG_PATH.relative_to(ROOT)}")
    print(f"  quarantine files      → {len(list(CLEAN_DIR.glob('quarantine_*.csv')))} files")
    print(f"  ABT rows/cols         → {len(abt):,} rows × {len(abt.columns)} cols")
    print(f"  Customer feature rows → {len(cust_features):,} (one per customer)")
    print("=" * 64)


if __name__ == "__main__":
    main()
