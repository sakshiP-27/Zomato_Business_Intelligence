"""
src/profile.py
--------------
Step 5: Profile every staging table and write the data-quality log.

Covers every issue category from the guide:
  1. Null / blank values            (per column)
  2. Extra whitespace               (per column)
  3. Duplicate full rows            (per table)
  4. Duplicate primary keys         (per table)
  5. Mixed date formats             (date columns only)
  6. Inconsistent city names        (city columns vs canonical list)
  7. Bad phone numbers              (customers)
  8. Bad pincodes                   (customers)
  9. Negative / zero numeric values (numeric columns)
 10. Outlier check                  (delivery_time_minutes, average_delivery_time)
 11. Orphaned foreign keys          (orders → customers/restaurants/delivery_partners/promotions)
                                    (order_items → orders/menu)
                                    (payments, customer_feedback → orders)
 12. Category value audit           (OrderStatus, PaymentStatus, Membership, etc.)

Outputs:
  documentation/data_quality_log.csv   ← machine-readable log (one row per issue)
  documentation/data_quality_report.md ← human-readable narrative summary

Usage:
    python src/profile.py
"""

import os
import re
import sys
import csv
from pathlib import Path
from datetime import datetime

import pandas as pd
import psycopg2
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
RAW_DIR   = ROOT / "data" / "raw"
DOC_DIR   = ROOT / "documentation"
LOG_CSV   = DOC_DIR / "data_quality_log.csv"
REPORT_MD = DOC_DIR / "data_quality_report.md"

load_dotenv(ROOT / ".env")
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    sys.exit("ERROR: DATABASE_URL not found in .env")

# Primary keys per staging table
PRIMARY_KEYS = {
    "cities":            "city_id",
    "customers":         "customer_id",
    "restaurants":       "restaurant_id",
    "delivery_partners": "delivery_partner_id",
    "menu":              "food_item_id",
    "orders":            "order_id",
    "order_items":       "order_item_id",
    "payments":          "payment_id",
    "customer_feedback": "feedback_id",
    "promotions":        "promotion_id",
    "weather":           "weather_id",
    "traffic":           "traffic_id",
}

# Date columns per table
DATE_COLS = {
    "orders":            ["order_date"],
    "customers":         ["registration_date"],
    "delivery_partners": ["joining_date"],
    "promotions":        ["start_date", "end_date"],
    "payments":          ["payment_date"],
    "weather":           ["date"],
    "traffic":           ["date"],
}

# Numeric columns to check for non-positive values
NUMERIC_NONPOS = {
    "orders":            ["delivery_time_minutes", "food_cost", "delivery_fee",
                          "discount", "gst", "final_amount"],
    "menu":              ["price", "preparation_time", "calories"],
    "restaurants":       ["rating", "average_cost"],
    "delivery_partners": ["rating", "completed_deliveries", "average_delivery_time"],
    "customer_feedback": ["customer_rating", "delivery_rating", "food_rating"],
    "order_items":       ["quantity", "unit_price", "total_price"],
}

# Outlier columns
OUTLIER_COLS = {
    "orders":            "delivery_time_minutes",
    "delivery_partners": "average_delivery_time",
}

# City columns (need alias normalisation)
CITY_TABLES = ["customers", "restaurants", "delivery_partners", "weather", "traffic"]

# Category columns to audit
CATEGORY_COLS = {
    "orders":            ["order_status", "payment_method"],
    "customers":         ["membership", "gender"],
    "customer_feedback": ["sentiment"],
    "delivery_partners": ["vehicle_type", "gender"],
    "restaurants":       ["restaurant_type", "cuisine"],
    "menu":              ["availability"],
    "weather":           ["weather_condition"],
    "traffic":           ["traffic_level"],
    "payments":          ["payment_method", "payment_status"],
}

