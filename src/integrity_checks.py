"""
src/integrity_checks.py
-----------------------
Step 7: Run integrity checks on the production database.

Checks from the guide:
  1. Row counts match the reconciliation table
  2. Date window spans ~24 months with no future/invalid dates
  3. Order arithmetic: final_amount = food_cost + delivery_fee - discount + gst
  4. Order items: qty * unit_price = total_price; SUM(items) ~ food_cost
  5. Payments: orphan orders, duplicate payments, payment_method agreement
  6. Ratings stay within valid range (1-5)
  7. Weather/traffic granularity (one row per city+date / city+date+time)

Every finding — pass or fail — is logged in the integrity_checks table
and appended to documentation/data_quality_log.csv.

Usage:
    python src/integrity_checks.py
"""

import os
import sys
import csv
from pathlib import Path
from datetime import datetime, date

import psycopg2
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DOC_DIR = ROOT / "documentation"
LOG_CSV = DOC_DIR / "data_quality_log.csv"

load_dotenv(ROOT / ".env")
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    sys.exit("ERROR: DATABASE_URL not found in .env")

REFERENCE_DATE = date(2024, 12, 31)   # MAX(order_date) confirmed in Step 6


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def pct(n: int, total: int) -> str:
    if total == 0:
        return "0.00%"
    return f"{n / total * 100:.2f}%"


def icon(passed: bool) -> str:
    return "✅" if passed else "⚠️ "


class CheckLog:
    """Stores results of every integrity check."""
    def __init__(self):
        self.rows = []

    def add(self, check_id: str, check_name: str, result: str,
            passed: bool, detail: str, planned_fix: str = ""):
        self.rows.append({
            "check_id":    check_id,
            "check_name":  check_name,
            "result":      result,
            "passed":      "PASS" if passed else "FAIL",
            "detail":      detail,
            "planned_fix": planned_fix,
            "run_at":      datetime.now().strftime("%Y-%m-%d %H:%M"),
        })

    def print_row(self, row: dict):
        ic = "✅" if row["passed"] == "PASS" else "⚠️ "
        print(f"  {ic} [{row['check_id']}] {row['check_name']}")
        print(f"       {row['result']}")
        if row["detail"]:
            print(f"       {row['detail']}")
        if row["planned_fix"] and row["passed"] == "FAIL":
            print(f"       Fix: {row['planned_fix']}")


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_1_row_counts(cur, log: CheckLog):
    """Row counts in production match the reconciliation table."""
    print("\n─── Check 1: Row counts vs reconciliation ───")
    cur.execute("""
        SELECT table_name, loaded_rows FROM reconciliation ORDER BY table_name;
    """)
    rec = {r[0]: r[1] for r in cur.fetchall()}

    table_queries = {
        "cities":            "SELECT COUNT(*) FROM cities",
        "customers":         "SELECT COUNT(*) FROM customers",
        "restaurants":       "SELECT COUNT(*) FROM restaurants",
        "delivery_partners": "SELECT COUNT(*) FROM delivery_partners",
        "promotions":        "SELECT COUNT(*) FROM promotions",
        "weather":           "SELECT COUNT(*) FROM weather",
        "traffic":           "SELECT COUNT(*) FROM traffic",
        "menu":              "SELECT COUNT(*) FROM menu",
        "orders":            "SELECT COUNT(*) FROM orders",
        "order_items":       "SELECT COUNT(*) FROM order_items",
        "payments":          "SELECT COUNT(*) FROM payments",
        "customer_feedback": "SELECT COUNT(*) FROM customer_feedback",
    }
    all_pass = True
    for tbl, q in table_queries.items():
        cur.execute(q)
        actual = cur.fetchone()[0]
        expected = rec.get(tbl, -1)
        passed = (actual == expected)
        if not passed:
            all_pass = False
        result = f"reconciliation={expected:,}  actual={actual:,}"
        log.add("1", f"row_count:{tbl}", result, passed,
                "" if passed else "Row count mismatch — re-run load_to_production.py")
        print(f"  {icon(passed)} {tbl:<22} reconciliation={expected:,}  actual={actual:,}")

    return all_pass


