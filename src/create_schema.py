"""
src/create_schema.py
--------------------
Step 3: Create the Zomato database schema.

Reads DATABASE_URL from .env, runs sql/schema.sql against the database,
and verifies all 12 production tables + helper objects were created.

Usage:
    python src/create_schema.py
"""

import os
import re
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent   # project root
SCHEMA_FILE = ROOT / "sql" / "schema.sql"

load_dotenv(ROOT / ".env")
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    sys.exit("ERROR: DATABASE_URL not found in .env")

EXPECTED_TABLES = [
    "city_aliases",
    "cities",
    "customers",
    "restaurants",
    "delivery_partners",
    "promotions",
    "weather",
    "traffic",
    "menu",
    "orders",
    "order_items",
    "payments",
    "customer_feedback",
]

# ---------------------------------------------------------------------------
# SQL splitter — strips line comments first, then splits on semicolons
# while respecting $$ dollar-quoted function bodies.
# ---------------------------------------------------------------------------

def strip_line_comments(sql: str) -> str:
    """Remove -- line comments, preserving newlines so line count stays stable."""
    cleaned = []
    for line in sql.splitlines():
        cleaned.append(re.sub(r"--.*$", "", line))
    return "\n".join(cleaned)


def split_statements(sql: str) -> list[str]:
    """
    Split a SQL script into individual statements.
    Handles $$ dollar-quoted PL/pgSQL bodies correctly.
    """
    sql = strip_line_comments(sql)
    statements: list[str] = []
    pos = 0
    start = 0
    in_dollar_quote = False
    length = len(sql)

    while pos < length:
        # Toggle dollar-quote mode on every $$ pair
        if sql[pos : pos + 2] == "$$":
            in_dollar_quote = not in_dollar_quote
            pos += 2
            continue

        # Statement boundary: semicolon outside any dollar-quote block
        if sql[pos] == ";" and not in_dollar_quote:
            stmt = sql[start : pos + 1].strip()
            if stmt:
                statements.append(stmt)
            start = pos + 1

        pos += 1

    # Flush any trailing content (e.g. a final statement without trailing newline)
    remainder = sql[start:].strip()
    if remainder:
        statements.append(remainder)

    return [s for s in statements if s.strip()]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 62)
    print("Zomato BI — Step 3: Create Database Schema")
    print("=" * 62)

    # 1. Read schema
    if not SCHEMA_FILE.exists():
        sys.exit(f"ERROR: Schema file not found at {SCHEMA_FILE}")

    sql_text = SCHEMA_FILE.read_text(encoding="utf-8")
    print(f"\nSchema file  : {SCHEMA_FILE.relative_to(ROOT)}")
    print(f"File size    : {len(sql_text):,} characters")

    statements = split_statements(sql_text)
    print(f"Statements   : {len(statements)}")

    # 2. Connect
    print(f"\nConnecting to database ...")
    try:
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=15)
        conn.autocommit = False
        cur = conn.cursor()
        cur.execute("SELECT version();")
        print(f"Connected    : {cur.fetchone()[0][:70]}")
    except Exception as e:
        sys.exit(f"ERROR: Connection failed — {e}")

    # 3. Execute each statement inside one transaction
    print("\nExecuting schema ...")
    print("-" * 62)

    counts = {"DROP": 0, "CREATE TABLE": 0, "CREATE INDEX": 0,
              "CREATE OR REPLACE FUNCTION": 0, "INSERT": 0, "OTHER": 0}
    errors: list[tuple] = []

    for i, stmt in enumerate(statements, 1):
        first_line = stmt.strip().splitlines()[0][:70]
        upper = stmt.strip().upper()

        try:
            cur.execute(stmt)
            label = "OTHER"
            for key in counts:
                if upper.startswith(key):
                    label = key
                    break
            counts[label] += 1
            print(f"  [{i:02d}] OK  {first_line}")

        except Exception as e:
            errors.append((i, first_line, str(e)))
            print(f"  [{i:02d}] ERR {first_line}")
            print(f"       --> {e}")
            # Roll back and abort — we want a clean schema or nothing
            conn.rollback()
            conn.close()
            print("\nTransaction rolled back. Fix the error and re-run.")
            sys.exit(1)

    # 4. Commit
    conn.commit()
    print("-" * 62)
    print("Transaction committed ✅\n")

    # 5. Execution summary
    print("Execution summary:")
    for k, v in counts.items():
        if v > 0:
            print(f"  {k:<30} {v}")

    # 6. Verify tables
    print("\nVerifying tables ...")
    cur.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """)
    existing = {row[0] for row in cur.fetchall()}

    all_ok = True
    for table in EXPECTED_TABLES:
        if table in existing:
            print(f"  ✅  {table}")
        else:
            print(f"  ❌  {table}  — MISSING")
            all_ok = False

    # 7. Verify indexes
    print("\nVerifying indexes ...")
    cur.execute("""
        SELECT indexname, tablename
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND indexname NOT LIKE '%_pkey'
          AND indexname NOT LIKE '%_key'
        ORDER BY tablename, indexname;
    """)
    indexes = cur.fetchall()
    for idx_name, tbl_name in indexes:
        print(f"  ✅  {idx_name}  (on {tbl_name})")
    print(f"  Total analytical indexes: {len(indexes)}")

    # 8. Verify helper functions
    print("\nVerifying helper functions ...")
    cur.execute("""
        SELECT routine_name, data_type
        FROM information_schema.routines
        WHERE routine_schema = 'public'
          AND routine_type = 'FUNCTION'
          AND routine_name IN ('parse_mixed_date', 'parse_ddmmyyyy', 'to_num')
        ORDER BY routine_name;
    """)
    funcs = cur.fetchall()
    for fn_name, ret_type in funcs:
        print(f"  ✅  {fn_name}()  → {ret_type}")

    # 9. city_aliases row count
    cur.execute("SELECT COUNT(*) FROM city_aliases;")
    alias_count = cur.fetchone()[0]
    print(f"\ncity_aliases rows : {alias_count} variant spellings seeded")

    conn.close()

    # 10. Final status
    print("\n" + "=" * 62)
    if all_ok:
        print("Step 3 COMPLETE ✅")
        print("All 12 production tables + helper objects created.")
        print("Next: python src/ingest.py   (loads staging area)")
    else:
        print("Step 3 completed WITH MISSING TABLES — review output above.")
    print("=" * 62)


if __name__ == "__main__":
    main()
