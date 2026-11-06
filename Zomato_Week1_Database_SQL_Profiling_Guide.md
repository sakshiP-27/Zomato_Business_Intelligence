# Week 1 Guide: Zomato Business Intelligence & Delivery Time Prediction
### A beginner-friendly walkthrough — Foundations: Database, SQL & Data Profiling

---

## Before You Start

**Goal for this week:** Get all 12 raw CSV files into a properly designed PostgreSQL database, find and log every data-quality problem, and write **20+ saved SQL queries** (including 2+ views and 1 index) that answer real business questions.

**Why this matters:** Everything after this week sits on top of it. Week 2 cleans and engineers features in Python, Week 3 does EDA and machine learning, and Week 4 builds the Power BI dashboard. If the database is wrong or the business definitions are fuzzy, every later number inherits the mistake. This week also covers two of the biggest rubric items: **Data Cleaning (15%)** and **SQL Skills (15%)**.

**The PRD's Week 1 plan, day by day:**

| Day | Focus |
|---|---|
| Day 1 | Review all 12 datasets, design the ER diagram, finalize keys and relationships |
| Day 2 | Write `CREATE TABLE` statements, load the data, run integrity checks |
| Day 3 | Profile every table for missing values, duplicates, and format issues; log findings |
| Day 4 | Write and test 10+ SQL queries (joins, aggregations, subqueries, CTEs) |
| Day 5 | Write 10+ advanced SQL queries (window functions, views); checkpoint review |

**Three things the PRD doesn't spell out, so read these before starting:**

1. **Dirty data vs. strict database rules.** The PRD wants primary and foreign keys *enforced* (FR-01), but it also says the files contain duplicate rows, mixed date formats, and orphaned foreign keys. A strict table will simply **reject** those rows, and the whole load will fail. The fix is a standard two-step method: load the raw files into a **staging area** first (everything stored as plain text), then move the data into the real tables with light cleaning (Steps 4–6). This guide uses that method.
2. **There is no "promised delivery time" column.** The PRD talks about "late deliveries (actual time exceeding promised time)", but `orders.csv` only has `DeliveryTimeMinutes`. So *she* has to define what "late" means and document it (Step 8). This is a real analyst decision, and graders will like seeing it handled deliberately.
3. **Never use "today's date" in the queries.** The data is a 24-month snapshot. A query like "last 6 months" must be measured back from the **latest order date in the data**, not from `CURRENT_DATE`, or it will return nothing (or the wrong thing).

**How Week 1 cleaning relates to Week 2 cleaning:** This week she only does the cleaning that is *needed to get data into the database* (trimming spaces, standardizing city names, parsing dates, removing exact duplicates, handling orphan rows) and she **logs** everything else. The heavy cleaning (outliers, imputation, phone/pincode repair, merging into the analytical table) is Week 2 in Python. Please don't try to do all of it now.

**What she needs before starting:**
- The 12 raw CSVs
- PostgreSQL 14+ (installed locally, or run with Docker: `docker run --name zomato-db -e POSTGRES_PASSWORD=yourpassword -p 5432:5432 -d postgres`)
- A SQL client: pgAdmin or DBeaver
- `pip install pandas numpy sqlalchemy psycopg2-binary jupyter`
- Git and a GitHub account

**This week's checkpoint:** an ER diagram, a working `schema.sql`, a populated database with row-count reconciliation, a data-quality log, and `business_queries.sql` with 20+ queries, 2+ views, and 1 documented index.

---

## Step 1 (Day 1): Set Up the Project Folder and Inspect All 12 Datasets

**Create the folder structure from the PRD:**

```
Zomato_Business_Intelligence_Project/
├── data/
│   ├── raw/          ← the 12 CSVs go here, never edited
│   └── cleaned/      ← Week 2 output
├── sql/
│   ├── schema.sql
│   └── business_queries.sql
├── notebooks/
├── src/
├── models/
├── reports/
├── powerbi/
├── images/
├── documentation/
├── README.md
└── requirements.txt
```
Run `git init`, add a `.gitignore`, and put the raw CSVs in `data/raw/`. **Never edit files in `raw/`**. They are the untouched source of truth.

**Then open every CSV and look before touching anything.** For each file, check:
1. **Row and column count**: does it match the PRD (customers ≈ 12,000, orders ≈ 20,000+, etc.)?
2. **What the ID columns look like**: are they plain numbers (`1042`) or text like `C00123`? This decides whether the key columns become `INT` or `VARCHAR`.
3. **The distinct values of every category column**: `OrderStatus`, `PaymentMethod`, `PaymentStatus`, `Membership`, `Gender`, `VehicleType`, `RestaurantType`, `Cuisine`, `Sentiment`, `WeatherCondition`, `TrafficLevel`, `Availability`. You will use these exact spellings in your queries (for example whether cancelled orders say `Cancelled`, `cancelled`, or `CANCELLED`).

Write what she notices in a short `documentation/data_notes.md`. A 12-row table is enough: file, rows, ID format, and anything odd.

```python
import pandas as pd
df = pd.read_csv("data/raw/orders.csv", dtype=str)   # dtype=str: read everything as text, no guessing
print(df.shape)
print(df.head())
print(df["OrderStatus"].value_counts(dropna=False))
```

✅ **Done when:** She has looked at all 12 files and `data_notes.md` lists row counts, ID formats, and the real values of each category column.

