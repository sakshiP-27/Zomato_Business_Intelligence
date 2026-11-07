# Week 3 Guide: Zomato Business Intelligence & Delivery Time Prediction
### A beginner-friendly walkthrough — Exploratory Analysis & Machine Learning

---

## Before You Start

**Goal for this week:** Use the cleaned data from Week 2 to (1) answer the PRD's eight business questions with **30+ charts** (15 Matplotlib + 15 Seaborn), (2) build a **delivery time regression model**, and (3) build a **60-day customer churn classification model**. Both models get compared, tuned, evaluated honestly, saved, and exported so Power BI can use them next week.

**Why this matters:** This is where the project stops describing the past and starts predicting the future. It covers four rubric rows: **EDA (10%)**, **Visualizations (10%)**, **Machine Learning (15%)**, and a good part of **Python Code Quality** and **Business Insights**. It also produces the content for the Power BI "ML Dashboard" page in Week 4.

**The PRD's Week 3 plan, day by day:**

| Day | Focus |
|---|---|
| Day 11 | EDA: revenue, cuisine, and city-level analysis (Matplotlib/Seaborn) |
| Day 12 | EDA: delivery, cancellation, and customer behaviour; correlation heatmaps |
| Day 13 | Build and tune the delivery time regression models; compare metrics |
| Day 14 | Build and tune the churn classification models; compare metrics |
| Day 15 | Final model selection; residual and feature-importance analysis; checkpoint review |

