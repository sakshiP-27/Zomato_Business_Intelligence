# Week 2 Guide: Zomato Business Intelligence & Delivery Time Prediction
### A beginner-friendly walkthrough — Python Cleaning, Wrangling & Feature Engineering

---

## Before You Start

**Goal for this week:** Build a **reusable Python pipeline** that takes the 12 raw CSVs and produces (1) 12 cleaned CSVs with a documented cleaning log, and (2) one **analytical base table**: a single order-level table with 10+ engineered features, ready for EDA and machine learning. Then prove the cleaned data agrees with the SQL database from Week 1.

**Why this matters:** Week 3 (EDA and both ML models) and Week 4 (Power BI) read directly from what she builds this week. The rubric rewards this week heavily: **Data Cleaning (15%)**, **Python Code Quality (10%)**, **Pandas & NumPy Usage (10%)**, and it sets up the ML score (15%).

**The PRD's Week 2 plan, day by day:**

| Day | Focus |
|---|---|
| Day 6 | Load all datasets into Pandas; build reusable cleaning functions per table |
| Day 7 | Fix inconsistent city names, phone/pincode formats, mixed date formats |
| Day 8 | Handle outliers and negative values; deduplicate; merge into an analytical base table |
| Day 9 | Engineer derived features (PeakHour, WeekendOrder, CustomerTenure, DeliveryEfficiency, etc.) |
| Day 10 | Validate cleaned data against the SQL source of truth; checkpoint review |

**Five things that will save her from mistakes this week (read these first):**