---

## Step 2 (Day 1): Design the ER Diagram

**What this means:** A picture of the tables and how they connect (which table points to which). It is the blueprint for the database.

**The 12 tables and how they link** (from PRD Section 18):

| Table | Primary key | Points to (foreign keys) |
|---|---|---|
| cities | city_id | — |
| customers | customer_id | city → cities |
| restaurants | restaurant_id | city → cities |
| menu | food_item_id | restaurant_id → restaurants |
| delivery_partners | delivery_partner_id | city → cities |
| promotions | promotion_id (coupon_code is unique) | — |
| orders | order_id | customer_id → customers, restaurant_id → restaurants, delivery_partner_id → delivery_partners, coupon_code → promotions |
| order_items | order_item_id | order_id → orders, food_item_id → menu |
| payments | payment_id | order_id → orders |
| customer_feedback | feedback_id | order_id → orders |
| weather | weather_id | city → cities |
| traffic | traffic_id | city → cities |

**A small inconsistency in the PRD that she should catch and fix herself:** `cities` has `CityID` as its primary key, but every other table points to `cities.City` (the *name*). In SQL, a foreign key can only point to a column that is **unique**. The simplest fix: keep `city_id` as the primary key and also make `city` **UNIQUE NOT NULL**, then link other tables on `city`. Write this decision in the design notes. It shows she read the design critically.

**Notes on the design that are worth understanding (they are also good interview answers):**
- `order_items` is separate from `orders` because one order has many items. That avoids repeating columns, which is what "normalization" means.
- `menu` is separate from `restaurants` because a food item has its own attributes (price, calories) that don't belong to the restaurant itself.
- City facts (population, income) live only in `cities`, not repeated in every customer row.
- `orders` has no city column. If she later needs "orders by city", the city comes from the order's **restaurant**. Decide this now, state it in the notes, and use it consistently.

**How to draw it:** Use dbdiagram.io (free, you type text and it draws), draw.io, or DBeaver's built-in ER diagram. Export the image to `images/er_diagram.png`.

✅ **Done when:** `images/er_diagram.png` shows all 12 tables with keys and arrows, and the `cities.city` decision is written down.

---

## Step 3 (Day 2): Create the Database and Write `schema.sql`

**What this means:** Turn the diagram into real tables with correct data types, primary keys, and foreign keys.

**How to do it:**
1. Create an empty database: `CREATE DATABASE zomato;`
2. Use **snake_case lowercase column names** (`order_id`, `delivery_time_minutes`). PostgreSQL silently lowercases unquoted names, so CamelCase like `OrderID` causes constant confusion. The next step converts the CSV headers automatically.
3. Write `sql/schema.sql`. **Create parent tables before child tables**, otherwise a foreign key points at a table that doesn't exist yet. Order: `cities` → `customers`, `restaurants`, `delivery_partners`, `promotions`, `weather`, `traffic` → `menu` → `orders` → `order_items`, `payments`, `customer_feedback`.

**Data-type habits that avoid pain later:**
- **Phone and pincode are `TEXT`, never numbers.** They are identifiers, not quantities, and numeric types would drop leading digits.
- Money columns: `NUMERIC(10,2)`. Never `FLOAT` for money.
- Dates: `DATE`. Times: `TIME`.
- Put `NOT NULL` only on primary keys and foreign keys for now. Don't add `CHECK (value > 0)` rules yet, because the data deliberately contains negative and zero values that you want to *find and study*, not reject.

**Example, the first tables (the rest follow the same pattern):**

```sql
CREATE TABLE cities (
    city_id        INT PRIMARY KEY,
    city           VARCHAR(60) NOT NULL UNIQUE,   -- UNIQUE so other tables can point to it
    population     BIGINT,
    region         VARCHAR(40),
    average_income NUMERIC(12,2)
);

CREATE TABLE customers (
    customer_id       VARCHAR(20) PRIMARY KEY,    -- use INT instead if your IDs are plain numbers
    name              VARCHAR(100),
    age               SMALLINT,
    gender            VARCHAR(20),
    phone             VARCHAR(20),
    email             VARCHAR(120),
    city              VARCHAR(60) REFERENCES cities(city),
    state             VARCHAR(60),
    pincode           VARCHAR(10),
    registration_date DATE,
    membership        VARCHAR(30),
    total_orders      INT,
    preferred_cuisine VARCHAR(60)
);

CREATE TABLE orders (
    order_id              VARCHAR(20) PRIMARY KEY,
    customer_id           VARCHAR(20) NOT NULL REFERENCES customers(customer_id),
    restaurant_id         VARCHAR(20) NOT NULL REFERENCES restaurants(restaurant_id),
    delivery_partner_id   VARCHAR(20) REFERENCES delivery_partners(delivery_partner_id),
    order_date            DATE,
    order_time            TIME,
    delivery_time_minutes NUMERIC(8,1),
    food_cost             NUMERIC(10,2),
    delivery_fee          NUMERIC(10,2),
    discount              NUMERIC(10,2),
    coupon_code           VARCHAR(30) REFERENCES promotions(coupon_code),
    gst                   NUMERIC(10,2),
    final_amount          NUMERIC(10,2),
    order_status          VARCHAR(30),
    payment_method        VARCHAR(30)
);
```
`delivery_partner_id` and `coupon_code` are deliberately *not* `NOT NULL`. A cancelled order may never have had a delivery partner, and most orders have no coupon. (`promotions.coupon_code` must be declared `UNIQUE` so `orders` can point to it.)

