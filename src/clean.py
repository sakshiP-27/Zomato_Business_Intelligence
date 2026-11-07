"""
src/clean.py
------------
Week 2, Steps 1–2: Cleaning framework for the Zomato BI project.

Provides:
  • CleaningLog       — collects one row per cleaning action with a count
  • Helper functions   — clean_text, to_number, standardize_city, parse_mixed_dates,
                         clean_phone, clean_pincode, validate_email
  • DataCleaner class  — one method per table; clean_all() dispatches to all 12

The same city aliases and date-parsing rules from Week 1 are reused so
Python and SQL numbers agree.

Usage:
    from src.ingest import load_all
    from src.clean import CleaningLog, DataCleaner

    raw = load_all()
    log = CleaningLog()

    # Build canonical cities + aliases from the cleaned cities.csv
    cities_list = raw["cities"]["city"].dropna().str.strip().tolist()
    aliases = _build_alias_dict()  # or load from the SQL city_aliases table

    cleaner = DataCleaner(cities_list, aliases, log)
    cleaned = cleaner.clean_all(raw)
    log.save("documentation/cleaning_log.csv")
"""

import re
import numpy as np
import pandas as pd
from pathlib import Path


# ---------------------------------------------------------------------------
# City aliases — same mapping as the SQL city_aliases table from Week 1
# ---------------------------------------------------------------------------

CITY_ALIASES = {
    "bangalore":     "Bengaluru",
    "bengaluru":     "Bengaluru",
    "bombay":        "Mumbai",
    "mumbai":        "Mumbai",
    "calcutta":      "Kolkata",
    "kolkata":       "Kolkata",
    "madras":        "Chennai",
    "chennai":       "Chennai",
    "new delhi":     "Delhi",
    "delhi":         "Delhi",
    "baroda":        "Vadodara",
    "vadodara":      "Vadodara",
    "ahmedabad":     "Ahmedabad",
    "bhopal":        "Bhopal",
    "bhubaneswar":   "Bhubaneswar",
    "chandigarh":    "Chandigarh",
    "coimbatore":    "Coimbatore",
    "guwahati":      "Guwahati",
    "hyderabad":     "Hyderabad",
    "indore":        "Indore",
    "jaipur":        "Jaipur",
    "kochi":         "Kochi",
    "lucknow":       "Lucknow",
    "ludhiana":      "Ludhiana",
    "nagpur":        "Nagpur",
    "nashik":        "Nashik",
    "patna":         "Patna",
    "pune":          "Pune",
    "raipur":        "Raipur",
    "surat":         "Surat",
    "visakhapatnam": "Visakhapatnam",
}


# ---------------------------------------------------------------------------
# CleaningLog
# ---------------------------------------------------------------------------

class CleaningLog:
    """
    Collects one row per cleaning action: what was done, to which table,
    how many rows were affected, plus an optional note.

    Call .save(path) at the end to write documentation/cleaning_log.csv.
    """

    def __init__(self):
        self.rows: list[dict] = []

    def add(self, table: str, step: str, affected: int, note: str = "") -> None:
        """Record a single cleaning action."""
        self.rows.append({
            "table":         table,
            "step":          step,
            "rows_affected": int(affected),
            "note":          note,
        })

    def save(self, path: str | Path) -> None:
        """Write the full log to a CSV file."""
        pd.DataFrame(self.rows).to_csv(path, index=False)

    def summary(self) -> pd.DataFrame:
        """Return a per-table, per-step summary of affected rows."""
        df = pd.DataFrame(self.rows)
        if df.empty:
            return df
        return (df.groupby(["table", "step"])["rows_affected"]
                  .sum()
                  .reset_index()
                  .sort_values(["table", "rows_affected"], ascending=[True, False]))


# ---------------------------------------------------------------------------
# Helper functions (vectorized, no row-by-row loops)
# ---------------------------------------------------------------------------

def clean_text(s: pd.Series) -> pd.Series:
    """
    Trim leading/trailing whitespace and collapse repeated inner spaces.

    Args:
        s: A pandas Series of text values.

    Returns:
        Cleaned Series with single spaces only.
    """
    # Works for object, string, and StringDtype columns; numeric columns pass through
    if pd.api.types.is_string_dtype(s):
        return s.str.strip().str.replace(r"\s+", " ", regex=True)
    return s


def to_number(s: pd.Series, log: CleaningLog, table: str, col: str) -> pd.Series:
    """
    Convert a text Series to numeric (float).  Values that are not valid
    numbers become NaN and are logged.

    Args:
        s:       Text Series to convert.
        log:     CleaningLog to record non-numeric values.
        table:   Table name for the log entry.
        col:     Column name for the log entry.

    Returns:
        Numeric Series (float64); invalid values are NaN.
    """
    out = pd.to_numeric(s.str.strip(), errors="coerce")
    bad = int((out.isna() & s.notna() & (s.str.strip() != "")).sum())
    if bad:
        log.add(table, f"{col}: non-numeric -> NaN", bad)
    return out


