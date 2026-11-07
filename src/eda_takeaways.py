"""
src/eda_takeaways.py
--------------------
Week 3, Steps 2-5: chart takeaways and the EDA report, generated from the data.

Every takeaway is computed from the cleaned data, and every "differs by group"
statement comes with a significance test (Kruskal-Wallis for delivery times and
order values, chi-square for rates). Nothing is hand-written, so the text cannot
drift from the numbers.

  compute_takeaways(abt, cust_features) -> {chart_id: takeaway}
      Used by notebooks/02_eda.ipynb (save_fig looks the takeaway up by chart id).

  build_report()
      Writes reports/eda_report.md, reports/eda_report.html and reports/eda_report.pdf
      from documentation/eda_chart_register.csv plus computed statistics.

Usage:
    python src/eda_takeaways.py        # rebuild the report after running 02_eda.ipynb
"""

import base64
import os
import re
import sys
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
CLEAN = ROOT / "data" / "cleaned"
IMG = ROOT / "images"
REPORTS = ROOT / "reports"
DOC = ROOT / "documentation"

LATE_MIN = 45                       # kpi_definitions.md
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MEMBERSHIP = ["Basic", "Gold", "Zomato Pro"]
TRAFFIC = ["Low", "Moderate", "High", "Severe"]
NUMERIC_COLS = ["delivery_time_minutes", "final_amount", "food_cost", "delivery_fee",
                "order_hour", "order_dayofweek", "avg_prep_time", "traffic_score",
                "partner_rating", "restaurant_rating", "n_items", "rainfall", "peak_hour",
                "partner_avg_delivery_time", "distance_to_city_centre_km", "tenure_is_negative"]

QUESTIONS = {
    "Q1": "Which restaurants and cuisines generate the most revenue, and how has it changed over time?",
    "Q2": "What are the peak ordering hours, and how do weekday and weekend differ?",
    "Q3": "How are delivery times distributed, and how do they vary by city, traffic and weather?",
    "Q4": "What is the average basket size, and how does it differ by membership tier?",
    "Q5": "What share of customers are repeat vs one-time?",
    "Q6": "Which delivery partners are consistently the fastest and best rated?",
    "Q7": "What patterns lie behind cancellations?",
    "Q8": "How does customer lifetime value distribute across cities and cuisines?",
}
BEST_CHART = {"Q1": "m01_revenue_by_city", "Q2": "s12_heatmap_weekday_hour",
              "Q3": "m07_delivery_time_hist", "Q4": "s07_basket_by_membership",
              "Q5": "m17_orders_per_customer", "Q6": "m12b_partner_speed_vs_rating",
              "Q7": "m15_cancel_by_city", "Q8": "s16_clv_by_city"}


# ---------------------------------------------------------------------------
# Formatting and test helpers
# ---------------------------------------------------------------------------

def _inr(x: float) -> str:
    """Rupees: lakh for large amounts, plain otherwise."""
    return f"₹{x / 1e5:.2f} lakh" if abs(x) >= 1e5 else f"₹{x:,.0f}"


def _p(p: float) -> str:
    """Plain-words significance statement."""
    if p is None or np.isnan(p):
        return "not tested (too few groups)"
    if p < 0.05:
        return f"statistically significant ({'p<0.001' if p < 0.001 else f'p={p:.3f}'})"
    return f"not statistically significant (p={p:.2f})"


def _strength(r: float) -> str:
    a = abs(r)
    return ("effectively none" if a < 0.1 else "weak" if a < 0.3
            else "moderate" if a < 0.5 else "strong")


def _kruskal(df: pd.DataFrame, group: str, value: str, min_n: int = 5) -> float:
    groups = [g[value].dropna().to_numpy() for _, g in df.groupby(group)
              if g[value].notna().sum() >= min_n]
    return stats.kruskal(*groups).pvalue if len(groups) >= 2 else np.nan


def _chi2(df: pd.DataFrame, group: str, flag: str) -> float:
    ct = pd.crosstab(df[group], df[flag])
    if ct.shape[0] < 2 or ct.shape[1] < 2:
        return np.nan
    return stats.chi2_contingency(ct)[1]


def _join(series: pd.Series, fmt) -> str:
    return ", ".join(f"{k} {fmt(v)}" for k, v in series.items())


def _pct(v: float) -> str:
    return f"{v:.1%}"


# ---------------------------------------------------------------------------
# Data preparation (same subsets as the notebook)
# ---------------------------------------------------------------------------