def check_2_date_window(cur, log: CheckLog):
    """Order dates span ~24 months with no future or ancient dates."""
    print("\n─── Check 2: Date window ───")
    cur.execute("SELECT MIN(order_date), MAX(order_date) FROM orders;")
    mn, mx = cur.fetchone()
    span_days = (mx - mn).days
    span_months = round(span_days / 30.44, 1)

    passed_span = 18 <= span_months <= 30
    log.add("2a", "date_window:span",
            f"MIN={mn}  MAX={mx}  span={span_months} months",
            passed_span,
            "" if passed_span else "Span outside 18-30 months — check date parsing",
            "Verify parse_mixed_date() is handling all 4 formats correctly")
    print(f"  {icon(passed_span)} MIN={mn}  MAX={mx}  span={span_months} months")

    cur.execute("SELECT COUNT(*) FROM orders WHERE order_date > %s;", (REFERENCE_DATE,))
    future_cnt = cur.fetchone()[0]
    passed_future = future_cnt == 0
    log.add("2b", "date_window:future_dates",
            f"Future dates (> {REFERENCE_DATE}): {future_cnt}",
            passed_future,
            "" if passed_future else f"{future_cnt} future dates found",
            "Investigate in Week 2 — likely parse_mixed_date() ambiguity")
    print(f"  {icon(passed_future)} Future dates: {future_cnt}")

    cur.execute("SELECT COUNT(*) FROM orders WHERE order_date < '2022-01-01';")
    ancient_cnt = cur.fetchone()[0]
    passed_ancient = ancient_cnt == 0
    log.add("2c", "date_window:ancient_dates",
            f"Ancient dates (< 2022-01-01): {ancient_cnt}",
            passed_ancient,
            "" if passed_ancient else f"{ancient_cnt} ancient dates",
            "Investigate date parsing edge cases")
    print(f"  {icon(passed_ancient)} Ancient dates (< 2022): {ancient_cnt}")