def standardize_city(s: pd.Series, aliases: dict, canonical_cities: list,
                     table: str, log: CleaningLog) -> pd.Series:
    """
    Map every city spelling variant to its canonical name.

    Uses the same alias dictionary as the SQL city_aliases table (Week 1).
    After mapping, any city not in the canonical list is flagged in the log.

    Args:
        s:                City column (text).
        aliases:          Dict of {lowercase_alias: canonical_name}.
        canonical_cities:  List of official city names from cities.csv.
        table:            Table name for logging.
        log:              CleaningLog instance.

    Returns:
        Series with canonical city names (title-cased).
    """
    cleaned = clean_text(s)
    key = cleaned.str.lower()
    fixed = key.map(aliases).fillna(cleaned.str.title())
    changed = int((fixed != cleaned).sum())
    if changed:
        log.add(table, "city standardized", changed)

    # Safety check: any city not in the canonical list?
    unknown = set(fixed.dropna()) - set(canonical_cities)
    if unknown:
        log.add(table, "city NOT in cities table", len(unknown),
                note=str(sorted(unknown)))
    return fixed


def parse_mixed_dates(s: pd.Series) -> pd.Series:
    """
    Parse the four date formats found in the raw CSVs into proper datetimes.

    Formats handled (same rules as SQL parse_mixed_date):
        DD-MM-YYYY    (separator: -)
        MM/DD/YYYY    (separator: /)  — used by orders, weather, traffic, payments
        YYYY.MM.DD    (separator: .)
        YYYY-MM-DD    (ISO, separator: -)

    Also handles DD Mon YYYY (e.g. "28 Feb 2024") found in customers & delivery_partners.

    Args:
        s: Text Series containing date strings.

    Returns:
        datetime64 Series; unparseable values are NaT.
    """
    s = s.str.strip()
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")

    formats = {
        r"^\d{2}-\d{2}-\d{4}$":  "%d-%m-%Y",
        r"^\d{4}\.\d{2}\.\d{2}$": "%Y.%m.%d",
        r"^\d{4}-\d{2}-\d{2}$":  "%Y-%m-%d",
        r"^\d{1,2} [A-Za-z]{3} \d{4}$": "%d %b %Y",
    }

    for pattern, fmt in formats.items():
        mask = s.str.match(pattern, na=False)
        out.loc[mask] = pd.to_datetime(s[mask], format=fmt, errors="coerce")

    # '/' dates mix DD/MM and MM/DD in the raw files. A first part above 12 can only be
    # a day, so read those as DD/MM; the rest default to MM/DD (ambiguous when both <= 12).
    slash = s.str.match(r"^\d{2}/\d{2}/\d{4}$", na=False)
    day_first = slash & (pd.to_numeric(s.str[:2], errors="coerce") > 12)
    out.loc[day_first] = pd.to_datetime(s[day_first], format="%d/%m/%Y", errors="coerce")
    out.loc[slash & ~day_first] = pd.to_datetime(s[slash & ~day_first], format="%m/%d/%Y", errors="coerce")

    return out

def parse_ddmmyyyy_dates(s: pd.Series) -> pd.Series:
    """
    Parse date columns that use DD/MM/YYYY (customers, delivery_partners)
    instead of MM/DD/YYYY (orders, payments, weather, traffic).

    Same as parse_mixed_dates but with the / separator read as day-first.

    Args:
        s: Text Series containing date strings.

    Returns:
        datetime64 Series; unparseable values are NaT.
    """
    s = s.str.strip()
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")

    formats = {
        r"^\d{2}-\d{2}-\d{4}$":  "%d-%m-%Y",
        r"^\d{4}\.\d{2}\.\d{2}$": "%Y.%m.%d",
        r"^\d{4}-\d{2}-\d{2}$":  "%Y-%m-%d",
        r"^\d{1,2} [A-Za-z]{3} \d{4}$": "%d %b %Y",
    }

    for pattern, fmt in formats.items():
        mask = s.str.match(pattern, na=False)
        out.loc[mask] = pd.to_datetime(s[mask], format=fmt, errors="coerce")

    # '/' dates mix DD/MM and MM/DD. A second part above 12 can only be a day, so read
    # those as MM/DD; the rest default to DD/MM for these tables.
    slash = s.str.match(r"^\d{2}/\d{2}/\d{4}$", na=False)
    month_first = slash & (pd.to_numeric(s.str[3:5], errors="coerce") > 12)
    out.loc[month_first] = pd.to_datetime(s[month_first], format="%m/%d/%Y", errors="coerce")
    out.loc[slash & ~month_first] = pd.to_datetime(s[slash & ~month_first], format="%d/%m/%Y", errors="coerce")

    return out