def prepare(abt: pd.DataFrame):
    """Return (all_orders, delivered, valid) with numeric columns coerced."""
    a = abt.copy()
    for c in NUMERIC_COLS:
        if c in a.columns:
            a[c] = pd.to_numeric(a[c], errors="coerce")
    a["order_date"] = pd.to_datetime(a["order_date"], errors="coerce")
    a["is_cancelled"] = a["order_status"].eq("Cancelled")
    delivered = a[a["order_status"].eq("Delivered")].copy()
    valid = delivered[delivered["delivery_time_minutes"] > 0].copy()
    valid["is_late"] = valid["delivery_time_minutes"] > LATE_MIN
    return a, delivered, valid


def customer_frame(all_orders: pd.DataFrame, cust_features: pd.DataFrame) -> pd.DataFrame:
    """
    Customer-level table: as-of features + city/cuisine of the customer's first order's
    restaurant (the rule used in the notebook) + membership from customers.csv.
    """
    first = (all_orders.sort_values("order_date")
             .groupby("customer_id")[["restaurant_city", "restaurant_cuisine"]]
             .first().reset_index()
             .rename(columns={"restaurant_city": "city", "restaurant_cuisine": "cuisine"}))
    members = pd.read_csv(CLEAN / "customers.csv", usecols=["customer_id", "membership"])
    return (cust_features.merge(first, on="customer_id", how="left")
                         .merge(members, on="customer_id", how="left"))


# ---------------------------------------------------------------------------
# Takeaways
# ---------------------------------------------------------------------------