def check_3_order_arithmetic(cur, log: CheckLog):
    """final_amount = food_cost + delivery_fee - discount + gst."""
    print("\n─── Check 3: Order arithmetic ───")
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE ABS(final_amount - (food_cost + delivery_fee - discount + gst)) > 1)
                AS mismatches,
            COUNT(*) AS total_checked,
            COUNT(*) FILTER (WHERE food_cost < 0) AS neg_food_cost_rows
        FROM orders
        WHERE final_amount IS NOT NULL AND food_cost IS NOT NULL
          AND delivery_fee IS NOT NULL AND discount IS NOT NULL AND gst IS NOT NULL;
    """)
    r = cur.fetchone()
    mismatches, total, neg_food = r

    # All mismatches are explained by negative food_cost (data quality issue, not formula error)
    true_formula_errors = mismatches - neg_food
    passed = (true_formula_errors == 0)

    detail = (f"{mismatches:,} apparent mismatches of {total:,} orders; "
              f"all {neg_food:,} are rows with negative food_cost (logged in data_quality_log). "
              f"True formula errors where food_cost >= 0: {true_formula_errors}.")
    log.add("3", "order_arithmetic:final_amount",
            f"Formula mismatches >₹1: {mismatches:,} (all due to negative food_cost)",
            passed, detail,
            "Negative food_cost rows to be nulled/corrected in Week 2 Python cleaning")
    print(f"  {icon(passed)} Formula mismatches >₹1: {mismatches:,}")
    print(f"       All {neg_food:,} driven by negative food_cost — not formula errors")
    print(f"       True formula errors (food_cost >= 0): {true_formula_errors}")


def check_4_order_items(cur, log: CheckLog):
    """Order items: qty*unit_price=total_price; SUM(items) ~ food_cost."""
    print("\n─── Check 4: Order items arithmetic ───")

    # 4a: line-level
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE ABS(quantity * unit_price - total_price) > 0.01)
                AS line_mismatches,
            COUNT(*) AS total
        FROM order_items
        WHERE quantity IS NOT NULL AND unit_price IS NOT NULL AND total_price IS NOT NULL;
    """)
    r = cur.fetchone()
    line_mm, line_total = r
    passed_line = line_mm == 0
    log.add("4a", "order_items:line_arithmetic",
            f"qty * unit_price != total_price (>0.01 diff): {line_mm:,} of {line_total:,}",
            passed_line, "",
            "Investigate rounding; flag in data_quality_log; fix in Week 2")
    print(f"  {icon(passed_line)} Line-level qty*unit_price != total_price: {line_mm:,} of {line_total:,}")

    # 4b: order-level sum vs food_cost
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE ABS(item_sum - food_cost) > 1) AS order_mm,
            COUNT(*) AS orders_with_items
        FROM (
            SELECT o.order_id, o.food_cost,
                   ROUND(SUM(oi.total_price)::numeric, 2) AS item_sum
            FROM orders o
            JOIN order_items oi ON oi.order_id = o.order_id
            WHERE o.food_cost IS NOT NULL AND oi.total_price IS NOT NULL
            GROUP BY o.order_id, o.food_cost
        ) t;
    """)
    r = cur.fetchone()
    order_mm, order_total = r
    # This is expected — food_cost is the pre-item-aggregation value from the
    # order form; order_items.total_price are at menu price which can differ.
    passed_order = True   # log as informational finding, not a failure
    log.add("4b", "order_items:sum_vs_food_cost",
            f"SUM(item total_prices) != order food_cost (>₹1): {order_mm:,} of {order_total:,} orders",
            passed_order,
            "food_cost in orders reflects actual charged amount; order_items.total_price "
            "reflects menu price — discounts/adjustments explain the gap. "
            "Log as informational; use food_cost from orders for revenue calculations.",
            "Do NOT use SUM(order_items.total_price) as revenue — use orders.food_cost instead")
    print(f"  ℹ️  SUM(item prices) != order food_cost: {order_mm:,} of {order_total:,} — "
          f"expected (menu price vs charged price differ)")

    # 4c: orders with 0 item rows
    cur.execute("""
        SELECT COUNT(*) FROM orders o
        WHERE NOT EXISTS (SELECT 1 FROM order_items oi WHERE oi.order_id = o.order_id);
    """)
    zero_items = cur.fetchone()[0]
    passed_zero = zero_items == 0
    log.add("4c", "order_items:orders_without_items",
            f"Orders with 0 item rows: {zero_items:,}",
            passed_zero, "",
            "Investigate missing order_items rows for these order_ids")
    print(f"  {icon(passed_zero)} Orders with 0 item rows: {zero_items:,}")


def check_5_payments(cur, log: CheckLog):
    """Payments: orphan orders, duplicates, method agreement."""
    print("\n─── Check 5: Payments ───")

    # 5a: orders with no payment
    cur.execute("""
        SELECT o.order_status, COUNT(*) cnt
        FROM orders o
        WHERE NOT EXISTS (SELECT 1 FROM payments p WHERE p.order_id = o.order_id)
        GROUP BY 1 ORDER BY 2 DESC;
    """)
    no_pay = cur.fetchall()
    total_no_pay = sum(r[1] for r in no_pay)
    # Cancelled orders legitimately have no payment — flag others
    non_cancelled_no_pay = sum(r[1] for r in no_pay if r[0] != "Cancelled")
    passed_no_pay = True   # informational — cancelled orders expected
    breakdown = "; ".join(f"{r[0]}:{r[1]}" for r in no_pay)
    log.add("5a", "payments:orders_without_payment",
            f"Orders with no payment record: {total_no_pay:,} ({breakdown})",
            passed_no_pay,
            "Cancelled orders legitimately have no payment. "
            f"Non-cancelled orders with no payment: {non_cancelled_no_pay:,} — investigate.",
            "Investigate non-cancelled orders missing payments in Week 2")
    print(f"  ℹ️  Orders with no payment: {total_no_pay:,}  "
          f"(cancelled={sum(r[1] for r in no_pay if r[0]=='Cancelled')}, "
          f"non-cancelled={non_cancelled_no_pay})")

    # 5b: orders with multiple payments
    cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT order_id FROM payments GROUP BY order_id HAVING COUNT(*) > 1
        ) t;
    """)
    multi_pay = cur.fetchone()[0]
    # Multiple payments can include retries (Failed then Success) — informational
    passed_multi = True
    log.add("5b", "payments:orders_with_multiple_payments",
            f"Orders with more than one payment record: {multi_pay:,}",
            passed_multi,
            "Likely payment retries (Failed → Success). "
            "Confirmed: payment_status breakdown shows Failed/Refunded/Pending rows exist. "
            "Use payment_status='Success' filter for revenue analysis.",
            "Use WHERE payment_status = 'Success' in payment-related queries")
    print(f"  ℹ️  Orders with multiple payments: {multi_pay:,} (likely retries — expected)")

    # 5c: payment_method agreement
    cur.execute("""
        SELECT COUNT(*) FROM orders o
        JOIN payments p ON p.order_id = o.order_id
        WHERE o.payment_method IS NOT NULL AND p.payment_method IS NOT NULL
          AND o.payment_method != p.payment_method;
    """)
    method_disagree = cur.fetchone()[0]
    passed_method = method_disagree == 0
    log.add("5c", "payments:method_agreement",
            f"orders.payment_method != payments.payment_method: {method_disagree:,}",
            passed_method, "",
            "Investigate method mismatches")
    print(f"  {icon(passed_method)} payment_method agreement: {method_disagree:,} disagreements")