def clean_phone(s: pd.Series) -> pd.Series:
    """
    Repair Indian mobile numbers: strip non-digits, drop leading 91 or 0,
    keep only valid 10-digit numbers starting with 6-9.

    Invalid numbers become NaN (not fabricated).

    Args:
        s: Phone column (text).

    Returns:
        Series of valid phone strings or NaN.
    """
    digits = s.str.replace(r"\D", "", regex=True)
    # Drop country code (91) or leading 0 if followed by exactly 10 digits
    digits = digits.str.replace(r"^(91|0)(?=\d{10}$)", "", regex=True)
    return digits.where(digits.str.match(r"^[6-9]\d{9}$", na=False))


def clean_pincode(s: pd.Series) -> pd.Series:
    """
    Keep digits only, require exactly 6 digits not starting with 0.

    Args:
        s: Pincode column (text).

    Returns:
        Series of valid pincode strings or NaN.
    """
    digits = s.str.replace(r"\D", "", regex=True)
    return digits.where(digits.str.match(r"^[1-9]\d{5}$", na=False))


def validate_email(s: pd.Series) -> pd.Series:
    """
    Lowercase emails and validate with a simple pattern.
    Invalid emails become NaN.

    Args:
        s: Email column (text).

    Returns:
        Series of lowercased valid emails or NaN.
    """
    s = clean_text(s).str.lower()
    valid = s.str.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", na=False)
    return s.where(valid)


def iqr_bounds(x: pd.Series, k: float = 1.5) -> tuple[float, float]:
    """
    Return (low, high) limits using the IQR rule, ignoring missing values.

    Args:
        x: Numeric Series.
        k: IQR multiplier (1.5 = standard, 3.0 = conservative).

    Returns:
        Tuple of (lower_bound, upper_bound).
    """
    q1, q3 = np.nanpercentile(x, [25, 75])
    iqr = q3 - q1
    return q1 - k * iqr, q3 + k * iqr


# ---------------------------------------------------------------------------
# DataCleaner class — one method per table
# ---------------------------------------------------------------------------