Keep `schema.sql` re-runnable by starting it with `DROP TABLE IF EXISTS ... CASCADE;` lines (children first).

✅ **Done when:** Running `schema.sql` creates all 12 empty tables with no errors, and DBeaver's ER view of the *real* database matches her diagram.

---

## Step 4 (Day 2): Load the Raw CSVs into a Staging Area

**What this means:** A "staging" schema is a holding area where every raw column is stored as plain text, with **no rules**. Nothing can fail to load, so the real data problems become visible and measurable with SQL.

**How to do it:**
```python
import re
import pandas as pd
from pathlib import Path
from sqlalchemy import create_engine, text

engine = create_engine("postgresql+psycopg2://postgres:yourpassword@localhost:5432/zomato")

def to_snake(name: str) -> str:
    """OrderID -> order_id, DeliveryTimeMinutes -> delivery_time_minutes"""
    name = name.strip()
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    return name.lower()

with engine.begin() as conn:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS staging"))

for csv in sorted(Path("data/raw").glob("*.csv")):
    df = pd.read_csv(csv, dtype=str)                 # everything as text, nothing "fixed" by pandas
    df.columns = [to_snake(c) for c in df.columns]
    df.to_sql(csv.stem, engine, schema="staging", if_exists="replace",
              index=False, chunksize=5000)
    print(f"{csv.stem}: {len(df):,} rows loaded to staging")
```
Check that `to_snake` produced the column names you used in `schema.sql` (for example `food_item_id`, `delivery_partner_id`). Fix any mismatch now.