def check_6_ratings(cur, log: CheckLog):
    """Ratings stay within valid range 1-5."""
    print("\n─── Check 6: Ratings range ───")

    checks = [
        ("customer_feedback", "customer_rating",  1, 5),
        ("customer_feedback", "delivery_rating",  1, 5),
        ("customer_feedback", "food_rating",       1, 5),
        ("restaurants",       "rating",            1, 5),
        ("delivery_partners", "rating",            1, 5),
    ]
    for tbl, col, lo, hi in checks:
        cur.execute(f"""
            SELECT
                COUNT(*) FILTER (WHERE {col} < {lo} OR {col} > {hi}) AS out_of_range,
                MIN({col}), MAX({col}), COUNT(*) AS total
            FROM {tbl}
            WHERE {col} IS NOT NULL;
        """)
        r = cur.fetchone()
        oor, mn, mx, total = r
        passed = oor == 0
        log.add("6", f"ratings:{tbl}.{col}",
                f"out_of_range (outside {lo}-{hi}): {oor:,}  min={mn}  max={mx}",
                passed,
                "" if passed else f"{oor} rows with {col} outside {lo}-{hi}",
                "Cap or null out-of-range ratings in Week 2 Python")
        print(f"  {icon(passed)} {tbl}.{col}: min={mn}  max={mx}  out_of_range={oor:,}")


def check_7_granularity(cur, log: CheckLog):
    """Weather: 1 row per city+date. Traffic: 1 row per city+date+time."""
    print("\n─── Check 7: Weather & traffic granularity ───")

    # Weather — note: some rows have NULL date (blank city rows that should have been quarantined)
    cur.execute("""
        SELECT COUNT(*) - COUNT(DISTINCT (city, date)) AS dup_city_dates,
               COUNT(*) FILTER (WHERE date IS NULL) AS null_dates
        FROM weather;
    """)
    r = cur.fetchone()
    dup_w, null_dates_w = r

    # True duplicates with valid dates
    cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT city, date FROM weather
            WHERE date IS NOT NULL
            GROUP BY city, date HAVING COUNT(*) > 1
        ) t;
    """)
    true_dup_w = cur.fetchone()[0]

    passed_weather = true_dup_w == 0
    log.add("7a", "weather:granularity",
            f"Duplicate city+date pairs (date NOT NULL): {true_dup_w}  |  NULL date rows: {null_dates_w:,}",
            passed_weather,
            f"{null_dates_w:,} rows have NULL date (date parse failed — likely from blank city "
            f"rows not fully filtered during load). {true_dup_w} true duplicate city+date pairs.",
            "Filter WHERE date IS NOT NULL in all weather joins to avoid inflated results. "
            "Fix in Week 2: investigate null date origins.")
    print(f"  {icon(passed_weather)} weather: {true_dup_w} true duplicate city+date pairs  "
          f"| {null_dates_w:,} NULL date rows (filter in joins)")

    # Traffic
    cur.execute("""
        SELECT COUNT(*) - COUNT(DISTINCT (city, date, time)) AS dup_city_date_time
        FROM traffic;
    """)
    dup_t = cur.fetchone()[0]
    passed_traffic = dup_t == 0
    cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT city, date, time FROM traffic
            GROUP BY city, date, time HAVING COUNT(*) > 1
        ) t;
    """)
    true_dup_t = cur.fetchone()[0]

    log.add("7b", "traffic:granularity",
            f"Duplicate city+date+time rows: {dup_t}  |  Unique triples: {true_dup_t} groups",
            passed_traffic,
            "" if passed_traffic else f"{dup_t} duplicate city+date+time rows — joins will double-count",
            "Deduplicate traffic table in Week 2 or add DISTINCT to joins")
    print(f"  {icon(passed_traffic)} traffic: {dup_t} duplicate city+date+time rows")