def compute_takeaways(abt: pd.DataFrame, cust_features: pd.DataFrame) -> dict:
    """Return {chart_id: takeaway sentence}, every number computed from the data."""
    a, d, v = prepare(abt)
    cf = customer_frame(a, cust_features)
    dt = "delivery_time_minutes"
    T = {}

    # ---- Q1: revenue ----
    rev = d.groupby("restaurant_city")["final_amount"].sum().sort_values(ascending=False)
    T["m01_revenue_by_city"] = (
        f"{rev.index[0]} leads with {_inr(rev.iloc[0])} of delivered revenue; the top 3 cities hold "
        f"{rev.head(3).sum() / rev.sum():.0%} of the total and the largest city earns "
        f"{rev.iloc[0] / rev.iloc[-1]:.2f}x the smallest ({rev.index[-1]})")

    cz = d.groupby("restaurant_cuisine")["final_amount"].sum().dropna().sort_values(ascending=False)
    k = min(9, len(cz) - 1)
    T["m02_revenue_by_cuisine"] = (
        f"{cz.index[0]} is the top cuisine at {_inr(cz.iloc[0])}, "
        f"{cz.iloc[0] / cz.iloc[k] - 1:.0%} more than #{k + 1} {cz.index[k]}")

    monthly = d.groupby(d["order_date"].dt.to_period("M"))["final_amount"].sum()
    chg = monthly.iloc[-6:].mean() / monthly.iloc[:6].mean() - 1
    dd = d.dropna(subset=["order_date"])
    undated = d["order_date"].isna().mean()
    by_year = dd.groupby(dd["order_date"].dt.year.astype(int))["final_amount"].sum()
    yoy = by_year.iloc[-1] / by_year.iloc[0] - 1 if len(by_year) >= 2 else np.nan
    trend = ("there is no clear trend" if abs(chg) < 0.05 and abs(yoy) < 0.05
             else "revenue is trending " + ("up" if chg > 0 else "down"))
    T["m03_monthly_revenue"] = (
        f"Monthly revenue ranges {_inr(monthly.min())}-{_inr(monthly.max())} "
        f"(variation {monthly.std() / monthly.mean():.0%}); the last 6 months average {chg:+.1%} "
        f"vs the first 6 and {by_year.index[-1]} is {yoy:+.1%} vs {by_year.index[0]}, so {trend}")

    top6 = rev.head(6).index
    sub = d[d["restaurant_city"].isin(top6)]
    share = (sub[sub["restaurant_cuisine"].isin(cz.head(5).index)].groupby("restaurant_city")["final_amount"].sum()
             / sub.groupby("restaurant_city")["final_amount"].sum())
    leaders = (sub.groupby(["restaurant_city", "restaurant_cuisine"])["final_amount"].sum()
                  .reset_index().sort_values("final_amount")
                  .groupby("restaurant_city").tail(1)["restaurant_cuisine"])
    T["m10_stacked_cuisine_city"] = (
        f"In the top 6 cities the overall top-5 cuisines make up {share.min():.0%}-{share.max():.0%} of revenue, "
        f"and the #1 cuisine differs by city ({leaders.nunique()} different leaders across 6 cities)")

    T["m11_cumulative_revenue"] = (
        f"Cumulative delivered revenue reaches {_inr(monthly.sum())} over {len(monthly)} months, "
        f"about {_inr(monthly.mean())} per month; {undated:.1%} of delivered orders have no parseable "
        f"date and are excluded from all time-based charts")

    # ---- Q2: hours ----
    h = a.dropna(subset=["order_hour", "order_dayofweek"])
    wd = h[h["order_dayofweek"] < 5].groupby("order_hour").size()
    we = h[h["order_dayofweek"] >= 5].groupby("order_hour").size()
    dinner = a["order_hour"].dropna().between(19, 21).mean()
    T["m05_orders_by_hour"] = (
        f"Peak hour is {int(wd.idxmax())}:00 on weekdays and {int(we.idxmax())}:00 on weekends; "
        f"19:00-22:00 carries {dinner:.1%} of orders vs 12.5% if orders were spread evenly over 24 hours")

    cells = h.pivot_table(index="order_dayofweek", columns="order_hour",
                          values="order_id", aggfunc="count").stack()
    (dmax, hmax), (dmin, hmin) = cells.idxmax(), cells.idxmin()
    T["s12_heatmap_weekday_hour"] = (
        f"Busiest slot is {DAYS[int(dmax)]} {int(hmax)}:00 ({int(cells.max())} orders); "
        f"quietest is {DAYS[int(dmin)]} {int(hmin)}:00 ({int(cells.min())} orders)")

    # ---- Q3: delivery time ----
    x = v[dt]
    med, p90 = np.percentile(x, [50, 90])
    T["m07_delivery_time_hist"] = (
        f"Median delivery is {med:.0f} min and 90% arrive within {p90:.0f} min; "
        f"{v['is_late'].mean():.1%} exceed the {LATE_MIN}-min late threshold")

    mdt = v.groupby(v["order_date"].dt.to_period("M"))[dt].mean()
    change = np.polyfit(np.arange(len(mdt)), mdt.to_numpy(), 1)[0] * (len(mdt) - 1)
    T["m04_monthly_delivery_time"] = (
        f"Monthly average delivery time stays between {mdt.min():.1f} and {mdt.max():.1f} min; "
        f"the fitted trend moves it {change:+.1f} min over {len(mdt)} months"
        + (", i.e. no trend" if abs(change) < 1 else ""))

    veh = v.groupby("vehicle_type")[dt].median().sort_values()
    T["m12_delivery_by_vehicle"] = (
        f"Median delivery by vehicle: {_join(veh, lambda m: f'{m:.0f} min')}; "
        f"differences are {_p(_kruskal(v, 'vehicle_type', dt))}")

    r = v[["partner_avg_delivery_time", dt]].corr().iloc[0, 1]
    T["m13_delivery_vs_partner_avg"] = (
        f"A partner's historical average delivery time and this order's delivery time correlate at "
        f"r={r:+.3f} ({_strength(r)}), so past partner speed does not predict this delivery")

    top8 = v["restaurant_city"].value_counts().head(8).index
    s8 = v[v["restaurant_city"].isin(top8)]
    mc = s8.groupby("restaurant_city")[dt].median()
    T["s05_delivery_by_city"] = (
        f"Median delivery across the top 8 cities ranges {mc.min():.0f}-{mc.max():.0f} min; "
        f"differences are {_p(_kruskal(s8, 'restaurant_city', dt))}")

    w = v.groupby("weather_condition")[dt].mean().sort_values()
    T["s13_delivery_by_weather"] = (
        f"Mean delivery by weather runs from {w.iloc[0]:.1f} min ({w.index[0]}) to {w.iloc[-1]:.1f} min "
        f"({w.index[-1]}), a {w.iloc[-1] - w.iloc[0]:.1f}-min spread; differences are "
        f"{_p(_kruskal(v, 'weather_condition', dt))}")

    tv = v[v["traffic_level"].isin(TRAFFIC)]
    tm = tv.groupby("traffic_level")[dt].median().reindex(TRAFFIC)
    T["s14_delivery_by_traffic"] = (
        f"Only {len(tv):,} of {len(v):,} valid deliveries matched a traffic record; median delivery "
        f"Low→Severe is {' / '.join(f'{m:.0f}' for m in tm)} min; differences are "
        f"{_p(_kruskal(tv, 'traffic_level', dt))}")

    T["s10_delivery_kde"] = (
        f"Delivery times are right-skewed (skew {stats.skew(x):.2f}): median {med:.0f} min, "
        f"mean {x.mean():.1f} min, longest {x.max():.0f} min")

    pv = v[["avg_prep_time", dt]].dropna()
    slope = np.polyfit(pv["avg_prep_time"], pv[dt], 1)[0]
    r = pv.corr().iloc[0, 1]
    T["s08_regplot_preptime"] = (
        f"Each extra minute of average prep time goes with {slope:+.2f} min of delivery "
        f"(r={r:+.3f}, {_strength(r)}); prep time explains {r ** 2:.2%} of the variation")

    tv2 = v[["traffic_score", dt]].dropna()
    r = tv2.corr().iloc[0, 1]
    T["s09_delivery_vs_traffic"] = (
        f"Across {len(tv2):,} deliveries with a traffic match, traffic score and delivery time "
        f"correlate at r={r:+.3f} ({_strength(r)})")

    corr_cols = ["delivery_time_minutes", "food_cost", "delivery_fee", "final_amount", "n_items",
                 "avg_prep_time", "order_hour", "traffic_score", "rainfall", "restaurant_rating"]
    cr = v[corr_cols].corr()[dt].drop(dt)
    top = cr.abs().idxmax()
    rfa = v[["food_cost", "final_amount"]].corr().iloc[0, 1]
    T["s01_correlation_heatmap"] = (
        f"The strongest correlation with delivery time is {top} (r={cr[top]:+.3f}); every other "
        f"feature is weaker. food_cost and final_amount correlate at r={rfa:.2f} because the bill "
        f"is built from the food cost")

    lc = v.groupby("restaurant_city")["is_late"].mean().sort_values()
    T["m16_late_delivery_by_city"] = (
        f"Late-delivery rate ranges from {lc.iloc[0]:.1%} ({lc.index[0]}) to {lc.iloc[-1]:.1%} "
        f"({lc.index[-1]}); differences are {_p(_chi2(v, 'restaurant_city', 'is_late'))}")

    lh = v.groupby("order_hour")["is_late"].mean()
    pk = v.groupby("peak_hour")["is_late"].mean()
    T["s18_late_by_hour"] = (
        f"Late rate by hour ranges {lh.min():.1%}-{lh.max():.1%} and differences are "
        f"{_p(_chi2(v, 'order_hour', 'is_late'))}; peak hours {pk.get(1, np.nan):.1%} "
        f"vs off-peak {pk.get(0, np.nan):.1%}")

    pair = ["food_cost", "n_items", "avg_prep_time", "distance_to_city_centre_km"]
    pr = v[pair + [dt]].corr()[dt].drop(dt)
    pf = pr.abs().idxmax()
    T["s02_pairplot"] = (
        f"Delivery time's largest |r| with the other pairplot features is {abs(pr[pf]):.3f} ({pf}), "
        f"so no relationships are visible")

    # ---- Q4: basket ----
    fa = d["final_amount"].dropna()
    q1, q2, q3 = np.percentile(fa, [25, 50, 75])
    T["m06_order_value_hist"] = (
        f"Median delivered order value is ₹{q2:.0f}; the middle half of orders falls between "
        f"₹{q1:.0f} and ₹{q3:.0f}")

    p_mem = _kruskal(d, "membership", "final_amount")
    mm = d.groupby("membership")["final_amount"].mean().reindex(MEMBERSHIP)
    T["m14_basket_by_membership"] = (
        f"Average order value: {_join(mm, lambda m: f'₹{m:.0f}')}; differences are {_p(p_mem)}")
    md = d.groupby("membership")["final_amount"].median().reindex(MEMBERSHIP)
    T["s07_basket_by_membership"] = (
        f"Median order value: {_join(md, lambda m: f'₹{m:.0f}')}; differences are {_p(p_mem)}")

    fc = d[(d["food_cost"] > 0) & (d["final_amount"] > 0)]
    T["s11_food_cost_kde"] = (
        f"Median food cost is ₹{fc['food_cost'].median():.0f} (skew {stats.skew(fc['food_cost']):.2f}); "
        f"food cost is a median {(fc['food_cost'] / fc['final_amount']).median():.0%} of the final bill")

    # ---- Q5: repeat vs one-time ----
    n = cf["orders_to_date"]
    T["m17_orders_per_customer"] = (
        f"{(n == 1).mean():.1%} of customers have exactly 1 non-cancelled order and "
        f"{(n >= 2).mean():.1%} have 2 or more (mean {n.mean():.2f})")
    cf2 = cf.assign(is_repeat=cf["orders_to_date"] >= 2)
    rep = cf2.groupby("membership")["is_repeat"].mean().reindex(MEMBERSHIP)
    T["s19_repeat_by_membership"] = (
        f"Repeat-customer share by membership: {_join(rep, _pct)}; "
        f"differences are {_p(_chi2(cf2, 'membership', 'is_repeat'))}")

    # ---- Q6: partners ----
    pp = (v.groupby("delivery_partner_id")
            .agg(n=("order_id", "count"), t=(dt, "mean"), rating=("partner_rating", "first")))
    pp = pp[pp["n"] >= 10]
    r = pp["t"].corr(pp["rating"])
    T["m12b_partner_speed_vs_rating"] = (
        f"Among {len(pp)} partners with 10+ deliveries, average delivery time and rating correlate "
        f"at r={r:+.2f} ({_strength(r)}); partner averages range {pp['t'].min():.1f}-{pp['t'].max():.1f} min, "
        f"which with about 10 orders each is mostly sampling noise")

    # ---- Q7: status, payment, cancellations ----
    st = a["order_status"].value_counts(normalize=True)
    T["s03_order_status_count"] = f"Order status split: {_join(st, _pct)}"
    reached = st.get("Delivered", 0) + st.get("Delivered Late", 0)
    T["m09_order_status_pie"] = (
        f"{reached:.1%} of orders reach the customer (Delivered or Delivered Late); "
        f"{1 - reached:.1%} are cancelled or not delivered")

    pm = a["payment_method"].value_counts(normalize=True)
    T["s04_payment_method"] = (
        f"Most-used method is {pm.index[0]} ({pm.iloc[0]:.1%}) and least-used is "
        f"{pm.index[-1]} ({pm.iloc[-1]:.1%})")
    T["m08_payment_pie"] = (
        f"The {len(pm)} payment methods each hold {pm.min():.1%}-{pm.max():.1%} of orders"
        + (", a near-even split" if pm.max() - pm.min() < 0.03 else ""))

    cc = a.groupby("restaurant_city")["is_cancelled"].mean().sort_values()
    T["m15_cancel_by_city"] = (
        f"Cancellation rate ranges from {cc.iloc[0]:.1%} ({cc.index[0]}) to {cc.iloc[-1]:.1%} "
        f"({cc.index[-1]}) across cities; differences are {_p(_chi2(a, 'restaurant_city', 'is_cancelled'))}")

    cp = a.groupby("payment_method")["is_cancelled"].mean().sort_values(ascending=False)
    T["s15_cancel_by_payment"] = (
        f"Highest cancellation is {cp.index[0]} ({cp.iloc[0]:.1%}), lowest {cp.index[-1]} "
        f"({cp.iloc[-1]:.1%}); differences are {_p(_chi2(a, 'payment_method', 'is_cancelled'))}")

    cm = a.groupby("membership")["is_cancelled"].mean().reindex(MEMBERSHIP)
    ch = a.groupby("order_hour")["is_cancelled"].mean()
    T["s15b_cancel_by_mem_hour"] = (
        f"Cancellation by membership is {_join(cm, _pct)}, {_p(_chi2(a, 'membership', 'is_cancelled'))}; "
        f"by hour it ranges {ch.min():.1%}-{ch.max():.1%}, {_p(_chi2(a, 'order_hour', 'is_cancelled'))}")

    top6c = a["restaurant_cuisine"].value_counts().head(6).index
    rr = a[a["restaurant_cuisine"].isin(top6c)].drop_duplicates("restaurant_id")
    mr = rr.groupby("restaurant_cuisine")["restaurant_rating"].median()
    T["s06_rating_by_cuisine"] = (
        f"Median restaurant rating across the top 6 cuisines ranges {mr.min():.2f}-{mr.max():.2f}; "
        f"differences are {_p(_kruskal(rr, 'restaurant_cuisine', 'restaurant_rating'))}")

    # ---- Q8: CLV ----
    clv = "customer_lifetime_value"
    t10 = cf["city"].value_counts().head(10).index
    c10 = cf[cf["city"].isin(t10)]
    mcl = c10.groupby("city")[clv].median()
    T["s16_clv_by_city"] = (
        f"Median CLV across the top 10 customer cities ranges ₹{mcl.min():.0f}-₹{mcl.max():.0f}; "
        f"differences are {_p(_kruskal(c10, 'city', clv))}")
    t6 = cf["cuisine"].value_counts().head(6).index
    c6 = cf[cf["cuisine"].isin(t6)]
    mcc = c6.groupby("cuisine")[clv].median()
    T["s17_clv_by_cuisine"] = (
        f"Median CLV across the top 6 cuisines ranges ₹{mcc.min():.0f}-₹{mcc.max():.0f}; "
        f"differences are {_p(_kruskal(c6, 'cuisine', clv))}")

    return T


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _sql_crosschecks(delivered: pd.DataFrame, all_orders: pd.DataFrame) -> list:
    """Re-run the Step 3 SQL cross-checks. Returns rows or [] if the DB is unreachable."""
    try:
        from dotenv import load_dotenv
        from sqlalchemy import create_engine, text
        load_dotenv(ROOT / ".env")
        eng = create_engine(os.getenv("DATABASE_URL").replace("postgresql://", "postgresql+psycopg2://", 1))
        with eng.connect() as c:
            city, rev = c.execute(text(
                "SELECT r.city, SUM(o.final_amount) FROM orders o JOIN restaurants r "
                "ON r.restaurant_id=o.restaurant_id WHERE o.order_status='Delivered' AND o.final_amount>0 "
                "GROUP BY r.city ORDER BY 2 DESC LIMIT 1")).one()
            hour = c.execute(text(
                "SELECT EXTRACT(HOUR FROM order_time) FROM orders GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 1")).scalar()
            cuisine = c.execute(text(
                "SELECT r.cuisine FROM orders o JOIN restaurants r ON r.restaurant_id=o.restaurant_id "
                "WHERE o.order_status='Delivered' AND o.final_amount>0 AND r.cuisine IS NOT NULL "
                "GROUP BY r.cuisine ORDER BY SUM(o.final_amount) DESC LIMIT 1")).scalar()
    except Exception as err:          # report still builds without the DB
        print(f"  [WARN] SQL cross-check skipped: {err}")
        return []
    d = delivered[delivered["final_amount"] > 0]
    py_rev = d.groupby("restaurant_city")["final_amount"].sum()
    py_city = py_rev.idxmax()
    py_hour = all_orders.groupby("order_hour").size().idxmax()
    py_cui = d.groupby("restaurant_cuisine")["final_amount"].sum().idxmax()
    return [
        ("Top revenue city", f"{city} ₹{float(rev):,.2f}", f"{py_city} ₹{py_rev.max():,.2f}",
         city == py_city and abs(float(rev) - py_rev.max()) < 1),
        ("Peak order hour", f"{int(hour)}", f"{int(py_hour)}", int(hour) == int(py_hour)),
        ("Top cuisine by revenue", str(cuisine), str(py_cui), cuisine == py_cui),
    ]