**Keep this as a script** (`src/ingest.py` fits the PRD's folder plan) so the load is repeatable, which the PRD requires (FR-10).

✅ **Done when:** `staging` contains 12 tables, and each `SELECT COUNT(*) FROM staging.<table>` matches the CSV's row count.

---

## Step 5 (Day 3): Profile Every Table and Write the Data-Quality Log

**What this means:** Before fixing anything, *measure* what is wrong, table by table, and write it down. The PRD requires this (FR-02), and the KPI "Data Cleaning Completeness ≥ 95%" is measured against this list. If it isn't on the list, it can't be counted as solved.

**The known issues from the PRD (Section 19.1), and how to find each one:**

| Issue | Tables | How to detect it | Week 1 action | Week 2 action |
|---|---|---|---|---|
| Missing values | Age, Rating, Phone, Email, DeliveryTimeMinutes, Review | Count NULL and blank per column | Load as NULL, log counts | Decide imputation per column |
| Duplicate rows | orders, payments, customer_feedback | Count repeated primary keys, and fully identical rows | Remove duplicates while loading | Document in cleaning log |
| Inconsistent city names | customers, restaurants, delivery_partners, weather, traffic | `SELECT DISTINCT LOWER(TRIM(city))` and compare with `cities` | Map to the canonical name (needed for the foreign key) | Re-verify in pandas |
| Extra whitespace | names, cuisines, areas | Compare `col` with `TRIM(col)` | `TRIM` while loading | Re-verify |
| Mixed date formats | orders, weather, traffic, promotions | Pattern checks (below) | Parse into real `DATE` while loading | Re-verify |
| Bad phone numbers / pincodes | customers (and others) | Regex checks (below) | Log only | Fix or null out |
| Negative / zero values | food_cost, delivery_fee, delivery_time_minutes | Count `<= 0` | Keep, log, and exclude them from analysis with a view | Decide fix |
| Outliers | delivery_time_minutes, average_delivery_time | Look at percentiles and a boxplot | Log only | Cap or remove |
| Orphaned foreign keys | orders and child tables | `LEFT JOIN ... WHERE parent IS NULL` | Move to a quarantine table | Document |

**A reusable profiling function (so she doesn't write 100 queries by hand):**

```python
import pandas as pd

def profile_table(name: str, df: pd.DataFrame, pk: str) -> pd.DataFrame:
    """Return one row per column describing its data-quality problems."""
    rows = []
    for col in df.columns:
        s = df[col]
        nonnull = s.dropna()
        rows.append({
            "table": name,
            "column": col,
            "null_or_blank": int(s.isna().sum() + (nonnull.str.strip() == "").sum()),
            "has_extra_spaces": int((nonnull != nonnull.str.strip()).sum()),
            "distinct_values": int(s.nunique()),
        })
    out = pd.DataFrame(rows)
    out["duplicate_full_rows"] = int(df.duplicated().sum())
    out["duplicate_primary_keys"] = int(df[pk].duplicated().sum())
    return out
```

**Specific format checks (add these on top):**

```python
def date_format_counts(s: pd.Series) -> pd.Series:
    """How many values follow each of the date formats named in the PRD?"""
    s = s.dropna().str.strip()
    counts = {
        "DD-MM-YYYY": s.str.match(r"^\d{2}-\d{2}-\d{4}$").sum(),
        "MM/DD/YYYY": s.str.match(r"^\d{2}/\d{2}/\d{4}$").sum(),
        "YYYY.MM.DD": s.str.match(r"^\d{4}\.\d{2}\.\d{2}$").sum(),
        "YYYY-MM-DD": s.str.match(r"^\d{4}-\d{2}-\d{2}$").sum(),
    }
    counts["other/invalid"] = len(s) - sum(counts.values())
    return pd.Series(counts)

# Indian mobile numbers: 10 digits starting with 6-9. Pincodes: 6 digits.
bad_phone   = ~df["phone"].dropna().str.strip().str.match(r"^[6-9]\d{9}$")
bad_pincode = ~df["pincode"].dropna().str.strip().str.match(r"^\d{6}$")
```
For non-positive values, run: `(pd.to_numeric(df["food_cost"], errors="coerce") <= 0).sum()`. For outliers, print `describe(percentiles=[.5,.9,.99])` on `delivery_time_minutes`.

**The Data-Quality Log (the deliverable of this step).** Save it as `documentation/data_quality_log.csv` or a markdown table with these columns:

| table | column | issue | count | % of rows | example bad value | planned fix | status |
|---|---|---|---|---|---|---|---|

The `status` column (`found` → `fixed in SQL` → `fixed in Python` → `verified`) is what turns this into your "% of issues resolved" number at the end. Keep updating it through Weeks 1 and 2.

✅ **Done when:** Every table has been profiled, every issue category above has at least a count (even if the count is zero), and the log file exists.

---

## Step 6 (Day 3): Move the Data from Staging into the Real Tables

**What this means:** Use SQL to copy each staging table into its typed, constrained table, applying only the light cleaning that is needed for the load to succeed. This is the "ETL" step (extract, transform, load).

**Load in the same parent-before-child order as the schema.** For each table, the pattern is: trim → convert type → remove duplicates → keep only rows whose parents exist.

### 6a. Two small helper functions (create these once)

```sql
-- Converts messy text to a DATE. Returns NULL instead of crashing when it can't parse.
CREATE OR REPLACE FUNCTION parse_mixed_date(s TEXT) RETURNS DATE AS $$
BEGIN
    s := NULLIF(TRIM(s), '');
    IF s IS NULL THEN RETURN NULL; END IF;
    IF    s ~ '^\d{2}-\d{2}-\d{4}$' THEN RETURN TO_DATE(s, 'DD-MM-YYYY');
    ELSIF s ~ '^\d{2}/\d{2}/\d{4}$' THEN RETURN TO_DATE(s, 'MM/DD/YYYY');
    ELSIF s ~ '^\d{4}\.\d{2}\.\d{2}$' THEN RETURN TO_DATE(s, 'YYYY.MM.DD');
    ELSIF s ~ '^\d{4}-\d{2}-\d{2}$' THEN RETURN s::date;
    ELSE RETURN NULL;
    END IF;
EXCEPTION WHEN others THEN
    RETURN NULL;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Converts text to a number, or NULL if it isn't one ('N/A', 'abc', blank...).
CREATE OR REPLACE FUNCTION to_num(s TEXT) RETURNS NUMERIC AS $$
BEGIN
    RETURN NULLIF(TRIM(s), '')::NUMERIC;
EXCEPTION WHEN others THEN
    RETURN NULL;
END;
$$ LANGUAGE plpgsql IMMUTABLE;
```
**Check the date parsing.** The three formats are told apart by their separators (`-`, `/`, `.`), so this works *if* the PRD's description is accurate. Verify it: after loading, `SELECT MIN(order_date), MAX(order_date) FROM orders;` should span about 24 months. If you see dates outside that window, some dates were probably read the wrong way round (day and month swapped), so investigate before moving on.

### 6b. Standardize city names with an alias table

1. Find every spelling: `SELECT DISTINCT LOWER(TRIM(city)) FROM staging.customers ORDER BY 1;` (repeat for restaurants, delivery_partners, weather, traffic).
2. Compare with the official list in `cities`. Build a small mapping table:

```sql
CREATE TABLE city_aliases (alias TEXT PRIMARY KEY, canonical TEXT NOT NULL);
INSERT INTO city_aliases VALUES
  ('bangalore', 'Bengaluru'),
  ('bengaluru', 'Bengaluru');
  -- add one row per variant you actually find
```
3. Use it while loading: `LEFT JOIN city_aliases a ON a.alias = LOWER(TRIM(s.city))` then `COALESCE(a.canonical, INITCAP(TRIM(s.city)))`.

Load `cities` first (trim it too), then everything else that points to it.

### 6c. Example: loading `customers`

```sql
INSERT INTO customers (customer_id, name, age, gender, phone, email, city, state,
                       pincode, registration_date, membership, total_orders, preferred_cuisine)
SELECT customer_id, name, age, gender, phone, email, city, state,
       pincode, registration_date, membership, total_orders, preferred_cuisine
FROM (
    SELECT TRIM(s.customer_id)                                    AS customer_id,
           TRIM(s.name)                                           AS name,
           CASE WHEN TRIM(s.age) ~ '^\d{1,3}$' THEN TRIM(s.age)::int END AS age,
           INITCAP(TRIM(s.gender))                                AS gender,
           NULLIF(TRIM(s.phone), '')                              AS phone,      -- logged only; fixed in Week 2
           NULLIF(TRIM(s.email), '')                              AS email,
           COALESCE(a.canonical, INITCAP(TRIM(s.city)))           AS city,
           TRIM(s.state)                                          AS state,
           NULLIF(TRIM(s.pincode), '')                            AS pincode,
           parse_mixed_date(s.registration_date)                  AS registration_date,
           INITCAP(TRIM(s.membership))                            AS membership,
           to_num(s.total_orders)::int                            AS total_orders,
           TRIM(s.preferred_cuisine)                              AS preferred_cuisine,
           ROW_NUMBER() OVER (PARTITION BY TRIM(s.customer_id))   AS rn   -- numbers repeats of the same ID
    FROM staging.customers s
    LEFT JOIN city_aliases a ON a.alias = LOWER(TRIM(s.city))
) x
WHERE rn = 1;   -- keep one row per customer_id
```
**Before relying on `rn = 1`, check what the duplicates really are.** If they are identical copies, which one you keep doesn't matter. If the same ID appears with *different* values, you need a rule (for example keep the row with fewer blanks) and you must write that rule in the log.

### 6d. Orders: the table where problems show up

`orders` has the most foreign keys, so most orphans appear here. The pattern is the same as above, plus one extra filter that keeps only rows whose parents exist:

```sql
WITH cleaned AS (
    SELECT TRIM(order_id)                       AS order_id,
           TRIM(customer_id)                    AS customer_id,
           TRIM(restaurant_id)                  AS restaurant_id,
           NULLIF(TRIM(delivery_partner_id),'') AS delivery_partner_id,
           parse_mixed_date(order_date)         AS order_date,
           CASE WHEN TRIM(order_time) ~ '^\d{1,2}:\d{2}(:\d{2})?$'
                THEN TRIM(order_time)::time END AS order_time,
           to_num(delivery_time_minutes)        AS delivery_time_minutes,
           to_num(food_cost)                    AS food_cost,
           to_num(delivery_fee)                 AS delivery_fee,
           to_num(discount)                     AS discount,
           NULLIF(UPPER(TRIM(coupon_code)),'')  AS coupon_code,
           to_num(gst)                          AS gst,
           to_num(final_amount)                 AS final_amount,
           INITCAP(TRIM(order_status))          AS order_status,
           INITCAP(TRIM(payment_method))        AS payment_method
    FROM staging.orders
),
deduped AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY order_id) AS rn FROM cleaned
)
INSERT INTO orders (order_id, customer_id, restaurant_id, delivery_partner_id, order_date,
                    order_time, delivery_time_minutes, food_cost, delivery_fee, discount,
                    coupon_code, gst, final_amount, order_status, payment_method)
SELECT order_id, customer_id, restaurant_id, delivery_partner_id, order_date,
       order_time, delivery_time_minutes, food_cost, delivery_fee, discount,
       coupon_code, gst, final_amount, order_status, payment_method
FROM deduped d
WHERE rn = 1
  AND EXISTS (SELECT 1 FROM customers   c WHERE c.customer_id   = d.customer_id)
  AND EXISTS (SELECT 1 FROM restaurants r WHERE r.restaurant_id = d.restaurant_id)
  AND (d.delivery_partner_id IS NULL
       OR EXISTS (SELECT 1 FROM delivery_partners p WHERE p.delivery_partner_id = d.delivery_partner_id))
  AND (d.coupon_code IS NULL
       OR EXISTS (SELECT 1 FROM promotions p WHERE p.coupon_code = d.coupon_code));
```
If the load fails on a particular row, the error message names the constraint. Read it carefully, because it is telling you exactly which kind of problem you've found.

### 6e. Don't throw away rejected rows: quarantine them

"Handled deliberately" (PRD) means she can show *what* was excluded and *why*.

```sql
CREATE TABLE quarantine_orders AS
SELECT s.*,
       CASE
         WHEN NOT EXISTS (SELECT 1 FROM customers c   WHERE c.customer_id   = TRIM(s.customer_id))   THEN 'unknown customer'
         WHEN NOT EXISTS (SELECT 1 FROM restaurants r WHERE r.restaurant_id = TRIM(s.restaurant_id)) THEN 'unknown restaurant'
         ELSE 'other (partner / coupon / key problem)'
       END AS reason
FROM staging.orders s
WHERE TRIM(s.order_id) NOT IN (SELECT order_id FROM orders);
```
Repeat the idea for child tables: `order_items`, `payments`, and `customer_feedback` should only load rows whose `order_id` now exists in `orders`, and `order_items` also needs its `food_item_id` to exist in `menu`.

### 6f. The reconciliation table (a great piece of evidence)

For every table, show that no rows silently disappeared:

```sql
SELECT 'orders' AS table_name,
       (SELECT COUNT(*) FROM staging.orders)                       AS raw_rows,
       (SELECT COUNT(DISTINCT TRIM(order_id)) FROM staging.orders) AS unique_ids,
       (SELECT COUNT(*) FROM orders)                               AS loaded_rows,
       (SELECT COUNT(*) FROM quarantine_orders)                    AS quarantined_rows;
```
`raw_rows − unique_ids` is the number of duplicates removed. The rule to check: `unique_ids = loaded_rows + quarantined_rows`. If the numbers don't add up, find the missing rows before going on.

✅ **Done when:** All 12 final tables are populated, quarantine tables exist for rejected rows, and a reconciliation table accounts for every raw row.

---

## Step 7 (Day 2–3): Run Integrity Checks

**What this means:** Prove the loaded database is internally consistent. Foreign keys already guarantee that parents exist, so these checks look at *meaning*, which constraints can't catch.

**A checklist of checks to run and write up:**
1. **Row counts** match the reconciliation table.
2. **Date window:** `MIN`/`MAX` of `order_date` span roughly 24 months, with no future dates.
3. **Arithmetic in orders:** does `final_amount` equal `food_cost + delivery_fee − discount + gst`? Count the rows that don't match by more than ₹1. *Test this before assuming it. The data's own formula may differ.*
```sql
SELECT COUNT(*) FILTER (WHERE ABS(final_amount - (food_cost + delivery_fee - discount + gst)) > 1) AS mismatches,
       COUNT(*) AS total
FROM orders
WHERE final_amount IS NOT NULL AND food_cost IS NOT NULL;
```
4. **Order items:** does `quantity × unit_price = total_price`? Does the sum of an order's item totals match its `food_cost`?
5. **Payments:** are there orders with no payment, or more than one? Does `payments.payment_method` agree with `orders.payment_method`?
6. **Ratings** in `customer_feedback` stay within the valid range (for example 1–5).
7. **Weather and traffic:** is there exactly one row per city per date (or per date-and-time for traffic)? If not, a later join will multiply rows and inflate your totals.

Log every finding in the data-quality log, even when everything is fine. A check that passes is still evidence.

✅ **Done when:** Each check has a result written down, and any surprise is logged with a plan.

---

## Step 8 (Day 4): Define the Business Rules Before Writing Queries

**What this means:** The PRD's whole business case is that teams use *inconsistent definitions* of "late delivery," "active customer," and "top restaurant." So write the definitions down once, and use them in every query, notebook, and dashboard.

| Term | Suggested definition (she should confirm after looking at the data) |
|---|---|
| **Revenue** | `SUM(final_amount)` for completed orders only. Check the exact `order_status` values from Step 1 and exclude cancelled ones. |
| **Valid delivery time** | `delivery_time_minutes > 0` for now. An upper cap is decided in Week 2 after outlier analysis. |
| **Late delivery** | There is no promised-time column, so choose a rule, for example *"delivery time above 45 minutes"*, or *"above the 75th percentile of that city"*. Look at the distribution first (median, 75th, 90th percentile), pick one, justify it in a sentence, and **keep it identical in Weeks 2–4** (Power BI's "% late deliveries" depends on it). |
| **Active customer** | Placed at least one order in the **60 days before the latest order date in the data**. (This also matches the 60-day churn horizon used in Week 3.) |
| **Top restaurant** | Highest composite performance score (rating, cancellation rate, delivery delay), built in Step 10. |
| **Reference date** | `SELECT MAX(order_date) FROM orders`. Use this, never `CURRENT_DATE`. |

Save this as `documentation/kpi_definitions.md`. It is quick to write and it is exactly the kind of thing the "Business Insights" and "Documentation" rubric rows reward.

✅ **Done when:** `kpi_definitions.md` exists, and the "late delivery" threshold is chosen and justified.

---

## Step 9 (Day 4): Write 10+ Core SQL Queries

**What this means:** The PRD requires **20+ distinct saved queries** overall. Day 4 covers the first half: joins, aggregations, subqueries, and CTEs. Save everything in `sql/business_queries.sql`, each with a comment on top stating the question it answers.

**Required constructs to hit (PRD Section 20), and suggested queries for each:**

| # | Business question | Constructs |
|---|---|---|
| 1 | Orders, revenue, and average order value by order status | `GROUP BY`, aggregates |
| 2 | Top 10 restaurants by revenue in the last 6 months | `JOIN`, `WHERE`, `ORDER BY`, date arithmetic |
| 3 | Average delivery time by city, slowest to fastest | `JOIN`, `GROUP BY`, `ORDER BY` |
| 4 | Cancellation % by cuisine | `CASE WHEN`, `JOIN` |
| 5 | Cities whose average delivery time is above the overall average | `HAVING`, scalar subquery |
| 6 | Customers who have never ordered | `LEFT JOIN … IS NULL` |
| 7 | The same result written with a `RIGHT JOIN` | `RIGHT JOIN` |
| 8 | Coupon codes: total discount given and order volume | `JOIN`, `HAVING` |
| 9 | Orders bucketed into low / medium / high value | `CASE WHEN` |
| 10 | Pairs of restaurants in the same city serving the same cuisine | `SELF JOIN` |
| 11 | One list combining top spenders and most frequent customers, with a label | `UNION` |
| 12 | Orders whose value is above that restaurant's own average | correlated subquery |
| 13 | New vs. repeat customers (one order vs. more) | CTE (`WITH`) |
| 14 | Average basket size by membership tier | multi-table `JOIN` |
| 15 | Payment method share of orders, in percent | aggregates, percentage maths |

**Worked examples, so she sees the style (adapt the column and status names to her data):**

```sql
-- Q2: Top 10 restaurants by revenue in the last 6 months of the data
SELECT r.restaurant_name, r.city, ROUND(SUM(o.final_amount), 2) AS revenue
FROM orders o
JOIN restaurants r ON r.restaurant_id = o.restaurant_id
WHERE o.order_status = 'Delivered'                       -- check the real status text!
  AND o.order_date > (SELECT MAX(order_date) FROM orders) - INTERVAL '6 months'
GROUP BY r.restaurant_id, r.restaurant_name, r.city
ORDER BY revenue DESC
LIMIT 10;
```

```sql
-- Q4: Cancellation percentage by cuisine
SELECT r.cuisine,
       COUNT(*) AS total_orders,
       SUM(CASE WHEN o.order_status = 'Cancelled' THEN 1 ELSE 0 END) AS cancelled,
       ROUND(100.0 * SUM(CASE WHEN o.order_status = 'Cancelled' THEN 1 ELSE 0 END) / COUNT(*), 2) AS cancel_pct
FROM orders o
JOIN restaurants r ON r.restaurant_id = o.restaurant_id
GROUP BY r.cuisine
ORDER BY cancel_pct DESC;
```

```sql
-- Q13: New vs repeat customers, using a CTE
WITH orders_per_customer AS (
    SELECT customer_id, COUNT(*) AS n_orders
    FROM orders
    GROUP BY customer_id
)
SELECT CASE WHEN n_orders = 1 THEN 'One-time' ELSE 'Repeat' END AS customer_type,
       COUNT(*) AS customers
FROM orders_per_customer
GROUP BY 1;
```

**Habits that make queries trustworthy:**
- After every query, ask: *does this number make sense?* A cancellation rate of 140% or a negative revenue means something is wrong in the query or the data.
- Exclude invalid delivery times (`<= 0`) when averaging delivery times, and say so in a comment.
- Beware of **join fan-out**: joining `orders` to `order_items` repeats the order's `final_amount` once per item, so summing revenue after that join inflates it. Aggregate before joining, or sum at the right level.

✅ **Done when:** 10–15 core queries run correctly, are saved with a comment each, and every PRD construct in the table above appears at least once.

---

## Step 10 (Day 5): Write 10+ Advanced Queries, Views, and an Index

**Suggested advanced queries:**

| # | Business question | Constructs |
|---|---|---|
| 16 | Top 3 restaurants by revenue **within each city** | `RANK()` / `DENSE_RANK()` with `PARTITION BY` |
| 17 | Each customer's most recent order, and days since it (recency) | `ROW_NUMBER()` and date arithmetic |
| 18 | Month-over-month revenue growth % per city | `LAG()` |
| 19 | Days between each customer's consecutive orders | `LEAD()` or `LAG()` |
| 20 | Delivery partners in the top 10% by completed deliveries and rating | `PERCENT_RANK()` or `NTILE(10)` |
| 21 | Cumulative (running) revenue over time | `SUM() OVER (ORDER BY …)` |
| 22 | Average delivery time by weather condition, and by traffic level | joins to `weather` / `traffic` (join on **city and date**, taking the city from the order's restaurant) |
| 23 | Quarterly revenue by cuisine | `EXTRACT(QUARTER …)`, `DATE_TRUNC` |
| 24 | % of late deliveries by city (using your Step 8 rule) | `CASE WHEN`, conditional aggregation |
| 25 | Top and bottom 10 restaurants **per city** by performance score | window function on a view |

**Worked example: month-over-month growth with `LAG()`:**

```sql
WITH monthly AS (
    SELECT r.city,
           DATE_TRUNC('month', o.order_date)::date AS month,
           SUM(o.final_amount) AS revenue
    FROM orders o
    JOIN restaurants r ON r.restaurant_id = o.restaurant_id
    WHERE o.order_status = 'Delivered'
    GROUP BY r.city, DATE_TRUNC('month', o.order_date)
)
SELECT city, month, revenue,
       LAG(revenue) OVER (PARTITION BY city ORDER BY month) AS prev_month_revenue,
       ROUND(100.0 * (revenue - LAG(revenue) OVER (PARTITION BY city ORDER BY month))
             / NULLIF(LAG(revenue) OVER (PARTITION BY city ORDER BY month), 0), 2) AS mom_growth_pct
FROM monthly
ORDER BY city, month;
```
(`NULLIF(..., 0)` prevents a divide-by-zero error.)

### The views (at least 2 are required; build these 4)

Views are saved queries that behave like tables. They keep definitions in one place, and Power BI and Python can read them later.

1. **`v_orders_valid`**: orders with usable values only (for example `delivery_time_minutes > 0`, `food_cost > 0`). Use it in analysis so bad rows don't skew averages, while the raw rows stay in `orders`.
2. **`v_monthly_revenue_by_city`**: the query above without the `LAG` part. PRD User Story 4 asks for exactly this view.
3. **`v_customer_rfm`**: per customer, the days since last order (recency), number of orders (frequency), and total spend (monetary). This becomes the backbone of the churn work in Week 3.
4. **`v_restaurant_performance`**: the composite score from User Story 2 (rating, cancellation rate, delivery delay):

```sql
CREATE OR REPLACE VIEW v_restaurant_performance AS
WITH stats AS (
    SELECT r.restaurant_id, r.restaurant_name, r.city, r.rating,
           COUNT(*) AS total_orders,
           AVG(CASE WHEN o.order_status = 'Cancelled' THEN 1.0 ELSE 0.0 END) AS cancel_rate,
           AVG(o.delivery_time_minutes) FILTER (WHERE o.delivery_time_minutes > 0) AS avg_delivery_min
    FROM restaurants r
    JOIN orders o ON o.restaurant_id = r.restaurant_id
    GROUP BY r.restaurant_id, r.restaurant_name, r.city, r.rating
    HAVING COUNT(*) >= 10          -- ignore restaurants with too few orders to judge fairly
)
SELECT *,
       ROUND((  0.4 * PERCENT_RANK() OVER (PARTITION BY city ORDER BY rating NULLS FIRST)   -- higher rating = better
              + 0.3 * (1 - PERCENT_RANK() OVER (PARTITION BY city ORDER BY cancel_rate))    -- lower cancellations = better
              + 0.3 * (1 - PERCENT_RANK() OVER (PARTITION BY city ORDER BY avg_delivery_min)) -- faster = better
             )::numeric, 3) AS performance_score
FROM stats;
```
The weights (0.4 / 0.3 / 0.3) and the 10-order minimum are **her design choices**. Write the reasoning in a comment. Ranking within each city (not across all cities) keeps the comparison fair between big and small markets. The `NULLS FIRST` on rating matters: it treats a missing rating as the *lowest* rank rather than the highest.

### The index (at least 1 is required, with a documented reason)

PostgreSQL automatically indexes primary keys, but **not foreign key columns**. Queries that look up a customer's orders are very common, so:

```sql
EXPLAIN ANALYZE SELECT * FROM orders WHERE customer_id = '<a real id from your data>';   -- before

CREATE INDEX idx_orders_customer_date ON orders (customer_id, order_date);
ANALYZE orders;

EXPLAIN ANALYZE SELECT * FROM orders WHERE customer_id = '<a real id from your data>';   -- after
```
Write a short note under it: the query, the plan before (for example *Seq Scan*), the plan after (*Index Scan*), and the timings. **Be honest in the note:** with only ~20,000 rows PostgreSQL may keep choosing a sequential scan because the table is small. If the gap is tiny, say so and explain that the index matters as the table grows. Honest reporting reads better than a forced result.

**Optional stretch (clearly mark it "optional" in the file):** one stored procedure and one trigger, for example a trigger that blocks a negative `food_cost`.

✅ **Done when:** She has 10+ advanced queries, at least 2 views (4 recommended), 1 index with a documented before/after, and the total in `business_queries.sql` is 20 or more.

---

## Step 11 (Day 5): Organize, Commit, and Do the Checkpoint Review

**Tidy up:**
1. `sql/schema.sql` runs from scratch with no errors. Test it by dropping and recreating the database once.
2. `sql/business_queries.sql` has numbered queries, each with its question as a comment, and each can be run on its own.
3. Put the load scripts in `sql/` (or `src/ingest.py` for the Python side), so the whole database can be rebuilt by someone else.
4. `documentation/` holds: `data_notes.md`, `data_quality_log.csv`, `kpi_definitions.md`, and the ER diagram lives in `images/`.
5. Commit to Git with clear messages (`Add schema`, `Load staging`, `Add restaurant performance view`) instead of one giant commit at the end.

**Checkpoint self-review (answer honestly):**
- Can I rebuild the database from the raw CSVs by running my scripts in order?
- Does every raw row appear either in a final table, in quarantine, or as a documented duplicate?
- Is every issue in the PRD's list present in my data-quality log with a count?
- Do I have 20+ queries, and does each required construct appear at least once?
- Can I explain, in one sentence each, my definitions of "late delivery", "active customer", and "top restaurant"?

✅ **Done when:** All five answers are "yes," or the gaps are written down with a plan to close them.

---

## Week 1 Checklist: Quick Reference

- [ ] Project folder created, Git initialized, raw CSVs untouched in `data/raw/`
- [ ] All 12 files inspected; `data_notes.md` written (ID formats, category values)
- [ ] ER diagram drawn and saved; `cities.city` made UNIQUE and the choice documented
- [ ] `schema.sql` creates all 12 tables with primary and foreign keys, parents first
- [ ] Raw CSVs loaded into a `staging` schema as text via a repeatable script
- [ ] Data-quality log written (counts for every known issue, with a status column)
- [ ] Helper functions created (`parse_mixed_date`, `to_num`); city alias table built
- [ ] Staging moved into final tables: trimmed, dates parsed, duplicates removed
- [ ] Orphan rows moved to quarantine tables, not silently deleted
- [ ] Reconciliation table shows every raw row accounted for
- [ ] Integrity checks run (date window, arithmetic, items vs. orders, payments, ratings, weather/traffic uniqueness)
- [ ] KPI definitions written (revenue, late delivery, active customer, top restaurant, reference date)
- [ ] 10–15 core queries done (joins incl. RIGHT and SELF, UNION, CASE, subqueries, CTE)
- [ ] 10+ advanced queries done (RANK/DENSE_RANK, ROW_NUMBER, LAG, LEAD, running totals)
- [ ] At least 2 views created (4 recommended) and 1 index with a documented before/after
- [ ] `business_queries.sql` has 20+ commented, runnable queries
- [ ] Everything committed to Git; checkpoint self-review done

---

## A Few Words of Encouragement

This week often feels slower than expected, because most of the effort goes into *understanding* the data rather than producing impressive outputs. That is the right way to spend it. Analysts who skip this usually discover the problems later, in the form of a dashboard number that doesn't match the database.

If a load step throws a foreign-key error, don't be discouraged. That message is the database pointing at a real data problem, and finding and documenting those is exactly what the Data Cleaning rubric rewards. Fix it, log it, and move on.

If time gets tight, protect these in order: (1) a database that loads and reconciles, (2) the data-quality log and KPI definitions, (3) the 20 queries. A tidy, well-explained 20 queries is better than 30 rushed ones.

Good luck with Week 1! 🎯