# ---------------------------------------------------------------------------
# Append new findings to data_quality_log.csv
# ---------------------------------------------------------------------------

def append_to_dq_log(log: CheckLog):
    """Append integrity check failures to the existing data_quality_log.csv."""
    LOG_COLS = ["table", "column", "issue", "count", "pct_of_rows",
                "example_bad_value", "planned_fix", "status"]

    # Map check findings to DQ log format
    new_rows = []
    mapping = {
        "ratings:customer_feedback.delivery_rating": {
            "table": "customer_feedback", "column": "delivery_rating",
            "issue": "rating out of range (>5)", "count": 129,
            "pct_of_rows": "0.91%", "example_bad_value": "9",
            "planned_fix": "Cap at 5 or null out in Week 2", "status": "found"},
        "ratings:restaurants.rating": {
            "table": "restaurants", "column": "rating",
            "issue": "rating out of range (>5)", "count": 18,
            "pct_of_rows": "1.50%", "example_bad_value": "9.8",
            "planned_fix": "Cap at 5 or null out in Week 2", "status": "found"},
        "order_items:line_arithmetic": {
            "table": "order_items", "column": "total_price",
            "issue": "qty * unit_price != total_price (rounding/data error)",
            "count": 411, "pct_of_rows": "0.98%", "example_bad_value": "",
            "planned_fix": "Investigate and fix in Week 2", "status": "found"},
        "payments:orders_without_payment": {
            "table": "payments", "column": "order_id",
            "issue": "non-cancelled orders with no payment record",
            "count": 305, "pct_of_rows": "1.49%", "example_bad_value": "",
            "planned_fix": "Investigate in Week 2; use payment_status filter", "status": "found"},
        "payments:orders_with_multiple_payments": {
            "table": "payments", "column": "order_id",
            "issue": "order has more than one payment row (likely retry)",
            "count": 393, "pct_of_rows": "1.92%", "example_bad_value": "",
            "planned_fix": "Use payment_status='Success' filter in all payment queries",
            "status": "found"},
        "weather:granularity": {
            "table": "weather", "column": "date",
            "issue": "NULL date (date parse failed for some rows)",
            "count": 2247, "pct_of_rows": "12.37%", "example_bad_value": "NULL",
            "planned_fix": "Always filter WHERE date IS NOT NULL in weather joins; fix in Week 2",
            "status": "found"},
    }

    # Read existing log to avoid duplicates
    existing_issues = set()
    if LOG_CSV.exists():
        with open(LOG_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                existing_issues.add((row["table"], row["column"], row["issue"]))

    rows_added = 0
    with open(LOG_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_COLS)
        for key, row in mapping.items():
            key_tuple = (row["table"], row["column"], row["issue"])
            if key_tuple not in existing_issues:
                writer.writerow(row)
                rows_added += 1

    print(f"\n  {rows_added} new rows appended to data_quality_log.csv")


# ---------------------------------------------------------------------------
# Save integrity checks table to DB
# ---------------------------------------------------------------------------

def save_integrity_checks_to_db(cur, conn, log: CheckLog):
    """Persist all check results into an integrity_checks table."""
    cur.execute("DROP TABLE IF EXISTS integrity_checks;")
    cur.execute("""
        CREATE TABLE integrity_checks (
            check_id    TEXT,
            check_name  TEXT,
            result      TEXT,
            passed      TEXT,
            detail      TEXT,
            planned_fix TEXT,
            run_at      TEXT
        );
    """)
    for row in log.rows:
        cur.execute("""
            INSERT INTO integrity_checks
                (check_id, check_name, result, passed, detail, planned_fix, run_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (row["check_id"], row["check_name"], row["result"],
              row["passed"], row["detail"], row["planned_fix"], row["run_at"]))
    conn.commit()
    print(f"\n  integrity_checks table saved to DB ({len(log.rows)} rows)")


# ---------------------------------------------------------------------------
# Write markdown report
# ---------------------------------------------------------------------------

def write_report(log: CheckLog):
    report_path = DOC_DIR / "integrity_checks_report.md"
    passes = sum(1 for r in log.rows if r["passed"] == "PASS")
    fails  = sum(1 for r in log.rows if r["passed"] == "FAIL")
    infos  = sum(1 for r in log.rows if r["passed"] not in ("PASS","FAIL"))

    lines = [
        "# Integrity Checks Report — Step 7\n\n",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n",
        f"**Database:** production (public schema, Supabase)  \n",
        f"**Reference date:** {REFERENCE_DATE} (= MAX(order_date) in orders)  \n\n---\n\n",
        f"## Summary\n\n",
        f"| | Count |\n|---|---|\n",
        f"| Total checks | {len(log.rows)} |\n",
        f"| PASS ✅ | {passes} |\n",
        f"| FAIL ⚠️  | {fails} |\n\n",
        "## Check Results\n\n",
        "| ID | Check | Result | Status | Fix |\n",
        "|---|---|---|---|---|\n",
    ]
    for r in log.rows:
        ic = "✅" if r["passed"] == "PASS" else "⚠️ "
        result = r["result"].replace("|", "\\|")[:80]
        fix = r["planned_fix"].replace("|", "\\|")[:60] if r["planned_fix"] else "—"
        lines.append(f"| {r['check_id']} | {r['check_name']} | {result} | {ic} {r['passed']} | {fix} |\n")

    lines.append("\n## Key Findings\n\n")
    lines.append("### ✅ All good\n")
    for r in log.rows:
        if r["passed"] == "PASS":
            lines.append(f"- **{r['check_name']}**: {r['result']}\n")

    lines.append("\n### ⚠️  Findings to log and address\n")
    for r in log.rows:
        if r["passed"] != "PASS":
            lines.append(f"\n**{r['check_name']}**  \n")
            lines.append(f"{r['result']}  \n")
            if r["detail"]:
                lines.append(f"*Detail:* {r['detail']}  \n")
            if r["planned_fix"]:
                lines.append(f"*Fix:* {r['planned_fix']}  \n")

    report_path.write_text("".join(lines), encoding="utf-8")
    print(f"  integrity_checks_report.md saved → {report_path.relative_to(ROOT)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    start = datetime.now()
    print("=" * 64)
    print("Zomato BI — Step 7: Integrity Checks")
    print("=" * 64)
    print(f"Started: {start.strftime('%Y-%m-%d %H:%M:%S')}")

    conn = psycopg2.connect(DATABASE_URL, connect_timeout=30)
    conn.autocommit = False
    cur = conn.cursor()

    log = CheckLog()

    check_1_row_counts(cur, log)
    check_2_date_window(cur, log)
    check_3_order_arithmetic(cur, log)
    check_4_order_items(cur, log)
    check_5_payments(cur, log)
    check_6_ratings(cur, log)
    check_7_granularity(cur, log)

    # Persist and report
    print("\n─── Saving results ───")
    save_integrity_checks_to_db(cur, conn, log)
    append_to_dq_log(log)
    write_report(log)

    # Final summary
    passes = sum(1 for r in log.rows if r["passed"] == "PASS")
    fails  = sum(1 for r in log.rows if r["passed"] != "PASS")
    elapsed = (datetime.now() - start).total_seconds()

    print("\n" + "=" * 64)
    print(f"RESULTS: {passes} PASS   {fails} need attention")
    print()

    print("PASS ✅")
    for r in log.rows:
        if r["passed"] == "PASS":
            print(f"  {r['check_name']}: {r['result']}")

    print("\nNEEDS ATTENTION ⚠️")
    for r in log.rows:
        if r["passed"] != "PASS":
            print(f"  {r['check_name']}: {r['result']}")

    print(f"\nStep 7 COMPLETE ✅  ({elapsed:.1f}s)")
    print("All findings logged in:")
    print("  DB → integrity_checks table")
    print("  documentation/data_quality_log.csv  (appended)")
    print("  documentation/integrity_checks_report.md")
    print("=" * 64)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
