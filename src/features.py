"""
src/features.py
---------------
Week 2, Step 8: Build the Analytical Base Table (ABT).

One row per order, with columns from every related table merged in.
The golden rule: a merge must never change the number of orders.

Also provides build_customer_features() for Step 10 (as-of-date customer features).
"""

import numpy as np
import pandas as pd
from pathlib import Path


# ---------------------------------------------------------------------------
# Haversine distance (NumPy vectorized — works on whole columns)
# ---------------------------------------------------------------------------

def haversine_km(lat1, lon1, lat2, lon2):
    """
    Great-circle distance in km between two points.
    Works on whole pandas/numpy columns at once (no Python loops).

    Args:
        lat1, lon1: Latitude/longitude of point 1 (degrees).
        lat2, lon2: Latitude/longitude of point 2 (degrees).

    Returns:
        Array of distances in km.
    """
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    a = (np.sin((lat2 - lat1) / 2) ** 2 +
         np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2)
    return 6371 * 2 * np.arcsin(np.sqrt(a))


# ---------------------------------------------------------------------------
# Analytical Base Table
# ---------------------------------------------------------------------------

def build_analytical_base_table(cleaned: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Merge all 12 cleaned tables into one row-per-order analytical base table.

    Merge order (all m:1 with row-count assertions):
        orders  →  customers  (on customer_id)
        →  restaurants  (on restaurant_id)
        →  delivery_partners  (on delivery_partner_id, nullable)
        →  promotions  (on coupon_code, nullable)
        →  order_items (aggregated to one row per order)
        →  weather  (on restaurant_city + order_date)
        →  traffic  (on restaurant_city + order_date + hour)
        →  customer_feedback  (on order_id, nullable)

    The order's city is the restaurant's city (Week 1 design decision).

    Args:
        cleaned: Dict of {table_name: cleaned DataFrame} from DataCleaner.clean_all().

    Returns:
        DataFrame with exactly one row per cleaned order.
    """
    orders  = cleaned["orders"].copy()
    cust    = cleaned["customers"].copy()
    rest    = cleaned["restaurants"].copy()
    dp      = cleaned["delivery_partners"].copy()
    promos  = cleaned["promotions"].copy()
    oi      = cleaned["order_items"].copy()
    menu    = cleaned["menu"].copy()
    weather = cleaned["weather"].copy()
    traffic = cleaned["traffic"].copy()
    feedback = cleaned["customer_feedback"].copy()

    n_orders = len(orders)

    # ---- 1. Rename clashing columns BEFORE merging ----
    cust = cust.rename(columns={
        "city": "customer_city", "name": "customer_name",
        "age": "customer_age", "gender": "customer_gender",
        "rating": "customer_rating_raw",
    })
    rest = rest.rename(columns={
        "city": "restaurant_city", "name": "restaurant_name_raw",
        "rating": "restaurant_rating", "cuisine": "restaurant_cuisine",
    })
    dp = dp.rename(columns={
        "city": "partner_city", "name": "partner_name",
        "age": "partner_age", "gender": "partner_gender",
        "rating": "partner_rating", "average_delivery_time": "partner_avg_delivery_time",
    })
    feedback = feedback.rename(columns={
        "customer_rating": "feedback_customer_rating",
        "delivery_rating": "feedback_delivery_rating",
        "food_rating": "feedback_food_rating",
    })

    # ---- 2. Merge customers (m:1) ----
    abt = orders.merge(
        cust[["customer_id", "customer_name", "customer_age", "customer_gender",
              "customer_city", "state", "membership", "registration_date",
              "total_orders", "preferred_cuisine"]],
        on="customer_id", how="left", validate="m:1"
    )
    assert len(abt) == n_orders, "customers merge changed row count!"

    # ---- 3. Merge restaurants (m:1) ----
    abt = abt.merge(
        rest[["restaurant_id", "restaurant_name", "restaurant_cuisine", "restaurant_city",
              "area", "restaurant_rating", "average_cost", "restaurant_type",
              "latitude", "longitude"]],
        on="restaurant_id", how="left", validate="m:1"
    )
    assert len(abt) == n_orders, "restaurants merge changed row count!"

    # ---- 4. Merge delivery_partners (m:1, nullable FK) ----
    abt = abt.merge(
        dp[["delivery_partner_id", "partner_name", "partner_age", "partner_gender",
            "vehicle_type", "joining_date", "partner_city", "partner_rating",
            "completed_deliveries", "partner_avg_delivery_time"]],
        on="delivery_partner_id", how="left", validate="m:1"
    )
    assert len(abt) == n_orders, "delivery_partners merge changed row count!"

    # ---- 5. Merge promotions (m:1, nullable FK) ----
    abt = abt.merge(
        promos[["coupon_code", "discount_percentage", "campaign_name"]],
        on="coupon_code", how="left", validate="m:1"
    )
    assert len(abt) == n_orders, "promotions merge changed row count!"

    # ---- 6. Aggregate order_items to one row per order, then merge (m:1) ----
    basket = (oi
              .merge(menu[["food_item_id", "preparation_time"]],
                     on="food_item_id", how="left", validate="m:1")
              .groupby("order_id")
              .agg(
                  n_items=("quantity", "sum"),
                  n_distinct_items=("food_item_id", "nunique"),
                  basket_value=("total_price", "sum"),
                  avg_prep_time=("preparation_time", "mean"),
                  max_prep_time=("preparation_time", "max"),
              )
              .reset_index())
    abt = abt.merge(basket, on="order_id", how="left", validate="m:1")
    assert len(abt) == n_orders, "order_items merge changed row count!"

    # ---- 7. Merge weather (m:1 on restaurant_city + order_date) ----
    # Weather may have duplicate city+date pairs — aggregate to one row per city+date
    weather_agg = (weather
                    .dropna(subset=["date"])
                    .groupby(["city", "date"])
                    .agg(
                        temperature=("temperature", "mean"),
                        rainfall=("rainfall", "mean"),
                        humidity=("humidity", "mean"),
                        weather_condition=("weather_condition",
                                            lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else None),
                    )
                    .reset_index())
    weather_agg = weather_agg.rename(columns={"city": "restaurant_city", "date": "order_date"})
    abt = abt.merge(weather_agg, on=["restaurant_city", "order_date"],
                    how="left", validate="m:1")
    assert len(abt) == n_orders, "weather merge changed row count!"

    # ---- 8. Merge traffic (m:1 on restaurant_city + order_date + hour) ----
    # Traffic has date AND time — match on city + date + hour
    # Extract hour from order_time (stored as HH:MM string)
    abt["order_hour"] = pd.to_datetime(
        abt["order_time"], format="mixed", errors="coerce"
    ).dt.hour

    # Aggregate traffic to one row per city + date + hour
    traffic["traffic_hour"] = pd.to_datetime(
        traffic["time"], format="mixed", errors="coerce"
    ).dt.hour
    traffic_level_map = {"Low": 1, "Moderate": 2, "High": 3, "Severe": 4}

    traffic_agg = (traffic
                   .dropna(subset=["date", "traffic_hour"])
                   .assign(traffic_score=lambda d: d["traffic_level"].map(traffic_level_map))
                   .groupby(["city", "date", "traffic_hour"])
                   .agg(
                       traffic_score=("traffic_score", "mean"),
                       average_speed=("average_speed", "mean"),
                       traffic_level=("traffic_level",
                                      lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else None),
                   )
                   .reset_index()
                   .rename(columns={"city": "restaurant_city", "date": "order_date",
                                    "traffic_hour": "order_hour"}))
    abt = abt.merge(traffic_agg, on=["restaurant_city", "order_date", "order_hour"],
                    how="left", validate="m:1")
    assert len(abt) == n_orders, "traffic merge changed row count!"

    # ---- 9. Merge customer_feedback (m:1, nullable — only ~70% of orders have feedback) ----
    # NOTE: feedback ratings are NOT inputs for the delivery-time model (known only after delivery)
    feedback_cols = ["order_id", "feedback_customer_rating", "feedback_delivery_rating",
                     "feedback_food_rating", "review", "sentiment", "has_review"]
    feedback_agg = (feedback[feedback_cols]
                    .drop_duplicates(subset="order_id", keep="first"))
    abt = abt.merge(feedback_agg, on="order_id", how="left", validate="m:1")
    assert len(abt) == n_orders, "feedback merge changed row count!"

    # ---- 10. Add distance proxy (restaurant to city centre) ----
    # customers.csv has no coordinates — use restaurant distance from city centre
    # as an honest proxy. Document this limitation.
    city_centres = (rest.groupby("restaurant_city")
                    .agg(city_lat=("latitude", "mean"),
                         city_lon=("longitude", "mean"))
                    .reset_index()
                    .rename(columns={"restaurant_city": "restaurant_city"}))
    abt = abt.merge(city_centres, on="restaurant_city", how="left", validate="m:1")
    assert len(abt) == n_orders, "city_centres merge changed row count!"

    abt["distance_to_city_centre_km"] = haversine_km(
        abt["latitude"].astype(float),
        abt["longitude"].astype(float),
        abt["city_lat"].astype(float),
        abt["city_lon"].astype(float),
    )

    # Flag: customer city differs from restaurant city (cross-city delivery)
    abt["is_cross_city"] = (abt["customer_city"].notna() &
                            abt["restaurant_city"].notna() &
                            (abt["customer_city"] != abt["restaurant_city"])).astype(int)

    # ---- 11. Add partner tenure days ----
    if "joining_date" in abt.columns and "order_date" in abt.columns:
        abt["partner_tenure_days"] = (abt["order_date"] - abt["joining_date"]).dt.days

    # ---- 12. Add discount percentage of food cost ----
    if "discount" in abt.columns and "food_cost" in abt.columns:
        abt["discount_pct"] = (abt["discount"] / abt["food_cost"].replace(0, np.nan)).clip(upper=1.0)

    # ---- Final assertion ----
    assert len(abt) == n_orders, f"ABT row count changed! {n_orders} → {len(abt)}"

    return abt


# ---------------------------------------------------------------------------
# Customer features "as of" a date (Step 10 — prep for churn)
# ---------------------------------------------------------------------------

def build_customer_features(orders: pd.DataFrame,
                            as_of: pd.Timestamp) -> pd.DataFrame:
    """
    Per-customer features using only orders on or before `as_of`.

    This prevents leakage: a churn model must not see orders it's supposed
    to predict. Week 3 will call this with an earlier cut-off and build
    the churn label from what happens in the following 60 days.

    Args:
        orders:  Cleaned orders DataFrame (must have order_date, final_amount,
                 order_status, customer_id, order_id).
        as_of:   Cut-off date. Only orders on or before this date are counted.

    Returns:
        DataFrame with one row per customer:
            customer_id, orders_to_date, customer_lifetime_value,
            average_basket_value, first_order, last_order,
            days_since_last_order, order_frequency_30d
    """
    hist = orders[(orders["order_date"] <= as_of) &
                  (orders["order_status"] != "Cancelled")].copy()

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


# Customer-page segments (Week 4). Thresholds are documented in kpi_definitions.md.
NEW_CUSTOMER_DAYS = 60
AT_RISK_QUIET_DAYS = 30


def assign_customer_segment(feats: pd.DataFrame, as_of: pd.Timestamp) -> pd.Series:
    """
    Label each customer who has ordered.

    New:     first order falls within the last 60 days (same window as the
             active-customer rule and the churn horizon).
    At-risk: not new, and quiet for more than 30 days. This is an earlier
             warning than the 60-day churn label.
    Repeat:  not new, and ordered within the last 30 days.
    """
    first_order = pd.to_datetime(feats["first_order"], errors="coerce")
    days_since = pd.to_numeric(feats["days_since_last_order"], errors="coerce")
    return pd.Series(
        np.select(
            [
                (as_of - first_order).dt.days <= NEW_CUSTOMER_DAYS,
                days_since > AT_RISK_QUIET_DAYS,
            ],
            ["New", "At-risk"],
            default="Repeat",
        ),
        index=feats.index,
    )


# ---------------------------------------------------------------------------
# Step 9: Engineered features
# ---------------------------------------------------------------------------

def add_features(abt: pd.DataFrame) -> pd.DataFrame:
    """
    Engineer 10+ features on the analytical base table.

    All calculations are vectorized (no Python loops).
    Features are grouped by type with a note on each.

    PRD-required features (11):
        PeakHour, WeekendOrder, RainImpact, TrafficScore, CustomerTenure,
        AverageBasketValue (→ in customer features), RestaurantPopularity,
        DeliveryEfficiency, CustomerLifetimeValue (→ customer features),
        OrderFrequency (→ customer features), AverageRating

    Extra features added:
        avg_prep_time, max_prep_time, n_items, discount_pct,
        partner_tenure_days, is_peak_and_rain, order_dayofweek,
        order_month, order_minute, is_weekend_and_rain, is_late

    NOTE: feedback ratings (feedback_customer_rating, feedback_delivery_rating,
          feedback_food_rating, average_rating) are present in the ABT for EDA
          and Power BI but must NEVER be used as inputs for the delivery-time
          prediction model — they are known only after delivery.

    NOTE: distance_to_city_centre_km is an honest proxy for restaurant-to-
          customer distance. customers.csv has no coordinates. Documented in
          kpi_definitions.md.

    Args:
        abt: Analytical base table from build_analytical_base_table().
            Date columns must be parsed as datetime64 (done in this function).

    Returns:
        ABT with all feature columns added in place.
    """
    df = abt.copy()

    # ---- Parse datetime columns from string (CSV round-trip converts to str) ----
    for col in ["order_date", "registration_date", "joining_date"]:
        if df[col].dtype == "object":
            df[col] = pd.to_datetime(df[col], errors="coerce")

    # order_time stored as HH:MM string — parse hour/minute directly
    if df["order_time"].dtype == "object":
        time_parsed = pd.to_datetime(df["order_time"], format="mixed", errors="coerce")
        df["order_hour"]   = time_parsed.dt.hour
        df["order_minute"] = time_parsed.dt.minute
    else:
        # Already numeric (shouldn't happen after CSV round-trip, but safe fallback)
        df["order_hour"]   = df["order_hour"]
        df["order_minute"] = df.get("order_minute", 0)

    # ---- Basic time components (must come before any feature using them) ----
    df["order_dayofweek"] = df["order_date"].dt.dayofweek   # Monday=0, Sunday=6
    df["order_month"]     = df["order_date"].dt.month

    # ---- Feature 1: PeakHour (binary 0/1) ----
    # Lunch peak: 12:00-13:59, Dinner peak: 19:00-21:59
    h = df["order_hour"] + df["order_minute"] / 60.0
    df["peak_hour"] = (((h >= 12) & (h < 14)) | ((h >= 19) & (h < 22))).astype(int)

    # ---- Feature 2: WeekendOrder (binary 0/1) ----
    # Saturday=5, Sunday=6
    df["weekend_order"] = (df["order_dayofweek"] >= 5).astype(int)

    # ---- Feature 3: RainImpact (ordinal bins + raw rainfall kept) ----
    # Bins derived from data distribution:
    #   None  = 0 mm (dry)
    #   Light = 0 < rainfall <= 6.7 mm (up to median)
    #   Moderate = 6.7 < rainfall <= 34.5 mm (median to p75)
    #   Heavy = > 34.5 mm
    df["rain_impact"] = pd.cut(
        df["rainfall"].fillna(-1),
        bins=[-2, 0, 6.7, 34.5, float("inf")],
        labels=["None", "Light", "Moderate", "Heavy"],
        right=True,
    )
    df["rain_impact"] = df["rain_impact"].astype(str)
    # Where rainfall was null (no weather record), set to None
    df.loc[df["rainfall"].isna(), "rain_impact"] = np.nan

    # ---- Feature 4: TrafficScore (numeric ordinal 1-4) ----
    # Already built during ABT construction as traffic_score (float).
    # Confirm the mapping is documented:
    #   Low=1, Moderate=2, High=3, Severe=4
    # traffic_score is already in the ABT — keep it, add readable label already there

    # ---- Feature 5: CustomerTenure (days from registration to order) ----
    df["customer_tenure_days"] = (df["order_date"] - df["registration_date"]).dt.days
    # Negative means order placed before registration date — data quality issue
    neg_tenure = (df["customer_tenure_days"] < 0)
    if neg_tenure.sum() > 0:
        # Keep rows but flag them — Week 3 can exclude from model features
        df["tenure_is_negative"] = neg_tenure.astype(int)
    else:
        df["tenure_is_negative"] = 0

    # ---- Feature 6: RestaurantPopularity (rank within city) ----
    # Count of orders per restaurant, ranked dense within each city
    rest_orders = (df.groupby("restaurant_id")["order_id"]
                   .count()
                   .reset_index()
                   .rename(columns={"order_id": "restaurant_order_count"}))
    df = df.merge(rest_orders, on="restaurant_id", how="left")
    df["restaurant_popularity_rank"] = (
        df.groupby("restaurant_city")["restaurant_order_count"]
          .rank(ascending=False, method="dense")
    )

    # ---- Feature 7: DeliveryEfficiency (partner vs city average) ----
    # partner_avg_delivery_time ÷ city mean partner time
    # Below 1 = faster than city average; above 1 = slower
    city_avg_time = (df.groupby("restaurant_city")["partner_avg_delivery_time"]
                       .transform("mean"))
    df["delivery_efficiency"] = df["partner_avg_delivery_time"] / city_avg_time.replace(0, np.nan)

    # ---- Feature 8: AverageRating (post-delivery — EDA/BI only, NOT model input) ----
    # Row mean of the three feedback ratings
    rating_cols = ["feedback_customer_rating", "feedback_delivery_rating", "feedback_food_rating"]
    available = [c for c in rating_cols if c in df.columns]
    if available:
        df["average_rating"] = df[available].mean(axis=1)

    # ---- Feature 9: Interaction — IsPeakAndRain ----
    df["is_peak_and_rain"] = ((df["peak_hour"] == 1) &
                               (df["rain_impact"].isin(["Moderate", "Heavy"]))).astype(int)

    # ---- Feature 10: IsWeekendAndRain ----
    df["is_weekend_and_rain"] = ((df["weekend_order"] == 1) &
                                  (df["rain_impact"].isin(["Moderate", "Heavy"]))).astype(int)

    # ---- Feature 11: CouponUsed (binary) ----
    df["coupon_used"] = df["coupon_code"].notna().astype(int)

    # ---- Late delivery flag (kpi_definitions.md; used by Power BI, not re-derived in DAX) ----
    # 1 = later than 45 minutes, 0 = on time.
    # Blank when the time is missing or not positive, so a late-rate ignores those rows.
    dt = pd.to_numeric(df["delivery_time_minutes"], errors="coerce")
    valid_time = dt.notna() & (dt > 0)
    is_late = pd.Series(pd.NA, index=df.index, dtype="Int64")
    is_late.loc[valid_time] = (dt.loc[valid_time] > 45).astype("int64").to_numpy()
    df["is_late"] = is_late

    # ---- Extra: partner_tenure_days already in ABT from Step 8 ----
    # avg_prep_time, max_prep_time, n_items, discount_pct, distance_to_city_centre_km
    # is_cross_city, dt_outlier_flag — all already in ABT

    return df