1. **Never fill in missing values of the target.** `DeliveryTimeMinutes` is what the regression model must predict. If she fills its blanks with the average, she is inventing the answers the model will later be graded on. Rows with a missing target stay in the cleaned table, but are **excluded from model training** next week. Also, a missing delivery time on a **cancelled** order is *normal* (nothing was delivered), so check that before calling it an error.
2. **Feedback is only known after delivery.** `CustomerRating`, `DeliveryRating`, and `FoodRating` exist only once the food has arrived. A model that predicts delivery time must **never** use them as inputs, or it would be using the future. They are fine for EDA and the dashboard.
3. **Features about a customer must only use data from before a cut-off date** (this is the same "leakage" idea as in her earlier projects). It matters for the churn model, so this week she builds the customer features as a function that takes an `as_of` date.
4. **The PRD asks for "restaurant-to-customer distance", but the customer file has no coordinates** (per the PRD's column list; she should verify in the real file). More on this in Step 8.
5. **Reuse the Week 1 rules.** The same city spellings, date-parsing rules, "late delivery" definition, and orphan-row handling must be used in Python, or the Python and SQL numbers will never agree.

**What she needs before starting:**
- Week 1 finished: the database, `kpi_definitions.md`, the data-quality log, the city alias list
- `pip install pandas numpy matplotlib seaborn sqlalchemy psycopg2-binary pytest` and **pandas 2.0 or newer** (`pip install -U pandas`)
- A virtual environment, and a `requirements.txt` she keeps updated (`pip freeze > requirements.txt`)

**This week's checkpoint:** `src/ingest.py`, `src/clean.py`, `src/features.py`, a one-command pipeline script, 12 cleaned CSVs plus the analytical base table in `data/cleaned/`, a cleaning log, notebooks `01_data_cleaning.ipynb` and `03_feature_engineering.ipynb`, and a validation table comparing Python to SQL.

---

## Step 1 (Day 6): Build the Loader with Explicit Types

**What this means:** Load every CSV the same safe way, from one function, so the pipeline can be re-run from scratch (the PRD requires this: FR-10).

**The safe approach:** Read every column as **text first**, then convert types yourself. If pandas guesses types, one junk value like `"N/A"` in a number column turns the whole column into text, or silently changes values.

```python
# src/ingest.py
import re
from pathlib import Path
import pandas as pd

RAW_DIR = Path("data/raw")
TABLES = ["cities", "customers", "restaurants", "menu", "delivery_partners", "promotions",
          "orders", "order_items", "payments", "customer_feedback", "weather", "traffic"]

def to_snake(name: str) -> str:
    """OrderID -> order_id (same rule used for the SQL staging tables in Week 1)."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name.strip()).lower()

def load_raw(table: str) -> pd.DataFrame:
    """Read one raw CSV as text, with snake_case column names."""
    path = RAW_DIR / f"{table}.csv"
    try:
        df = pd.read_csv(path, dtype=str)
    except FileNotFoundError as err:
        raise FileNotFoundError(f"Raw file not found: {path}") from err
    df.columns = [to_snake(c) for c in df.columns]
    return df

def load_all() -> dict[str, pd.DataFrame]:
    return {t: load_raw(t) for t in TABLES}
```
**Why the `try/except`:** The PRD asks for explicit exception handling around file reading, type conversion, and model training. A clear error message ("file not found: ...") is much better than a long pandas traceback.

✅ **Done when:** `load_all()` returns 12 DataFrames whose row counts match the CSVs and the Week 1 staging tables.

---

## Step 2 (Day 6): Build the Cleaning Framework (a Class and an Automatic Log)

**What this means:** One `DataCleaner` class with a method per table, plus a small `CleaningLog` that records *every change* with a count. The PRD wants "a documented transformation log" (FR-03). If the code writes the log itself, she never has to remember to document anything.

```python
# src/clean.py
import numpy as np
import pandas as pd

class CleaningLog:
    """Collects one row per cleaning action: what was done, to which table, how many rows."""
    def __init__(self):
        self.rows = []

    def add(self, table: str, step: str, affected: int, note: str = "") -> None:
        self.rows.append({"table": table, "step": step,
                          "rows_affected": int(affected), "note": note})

    def save(self, path: str) -> None:
        pd.DataFrame(self.rows).to_csv(path, index=False)


def clean_text(s: pd.Series) -> pd.Series:
    """Trim the ends and collapse repeated inner spaces."""
    return s.str.strip().str.replace(r"\s+", " ", regex=True)


def to_number(s: pd.Series, log: CleaningLog, table: str, col: str) -> pd.Series:
    """Convert text to numbers; log how many values were not valid numbers."""
    out = pd.to_numeric(s.str.strip(), errors="coerce")
    bad = int((out.isna() & s.notna()).sum())          # had text, but it wasn't a number
    if bad:
        log.add(table, f"{col}: non-numeric -> NaN", bad)
    return out


class DataCleaner:
    """Cleans the 12 Zomato tables. Each clean_<table> method returns a new DataFrame."""
    def __init__(self, canonical_cities: list[str], city_aliases: dict[str, str], log: CleaningLog):
        self.cities = canonical_cities
        self.aliases = city_aliases          # e.g. {"bangalore": "Bengaluru"}
        self.log = log
```
Then add methods in the same style: `clean_customers`, `clean_orders`, and so on. Each method follows the **same recipe**: trim text → standardize categories → convert types → fix formats → handle duplicates → handle invalid values → log everything.

**Habit to build:** inside each method, log counts at the moment you change something:
```python
before = len(df)
df = df.drop_duplicates(subset="order_id")
self.log.add("orders", "drop duplicate order_id", before - len(df))
```
**Notebook vs. module:** put the logic in `src/clean.py` and keep `01_data_cleaning.ipynb` thin: it *calls* the functions and shows before/after tables and charts. That keeps the code reusable and the notebook readable.

✅ **Done when:** `CleaningLog`, the helper functions, and a `DataCleaner` class with at least `clean_customers` exist, with docstrings on everything.

---

## Step 3 (Day 7): Fix City Names, Whitespace, and Category Spellings

**City names:**
```python
def standardize_city(self, s: pd.Series, table: str) -> pd.Series:
    key = clean_text(s).str.lower()
    fixed = key.map(self.aliases).fillna(clean_text(s).str.title())
    changed = int((fixed != clean_text(s)).sum())
    self.log.add(table, "city standardized", changed)
    unknown = set(fixed.dropna()) - set(self.cities)
    if unknown:
        self.log.add(table, "city NOT in cities table", len(unknown), note=str(sorted(unknown)))
    return fixed
```
The canonical list is the cleaned `cities.csv`; the alias dictionary is the one she built in Week 1 (`bangalore → Bengaluru` and so on). The "unknown" check is a safety net: after cleaning, **every** city in every table should be one of the ~25 official cities.

**Category spellings:** `order_status`, `payment_method`, `membership`, `gender`, `sentiment`, and similar columns often differ only by capital letters or spelling (for example `Canceled` vs `Cancelled`). After `clean_text(...).str.title()`, look at `value_counts()` and add a small mapping dictionary for anything that still has two spellings. Use the same final labels as in the SQL database.

**Emails:** lowercase them and validate with a simple pattern such as `^[^@\s]+@[^@\s]+\.[^@\s]+$`. Invalid ones become missing (and are logged).

✅ **Done when:** After cleaning, a check like `assert set(df["city"].dropna()) <= set(canonical_cities)` passes for every table with a city column.

---

## Step 4 (Day 7): Fix Mixed Date Formats, Phone Numbers, and Pincodes

**Dates.** The PRD names three formats. Pandas' automatic parsing can't tell `03/04/2024` (March 4th or April 3rd?) apart, so use the **same rule as in the SQL function from Week 1**: identify the format by its separators, then parse each group with an explicit format.

```python
def parse_mixed_dates(s: pd.Series) -> pd.Series:
    """Parse DD-MM-YYYY, MM/DD/YYYY, YYYY.MM.DD and YYYY-MM-DD into proper dates."""
    s = s.str.strip()
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    formats = {
        r"^\d{2}-\d{2}-\d{4}$": "%d-%m-%Y",
        r"^\d{2}/\d{2}/\d{4}$": "%m/%d/%Y",
        r"^\d{4}\.\d{2}\.\d{2}$": "%Y.%m.%d",
        r"^\d{4}-\d{2}-\d{2}$": "%Y-%m-%d",
    }
    for pattern, fmt in formats.items():
        mask = s.str.match(pattern, na=False)
        out.loc[mask] = pd.to_datetime(s[mask], format=fmt, errors="coerce")
    return out
```
**Sanity-check it:** the parsed `order_date` values should fall inside the 24-month window, and the counts of valid dates should equal what the SQL database has. Anything outside the window or left as `NaT` goes into the log.

**Times** (`order_time`, traffic `time`): use `pd.to_datetime(s, format="mixed", errors="coerce")` (pandas 2+), then take `.dt.hour` and `.dt.minute`.

**Phone numbers.** She can *repair* some, but not invent any:
```python
def clean_phone(s: pd.Series) -> pd.Series:
    digits = s.str.replace(r"\D", "", regex=True)                       # keep digits only
    digits = digits.str.replace(r"^(91|0)(?=\d{10}$)", "", regex=True)  # drop +91 or a leading 0
    return digits.where(digits.str.match(r"^[6-9]\d{9}$", na=False))    # invalid -> NaN
```
**Pincodes:** keep digits only, then require exactly 6 digits not starting with 0:
```python
def clean_pincode(s: pd.Series) -> pd.Series:
    digits = s.str.replace(r"\D", "", regex=True)
    return digits.where(digits.str.match(r"^[1-9]\d{5}$", na=False))
```
Keep phone and pincode as **text**. Add flag columns such as `phone_valid` so the dashboard or an analyst can see how many were unusable, and log the number repaired and the number invalid.

✅ **Done when:** All date columns are real datetimes, phone and pincode have only valid or missing values, and the log shows counts for each repair.

---

## Step 5 (Day 7–8): Handle Missing Values, Column by Column

**What this means:** The PRD asks for strategies "appropriate to each column." No single rule works. Write a strategy for each, and put the reason in the log or the notebook.

| Column | Suggested strategy | Why |
|---|---|---|
| `age` (customers, partners) | First set impossible ages to missing (for example under 15 or over 90, her call). Then fill with the **median** (by membership or gender if it differs). Add an `age_was_missing` flag. | Median resists outliers; the flag keeps the information that it was filled |
| `rating` (restaurants, partners) | Fill with the median of the same city or cuisine, or leave missing and tell the dashboard "not rated" | A new restaurant may legitimately have no rating |
| `customer_rating`, `delivery_rating`, `food_rating` | **Leave missing** | Missing means "didn't rate". Filling would fake opinions |
| `phone`, `email` | **Leave missing**, keep the `*_valid` flags | A contact detail can't be guessed |
| `review` | Leave missing; add `has_review` (0/1) | It's free text |
| `delivery_time_minutes` | **Do not impute.** Keep the row, mark it, and exclude it from model training | It is the prediction target |
| `delivery_partner_id` in orders | Leave missing for cancelled orders; investigate it for delivered ones | Cancelled orders may never be assigned |

**Check the "why" before filling.** One quick way: `pd.crosstab(orders["order_status"], orders["delivery_time_minutes"].isna())`. If missing times are almost all on cancelled orders, they are expected, not errors. That is a finding worth one sentence in the report.

**Typical code for a grouped median fill:**
```python
df["age"] = df["age"].where(df["age"].between(15, 90))             # impossible ages -> NaN
df["age_was_missing"] = df["age"].isna().astype(int)
group_median = df.groupby("membership")["age"].transform("median")
df["age"] = df["age"].fillna(group_median).fillna(df["age"].median())
```
✅ **Done when:** Every column listed in the PRD's missing-value list has a documented strategy, and the delivery-time target is **not** imputed.

---

## Step 6 (Day 8): Negative Values, Outliers, Duplicates, and Orphans

### Non-positive values
- `food_cost <= 0` and `delivery_time_minutes <= 0` are invalid, so set them to missing and log them.
- **Be careful with `delivery_fee = 0`.** It may be legitimate (free delivery for some membership tiers). Compare with `membership` before declaring it an error. Negative fees are invalid.
- **Don't just flip the sign** of a negative with `abs()`. Only do that if the arithmetic check from Week 1 (`final_amount ≈ food_cost + delivery_fee − discount + gst`) proves it was a sign error. Otherwise, set it to missing.

### Outliers (vectorized, as the PRD requires)
```python
def iqr_bounds(x: pd.Series, k: float = 1.5):
    """Return (low, high) limits using the IQR rule, ignoring missing values."""
    q1, q3 = np.nanpercentile(x, [25, 75])
    iqr = q3 - q1
    return q1 - k * iqr, q3 + k * iqr

low, high = iqr_bounds(orders["delivery_time_minutes"])
orders["dt_outlier_flag"] = ~orders["delivery_time_minutes"].between(low, high)   # no Python loop
```
You can also use a z-score: `(x - x.mean()) / x.std()`.

**How to decide what to do with the flagged rows:**
1. **Look first.** Plot a histogram and a boxplot, and print `np.percentile(x, [50, 90, 95, 99, 99.9])`. Delivery times are naturally right-skewed, so a strict IQR rule will flag many *legitimate* slow deliveries.
2. **Separate "impossible" from "unusual".** A 700-minute delivery is almost certainly an error; a 75-minute delivery in heavy rain is real. Pick a defensible upper limit from the data and domain sense (not blindly from the IQR) and write why.
3. **For the target** (`delivery_time_minutes`), prefer **excluding** clearly impossible rows from model training over *capping* them, because capping changes the answer the model is learning.
4. **For feature columns** (for example `average_delivery_time` of partners), capping ("winsorizing") at the limits is acceptable.
5. Keep a flag column (`dt_outlier_flag`) instead of deleting rows, so Week 3 can choose.
6. Show a **before/after** histogram in the notebook. It is great evidence for the Data Cleaning rubric.

### Duplicates
`orders`, `payments`, and `customer_feedback` have repeats from "repeated exports". First count both **fully identical rows** and **repeated IDs**. If the same ID appears with *different* values, you need a written rule (for example keep the row with the fewest missing values). Use the **same rule as in the SQL load** so the counts match.

### Orphans
Rows whose foreign key points to nothing (for example an order for a customer that doesn't exist) get the same treatment as in Week 1: separate them into a quarantine file such as `data/cleaned/quarantine_orders.csv`, and log the count. Then child tables (`payments`, `customer_feedback`, `order_items`) keep only rows whose order survived.

✅ **Done when:** Every invalid value, outlier decision, duplicate rule, and orphan count is in the log, and the before/after outlier plot exists.

---

## Step 7 (Day 8): Run It All as One Pipeline and Save the Cleaned Files

**What this means:** One script that goes from raw CSVs to cleaned CSVs without manual steps. That is the PRD's "reproducible Python pipeline runnable end-to-end" requirement.

```python
# src/run_pipeline.py
from pathlib import Path
from src.ingest import load_all
from src.clean import CleaningLog, DataCleaner
from src.features import build_analytical_base_table

CLEAN_DIR = Path("data/cleaned")

def main():
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    log = CleaningLog()
    raw = load_all()
    cleaner = DataCleaner(canonical_cities=..., city_aliases=..., log=log)
    cleaned = cleaner.clean_all(raw)                       # dict of table name -> DataFrame
    for name, df in cleaned.items():
        df.to_csv(CLEAN_DIR / f"{name}.csv", index=False)
    abt = build_analytical_base_table(cleaned)
    abt.to_csv(CLEAN_DIR / "analytical_base_table.csv", index=False)
    log.save("documentation/cleaning_log.csv")

if __name__ == "__main__":
    main()
```
**Why the file format matters for Week 4:** Power BI must "refresh from the cleaned CSVs without manual re-mapping" (NFR-04). So decide now and **keep stable** the file names, column names, and formats: dates as `YYYY-MM-DD`, yes/no flags as `0/1`, no index column. Changing a column name next week would break her Power BI model.

**Performance:** The whole pipeline should run in well under 30 minutes on a laptop (NFR-01). With ~20,000 orders that is easy, as long as she uses vectorized pandas operations instead of looping through rows.

✅ **Done when:** `python -m src.run_pipeline` creates 12 cleaned CSVs, the analytical base table, and `cleaning_log.csv` in one go, even after deleting `data/cleaned/` first.

---

## Step 8 (Day 8): Merge Everything into the Analytical Base Table

**What this means:** One row **per order**, with columns from every related table. This is the table she'll use for EDA, the delivery-time model, and Power BI.

**Golden rule: a merge must never change the number of orders.** Add a check after each merge, and use pandas' `validate` option, which raises an error if the "one" side of a join isn't actually unique:

```python
n_orders = len(orders)
abt = orders.merge(cust, on="customer_id", how="left", validate="m:1")
assert len(abt) == n_orders, "merge duplicated or dropped orders!"
```
(`validate="m:1"` means: many orders to one customer.)

**Prepare each side first:**
1. **Rename clashing columns.** Both `customers` and `restaurants` have `city`, so create `customer_city` and `restaurant_city` before merging. Do the same for the many tables that have `rating`.
2. **Aggregate "many" tables down to one row per order *before* merging.** `order_items` has several rows per order. If you merge it directly, each order's amount repeats once per item and revenue is overcounted (the join fan-out from Week 1).
```python
basket = (order_items
          .merge(menu[["food_item_id", "preparation_time"]], on="food_item_id", how="left", validate="m:1")
          .groupby("order_id")
          .agg(n_items=("quantity", "sum"),
               n_distinct_items=("food_item_id", "nunique"),
               basket_value=("total_price", "sum"),
               avg_prep_time=("preparation_time", "mean"),
               max_prep_time=("preparation_time", "max"))
          .reset_index())
```
(Preparation time is a likely strong predictor of delivery time: a dish that takes 25 minutes to cook can't arrive in 20.)

3. **Weather:** join on `restaurant_city` and `order_date`. First check `weather.duplicated(["city", "date"]).sum()`. If it isn't zero, aggregate to one row per city and day.
4. **Traffic:** it has a date **and a time**, so match on city + date + **hour**. Make an hour column in both tables, then average the traffic score and speed per `(city, date, hour)` before merging. Write down what happens when no traffic record exists for that hour (leave it missing, and say so).
5. **Feedback:** only ~14,000 of ~20,000 orders have feedback, so these columns will be missing for roughly a third of orders (a left join keeps all orders). **Remember rule 2: never feed these to the delivery-time model.**
6. **Which city belongs to an order?** Use the **restaurant's city** (the Week 1 decision) and use it everywhere.

**Row counts to track:** orders in → orders in the base table. They must be equal.

✅ **Done when:** `analytical_base_table.csv` has exactly one row per cleaned order, and an assertion after every merge confirms the count didn't change.

---

## Step 9 (Day 9): Engineer the Features

**What this means:** Create the columns that capture *why* a delivery is slow or a customer leaves. The PRD asks for **at least 10** (FR-05) and lists 11. Put them in `src/features.py` as functions, not in scattered notebook cells.

**Do the basics once, up front:**
```python
abt["order_hour"] = abt["order_time"].dt.hour
abt["order_minute"] = abt["order_time"].dt.minute
abt["order_dayofweek"] = abt["order_date"].dt.dayofweek      # Monday = 0
abt["order_month"] = abt["order_date"].dt.month
```

| Feature | How to build it | Notes |
|---|---|---|
| **PeakHour** | Lunch is 12–2 PM, dinner is 7–10 PM. `h = hour + minute/60`, then `(((h >= 12) & (h < 14)) \| ((h >= 19) & (h < 22))).astype(int)` | Binary 0/1 |
| **WeekendOrder** | `(abt["order_dayofweek"] >= 5).astype(int)` | Saturday and Sunday |
| **RainImpact** | Bin `rainfall` with `pd.cut` into None / Light / Moderate / Heavy, and keep the numeric rainfall too | **Check the unit and distribution first**; choose cut-offs from the data |
| **TrafficScore** | Map `traffic_level` to a number (Low = 1, Medium = 2, High = 3, ...) | Use the **real labels** from `value_counts()`; it's an ordered scale |
| **CustomerTenure** | `(order_date - registration_date).dt.days` | Check for negative values (order before registration) and log them |
| **AverageBasketValue** | Mean `final_amount` per customer | **Customer-level**, so use the as-of function in Step 10 |
| **RestaurantPopularity** | Order count and revenue per restaurant, then `rank` within the city | `groupby` then `groupby("city")["revenue"].rank(ascending=False, method="dense")` |
| **DeliveryEfficiency** | Partner `average_delivery_time` ÷ the city's average partner time (`groupby("city")["average_delivery_time"].transform("mean")`) | Below 1 = faster than the city typical |
| **CustomerLifetimeValue** | Cumulative `final_amount` per customer to date | Customer-level (Step 10) |
| **OrderFrequency** | Orders per customer per 30-day window | Customer-level (Step 10) |
| **AverageRating** | Row mean of `customer_rating`, `delivery_rating`, `food_rating` | **Not for the delivery-time model** (known only after delivery); fine for EDA and Power BI |

**Extra features worth adding (the PRD only sets a minimum):** `avg_prep_time` and `max_prep_time` (from Step 8), `n_items`, `discount_pct` (`discount / food_cost`), `partner_tenure_days` (from the partner's joining date), and `is_peak_and_rain` (an interaction of PeakHour and rain).

**The distance problem.** The PRD lists "restaurant-to-customer distance (from latitude/longitude)" as a model input, but only `restaurants.csv` has coordinates. **First, open the real `customers.csv` and check.** If it truly has no latitude or longitude:
- Don't invent customer locations, and don't call an external mapping service (that is out of scope).
- Tell the mentor and write the limitation in the report.
- Use an honest proxy and label it that way, for example the distance of the restaurant from its **city centre** (the mean latitude/longitude of that city's restaurants), or a flag for whether the customer's city differs from the restaurant's city.
- Either way, write the distance function with NumPy, so it works for real coordinates too:

```python
def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km between two points; works on whole columns at once."""
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))
```

**Two more honest notes about leakage:**
- `delivery_partners.average_delivery_time` and `completed_deliveries` summarize the partner's history, which probably includes the very orders in the dataset. It's a provided column and the PRD lists partner efficiency as a predictor, so use it, but mention the limitation in the model write-up.
- `customers.total_orders` is a snapshot over the whole period (including "future" orders). Compare it with the real count from `orders`, but **don't use it as a churn feature**.

✅ **Done when:** 10+ features exist, each defined in code with a docstring, and the notebook shows a short table of each feature with its meaning.

---

## Step 10 (Day 9): Build Customer Features "As Of" a Date (Prep for Churn)

**What this means:** Customer-level features (lifetime value, basket value, frequency, recency) must only count orders **up to a cut-off date**. Otherwise, a churn model "sees" the orders it's supposed to predict. Build one function now, and Week 3 will call it with the right cut-off.

```python
def build_customer_features(orders: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """Per-customer features using only orders on or before `as_of`."""
    hist = orders[(orders["order_date"] <= as_of) & (orders["order_status"] != "Cancelled")]
    agg = hist.groupby("customer_id").agg(
        orders_to_date=("order_id", "count"),
        customer_lifetime_value=("final_amount", "sum"),
        average_basket_value=("final_amount", "mean"),
        first_order=("order_date", "min"),
        last_order=("order_date", "max"),
    )
    agg["days_since_last_order"] = (as_of - agg["last_order"]).dt.days
    span_days = (as_of - agg["first_order"]).dt.days.clip(lower=1)
    agg["order_frequency_30d"] = agg["orders_to_date"] / (span_days / 30)
    return agg.reset_index()
```
Use the **same definitions as in Week 1** (for example, which statuses count as completed revenue), and note any choice in `kpi_definitions.md`.

**For this week:** call it with `as_of = orders["order_date"].max()` to get customer values for EDA and Power BI (segments, CLV distribution). **Next week** she will call it again with an *earlier* cut-off, and build the churn label from what happens in the following 60 days.

✅ **Done when:** `build_customer_features` runs, returns one row per customer, and she can explain in one sentence why the cut-off date matters.

---

## Step 11 (Day 10): Validate Against the SQL Source of Truth

**What this means:** The Python-cleaned data and the SQL database are two independent versions of "the truth". If they disagree, one has a bug, or the two used different rules. Compare them.

```python
import numpy as np
import pandas as pd
from sqlalchemy import create_engine

engine = create_engine("postgresql+psycopg2://postgres:yourpassword@localhost:5432/zomato")

checks = {
    "orders rows":        ("SELECT COUNT(*) FROM orders",    len(orders_clean)),
    "customers rows":     ("SELECT COUNT(*) FROM customers", len(customers_clean)),
    "delivered revenue":  ("SELECT SUM(final_amount) FROM orders WHERE order_status = 'Delivered'",
                           orders_clean.loc[orders_clean["order_status"] == "Delivered", "final_amount"].sum()),
    "avg delivery time (valid only)":
                          ("SELECT AVG(delivery_time_minutes) FROM orders WHERE delivery_time_minutes > 0",
                           orders_clean.loc[orders_clean["delivery_time_minutes"] > 0, "delivery_time_minutes"].mean()),
}
for name, (sql, py_value) in checks.items():
    sql_value = pd.read_sql(sql, engine).iloc[0, 0]
    ok = np.isclose(float(sql_value), float(py_value), rtol=1e-6)
    print(f"{name:35s} SQL={sql_value}  Python={py_value}  {'OK' if ok else 'DIFFERENT'}")
```
**Compare fairly.** Python also does things SQL didn't (outlier flags, extra imputation). So compare at the stage **before** those Python-only steps, or apply the same filter on both sides. Keep an intermediate "structurally cleaned" DataFrame for this purpose.

Also compare: **orders per city**, **orders per status**, **customer count**, and the **min/max dates**.

**Record the result** in a table (`documentation/validation_report.md`): check, SQL value, Python value, match?, explanation if different. A difference is not a failure. An **unexplained** difference is.

**Compute the KPI the PRD cares about:** "Data Cleaning Completeness ≥ 95%". Update the `status` column of the Week 1 data-quality log (`fixed in Python` or `verified`), then:
```
% resolved = rows with status "fixed"/"verified" ÷ total rows in the log
```

✅ **Done when:** The validation table exists, every difference is explained, and the "% of known issues resolved" is calculated.

---

## Step 12 (Day 10): Notebooks, Tidy-Up, and the Checkpoint Review

**Notebooks:**
- `01_data_cleaning.ipynb`: for each table, show the profile **before**, call the cleaner, show it **after**, and display that table's slice of the cleaning log. Add the outlier before/after plots.
- `03_feature_engineering.ipynb`: build the analytical base table, show each feature with a one-line explanation, check distributions, and show a couple of sanity plots (for example delivery time by `PeakHour`).
- Every notebook should run top to bottom with **Restart & Run All**. (`02_eda.ipynb` is next week; the number is just a label.)

**NumPy and Pandas requirements to tick off (PRD Sections 21.2 and 21.3):**
- Vectorized calculations (no row-by-row loops) ✔ haversine, flags, bins
- Percentiles: `np.percentile` for delivery-time limits and the SLA choice ✔
- A seeded random generator for any sampling: `rng = np.random.default_rng(42)` ✔ (use it for the swarm-plot samples next week and for train/test splits in Week 3)
- GroupBy, pivot, and cross-tabulation summaries: a few quick ones such as `pd.crosstab(abt["membership"], abt["order_status"])` and a city × status `pivot_table` ✔
- Categorical encoding: ordinal for `traffic_level` now. For nominal columns (cuisine, city, payment method), show `pd.get_dummies` in the feature notebook as a demo, but do the *real* encoding inside the scikit-learn pipeline in Week 3, so it's fitted only on training data.

**Code-quality checks:**
- [ ] Every function has a docstring and a sensible name
- [ ] No hard-coded passwords (database URL comes from a `.env` or config)
- [ ] `requirements.txt` is up to date
- [ ] Commit with clear messages, not one big commit

**Checkpoint self-review:**
- Can she delete `data/cleaned/` and rebuild everything with one command?
- Does the base table have one row per order?
- Is the target column untouched by imputation?
- Are feedback ratings kept out of the delivery-time feature list?
- Does every difference between Python and SQL have an explanation?
- Is the distance limitation written down?

✅ **Done when:** All six answers are "yes," or the gaps are written down with a plan.

---

## Week 2 Checklist: Quick Reference

- [ ] Loader reads all 12 CSVs as text with snake_case headers and clear error messages
- [ ] `CleaningLog` and `DataCleaner` class created; every change is logged with a count
- [ ] City names standardized and checked against the official list in every table
- [ ] Category spellings unified (for example Canceled/Cancelled); whitespace trimmed
- [ ] Mixed dates parsed with explicit formats; parsed dates fall in the 24-month window
- [ ] Phone numbers and pincodes repaired where possible, otherwise missing, with validity flags
- [ ] A documented missing-value strategy for every flagged column; **delivery-time target not imputed**
- [ ] Negative and zero values handled (free-delivery zeros checked, no blind `abs()`)
- [ ] Outliers flagged with IQR or z-score (vectorized), decisions justified, before/after plot made
- [ ] Duplicates removed with a written rule; orphans quarantined, matching Week 1
- [ ] One command runs the pipeline end to end, producing 12 cleaned CSVs + `cleaning_log.csv`
- [ ] Analytical base table has exactly one row per order; merges asserted and validated
- [ ] 10+ features built (11 from the PRD, plus extras like prep time); each documented
- [ ] Distance limitation checked, handled honestly, and written down
- [ ] `build_customer_features(orders, as_of)` written (recency, frequency, CLV, basket)
- [ ] No post-delivery fields (feedback ratings) in the delivery-time feature list
- [ ] Python vs. SQL validation table complete; "% of issues resolved" calculated
- [ ] Notebooks 01 and 03 run top to bottom; code has docstrings; everything committed

---

## A Few Words of Encouragement

This is the most "engineering" week of the project, and it's where good habits show. Two ideas carry most of the weight: **every cleaning decision is logged, and every merge is checked.** If she does only those two things consistently, her data will be trustworthy and her rubric marks for cleaning and code quality will largely take care of themselves.

If the pipeline feels like a lot of small pieces, build it in the order of the days: first one table cleaned end to end (customers is a good start), then copy the pattern to the others. The first table takes the longest; the rest go quickly.

If time gets tight, protect these in order: (1) cleaned CSVs plus the log, (2) the base table with a verified row count, (3) the 10 features, (4) the SQL validation. Nice-to-have extras can wait.

Good luck with Week 2! 🎯