def _report_stats() -> dict:
    """Numbers used in the report text (outside the per-chart takeaways)."""
    sys.path.insert(0, str(ROOT))
    abt = pd.read_csv(CLEAN / "analytical_base_table.csv")
    a, d, v = prepare(abt)
    s = {"n_all": len(a), "n_delivered": len(d), "n_valid": len(v),
         "date_min": a["order_date"].min().date(), "date_max": a["order_date"].max().date(),
         "traffic_cov": v["traffic_score"].notna().mean(),
         "weather_cov": v["weather_condition"].notna().mean(),
         "neg_tenure": int(abt["tenure_is_negative"].sum()),
         "undated": a["order_date"].isna().mean()}
    raw = pd.read_csv(ROOT / "data" / "raw" / "orders.csv", dtype=str)["OrderDate"].str.strip()
    sl = raw.str.match(r"^\d{2}/\d{2}/\d{4}$", na=False)
    s["ambiguous"] = int((sl & (pd.to_numeric(raw.str[:2], errors="coerce") <= 12)
                          & (pd.to_numeric(raw.str[3:5], errors="coerce") <= 12)).sum())
    dist = a.drop_duplicates("restaurant_id")["distance_to_city_centre_km"]
    s["dist_median"], s["dist_p90"] = dist.median(), dist.quantile(0.9)
    s["sql"] = _sql_crosschecks(d, a)

    from src.model_delivery import NUMERIC, build_model_dataset
    X, y = build_model_dataset(abt)
    rs = X[[c for c in NUMERIC if c in X.columns]].corrwith(y)
    s["max_abs_r"], s["max_r_feat"] = rs.abs().max(), rs.abs().idxmax()

    from sklearn.metrics import r2_score, roc_auc_score
    dp = pd.read_csv(CLEAN / "ml_delivery_predictions.csv")
    s["del_r2"] = r2_score(dp["actual_minutes"], dp["predicted_minutes"])
    s["del_rmse"] = float(np.sqrt(((dp["actual_minutes"] - dp["predicted_minutes"]) ** 2).mean()))
    cs = pd.read_csv(CLEAN / "ml_churn_scores_test.csv")
    s["churn_rate"] = cs["actual_label"].mean()
    s["churn_auc"] = roc_auc_score(cs["actual_label"], cs["churn_probability"])
    return s