class DataCleaner:
    """
    Cleans the 12 Zomato tables using the same rules as Week 1 SQL.

    Each clean_<table> method follows the same recipe:
        trim text -> standardize categories -> convert types ->
        fix formats -> handle duplicates -> handle invalid values ->
        log everything.

    Attributes:
        cities:    List of canonical city names.
        aliases:   Dict of {lowercase_alias: canonical_name}.
        log:       CleaningLog instance that records every change.
    """

    def __init__(self, canonical_cities: list[str],
                 city_aliases: dict[str, str],
                 log: CleaningLog):
        self.cities = canonical_cities
        self.aliases = city_aliases
        self.log = log

    # -------------------------------------------------------------------------
    # Dispatcher
    # -------------------------------------------------------------------------

    def clean_all(self, raw: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        """
        Clean all 12 tables in dependency order (parents before children).

        Args:
            raw: Dict of {table_name: raw DataFrame} from load_all().

        Returns:
            Dict of {table_name: cleaned DataFrame}.
        """
        order = [
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
        cleaned = {}
        for table in order:
            if table not in raw:
                self.log.add(table, "table missing from raw data", 0, "SKIPPED")
                continue
            method = getattr(self, f"clean_{table}", None)
            if method is None:
                self.log.add(table, "no clean method defined", 0, "SKIPPED")
                cleaned[table] = raw[table]
                continue
            cleaned[table] = method(raw[table])

        # Orphan handling — quarantine orders with unknown FKs, then filter children
        self._handle_orphans(cleaned)

        return cleaned

    # -------------------------------------------------------------------------
    # Orphan handling (Step 6)
    # -------------------------------------------------------------------------

    def _handle_orphans(self, cleaned: dict[str, pd.DataFrame]) -> None:
        """
        Quarantine orders whose customer_id or restaurant_id doesn't exist,
        then filter child tables (order_items, payments, customer_feedback)
        to keep only rows whose order survived.

        Mutates the 'cleaned' dict in place. Writes quarantine CSVs to
        data/cleaned/quarantine_*.csv.
        """
        from pathlib import Path
        clean_dir = Path("data/cleaned")
        clean_dir.mkdir(parents=True, exist_ok=True)

        orders = cleaned.get("orders")
        if orders is None or len(orders) == 0:
            return

        valid_customers = set(cleaned["customers"]["customer_id"].dropna())
        valid_restaurants = set(cleaned["restaurants"]["restaurant_id"].dropna())

        # Find orphan orders
        orphan_mask = (~orders["customer_id"].isin(valid_customers) |
                       ~orders["restaurant_id"].isin(valid_restaurants))
        orphan_orders = orders[orphan_mask].copy()
        orphan_count = int(orphan_mask.sum())

        if orphan_count > 0:
            # Label the reason
            orphan_orders["quarantine_reason"] = ""
            unknown_cust = ~orphan_orders["customer_id"].isin(valid_customers)
            unknown_rest = ~orphan_orders["restaurant_id"].isin(valid_restaurants)
            orphan_orders.loc[unknown_cust, "quarantine_reason"] = "unknown customer_id"
            orphan_orders.loc[unknown_rest & ~unknown_cust, "quarantine_reason"] = "unknown restaurant_id"
            orphan_orders.loc[unknown_rest & unknown_cust, "quarantine_reason"] = "unknown customer_id + restaurant_id"

            # Save quarantine file
            orphan_orders.to_csv(clean_dir / "quarantine_orders.csv", index=False)
            self.log.add("orders", "quarantine orphan orders", orphan_count,
                         f"unknown customer/restaurant — saved to quarantine_orders.csv")

            # Remove orphans from orders
            cleaned["orders"] = orders[~orphan_mask].copy()

        # Filter child tables to keep only rows whose order_id survived
        valid_order_ids = set(cleaned["orders"]["order_id"].dropna())

        for child, id_col in [("order_items", "order_id"),
                              ("payments", "order_id"),
                              ("customer_feedback", "order_id")]:
            if child not in cleaned:
                continue
            child_df = cleaned[child]
            orphan_child = ~child_df[id_col].isin(valid_order_ids)
            orphan_child_count = int(orphan_child.sum())
            if orphan_child_count > 0:
                orphan_child_df = child_df[orphan_child].copy()
                orphan_child_df["quarantine_reason"] = f"order_id not in cleaned orders"
                orphan_child_df.to_csv(clean_dir / f"quarantine_{child}.csv", index=False)
                self.log.add(child, f"quarantine orphan {id_col}", orphan_child_count,
                             f"parent order was quarantined — saved to quarantine_{child}.csv")
                cleaned[child] = child_df[~orphan_child].copy()

    # -------------------------------------------------------------------------
    # 1. CITIES
    # -------------------------------------------------------------------------

    def clean_cities(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean the cities table: trim text, convert numeric columns.

        This is the root table — no foreign keys. Its 'city' column must be
        unique and clean because every other table's city column maps to it.
        """
        df = df.copy()

        df["city_id"] = to_number(df["city_id"], self.log, "cities", "city_id").astype("Int64")
        df["city"] = clean_text(df["city"])
        df["population"] = to_number(df["population"], self.log, "cities", "population")
        df["region"] = clean_text(df["region"])
        df["average_income"] = to_number(df["average_income"], self.log, "cities", "average_income")

        # Log nulls
        nulls = int(df["average_income"].isna().sum())
        if nulls:
            self.log.add("cities", "average_income: null values", nulls)

        return df

    # -------------------------------------------------------------------------
    # 2. CUSTOMERS
    # -------------------------------------------------------------------------

    def clean_customers(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean customers: trim, standardize city, parse dates, fix phone/pincode,
        remove duplicates, add validity flags.

        Duplicate rule (same as Week 1 SQL): keep first occurrence per customer_id.
        All 180 duplicates are exact copies (verified in Week 1 profiling).
        """
        df = df.copy()
        n = len(df)

        # Trim text columns
        text_cols = ["name", "gender", "email", "state", "membership", "preferred_cuisine"]
        for col in text_cols:
            if col in df.columns:
                df[col] = clean_text(df[col])

        # IDs
        df["customer_id"] = to_number(df["customer_id"], self.log, "customers", "customer_id").astype("Int64")

        # Age: set impossible values to NaN, add flag, fill with median by membership
        df["age"] = to_number(df["age"], self.log, "customers", "age")
        impossible_age = ~df["age"].between(15, 90)
        impossible_count = int(impossible_age.sum())
        if impossible_count:
            self.log.add("customers", "age: impossible values -> NaN", impossible_count,
                         "outside 15-90 range")
        df["age_was_missing"] = df["age"].isna().astype(int)
        df.loc[impossible_age, "age"] = np.nan
        group_median = df.groupby("membership")["age"].transform("median")
        df["age"] = df["age"].fillna(group_median).fillna(df["age"].median())

        # City
        df["city"] = standardize_city(df["city"], self.aliases, self.cities, "customers", self.log)

        # Phone — repair +91/0 prefix, validate, add flag
        raw_phone = df["phone"].copy()
        repairable = raw_phone.str.replace(r"\D", "", regex=True).str.match(
            r"^(91|0)\d{10}$", na=False
        )
        repaired_count = int(repairable.sum())
        if repaired_count:
            self.log.add("customers", "phone: repaired (stripped +91/0 prefix)", repaired_count)
        df["phone"] = clean_phone(df["phone"])
        df["phone_valid"] = df["phone"].notna().astype(int)
        bad_phone = int(df["phone"].isna().sum())
        if bad_phone:
            self.log.add("customers", "phone: invalid -> NaN", bad_phone)

        # Email — validate, add flag
        df["email"] = validate_email(df["email"])
        df["email_valid"] = df["email"].notna().astype(int)
        bad_email = int(df["email"].isna().sum())
        if bad_email:
            self.log.add("customers", "email: invalid -> NaN", bad_email)

        # Pincode — validate, add flag
        df["pincode"] = clean_pincode(df["pincode"])
        df["pincode_valid"] = df["pincode"].notna().astype(int)
        bad_pincode = int(df["pincode"].isna().sum())
        if bad_pincode:
            self.log.add("customers", "pincode: invalid -> NaN", bad_pincode)

        # Registration date — uses DD/MM/YYYY (day-first, not MM/DD/YYYY)
        df["registration_date"] = parse_ddmmyyyy_dates(df["registration_date"])
        null_dates = int(df["registration_date"].isna().sum())
        if null_dates:
            self.log.add("customers", "registration_date: unparseable -> NaT", null_dates)

        # Standardize categories
        if "gender" in df.columns:
            df["gender"] = df["gender"].str.title()
        if "membership" in df.columns:
            df["membership"] = df["membership"].str.title()

        # Numeric
        df["total_orders"] = to_number(df["total_orders"], self.log, "customers", "total_orders").astype("Int64")

        # Duplicates — same rule as Week 1: keep first per customer_id
        before = len(df)
        df = df.drop_duplicates(subset="customer_id", keep="first")
        removed = before - len(df)
        if removed:
            self.log.add("customers", "drop duplicate customer_id", removed,
                         "exact copies — keep first occurrence")

        return df

    # -------------------------------------------------------------------------
    # 3. RESTAURANTS
    # -------------------------------------------------------------------------

    def clean_restaurants(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean restaurants: trim, standardize city, parse times, convert numerics."""
        df = df.copy()

        text_cols = ["restaurant_name", "cuisine", "area", "owner_name", "restaurant_type"]
        for col in text_cols:
            if col in df.columns:
                df[col] = clean_text(df[col])

        df["restaurant_id"] = to_number(df["restaurant_id"], self.log, "restaurants", "restaurant_id").astype("Int64")
        df["city"] = standardize_city(df["city"], self.aliases, self.cities, "restaurants", self.log)

        # Rating: cap out-of-range values (integrity check found max=9.8)
        df["rating"] = to_number(df["rating"], self.log, "restaurants", "rating")
        oor_rating = (df["rating"] > 5) | (df["rating"] < 1)
        oor_count = int(oor_rating.sum())
        if oor_count:
            self.log.add("restaurants", "rating: out of range (>5) -> NaN", oor_count)
            df.loc[oor_rating, "rating"] = np.nan

        # Fill missing ratings with median by city (a new restaurant may have no rating)
        null_ratings = int(df["rating"].isna().sum())
        if null_ratings:
            city_median = df.groupby("city")["rating"].transform("median")
            df["rating"] = df["rating"].fillna(city_median)
            remaining = int(df["rating"].isna().sum())
            filled = null_ratings - remaining
            if filled:
                self.log.add("restaurants", "rating: filled with city median", filled)
            if remaining:
                self.log.add("restaurants", "rating: still null (no city median)", remaining)

        # Times
        for col in ["opening_time", "closing_time"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col].str.strip(), format="%H:%M", errors="coerce").dt.time

        df["average_cost"] = to_number(df["average_cost"], self.log, "restaurants", "average_cost")
        df["latitude"] = to_number(df["latitude"], self.log, "restaurants", "latitude")
        df["longitude"] = to_number(df["longitude"], self.log, "restaurants", "longitude")

        return df

    # -------------------------------------------------------------------------
    # 4. DELIVERY_PARTNERS
    # -------------------------------------------------------------------------

    def clean_delivery_partners(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean delivery_partners: trim, city, dates, numerics."""
        df = df.copy()

        text_cols = ["name", "gender", "vehicle_type"]
        for col in text_cols:
            if col in df.columns:
                df[col] = clean_text(df[col])

        df["delivery_partner_id"] = to_number(
            df["delivery_partner_id"], self.log, "delivery_partners", "delivery_partner_id"
        ).astype("Int64")

        # Age
        df["age"] = to_number(df["age"], self.log, "delivery_partners", "age")
        impossible_age = ~df["age"].between(16, 70)
        if impossible_age.any():
            self.log.add("delivery_partners", "age: impossible -> NaN", int(impossible_age.sum()))
            df.loc[impossible_age, "age"] = np.nan
        df["age_was_missing"] = df["age"].isna().astype(int)
        df["age"] = df["age"].fillna(df["age"].median())

        # City
        df["city"] = standardize_city(df["city"], self.aliases, self.cities, "delivery_partners", self.log)

        # Joining date — uses DD/MM/YYYY (day-first)
        df["joining_date"] = parse_ddmmyyyy_dates(df["joining_date"])

        # Rating: cap at 5, then fill missing with city median
        df["rating"] = to_number(df["rating"], self.log, "delivery_partners", "rating")
        oor = df["rating"] > 5
        if oor.any():
            self.log.add("delivery_partners", "rating: >5 -> NaN", int(oor.sum()))
            df.loc[oor, "rating"] = np.nan
        null_ratings = int(df["rating"].isna().sum())
        if null_ratings:
            city_median = df.groupby("city")["rating"].transform("median")
            df["rating"] = df["rating"].fillna(city_median).fillna(df["rating"].median())
            self.log.add("delivery_partners", "rating: filled with city median", null_ratings)

        df["completed_deliveries"] = to_number(
            df["completed_deliveries"], self.log, "delivery_partners", "completed_deliveries"
        ).astype("Int64")
        df["average_delivery_time"] = to_number(
            df["average_delivery_time"], self.log, "delivery_partners", "average_delivery_time"
        )

        # Winsorize average_delivery_time (feature column — capping is acceptable per guide)
        neg_adt = df["average_delivery_time"] <= 0
        if neg_adt.any():
            self.log.add("delivery_partners", "average_delivery_time: <=0 -> NaN", int(neg_adt.sum()))
            df.loc[neg_adt, "average_delivery_time"] = np.nan
        low, high = iqr_bounds(df["average_delivery_time"], k=3.0)  # conservative
        outlier_mask = (df["average_delivery_time"] < low) | (df["average_delivery_time"] > high)
        if outlier_mask.any():
            self.log.add("delivery_partners", "average_delivery_time: winsorized (IQR k=3.0)", int(outlier_mask.sum()))
            df.loc[df["average_delivery_time"] < low, "average_delivery_time"] = low
            df.loc[df["average_delivery_time"] > high, "average_delivery_time"] = high

        return df

    # -------------------------------------------------------------------------
    # 5. PROMOTIONS
    # -------------------------------------------------------------------------

    def clean_promotions(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean promotions: trim, uppercase coupon_code, parse dates."""
        df = df.copy()

        df["promotion_id"] = to_number(df["promotion_id"], self.log, "promotions", "promotion_id").astype("Int64")
        df["coupon_code"] = clean_text(df["coupon_code"]).str.upper()
        df["discount_percentage"] = to_number(df["discount_percentage"], self.log, "promotions", "discount_percentage")
        df["campaign_name"] = clean_text(df["campaign_name"])
        df["start_date"] = parse_mixed_dates(df["start_date"])
        df["end_date"] = parse_mixed_dates(df["end_date"])

        return df

    # -------------------------------------------------------------------------
    # 6. WEATHER
    # -------------------------------------------------------------------------

    def clean_weather(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean weather: city, date, numerics. Drop rows with blank city."""
        df = df.copy()

        df["weather_id"] = to_number(df["weather_id"], self.log, "weather", "weather_id").astype("Int64")

        # Drop rows with blank city (91 rows quarantined in Week 1)
        blank_city = df["city"].isna() | (df["city"].str.strip() == "")
        if blank_city.any():
            self.log.add("weather", "drop blank city rows", int(blank_city.sum()),
                         "no FK target — quarantined in Week 1 SQL too")
            df = df[~blank_city].copy()

        df["city"] = standardize_city(df["city"], self.aliases, self.cities, "weather", self.log)
        df["date"] = parse_mixed_dates(df["date"])
        df["temperature"] = to_number(df["temperature"], self.log, "weather", "temperature")
        df["rainfall"] = to_number(df["rainfall"], self.log, "weather", "rainfall")
        df["humidity"] = to_number(df["humidity"], self.log, "weather", "humidity")
        df["weather_condition"] = clean_text(df["weather_condition"])

        return df

    # -------------------------------------------------------------------------
    # 7. TRAFFIC
    # -------------------------------------------------------------------------

    def clean_traffic(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean traffic: city, date, time, numerics."""
        df = df.copy()

        df["traffic_id"] = to_number(df["traffic_id"], self.log, "traffic", "traffic_id").astype("Int64")
        df["city"] = standardize_city(df["city"], self.aliases, self.cities, "traffic", self.log)
        df["date"] = parse_mixed_dates(df["date"])

        # Time — keep as HH:MM string for CSV compatibility
        if "time" in df.columns:
            parsed = pd.to_datetime(df["time"].str.strip(), format="mixed", errors="coerce")
            df["time"] = parsed.dt.strftime("%H:%M")

        df["traffic_level"] = clean_text(df["traffic_level"])
        df["average_speed"] = to_number(df["average_speed"], self.log, "traffic", "average_speed")

        return df

    # -------------------------------------------------------------------------
    # 8. MENU
    # -------------------------------------------------------------------------

    def clean_menu(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean menu: trim, convert numerics, standardize availability."""
        df = df.copy()

        df["food_item_id"] = to_number(df["food_item_id"], self.log, "menu", "food_item_id").astype("Int64")
        df["restaurant_id"] = to_number(df["restaurant_id"], self.log, "menu", "restaurant_id").astype("Int64")
        df["food_name"] = clean_text(df["food_name"])
        df["category"] = clean_text(df["category"])
        df["price"] = to_number(df["price"], self.log, "menu", "price")
        df["preparation_time"] = to_number(df["preparation_time"], self.log, "menu", "preparation_time")
        df["calories"] = to_number(df["calories"], self.log, "menu", "calories")
        df["availability"] = clean_text(df["availability"]).str.title()

        return df

    # -------------------------------------------------------------------------
    # 9. ORDERS
    # -------------------------------------------------------------------------

    def clean_orders(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean orders: trim, parse dates/times, convert numerics, standardize
        status, handle duplicates, flag invalid values.

        IMPORTANT: delivery_time_minutes (the ML target) is NOT imputed.
        Negative/zero values are flagged and set to NaN, but rows are kept.
        """
        df = df.copy()

        # IDs
        df["order_id"] = to_number(df["order_id"], self.log, "orders", "order_id").astype("Int64")
        df["customer_id"] = to_number(df["customer_id"], self.log, "orders", "customer_id").astype("Int64")
        df["restaurant_id"] = to_number(df["restaurant_id"], self.log, "orders", "restaurant_id").astype("Int64")

        # delivery_partner_id — nullable (cancelled orders may have none)
        df["delivery_partner_id"] = to_number(
            df["delivery_partner_id"], self.log, "orders", "delivery_partner_id"
        ).astype("Int64")

        # Date — "/" dates are disambiguated in parse_mixed_dates(); log the ambiguous ones
        _s = df["order_date"].str.strip()
        _sl = _s.str.match(r"^\d{2}/\d{2}/\d{4}$", na=False)
        _amb = int((_sl & (pd.to_numeric(_s.str[:2], errors="coerce") <= 12)
                    & (pd.to_numeric(_s.str[3:5], errors="coerce") <= 12)).sum())
        if _amb:
            self.log.add("orders", "order_date: ambiguous '/' date read as MM/DD", _amb,
                         "both parts <= 12; day and month may be swapped")
        df["order_date"] = parse_mixed_dates(df["order_date"])

        # Time — keep as HH:MM string for CSV compatibility
        if "order_time" in df.columns:
            parsed_time = pd.to_datetime(df["order_time"].str.strip(), format="mixed", errors="coerce")
            df["order_time"] = parsed_time.dt.strftime("%H:%M")

        # Numeric columns — flag non-positive values but don't impute the target
        num_cols = ["delivery_time_minutes", "food_cost", "delivery_fee",
                    "discount", "gst", "final_amount"]
        for col in num_cols:
            if col in df.columns:
                df[col] = to_number(df[col], self.log, "orders", col)

        # Flag and null out negative food_cost (Week 1 found 182 negatives)
        if "food_cost" in df.columns:
            neg_fc = df["food_cost"] <= 0
            if neg_fc.any():
                self.log.add("orders", "food_cost: <=0 -> NaN", int(neg_fc.sum()),
                             "data quality issue — Week 1 integrity check confirmed")
                df.loc[neg_fc, "food_cost"] = np.nan

        # Flag negative delivery_time_minutes (target — do NOT impute)
        if "delivery_time_minutes" in df.columns:
            neg_dt = df["delivery_time_minutes"] <= 0
            if neg_dt.any():
                self.log.add("orders", "delivery_time_minutes: <=0 -> NaN", int(neg_dt.sum()),
                             "TARGET — not imputed; rows kept but excluded from model training")
                df.loc[neg_dt, "delivery_time_minutes"] = np.nan

        # delivery_fee = 0 may be legitimate (free delivery) — don't null
        # But negative delivery_fee is invalid
        if "delivery_fee" in df.columns:
            neg_fee = df["delivery_fee"] < 0
            if neg_fee.any():
                self.log.add("orders", "delivery_fee: negative -> NaN", int(neg_fee.sum()))
                df.loc[neg_fee, "delivery_fee"] = np.nan

        # final_amount nulls
        if "final_amount" in df.columns:
            nulls = int(df["final_amount"].isna().sum())
            if nulls:
                self.log.add("orders", "final_amount: null values", nulls)

        # Coupon code — uppercase for consistency with promotions
        df["coupon_code"] = clean_text(df["coupon_code"]).str.upper()
        df["coupon_code"] = df["coupon_code"].replace("", np.nan)

        # Standardize categories
        df["order_status"] = clean_text(df["order_status"]).str.title()
        df["payment_method"] = clean_text(df["payment_method"]).str.title()

        # Duplicates — same rule as Week 1
        before = len(df)
        df = df.drop_duplicates(subset="order_id", keep="first")
        removed = before - len(df)
        if removed:
            self.log.add("orders", "drop duplicate order_id", removed,
                         "exact copies — keep first occurrence")

        # Outlier flag for delivery_time_minutes (target — flag, don't cap)
        # IQR k=3.0 is conservative; delivery times are right-skewed so strict
        # IQR would flag many legitimate slow deliveries. The flag lets Week 3 choose.
        if "delivery_time_minutes" in df.columns:
            valid_dt = df["delivery_time_minutes"].dropna()
            if len(valid_dt) > 0:
                low, high = iqr_bounds(valid_dt, k=3.0)
                df["dt_outlier_flag"] = (~df["delivery_time_minutes"].isna() &
                                         (~df["delivery_time_minutes"].between(low, high))).astype(int)
                flagged = int(df["dt_outlier_flag"].sum())
                if flagged:
                    self.log.add("orders", "delivery_time_minutes: outlier flag (IQR k=3.0)", flagged,
                                 f"bounds=[{low:.1f}, {high:.1f}] — flagged not capped (target)")
                # Log the crosstab finding
                import pandas as _pd
                ct = _pd.crosstab(df["order_status"], df["delivery_time_minutes"].isna())
                cancelled_nulls = int(ct.get(True, _pd.Series()).get("Cancelled", 0)) if True in ct.columns else 0
                self.log.add("orders", "delivery_time nulls mostly on non-delivered orders",
                             int(df["delivery_time_minutes"].isna().sum()),
                             f"cancelled:{cancelled_nulls} — expected, not errors")

        return df

    # -------------------------------------------------------------------------
    # 10. ORDER_ITEMS
    # -------------------------------------------------------------------------

    def clean_order_items(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean order_items: convert IDs and numerics."""
        df = df.copy()

        df["order_item_id"] = to_number(df["order_item_id"], self.log, "order_items", "order_item_id").astype("Int64")
        df["order_id"] = to_number(df["order_id"], self.log, "order_items", "order_id").astype("Int64")
        df["food_item_id"] = to_number(df["food_item_id"], self.log, "order_items", "food_item_id").astype("Int64")
        df["quantity"] = to_number(df["quantity"], self.log, "order_items", "quantity")
        df["unit_price"] = to_number(df["unit_price"], self.log, "order_items", "unit_price")
        df["total_price"] = to_number(df["total_price"], self.log, "order_items", "total_price")

        return df

    # -------------------------------------------------------------------------
    # 11. PAYMENTS
    # -------------------------------------------------------------------------

    def clean_payments(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean payments: trim, convert types, parse dates, check duplicates."""
        df = df.copy()

        df["payment_id"] = to_number(df["payment_id"], self.log, "payments", "payment_id").astype("Int64")
        df["order_id"] = to_number(df["order_id"], self.log, "payments", "order_id").astype("Int64")
        df["payment_method"] = clean_text(df["payment_method"]).str.title()
        df["payment_status"] = clean_text(df["payment_status"]).str.title()
        df["transaction_id"] = clean_text(df["transaction_id"])
        df["payment_date"] = parse_mixed_dates(df["payment_date"])

        # Check duplicates (Week 1 found 0, but verify)
        dup_ids = int(df["payment_id"].duplicated().sum())
        if dup_ids:
            self.log.add("payments", "drop duplicate payment_id", dup_ids)
            df = df.drop_duplicates(subset="payment_id", keep="first")

        return df

    # -------------------------------------------------------------------------
    # 12. CUSTOMER_FEEDBACK
    # -------------------------------------------------------------------------

    def clean_customer_feedback(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean customer_feedback: trim, convert numerics, cap ratings.

        delivery_rating had values up to 9 (Week 1 integrity check) — cap at 5.
        Ratings are LEFT as-is (not imputed) — missing means "didn't rate".
        """
        df = df.copy()

        df["feedback_id"] = to_number(df["feedback_id"], self.log, "customer_feedback", "feedback_id").astype("Int64")
        df["order_id"] = to_number(df["order_id"], self.log, "customer_feedback", "order_id").astype("Int64")

        # Ratings — cap out-of-range values
        for col in ["customer_rating", "delivery_rating", "food_rating"]:
            if col in df.columns:
                df[col] = to_number(df[col], self.log, "customer_feedback", col)
                oor = (df[col] > 5) | (df[col] < 1)
                if oor.any():
                    self.log.add("customer_feedback", f"{col}: out of range -> NaN", int(oor.sum()))
                    df.loc[oor, col] = np.nan

        df["review"] = clean_text(df["review"])
        df["sentiment"] = clean_text(df["sentiment"]).str.title()

        # Add has_review flag (0/1) — free text, can't be guessed
        df["has_review"] = df["review"].notna().astype(int)
        self.log.add("customer_feedback", "has_review flag added", int(df["has_review"].sum()))

        # Check duplicates (Week 1 found 0, but verify)
        dup_ids = int(df["feedback_id"].duplicated().sum())
        if dup_ids:
            self.log.add("customer_feedback", "drop duplicate feedback_id", dup_ids)
            df = df.drop_duplicates(subset="feedback_id", keep="first")

        return df