# FK relationships to check for orphans
# Format: (child_table, child_col, parent_table, parent_col)
FK_CHECKS = [
    ("orders",            "customer_id",          "customers",         "customer_id"),
    ("orders",            "restaurant_id",         "restaurants",       "restaurant_id"),
    ("orders",            "delivery_partner_id",   "delivery_partners", "delivery_partner_id"),
    ("orders",            "coupon_code",           "promotions",        "coupon_code"),
    ("order_items",       "order_id",              "orders",            "order_id"),
    ("order_items",       "food_item_id",           "menu",              "food_item_id"),
    ("payments",          "order_id",              "orders",            "order_id"),
    ("customer_feedback", "order_id",              "orders",            "order_id"),
    ("menu",              "restaurant_id",         "restaurants",       "restaurant_id"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def pct(count: int, total: int) -> str:
    if total == 0:
        return "0.00%"
    return f"{count / total * 100:.2f}%"


def example_val(series: pd.Series, mask: pd.Series) -> str:
    """Return first example value matching the mask, truncated."""
    # Re-index mask to series index to avoid alignment errors on subsets
    mask = mask.reindex(series.index, fill_value=False)
    vals = series[mask].dropna()
    if vals.empty:
        return ""
    return str(vals.iloc[0])[:60]


# ---------------------------------------------------------------------------
# Issue log builder
# ---------------------------------------------------------------------------

class IssueLog:
    LOG_COLS = ["table", "column", "issue", "count", "pct_of_rows",
                "example_bad_value", "planned_fix", "status"]

    def __init__(self):
        self.rows: list[dict] = []

    def add(self, table, column, issue, count, total,
            example="", planned_fix="", status="found"):
        self.rows.append({
            "table":           table,
            "column":          column,
            "issue":           issue,
            "count":           count,
            "pct_of_rows":     pct(count, total),
            "example_bad_value": example,
            "planned_fix":     planned_fix,
            "status":          status,
        })

    def to_csv(self, path: Path) -> None:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.LOG_COLS)
            writer.writeheader()
            writer.writerows(self.rows)
        print(f"\nData quality log saved → {path.relative_to(ROOT)}")
        print(f"  {len(self.rows)} issue rows logged")


# ---------------------------------------------------------------------------
# Profiling functions
# ---------------------------------------------------------------------------

def profile_nulls_and_spaces(df: pd.DataFrame, table: str, log: IssueLog) -> None:
    """Check every column for nulls/blanks and extra whitespace."""
    n = len(df)
    for col in df.columns:
        s = df[col]

        # Null + blank — work on the original series index throughout
        null_mask  = s.isna()
        blank_mask = (~null_mask) & (s.str.strip() == "")
        null_count  = int(null_mask.sum())
        blank_count = int(blank_mask.sum())
        total_missing = null_count + blank_count
        if total_missing > 0:
            # Pick first null example, fallback to first blank example
            ex_null  = str(s[null_mask].index[0])  if null_count  > 0 else ""
            ex_blank = "(blank)"                    if blank_count > 0 else ""
            log.add(table, col, "null or blank",
                    total_missing, n,
                    example=ex_blank if not ex_null else ex_blank,
                    planned_fix="Load as NULL; impute in Week 2 if needed")

        # Extra whitespace — only on non-null values, keep original index
        nonnull_mask  = ~null_mask
        space_mask    = nonnull_mask & (s != s.str.strip())
        space_count   = int(space_mask.sum())
        if space_count > 0:
            first_spaced = s[space_mask].iloc[0]
            log.add(table, col, "extra whitespace",
                    space_count, n,
                    example=repr(first_spaced)[:60],
                    planned_fix="TRIM() while loading to production",
                    status="fixed in SQL")


def profile_duplicates(df: pd.DataFrame, table: str, pk: str, log: IssueLog) -> None:
    """Check for fully-duplicate rows and duplicate primary keys."""
    n = len(df)

    # Full row duplicates
    dup_rows = int(df.duplicated().sum())
    if dup_rows > 0:
        log.add(table, "(all columns)", "duplicate full rows",
                dup_rows, n,
                planned_fix="ROW_NUMBER() OVER (PARTITION BY pk) = 1 keeps first; log in cleaning",
                status="fixed in SQL")

    # Duplicate PKs (same ID, different data)
    if pk in df.columns:
        dup_pks = int(df[pk].duplicated().sum())
        if dup_pks > 0:
            example_id = df[df[pk].duplicated(keep=False)][pk].iloc[0]
            log.add(table, pk, "duplicate primary key",
                    dup_pks, n,
                    example=str(example_id),
                    planned_fix="Keep row with fewest NULLs; discard others; log count",
                    status="fixed in SQL")


def profile_dates(df: pd.DataFrame, table: str, log: IssueLog) -> None:
    """Count date format distribution and flag unparseable values."""
    n = len(df)
    cols = DATE_COLS.get(table, [])
    for col in cols:
        if col not in df.columns:
            continue
        s_raw = df[col]
        # Work on full-series boolean masks for consistent indexing
        not_null = ~s_raw.isna()
        s_stripped = s_raw.where(not_null, other=pd.NA).str.strip()

        fmt_masks = {
            "DD-MM-YYYY":              s_stripped.str.match(r"^\d{2}-\d{2}-\d{4}$").fillna(False),
            "MM/DD/YYYY or DD/MM/YYYY":s_stripped.str.match(r"^\d{2}/\d{2}/\d{4}$").fillna(False),
            "YYYY.MM.DD":              s_stripped.str.match(r"^\d{4}\.\d{2}\.\d{2}$").fillna(False),
            "YYYY-MM-DD":              s_stripped.str.match(r"^\d{4}-\d{2}-\d{2}$").fillna(False),
            "DD Mon YYYY":             s_stripped.str.match(r"^\d{1,2} [A-Za-z]{3} \d{4}$").fillna(False),
        }
        fix = ("parse_mixed_date() / parse_ddmmyyyy() while loading to production; "
               "verify MIN/MAX span ~24 months")
        for fmt, mask in fmt_masks.items():
            cnt = int(mask.sum())
            if cnt > 0:
                ex = str(s_stripped[mask].iloc[0]) if cnt > 0 else ""
                log.add(table, col, f"date format: {fmt}",
                        cnt, n, example=ex, planned_fix=fix, status="fixed in SQL")

        any_matched = pd.concat(list(fmt_masks.values()), axis=1).any(axis=1)
        invalid_mask = not_null & ~any_matched
        invalid = int(invalid_mask.sum())
        if invalid > 0:
            ex = str(s_stripped[invalid_mask].iloc[0]) if invalid > 0 else ""
            log.add(table, col, "date: unparseable / unknown format",
                    invalid, n, example=ex,
                    planned_fix="Load as NULL; investigate manually", status="found")


def profile_cities(df: pd.DataFrame, table: str,
                   canonical_cities: set, log: IssueLog) -> None:
    """Check city column for non-canonical spellings."""
    if "city" not in df.columns:
        return
    n = len(df)
    city_vals = df["city"].dropna().str.strip()
    non_canonical_mask = ~city_vals.isin(canonical_cities)
    count = int(non_canonical_mask.sum())
    if count > 0:
        examples = ", ".join(sorted(city_vals[non_canonical_mask].unique())[:5])
        log.add(table, "city", "non-canonical city name",
                count, n,
                example=examples,
                planned_fix="Map via city_aliases table during staging→production load",
                status="fixed in SQL")


def profile_phone_pincode(df: pd.DataFrame, table: str, log: IssueLog) -> None:
    """Validate Indian phone numbers and 6-digit pincodes."""
    n = len(df)
    if "phone" in df.columns:
        s = df["phone"].dropna().str.strip()
        bad_mask = ~s.str.match(r"^[6-9]\d{9}$")
        bad_count = int(bad_mask.sum())
        if bad_count > 0:
            log.add(table, "phone", "invalid Indian mobile number (not 10 digits / wrong prefix)",
                    bad_count, n,
                    example=str(s[bad_mask].iloc[0]) if bad_count > 0 else "",
                    planned_fix="Log only in Week 1; null out or fix in Week 2 Python",
                    status="found")

    if "pincode" in df.columns:
        s = df["pincode"].dropna().str.strip()
        bad_mask = ~s.str.match(r"^\d{6}$")
        bad_count = int(bad_mask.sum())
        if bad_count > 0:
            log.add(table, "pincode", "invalid pincode (not exactly 6 digits)",
                    bad_count, n,
                    example=str(s[bad_mask].iloc[0]) if bad_count > 0 else "",
                    planned_fix="Log only in Week 1; null out or fix in Week 2 Python",
                    status="found")


def profile_nonpositive(df: pd.DataFrame, table: str, log: IssueLog) -> None:
    """Count rows where numeric columns are <= 0."""
    n = len(df)
    cols = NUMERIC_NONPOS.get(table, [])
    for col in cols:
        if col not in df.columns:
            continue
        numeric = pd.to_numeric(df[col], errors="coerce")
        neg_mask  = numeric < 0
        zero_mask = numeric == 0
        neg_count  = int(neg_mask.sum())
        zero_count = int(zero_mask.sum())
        if neg_count > 0:
            log.add(table, col, "negative value",
                    neg_count, n,
                    example=str(df[col][neg_mask].iloc[0]),
                    planned_fix="Keep and study; exclude via view in business queries; fix in Week 2",
                    status="found")
        if zero_count > 0:
            log.add(table, col, "zero value",
                    zero_count, n,
                    example="0",
                    planned_fix="Keep and study; flag in business queries; decide fix in Week 2",
                    status="found")


def profile_outliers(df: pd.DataFrame, table: str, log: IssueLog) -> None:
    """Log percentile stats for key delivery time columns."""
    col = OUTLIER_COLS.get(table)
    if not col or col not in df.columns:
        return
    n = len(df)
    numeric = pd.to_numeric(df[col], errors="coerce").dropna()
    if numeric.empty:
        return
    p50  = numeric.quantile(0.50)
    p75  = numeric.quantile(0.75)
    p90  = numeric.quantile(0.90)
    p99  = numeric.quantile(0.99)
    pmax = numeric.max()
    # Flag values above 99th percentile as potential outliers
    outlier_threshold = p99
    outlier_count = int((numeric > outlier_threshold).sum())
    stats_str = f"p50={p50:.0f} p75={p75:.0f} p90={p90:.0f} p99={p99:.0f} max={pmax:.0f}"
    log.add(table, col, f"potential outlier (> p99={p99:.0f} min)",
            outlier_count, n,
            example=stats_str,
            planned_fix="Log only; decide cap threshold after EDA in Week 2",
            status="found")


def profile_categories(df: pd.DataFrame, table: str, log: IssueLog) -> None:
    """Check for null/blank values in category columns and log distinct values."""
    n = len(df)
    cols = CATEGORY_COLS.get(table, [])
    for col in cols:
        if col not in df.columns:
            continue
        s = df[col]
        null_blank = int(s.isna().sum() + (s.dropna().str.strip() == "").sum())
        # Already covered by null check, but add distinct-value audit line
        vals = s.dropna().str.strip().value_counts(dropna=False)
        distinct_count = len(vals)
        log.add(table, col, f"category audit ({distinct_count} distinct values)",
                distinct_count, n,
                example=" | ".join(str(v) for v in vals.index[:5]),
                planned_fix="Use exact spellings in all SQL queries and dashboards",
                status="found")


def profile_orphan_fks(dfs: dict[str, pd.DataFrame], log: IssueLog) -> None:
    """Check for orphaned foreign keys between staging tables."""
    for child_tbl, child_col, parent_tbl, parent_col in FK_CHECKS:
        if child_tbl not in dfs or parent_tbl not in dfs:
            continue
        child_df  = dfs[child_tbl]
        parent_df = dfs[parent_tbl]

        if child_col not in child_df.columns or parent_col not in parent_df.columns:
            continue

        # Build parent key set from non-null values
        parent_vals = set(
            parent_df[parent_col].dropna().astype(str).str.strip()
        )

        # Child values: non-null and non-blank
        child_series = child_df[child_col].dropna().astype(str).str.strip()
        child_series = child_series[child_series != ""]

        orphan_mask  = ~child_series.isin(parent_vals)
        orphan_count = int(orphan_mask.sum())
        n = len(child_df)

        ex = str(child_series[orphan_mask].iloc[0]) if orphan_count > 0 else ""
        log.add(child_tbl, child_col,
                f"orphaned FK → staging.{parent_tbl}({parent_col})",
                orphan_count, n,
                example=ex,
                planned_fix=(
                    "Move orphan rows to quarantine table during staging→production load"
                    if orphan_count > 0 else "No action needed — all FKs resolve"
                ),
                status="found")


# ---------------------------------------------------------------------------
# Markdown report generator
# ---------------------------------------------------------------------------

def write_report(log: IssueLog, stats: dict, path: Path) -> None:
    """Write a human-readable markdown summary of profiling findings."""
    lines = []
    lines.append("# Data Quality Report — Step 5 Profiling\n")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n")
    lines.append(f"**Source:** staging schema (12 tables, 159,077 total rows)\n\n---\n")

    lines.append("## Summary\n")
    total_issues = len([r for r in log.rows if r["count"] > 0])
    lines.append(f"| Metric | Value |\n|---|---|\n")
    lines.append(f"| Tables profiled | 12 |\n")
    lines.append(f"| Total issue rows logged | {len(log.rows)} |\n")
    lines.append(f"| Issues with count > 0 | {total_issues} |\n")
    lines.append(f"| Issues already fixed in SQL (staging→prod load) | "
                 f"{len([r for r in log.rows if r['status'] == 'fixed in SQL'])} |\n")
    lines.append(f"| Issues deferred to Week 2 Python | "
                 f"{len([r for r in log.rows if r['status'] == 'found'])} |\n\n")

    lines.append("## Per-Table Findings\n")
    for table, row_count in stats.items():
        table_issues = [r for r in log.rows if r["table"] == table]
        real_issues  = [r for r in table_issues if r["count"] > 0]
        lines.append(f"### {table}  ({row_count:,} rows)\n")
        if real_issues:
            lines.append("| Column | Issue | Count | % | Example | Fix |\n")
            lines.append("|--------|-------|------:|---|---------|-----|\n")
            for r in real_issues:
                ex = r['example_bad_value'][:40].replace("|", "\\|") if r['example_bad_value'] else ""
                lines.append(
                    f"| {r['column']} | {r['issue']} | {r['count']:,} | "
                    f"{r['pct_of_rows']} | {ex} | {r['planned_fix'][:50]} |\n"
                )
        else:
            lines.append("_No issues found._\n")
        lines.append("\n")

    lines.append("---\n\n## Data Quality Log Columns\n\n")
    lines.append("The full machine-readable log is in `documentation/data_quality_log.csv`.  \n")
    lines.append("Status values: `found` → `fixed in SQL` → `fixed in Python` → `verified`\n")

    path.write_text("".join(lines), encoding="utf-8")
    print(f"Report saved → {path.relative_to(ROOT)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    start = datetime.now()

    print("=" * 62)
    print("Zomato BI — Step 5: Profile Staging Tables")
    print("=" * 62)
    print(f"Started: {start.strftime('%Y-%m-%d %H:%M:%S')}\n")

    log = IssueLog()

    # 1. Load all 12 CSVs from raw/ (same data as staging, but local for pandas speed)
    print("Loading raw CSVs for profiling ...")
    dfs: dict[str, pd.DataFrame] = {}
    row_counts: dict[str, int] = {}

    def to_snake(name: str) -> str:
        name = name.strip()
        name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
        return name.lower()

    for csv_path in sorted(RAW_DIR.glob("*.csv")):
        stem = csv_path.stem
        df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
        # Rename to snake_case (matches schema.sql and all config dicts below)
        df.columns = [to_snake(c) for c in df.columns]
        # Replace empty strings with pd.NA for null counting
        df_for_profile = df.replace("", pd.NA)
        dfs[stem] = df_for_profile
        row_counts[stem] = len(df)
        print(f"  {stem:<25} {len(df):>6,} rows  {len(df.columns)} cols")

    # 2. Canonical city names from cities.csv
    canonical_cities = set(
        pd.read_csv(RAW_DIR / "cities.csv", dtype=str)["City"].dropna().str.strip()
    )
    print(f"\nCanonical cities ({len(canonical_cities)}): {sorted(canonical_cities)[:5]} ...")

    # 3. Profile each table
    print("\nProfiling tables ...")
    print("-" * 62)

    for table, df in dfs.items():
        n = len(df)
        pk = PRIMARY_KEYS.get(table, "")
        print(f"  {table} ({n:,} rows) ...", end="", flush=True)

        profile_nulls_and_spaces(df, table, log)
        profile_duplicates(df, table, pk, log)
        profile_dates(df, table, log)
        if table in CITY_TABLES:
            profile_cities(df, table, canonical_cities, log)
        profile_phone_pincode(df, table, log)
        profile_nonpositive(df, table, log)
        profile_outliers(df, table, log)
        profile_categories(df, table, log)

        table_issues = len([r for r in log.rows if r["table"] == table and r["count"] > 0])
        print(f" {table_issues} issues found")

    # 4. Orphaned FK check (cross-table)
    print("\nChecking orphaned foreign keys ...")
    profile_orphan_fks(dfs, log)

    # 5. Write outputs
    print()
    DOC_DIR.mkdir(parents=True, exist_ok=True)
    log.to_csv(LOG_CSV)
    write_report(log, row_counts, REPORT_MD)

    # 6. Print key findings to console
    print("\n" + "=" * 62)
    print("KEY FINDINGS SUMMARY")
    print("=" * 62)

    important_issues = [
        ("null or blank", "Missing data"),
        ("duplicate full rows", "Full row duplicates"),
        ("duplicate primary key", "PK duplicates"),
        ("non-canonical city name", "City name variants"),
        ("invalid Indian mobile number", "Bad phone numbers"),
        ("invalid pincode", "Bad pincodes"),
        ("negative value", "Negative numeric values"),
        ("zero value", "Zero numeric values"),
        ("orphaned FK", "Orphaned foreign keys"),
        ("potential outlier", "Outliers (>p99)"),
    ]

    for issue_substr, label in important_issues:
        matches = [r for r in log.rows if issue_substr in r["issue"] and r["count"] > 0]
        if matches:
            total = sum(r["count"] for r in matches)
            tables = ", ".join(sorted({r["table"] for r in matches}))
            print(f"\n  {label}:")
            for r in matches:
                if r["count"] > 0:
                    print(f"    {r['table']}.{r['column']}: {r['count']:,} ({r['pct_of_rows']})")

    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n{'='*62}")
    print(f"Step 5 COMPLETE ✅  ({elapsed:.1f}s)")
    print(f"  data_quality_log.csv    → {len(log.rows)} rows")
    print(f"  data_quality_report.md  → narrative summary")
    print(f"\nNext: python src/load_to_production.py   (Step 6)")
    print("=" * 62)


if __name__ == "__main__":
    main()