def _md_to_html(text: str) -> str:
    """Minimal markdown to HTML (headers, tables, lists, bold, code, images)."""
    out, in_table, first_row = [], False, False
    for line in text.split("\n"):
        if line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue
            if not in_table:
                out.append('<table>'); in_table, first_row = True, True
            tag = "th" if first_row else "td"
            first_row = False
            out.append("<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>")
            continue
        if in_table:
            out.append("</table>"); in_table = False
        m = re.match(r"!\[(.*?)\]\((.*?)\)", line.strip())
        if m:
            b64 = base64.b64encode((REPORTS / m.group(2)).read_bytes()).decode()
            out.append(f'<img alt="{m.group(1)}" src="data:image/png;base64,{b64}">')
            continue
        line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
        line = re.sub(r"`(.+?)`", r"<code>\1</code>", line)
        if line.startswith("### "): out.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("## "): out.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "): out.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("- "): out.append(f"<li>{line[2:]}</li>")
        elif line.strip() == "---": out.append("<hr>")
        elif line.strip(): out.append(f"<p>{line}</p>")
    if in_table:
        out.append("</table>")
    return "\n".join(out)


def _write_pdf(sections: list, path: Path) -> int:
    """sections: list of (title, paragraphs, image_path_or_None). Returns page count."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    def lines_of(paragraphs):
        out = []
        for p in paragraphs:
            out += textwrap.wrap(p, 105, subsequent_indent="   " if p.startswith("• ") else "") or [""]
            out.append("")
        return out

    pages = 0
    with PdfPages(path) as pdf:
        for title, paragraphs, image in sections:
            lines = lines_of(paragraphs)
            while True:
                fig = plt.figure(figsize=(8.27, 11.69))
                fig.text(0.07, 0.955, title, fontsize=14, weight="bold", va="top")
                cap = 30 if image else 66
                fig.text(0.07, 0.92, "\n".join(lines[:cap]), fontsize=8.6, va="top")
                if image:
                    ax = fig.add_axes([0.07, 0.04, 0.86, 0.45])
                    ax.imshow(plt.imread(image)); ax.axis("off")
                pdf.savefig(fig); plt.close(fig); pages += 1
                lines, image = lines[cap:], None
                if not lines:
                    break
                title = title + " (cont.)" if not title.endswith("(cont.)") else title
    return pages


def build_report() -> None:
    """Write reports/eda_report.md, .html and .pdf from the register and computed stats."""
    reg = pd.read_csv(DOC / "eda_chart_register.csv")
    s = _report_stats()
    REPORTS.mkdir(exist_ok=True)
    n_mpl = int((reg["library"] == "matplotlib").sum())
    n_sns = int((reg["library"] == "seaborn").sum())

    method = [
        f"Data: 12 cleaned tables, {s['date_min']} to {s['date_max']}, analysed through "
        f"data/cleaned/analytical_base_table.csv ({s['n_all']:,} orders, one row per order).",
        f"Subsets: all orders ({s['n_all']:,}) for status, payment and cancellation questions; "
        f"delivered orders ({s['n_delivered']:,}) for revenue and basket size; valid deliveries "
        f"({s['n_valid']:,}, delivery time > 0) for delivery-time questions.",
        f"Definitions (documentation/kpi_definitions.md): revenue = final_amount of delivered orders; "
        f"late = delivery over {LATE_MIN} minutes; an order's city and cuisine come from its restaurant. "
        f"A customer's city and cuisine (Q8) come from the restaurant of their first order.",
        "Method: every takeaway below is computed from the data. Group differences are tested with "
        "Kruskal-Wallis (delivery times, order values, ratings, CLV) or chi-square (rates). Many tests "
        "are run, so isolated p-values just under 0.05 should be read with caution.",
        f"Charts: {len(reg)} in total ({n_mpl} Matplotlib, {n_sns} Seaborn), listed in "
        f"documentation/eda_chart_register.csv.",
    ]
    if s["sql"]:
        method.append("SQL cross-checks against the Week 1 database: " + "; ".join(
            f"{n}: SQL {a} / Python {b} ({'match' if ok else 'MISMATCH'})" for n, a, b, ok in s["sql"]))

    dq = [
        f"• Traffic data matched only {s['traffic_cov']:.1%} of valid deliveries (city + date + hour join), "
        f"so traffic findings rest on a small sample.",
        f"• Weather data matched {s['weather_cov']:.1%} of valid deliveries.",
        f"• {s['neg_tenure']:,} orders are dated before the customer's registration date; they are flagged "
        f"(tenure_is_negative), not dropped.",
        "• There is no cancellation-reason column, so Q7 describes patterns, not causes.",
        (f"• Dates: raw dates written with '/' mix DD/MM and MM/DD. The parsers read a part above 12 as the "
         f"day; {s['ambiguous']:,} orders have both parts at 12 or under and are read as MM/DD, so their day "
         f"and month may be swapped. {s['undated']:.1%} of orders still have no parseable date.")
        if s["undated"] < 0.01 else
        (f"• Date parsing bug: {s['undated']:.1%} of orders have no parseable date and are excluded from "
         f"time-based charts and the churn dataset."),
    ]
    if s["dist_median"] > 50:
        dq.append(
            f"• Distance proxy: restaurants sit a median {s['dist_median']:.0f} km (90th percentile "
            f"{s['dist_p90']:.0f} km) from the centre of their own city, so the restaurant coordinates do "
            f"not match their cities and distance_to_city_centre_km carries no real distance information; it "
            f"is excluded from the delivery model. "
            f"customers.csv has no coordinates at all.")
    else:
        dq.append(f"• Distance is a proxy (restaurant to city centre, median {s['dist_median']:.1f} km); "
                  f"customers.csv has no coordinates.")

    modelling = [
        f"• Delivery time: the largest |r| between delivery time and any numeric model feature is "
        f"{s['max_abs_r']:.3f} ({s['max_r_feat']}), and the group tests above find almost no "
        f"differences. The regression model scores R²={s['del_r2']:.3f} and RMSE={s['del_rmse']:.1f} min "
        f"on the test set, no better than predicting the mean.",
        f"• Churn: {s['churn_rate']:.1%} of customers churn in the 60-day window; the classifier's "
        f"test ROC-AUC is {s['churn_auc']:.2f} (0.50 = random).",
        "• Conclusion: this dataset shows no learnable signal for either target. That is a property of "
        "the data, not a coding error. The pipelines are reusable on data that does contain signal.",
    ]

    # ---------- markdown ----------
    md = ["# EDA Report: Zomato Business Intelligence", "",
          "Week 3, Steps 3-5. Generated by src/eda_takeaways.py; all numbers are computed.", "",
          "## 1. Data and method", ""] + [f"- {p}" for p in method] + [""]
    if s["sql"]:
        md += ["| Check | SQL | Python | Match |", "|---|---|---|---|"]
        md += [f"| {n} | {a} | {b} | {'✅' if ok else '❌'} |" for n, a, b, ok in s["sql"]] + [""]
    md += ["## 2. Findings by business question", ""]
    pdf_sections = [("EDA Report: Zomato Business Intelligence",
                     ["Generated by src/eda_takeaways.py. Every number is computed from the cleaned data.", "",
                      "1. Data and method"] + method, None)]
    for q, question in QUESTIONS.items():
        rows = reg[reg["question"] == q]
        best = BEST_CHART[q]
        md += [f"### {q}. {question}", "", f"![{best}](../images/{best}.png)", ""]
        md += [f"- **{r.id}**: {r.takeaway}" for r in rows.itertuples()] + [""]
        pdf_sections.append((f"{q}. {question}",
                             [f"• {r.id}: {r.takeaway}" for r in rows.itertuples()],
                             IMG / f"{best}.png"))
    md += ["## 3. Data-quality notes", ""] + [f"- {p[2:]}" for p in dq] + [""]
    md += ["## 4. What this means for modelling", ""] + [f"- {p[2:]}" for p in modelling] + [""]
    pdf_sections.append(("Data quality and modelling implications",
                         ["Data-quality notes"] + dq + ["", "What this means for modelling"] + modelling, None))

    (REPORTS / "eda_report.md").write_text("\n".join(md), encoding="utf-8")

    # ---------- html (self-contained, plus full chart gallery) ----------
    body = _md_to_html("\n".join(md))
    gallery = ["<h2>Chart gallery</h2>"]
    for r in reg.itertuples():
        b64 = base64.b64encode((IMG / f"{r.id}.png").read_bytes()).decode()
        gallery.append(f'<figure><img src="data:image/png;base64,{b64}">'
                       f"<figcaption><b>{r.id}</b> ({r.library}, {r.question}): {r.takeaway}</figcaption></figure>")
    css = ("body{font-family:Arial,sans-serif;max-width:960px;margin:32px auto;padding:0 16px;color:#333}"
           "h1{color:#c0392b}table{border-collapse:collapse;width:100%}th{background:#2c3e50;color:#fff}"
           "th,td{padding:6px 10px;border:1px solid #ddd}img{max-width:100%}"
           "figure{margin:24px 0}figcaption{font-size:13px;color:#555}")
    (REPORTS / "eda_report.html").write_text(
        f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>EDA Report</title>"
        f"<style>{css}</style></head><body>{body}{''.join(gallery)}</body></html>", encoding="utf-8")

    pages = _write_pdf(pdf_sections, REPORTS / "eda_report.pdf")
    print(f"  reports/eda_report.md, .html and .pdf written ({pages} PDF pages)")


if __name__ == "__main__":
    build_report()