**Six things to understand before starting (they prevent most of this week's mistakes):**

1. **EDA is about answering questions, not about making 30 charts.** Every chart should belong to one of the PRD's eight business questions and end with a one-line takeaway. A reviewer reads the takeaways, not the code.
2. **The test set is opened once.** She picks models using cross-validation on the *training* set, tunes on the training set, and only at the very end scores the held-out test set. If she changes her mind after seeing test scores, the test score is no longer honest.
3. **The delivery-time model may only use facts known when the order is placed.** No feedback ratings (those exist only after delivery), no order status, no IDs treated as numbers.
4. **For churn, features come from the past and the label comes from the future.** She must build it in time order (Step 10). This is the most important idea of the week.
5. **The KPI targets are targets, not promises.** R² ≥ 0.75 and RMSE ≤ 6 minutes (delivery), F1 ≥ 0.70 (churn). If she misses one, the right move is to investigate and report honestly, never to peek at the test set. If a score looks *too* perfect (R² of 0.99), suspect leakage.
6. **Always compare with a dumb baseline.** A model is only impressive if it beats "predict the average delivery time" or "predict that everyone churns."

**What she needs before starting:**
- Week 2 finished: `analytical_base_table.csv`, the cleaned CSVs, `build_customer_features()`, and the KPI definitions from Week 1
- `pip install scikit-learn matplotlib seaborn joblib` (scikit-learn **1.2 or newer**), optionally `xgboost` and `imbalanced-learn`
- Notebooks to create: `02_eda.ipynb`, `04_delivery_time_model.ipynb`, `05_churn_model.ipynb`; modules `src/model_delivery.py` and `src/model_churn.py`

**This week's checkpoint:** 30+ saved charts and an EDA report, two comparison tables, two saved models, residual and feature-importance analysis, and exported tables for Power BI.

---

# PART A: Exploratory Data Analysis (Days 11–12)

## Step 1: Set Up the EDA Notebook and a Chart Register

**What this means:** A tidy notebook that loads the cleaned data once, defines the data subsets, and **counts every chart** as it is saved. The register is proof that she hit "15 + 15, no duplicates."

```python
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

sns.set_theme(style="whitegrid")
rng = np.random.default_rng(42)                      # seeded: same samples every run

abt = pd.read_csv("data/cleaned/analytical_base_table.csv", parse_dates=["order_date"])

# Three subsets, each used for a different kind of question
all_orders = abt                                                   # status, payment, cancellations
delivered  = abt[abt["order_status"] == "Delivered"]               # revenue (check the real label!)
valid      = delivered[delivered["delivery_time_minutes"] > 0]     # delivery-time charts

CHARTS = []
def save_fig(file_id, library, kind, question, takeaway):
    """Save the current figure and record it in the chart register."""
    plt.tight_layout()
    plt.savefig(f"images/{file_id}.png", dpi=150, bbox_inches="tight")
    CHARTS.append({"id": file_id, "library": library, "type": kind,
                   "question": question, "takeaway": takeaway})
    plt.show()
```
At the end of the notebook: `pd.DataFrame(CHARTS).to_csv("documentation/eda_chart_register.csv", index=False)` and `pd.DataFrame(CHARTS).groupby("library").size()` should show 15 or more for each library.

**Chart-quality habits (these are graded under Visualizations):**
- Every chart has a **title, axis labels, and units** (₹, minutes, %).
- Sort bars; rotate long labels; never use 25 colours at once (show the top 8–10 categories and group the rest).
- Use the subset that matches the question (for example, don't average delivery time over cancelled orders).
- Write the takeaway as a sentence with a number: *"Dinner (7–10 PM) accounts for 38% of orders."*

✅ **Done when:** The notebook loads, the three subsets exist, and a test chart is saved to `images/` and appears in the register.

---

## Step 2: Plan the Charts Against the Eight Business Questions

**The PRD's eight questions** (Section 22.1) and how to answer each:

| # | Question | How to answer it |
|---|---|---|
| Q1 | Which restaurants and cuisines generate the most revenue, and how has it changed over time? | Revenue by city/cuisine/restaurant; monthly trend; stacked bars over time |
| Q2 | What are the peak ordering hours, and how do weekday and weekend differ? | Orders by hour (weekday vs weekend); weekday × hour heatmap |
| Q3 | How are delivery times distributed, and how do they vary by city, traffic, and weather? | Histogram/KDE; violin by city; box/bar by traffic level and weather condition |
| Q4 | What is the average basket size, and how does it differ by membership tier? | Boxplot and grouped bar by membership |
| Q5 | What share of customers are repeat vs one-time? | Customer-level order counts; one bar or pie |
| Q6 | Which delivery partners are consistently the fastest and best rated? | Top-N partners; partner rating vs average delivery time |
| Q7 | What patterns lie behind cancellations? | Cancellation rate by city, hour, payment method, weather, order value, membership |
| Q8 | How does customer lifetime value distribute across cities and cuisines? | `build_customer_features(orders, as_of=orders["order_date"].max())`, then boxplots by city/cuisine |

**Two honest notes on wording:**
- **Q7:** The data has **no cancellation-reason column**. She can find *patterns and associations* (cancellations are higher at peak hours in heavy rain), but she must not claim to have found *causes*. The PRD's phrase "leading causes" is best answered as "leading patterns."
- **Q1 and Q8:** "Cuisine" of an order comes from the restaurant. For a customer's cuisine, decide between their `preferred_cuisine` and their most-ordered cuisine, and write which one she used.

**A checklist of the required chart types (PRD Sections 22.2 and 22.3), with suggestions.** Hitting the minimums is easy if she uses this as a menu:

**Matplotlib (15 or more):**

| # | Chart | Suggested content |
|---|---|---|
| 1 | Bar | Revenue by city (Q1) |
| 2 | Bar | Top 10 cuisines by revenue or order count (Q1) |
| 3 | Line | Monthly revenue trend (Q1) |
| 4 | Line | Monthly average delivery time (Q3) |
| 5 | Line | Orders by hour, weekday vs weekend (Q2) |
| 6 | Histogram | Order value distribution (Q4) |
| 7 | Histogram | Delivery time, with a vertical line at the "late" threshold (Q3) |
| 8 | Pie | Payment method share |
| 9 | Pie | Order status share |
| 10 | Stacked bar | Revenue by cuisine within the top 6 cities (Q1) |
| 11 | Area | Cumulative revenue growth (Q1) |
| 12 | Box plot | Delivery time by vehicle type (Q6) |
| 13 | Scatter | Delivery time vs distance (or vs prep time / traffic score) (Q3) |
| 14 | Grouped bar | Average basket size by membership tier (Q4) |
| 15 | Bar | Cancellation rate by city or by hour (Q7) |

**Seaborn (15 or more):**

| # | Chart | Suggested content |
|---|---|---|
| 1 | Correlation heatmap | Numeric features (Step 4) |
| 2 | Pairplot | 4–5 key delivery/order features, on a sample |
| 3 | Countplot | Order status |
| 4 | Countplot | Payment method (maybe with `hue` = status) |
| 5 | Violin | Delivery time by city (top 8 cities) |
| 6 | Swarm or strip | Rating by cuisine, on a **sampled subset** |
| 7 | Boxplot | Basket value by membership tier (Q4) |
| 8 | Regression plot | Delivery time vs distance or prep time |
| 9 | Regression/box plot | Delivery time vs traffic score or level |
| 10 | KDE | Delivery time distribution |
| 11 | KDE | Food cost distribution |
| 12 | Heatmap | Orders by weekday × hour (Q2) |
| 13 | Barplot | Average delivery time by weather condition (Q3) |
| 14 | Boxplot | Delivery time by traffic level, in logical order (Q3) |
| 15 | Barplot | Cancellation rate by payment method or membership (Q7) |
| extra | Bar / scatter / boxplot | Repeat vs one-time customers (Q5); partner rating vs speed (Q6); CLV by city and by cuisine (Q8) |

**Things that make big charts work:**
- **Pairplot and swarm plots are slow on 20,000 rows.** Use a seeded sample: `sample = valid.sample(1500, random_state=42)`. (The PRD explicitly says "on a sampled subset" for swarm plots.)
- **Pie charts** are weak for many categories, but the PRD requires them. Keep them to 5 or fewer slices and print the percentages.
- If distance is only a proxy (Week 2 limitation), label the axis honestly ("distance from city centre, km") or use prep time and traffic score instead.

**Examples to show the style:**

```python
# Matplotlib #1: revenue by city
rev_city = delivered.groupby("restaurant_city")["final_amount"].sum().sort_values(ascending=False).head(10)
fig, ax = plt.subplots(figsize=(9, 5))
ax.bar(rev_city.index, rev_city.values / 1e5)
ax.set_title("Top 10 cities by revenue")
ax.set_xlabel("City")
ax.set_ylabel("Revenue (₹ lakh)")
ax.tick_params(axis="x", rotation=45)
save_fig("m01_revenue_by_city", "matplotlib", "bar", "Q1",
         f"{rev_city.index[0]} leads with {rev_city.iloc[0] / rev_city.sum():.0%} of top-10 revenue")
```

```python
# Seaborn #5: delivery time by city (violin)
top_cities = valid["restaurant_city"].value_counts().head(8).index
fig, ax = plt.subplots(figsize=(11, 5))
sns.violinplot(data=valid[valid["restaurant_city"].isin(top_cities)],
               x="restaurant_city", y="delivery_time_minutes", cut=0, inner="quartile", ax=ax)
ax.set_title("Delivery time by city (top 8 cities by orders)")
ax.set_xlabel("City"); ax.set_ylabel("Delivery time (minutes)")
save_fig("s05_delivery_by_city", "seaborn", "violin", "Q3", "Takeaway goes here")
```

✅ **Done when:** A chart plan exists mapping each chart to a question, and every one of the 8 questions has at least two charts planned.

---

## Step 3 (Day 11): Revenue, Cuisine, City, and Time Analysis

Build the charts for **Q1, Q2, and Q4**: revenue by city/cuisine/restaurant, monthly trends, cumulative growth, hourly and weekday patterns, basket size by membership.

**Practical tips:**
- Use **Pandas summaries before charts**: `groupby`, `pivot_table`, `pd.crosstab` (the PRD wants these used for EDA). Print the small table, then chart it.
- For the weekday × hour heatmap: `pivot = all_orders.pivot_table(index="order_dayofweek", columns="order_hour", values="order_id", aggfunc="count")` then `sns.heatmap(pivot, cmap="YlOrRd")`.
- For "how has it changed over time," compare the first and last six months, and mention seasonality only if the chart clearly shows it. With 24 months of data a year-over-year comparison is possible for the overlapping months.
- **Cross-check against SQL.** The "top restaurants" or "revenue by city" numbers should match her Week 1 queries (using the same definitions). If they don't, find out why before building more charts on top.

✅ **Done when:** Q1, Q2, and Q4 each have charts with written takeaways, and at least two numbers have been cross-checked against SQL.

---

## Step 4 (Day 12): Delivery, Cancellation, Customer Behaviour, and Correlations

Build the charts for **Q3, Q5, Q6, Q7, and Q8**, plus the correlation heatmap.

**Correlation heatmap:**
```python
num_cols = ["delivery_time_minutes", "food_cost", "delivery_fee", "final_amount", "n_items",
            "avg_prep_time", "order_hour", "traffic_score", "rainfall", "restaurant_rating"]
corr = valid[num_cols].corr()
fig, ax = plt.subplots(figsize=(9, 7))
sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm", center=0, ax=ax)
```
Read it carefully: `food_cost`, `gst`, and `final_amount` will be almost perfectly correlated with each other because one is calculated from the others. That isn't an insight. The interesting cells are the ones against `delivery_time_minutes`. Correlation measures straight-line association, **not** causation.

**Delivery analysis (Q3):** show the shape of delivery times, then how they shift with city, traffic level, and weather. Add the late-delivery percentage (using the Week 1 definition) by city. Use `np.percentile` for the median, 90th, and 95th percentile (a PRD NumPy requirement).

**Cancellation patterns (Q7):** cancellation rate by city, hour, payment method, membership, order-value band, weather, and whether a coupon was used. Look for the *largest differences*, and check the group sizes. A 40% rate from a group of 12 orders means nothing.

**Repeat vs one-time (Q5):** count orders per customer. Check how many customers have 0, 1, or 2+ orders. This also tells her something important for the churn model later: **if the average customer has only about 1–2 orders, "churn" will mostly be about one-time buyers.** Note the number down.

**Partners (Q6):** "consistently" means looking at both speed and rating, with enough deliveries. Filter out partners with very few deliveries before ranking.

**Customer lifetime value (Q8):** use the as-of function from Week 2 with the latest date, then box plots or violin plots by city and by cuisine (limit to the top groups).

✅ **Done when:** All 8 questions are answered, the register shows 15+ Matplotlib and 15+ Seaborn charts, and no two charts are identical.

---

## Step 5 (Day 12): Write the EDA Report

**What this means:** A short document `reports/eda_report.pdf` (roughly 6–10 pages) that a manager could read without opening the notebook. The PRD lists it as a deliverable.

**A simple structure:**
1. **Data and method:** two short paragraphs (12 tables, cleaned, definitions used, subsets used)
2. **Key findings:** one section per business question, each with its best chart and 2–3 sentences
3. **Data-quality notes:** what was fixed, what limitations remain (for example the distance proxy)
4. **What this means for modeling:** which factors look most important for delivery time and for churn

**How to make the PDF easily:** write it in a Word or Google Doc using the exported images from `images/`, then export as PDF. (Or run `jupyter nbconvert --to html 02_eda.ipynb`, open the HTML in a browser, and "Print to PDF.") The first option gives a cleaner report.

✅ **Done when:** `eda_report.pdf` exists with all eight questions answered and charts embedded, and `images/` contains the exported charts.

---

# PART B: Delivery Time Regression (Day 13)

## Step 6: Build the Modeling Dataset (and Decide What the Model May Use)

**What this means:** Choose the rows and the columns. This choice decides whether the model is honest.

**Rows:** delivered orders with a valid delivery time.
```python
model_df = abt[(abt["order_status"] == "Delivered")
               & (abt["delivery_time_minutes"] > 0)
               & (abt["dt_outlier_flag"] == 0)]          # use the rule you justified in Week 2
```
If her Week 2 flag also catches legitimately slow deliveries, don't drop all of them. Drop only the impossible ones.

**Columns (predictors): everything known when the order is placed:**
- **Numeric:** `traffic_score`, `rainfall`, `temperature`, `humidity`, `peak_hour`, `weekend_order`, `order_hour`, `distance_km` (or the proxy), `n_items`, `avg_prep_time`, `max_prep_time`, `basket_value`, `partner_efficiency`, `partner_rating`, `restaurant_rating`, `customer_tenure_days`, `discount_pct`
- **Categorical:** `restaurant_city`, `cuisine`, `vehicle_type`, `weather_condition`, `membership`, `payment_method`

**Do not use:**
- `customer_rating`, `delivery_rating`, `food_rating`, `average_rating`, review text, sentiment (known only after delivery)
- `order_status` (every row is "Delivered" now, so it carries nothing)
- ID columns as numbers (`restaurant_id`, `customer_id`); and don't one-hot them either, because there are ~1,200 restaurants. Use restaurant *attributes* instead (cuisine, rating, popularity).

```python
TARGET = "delivery_time_minutes"
X = model_df[NUMERIC + CATEGORICAL]
y = model_df[TARGET]
```

✅ **Done when:** The feature lists are written in `src/model_delivery.py` as `NUMERIC` and `CATEGORICAL` constants, and she can explain why each excluded column was excluded.

---

## Step 7: Split, Preprocess in a Pipeline, and Compare Four Models

**The split:** 80/20 with a fixed seed. Do this **before** any imputing, scaling, or encoding.
```python
from sklearn.model_selection import train_test_split, KFold
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
cv = KFold(n_splits=5, shuffle=True, random_state=42)
```
(Next week she may mention that a time-based split, training on the earlier months and testing on the latest, would be a stricter test of how the model performs on the future. It's a nice point for the report, but the PRD asks for a random split plus k-fold.)

**One pipeline per model, so preprocessing is learned only from training data:**
```python
# src/model_delivery.py
import numpy as np, pandas as pd, joblib
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.model_selection import cross_validate
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import LinearRegression
from sklearn.tree import DecisionTreeRegressor
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

def make_preprocessor(scale: bool) -> ColumnTransformer:
    """Median-impute numbers (scale for linear models); mode-impute and one-hot categories."""
    num_steps = [("impute", SimpleImputer(strategy="median"))]
    if scale:
        num_steps.append(("scale", StandardScaler()))
    return ColumnTransformer([
        ("num", Pipeline(num_steps), NUMERIC),
        ("cat", Pipeline([("impute", SimpleImputer(strategy="most_frequent")),
                          ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False))]),
         CATEGORICAL),
    ])

MODELS = {   # name: (model, needs_scaling)
    "Baseline (predict the mean)": (DummyRegressor(strategy="mean"), True),
    "Linear Regression":           (LinearRegression(), True),
    "Decision Tree":               (DecisionTreeRegressor(max_depth=8, random_state=42), False),
    "Random Forest":               (RandomForestRegressor(n_estimators=200, random_state=42), False),
    "Gradient Boosting":           (GradientBoostingRegressor(random_state=42), False),
}

def compare_models(X_train, y_train, cv) -> pd.DataFrame:
    """Cross-validate every model on the TRAINING data and return a comparison table."""
    rows = []
    for name, (model, scale) in MODELS.items():
        pipe = Pipeline([("prep", make_preprocessor(scale)), ("model", model)])
        try:
            res = cross_validate(pipe, X_train, y_train, cv=cv, n_jobs=-1,
                                 scoring={"mae": "neg_mean_absolute_error",
                                          "rmse": "neg_root_mean_squared_error",
                                          "r2": "r2"})
        except Exception as err:
            raise RuntimeError(f"Training failed for {name}") from err
        rows.append({"model": name,
                     "cv_mae": -res["test_mae"].mean(),
                     "cv_rmse": -res["test_rmse"].mean(),
                     "cv_rmse_std": res["test_rmse"].std(),
                     "cv_r2": res["test_r2"].mean()})
    return pd.DataFrame(rows).sort_values("cv_rmse").reset_index(drop=True)
```
**What to look at:** The baseline row shows the "no skill" level; every real model should beat it clearly. Linear Regression shows how much of the pattern is simple and straight-line; the tree-based models show whether interactions (such as rain × peak hour) matter. Use the *standard deviation* column to see how stable each model is across folds.

(XGBoost is an optional stretch model, and drops into the same dictionary: `XGBRegressor(n_estimators=300, learning_rate=0.1, max_depth=6, random_state=42)`.)

✅ **Done when:** The comparison table (CV scores for 4+ models plus the baseline) is saved to `data/cleaned/ml_model_comparison_delivery.csv`.

---

## Step 8: Tune the Two Best Models

**What this means:** The PRD asks for hyperparameter tuning on **at least the two best-performing models** using `GridSearchCV` or `RandomizedSearchCV`. `RandomizedSearchCV` samples combinations instead of trying all of them, so it's much faster on a laptop.

```python
from sklearn.model_selection import RandomizedSearchCV

pipe = Pipeline([("prep", make_preprocessor(False)), ("model", GradientBoostingRegressor(random_state=42))])
search = RandomizedSearchCV(
    pipe,
    param_distributions={
        "model__n_estimators": [200, 400, 600],
        "model__learning_rate": [0.03, 0.05, 0.1],
        "model__max_depth": [3, 4, 5],
        "model__subsample": [0.7, 0.85, 1.0],
        "model__min_samples_leaf": [1, 5, 10],
    },
    n_iter=20, cv=cv, scoring="neg_root_mean_squared_error", n_jobs=-1, random_state=42)
search.fit(X_train, y_train)
print(search.best_params_, -search.best_score_)
```
Do the same for the second-best model (for example Random Forest with `n_estimators`, `max_depth`, `min_samples_leaf`, `max_features`).

**Rules:** tune with the **training set only** (the cross-validation inside the search handles validation). Record "before tuning vs after tuning" CV RMSE for both models. If tuning barely helps, say so. That is a finding, not a failure.

✅ **Done when:** Two models are tuned, best parameters are recorded, and the before/after table is saved.

---

## Step 9: Final Evaluation, Residual Analysis, and Feature Importance (Day 15 for the polish)

**Pick the winner using the cross-validation numbers**, then evaluate it **once** on the test set.

```python
def evaluate(model, X_test, y_test):
    """Return the four required metrics and the predictions."""
    pred = model.predict(X_test)
    mse = mean_squared_error(y_test, pred)
    metrics = {"MAE": mean_absolute_error(y_test, pred), "MSE": mse,
               "RMSE": np.sqrt(mse), "R2": r2_score(y_test, pred)}
    return metrics, pred

best_model = search.best_estimator_
metrics, pred = evaluate(best_model, X_test, y_test)
```
(Using `np.sqrt` of the MSE works on every scikit-learn version.) Compare the result with the KPI targets: **R² ≥ 0.75** and **RMSE ≤ 6 minutes**. State plainly whether they were met, and interpret MAE in plain words ("on average the prediction is off by about X minutes").

**The two required plots, plus one useful extra:**
```python
resid = y_test - pred

fig, ax = plt.subplots(1, 3, figsize=(16, 4.5))
ax[0].scatter(y_test, pred, alpha=0.3, s=10)                       # predicted vs actual
lims = [min(y_test.min(), pred.min()), max(y_test.max(), pred.max())]
ax[0].plot(lims, lims, "r--"); ax[0].set(title="Predicted vs actual", xlabel="Actual (min)", ylabel="Predicted (min)")

ax[1].scatter(pred, resid, alpha=0.3, s=10)                        # residual plot
ax[1].axhline(0, color="r", linestyle="--"); ax[1].set(title="Residuals vs predicted", xlabel="Predicted (min)", ylabel="Residual (min)")

ax[2].hist(resid, bins=40); ax[2].set(title="Residual distribution", xlabel="Residual (min)")
```
**How to read them:** In the first plot, points hugging the dashed line are good. In the residual plot, a random cloud around zero is good. A curve or a funnel shape means the model is missing something (for example it's under-predicting the very slow deliveries).

**Error analysis (this is what separates a good project from an average one):** find *where* the model is wrong.
```python
errors = X_test.assign(abs_err=np.abs(resid))
print(errors.groupby("peak_hour")["abs_err"].mean())
print(errors.groupby("restaurant_city")["abs_err"].mean().sort_values(ascending=False).head(5))
```
Is the model worse at peak hour, in heavy rain, in one city? That is a business insight, and it feeds the report.

**Feature importance (User Story 1):** The PRD wants it "visualized and explained in plain language." The built-in tree importance is quick, but it favours continuous features. A more reliable check is **permutation importance**, which shuffles one column at a time and measures how much worse the predictions get. Applying it to the *whole pipeline* keeps each original feature as one bar, instead of splitting a category like `cuisine` into 20 one-hot columns.
```python
from sklearn.inspection import permutation_importance
imp = permutation_importance(best_model, X_test, y_test, n_repeats=10, random_state=42,
                             scoring="neg_root_mean_squared_error", n_jobs=-1)
importance = (pd.DataFrame({"feature": X_test.columns, "importance": imp.importances_mean})
              .sort_values("importance", ascending=False))
```
Show the top 10 as a horizontal bar chart, and write 3–4 plain sentences, for example: *"Preparation time and traffic score matter most. Heavy rain adds about X minutes during peak hours, so the operations head should add partners in those windows."* Phrase it as what the model **associates** with longer delivery, not as proven causes.

**If the KPIs are missed:** (1) re-check for leakage or noisy features, (2) look at the biggest residuals, (3) try an extra feature (for example the traffic match by hour, or prep time), (4) tune a little more, (5) if it still misses, report the honest number with the error analysis. Never tune on the test set.

✅ **Done when:** Final test metrics (MAE, MSE, RMSE, R²) are in a table next to the KPI targets, all three plots exist, error analysis is written, and the top-10 importance chart has a plain-language explanation.

---

# PART C: Customer Churn Classification (Day 14)

## Step 10: Build the Churn Dataset in Time Order (the Most Important Step)

**What this means:** The PRD defines the target as "whether a customer is likely to be inactive (no orders) in the next 60 days." To predict the *future*, features must come from *before* a cut-off date, and the label from the 60 days *after* it.

```
        features use orders up to here           label looks at these 60 days
 ──────────────────────────────────────────┬─────────────────────────────────────┐
 first order                           cutoff T                       latest order date
```

```python
def build_churn_dataset(orders: pd.DataFrame, cutoff: pd.Timestamp, horizon_days: int = 60) -> pd.DataFrame:
    """One row per customer: features from orders <= cutoff, label from the next `horizon_days`."""
    feats = build_customer_features(orders, as_of=cutoff)              # Week 2 function (past only)
    window_end = cutoff + pd.Timedelta(days=horizon_days)
    future = orders[(orders["order_date"] > cutoff) & (orders["order_date"] <= window_end)]
    feats["churned"] = (~feats["customer_id"].isin(set(future["customer_id"]))).astype(int)
    return feats

cutoff = orders["order_date"].max() - pd.Timedelta(days=60)
churn_df = build_churn_dataset(orders, cutoff)
```
**Why not simply define "churned" as "no order for 60 days" from the same data the features use?** Because then the label is built from the same numbers as the "days since last order" feature, and the model just rediscovers its own definition (circular, and useless in real life).

**Decisions she has to make and write down:**
- **Who is in the dataset:** customers with at least one order on or before the cutoff (the function does this automatically). Customers who never ordered, or who registered after the cutoff, have no history to learn from.
- **What counts as activity in the label:** the PRD says "no orders", so count any placed order. Note that Week 2's features excluded cancelled orders from spend. Write down that the label and the features use slightly different rules, and why.
- **Do not use `customers.total_orders`.** It's a snapshot over the whole period (including the future window).

**Add more features that capture behaviour just before the cutoff** (these are usually the strongest churn signals):
```python
def add_recent_activity(feats, orders, cutoff):
    """Order counts in the last 30/60/90 days before the cutoff."""
    for days in (30, 60, 90):
        recent = orders[(orders["order_date"] > cutoff - pd.Timedelta(days=days))
                        & (orders["order_date"] <= cutoff)]
        counts = recent.groupby("customer_id").size()
        feats[f"orders_last_{days}d"] = feats["customer_id"].map(counts).fillna(0)
    return feats
```
And **experience features**, because customers who had a bad experience tend to leave. Precompute 0/1 columns on `orders` (`is_cancelled`, `has_coupon`, `is_late`, using NaN where there's no delivery time), then average them per customer using only orders on or before the cutoff:
```python
hist = orders[orders["order_date"] <= cutoff]
exp = hist.groupby("customer_id").agg(
    cancel_rate=("is_cancelled", "mean"),
    late_rate=("is_late", "mean"),
    avg_delivery_time=("delivery_time_minutes", "mean"),
    coupon_rate=("has_coupon", "mean"),
    avg_rating_given=("average_rating", "mean"),       # feedback on orders before the cutoff: allowed here
    n_restaurants=("restaurant_id", "nunique"),
).reset_index()
churn_df = churn_df.merge(exp, on="customer_id", how="left", validate="1:1")
```
(Here, using past feedback is fine, because every order and rating happened *before* the cutoff. Add customer attributes known at the cutoff too: `membership`, `city`, `preferred_cuisine`, `age`, and tenure in days as of the cutoff.)

**First look at the numbers, because they shape everything else:**
- What share of customers churned? (`churn_df["churned"].mean()`)
- How many orders does the typical customer have before the cutoff?

If the churn rate is very high (for example 80%), then "predict that everyone churns" already scores a high F1. The PRD target of F1 ≥ 0.70 would then be easy and meaningless. She must compare against that baseline and lean on ROC-AUC and PR-AUC to show real skill.

✅ **Done when:** `churn_df` has one row per customer, the cutoff and label rules are written down, and the churn rate and baseline are recorded.

---

## Step 11: Split, Handle Class Imbalance, and Compare Four Classifiers

**Split by customer, stratified** (so the churn share is the same in both parts):
```python
from sklearn.model_selection import train_test_split, StratifiedKFold
X = churn_df[CHURN_NUMERIC + CHURN_CATEGORICAL]
y = churn_df["churned"]
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
```

**Class imbalance (the PRD requires an explicit, documented choice).** The simplest and most reliable way is **class weights**, which make mistakes on the rarer class cost more: `class_weight="balanced"`. She should compare at least two options and record the result:
- (a) no handling
- (b) `class_weight="balanced"` (recommended default)
- (c) *(optional)* resampling with SMOTE. If she tries it, SMOTE on one-hot columns creates meaningless fractional values, so the right variant is `SMOTENC`, and it must be done **inside** the cross-validation pipeline (imbalanced-learn's `Pipeline`), never on the full data before splitting.

**Four classifiers and a baseline:**
```python
# src/model_churn.py
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.dummy import DummyClassifier

CLASSIFIERS = {   # name: (model, needs_scaling)
    "Baseline (predict majority)": (DummyClassifier(strategy="most_frequent"), True),
    "Logistic Regression": (LogisticRegression(max_iter=1000, class_weight="balanced"), True),
    "Decision Tree":       (DecisionTreeClassifier(max_depth=6, class_weight="balanced", random_state=42), False),
    "Random Forest":       (RandomForestClassifier(n_estimators=300, class_weight="balanced", random_state=42), False),
    "Gradient Boosting":   (HistGradientBoostingClassifier(class_weight="balanced", random_state=42), False),
}
```
(`HistGradientBoostingClassifier` is scikit-learn's fast gradient boosting. `GradientBoostingClassifier` also works, but it has no `class_weight` option and needs `sample_weight`, which is fiddlier in a pipeline.)

Reuse the same pattern from Step 7: preprocessing in a `Pipeline`, and cross-validate with scoring such as `{"f1": "f1", "precision": "precision", "recall": "recall", "roc_auc": "roc_auc", "pr_auc": "average_precision"}`. Wrap the training in `try/except`, with a clear error message.

**Which metric to lead with:** Not accuracy. Lead with **F1 (the KPI), ROC-AUC, and PR-AUC**, and show precision and recall separately. Accuracy goes in the table, but the discussion should say why it can mislead when classes are unbalanced.

✅ **Done when:** The comparison table (CV scores for 4 models plus the baseline, and the imbalance experiment) is saved to `data/cleaned/ml_model_comparison_churn.csv`, with a sentence on the imbalance choice.

---

## Step 12: Tune, Pick a Threshold, and Evaluate on the Test Set Once

**Tune** the best two models with `RandomizedSearchCV` (scoring `"f1"` or `"average_precision"`), exactly as in Step 8.

**Pick the decision threshold without touching the test set.** The default 0.5 is arbitrary. For a retention campaign, the right cut-off depends on the trade-off: a lower threshold catches more future churners (higher recall) but sends offers to more people who would have stayed (lower precision). Use *out-of-fold* predictions from the training set:
```python
from sklearn.model_selection import cross_val_predict
from sklearn.metrics import precision_recall_curve

oof_proba = cross_val_predict(best_model, X_train, y_train, cv=cv, method="predict_proba")[:, 1]
prec, rec, thr = precision_recall_curve(y_train, oof_proba)
f1 = 2 * prec * rec / (prec + rec + 1e-12)
best_threshold = thr[np.argmax(f1[:-1])]          # the F1-maximising cut-off
```
Write a sentence on whether the marketing team might prefer a different one (for example, a higher-recall threshold if offers are cheap).

**Evaluate once on the test set:**
```python
from sklearn.metrics import (accuracy_score, precision_score, recall_score, f1_score,
                             roc_auc_score, average_precision_score, confusion_matrix,
                             ConfusionMatrixDisplay, RocCurveDisplay)

proba = best_model.predict_proba(X_test)[:, 1]
pred = (proba >= best_threshold).astype(int)
test_metrics = {"accuracy": accuracy_score(y_test, pred), "precision": precision_score(y_test, pred),
                "recall": recall_score(y_test, pred), "f1": f1_score(y_test, pred),
                "roc_auc": roc_auc_score(y_test, proba), "pr_auc": average_precision_score(y_test, proba)}
baseline_f1 = f1_score(y_test, np.ones_like(y_test))        # "everyone churns"
ConfusionMatrixDisplay.from_predictions(y_test, pred)
RocCurveDisplay.from_predictions(y_test, proba)
```
The PRD's User Story 3 wants the confusion matrix and ROC curve, so include both. **Compare F1 with the 0.70 target *and* with `baseline_f1`**, and say what the result means in plain words ("of every 100 customers we flag, about X really would have left").

**Sanity check:** An ROC-AUC above about 0.95 is a warning sign. Look for a feature that secretly contains the future (for example `total_orders`, or something computed past the cutoff).

✅ **Done when:** Test metrics, a confusion matrix, an ROC curve, the chosen threshold, and a comparison against the KPI and the baseline are all in the notebook.

---

## Step 13: Top 10 Churn Drivers and Risk Segments

**Top 10 features (PRD requirement):** Use permutation importance on the whole pipeline (as in Step 9, with `scoring="roc_auc"`), so each bar is one real feature. For direction ("does more of this raise or lower risk?"), look at the sign of the Logistic Regression coefficients, or compare average feature values between churners and non-churners. Explain in plain language, for example: *"Customers who ordered nothing in the last 30 days, and whose last two deliveries were late, are the most likely to leave."* Recommend an action to match (for example, a win-back offer after 30 days of silence).

**Risk segments for the dashboard:** turn the probability into three bands that a marketer can act on.
```python
scores = pd.DataFrame({"customer_id": X_test.index.map(churn_df["customer_id"]),   # keep customer_id with the rows
                       "churn_probability": proba, "predicted_label": pred, "actual_label": y_test.values})
scores["risk_segment"] = pd.cut(scores["churn_probability"], [0, 0.4, 0.7, 1.0],
                                labels=["Low", "Medium", "High"], include_lowest=True)
```
Choose the band edges deliberately (for example, tie "High" to her chosen threshold) and write down what each band means in business terms.

**Optional extra (clearly labelled):** score every customer **as of the latest date** with the same feature code to produce a "currently at risk" list (`churn_scores_current.csv`). There's no future data to validate it, so label it as forward-looking.

✅ **Done when:** A top-10 driver chart with a plain-language explanation exists, and every test-set customer has a probability and a risk segment.

---

# PART D: Wrap-Up (Day 15)

## Step 14: Save the Models, Metadata, and Power BI Exports

**Models (the PRD folder layout):**
```python
import joblib, json, sklearn
joblib.dump(best_delivery_model, "models/delivery_time_best_model.pkl")
joblib.dump(best_churn_model,    "models/churn_best_model.pkl")
json.dump({"churn_threshold": float(best_threshold), "risk_bands": [0.4, 0.7],
           "cutoff": str(cutoff.date()), "horizon_days": 60,
           "sklearn_version": sklearn.__version__, "trained_on": str(pd.Timestamp.today().date())},
          open("models/model_metadata.json", "w"), indent=2)
```
Save the **whole pipeline** (preprocessing + model), so predicting on raw columns just works. Saved models can break across scikit-learn versions, so record the version. **Test the reload in a fresh Python session:** load each `.pkl`, predict on 5 rows, and confirm the output makes sense.

**Exports that Week 4's Power BI "ML Dashboard" page will read** (keep the file and column names stable, as in Week 2):

| File (`data/cleaned/`) | Contents |
|---|---|
| `ml_delivery_predictions.csv` | `order_id`, actual, predicted, residual, plus city, peak_hour, weather for slicing (test set) |
| `ml_delivery_feature_importance.csv` | feature, importance |
| `ml_model_comparison_delivery.csv` | the comparison table |
| `ml_churn_scores_test.csv` | `customer_id`, churn_probability, predicted_label, actual_label, risk_segment, city, membership |
| `ml_churn_feature_importance.csv` | top drivers, with direction if known |
| `ml_model_comparison_churn.csv` | the comparison table |

✅ **Done when:** Both `.pkl` files reload and predict in a fresh session, and all six export files exist.

---

## Step 15: Tidy the Code and Run the Checkpoint Review

**Code quality (PRD 21.1):**
- [ ] Logic lives in `src/model_delivery.py` and `src/model_churn.py` (functions: `make_preprocessor`, `compare_models`, `tune`, `evaluate`, `build_churn_dataset`); notebooks 04 and 05 call them
- [ ] Docstrings and clear names; `try/except` around model training and file reading
- [ ] Every random step uses a seed (`random_state=42` or `np.random.default_rng(42)`)
- [ ] `requirements.txt` updated (scikit-learn, matplotlib, seaborn, joblib, and optional extras)
- [ ] Notebooks run top to bottom after **Restart & Run All**
- [ ] Commit often with clear messages

**Checkpoint self-review:**
- Does every one of the 8 business questions have charts plus written takeaways, and does the register show 15+ and 15+?
- Did I use the test set only once for each model?
- Are post-delivery fields (feedback ratings) excluded from the delivery-time model?
- Are churn features built only from data on or before the cutoff?
- Did I compare both models against a simple baseline?
- Did I state honestly whether R² ≥ 0.75, RMSE ≤ 6 min, and F1 ≥ 0.70 were met?
- Are there plain-language explanations of the feature importances for both models?

✅ **Done when:** All seven answers are "yes," or the gaps are written down with a plan.

---

## Week 3 Checklist: Quick Reference

**EDA**
- [ ] EDA notebook set up with a chart register; subsets defined (all / delivered / valid)
- [ ] 15+ Matplotlib charts covering bar, line, scatter, histogram, pie, stacked bar, area, box
- [ ] 15+ Seaborn charts covering heatmap, pairplot, countplot, violin, swarm/strip, boxplot, regplot, KDE
- [ ] All 8 business questions answered, each chart with a title, labels, units, and a takeaway
- [ ] Pairplot and swarm plots drawn on a seeded sample; a few numbers cross-checked against SQL
- [ ] `eda_report.pdf` written; charts exported to `images/`

**Delivery time regression**
- [ ] Modeling dataset limited to delivered orders with valid times; only order-time features used
- [ ] 80/20 split before preprocessing; pipelines with imputing, scaling, one-hot encoding
- [ ] Baseline + 4 models compared with 5-fold CV; two best tuned with RandomizedSearchCV
- [ ] Test-set MAE, MSE, RMSE, R² reported once; compared with R² ≥ 0.75 and RMSE ≤ 6 min
- [ ] Predicted-vs-actual and residual plots; error analysis by segment
- [ ] Permutation importance explained in plain language

**Churn classification**
- [ ] Cutoff date chosen; features from before it, 60-day label from after it; rules written down
- [ ] Churn rate and the "everyone churns" baseline recorded
- [ ] Stratified split by customer; imbalance handled and documented (class weights compared with alternatives)
- [ ] 4 classifiers compared with CV; two best tuned
- [ ] Threshold chosen from out-of-fold predictions (not the test set)
- [ ] Test metrics, confusion matrix, ROC curve; F1 compared with 0.70 and with the baseline
- [ ] Top 10 drivers explained; risk segments defined

**Wrap-up**
- [ ] Two models saved as `.pkl`, metadata saved, reload tested in a fresh session
- [ ] Six export CSVs for Power BI saved with stable names
- [ ] Code modular, documented, seeded, committed; checkpoint self-review done

---

## A Few Words of Encouragement

This is the week that rewards patience. The charts feel slow at first, and the churn dataset takes some thought, but the logic is always the same: **make the question clear, use the right data for it, and be honest about what the numbers show.** A model that misses a KPI target but is explained with careful error analysis will score better than a model that hits the number because of a hidden leak.

If time gets tight, protect these in order: (1) the delivery model with an honest test evaluation, (2) the churn dataset built in the right time order, (3) the 30 charts and the EDA report, (4) the exports for Power BI. Optional extras such as XGBoost or the "currently at risk" list can wait.

If something looks too good to be true, it usually is. Pause and ask: *"Would I really know this at the moment of prediction?"*

Good luck with Week 3! 🎯
