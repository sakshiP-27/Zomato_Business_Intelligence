# Week 4 Guide: Zomato Business Intelligence & Delivery Time Prediction
### A beginner-friendly walkthrough — Power BI, Reporting & Final Delivery

---

## Before You Start

**Goal for this week:** Turn everything from Weeks 1–3 into something a business stakeholder can actually use and understand: a **6-page Power BI dashboard**, a **business insights report**, a **10–15 slide presentation**, and a clean **GitHub repository with a complete README**. Then submit.

**Why this matters:** The first three weeks produced a database, a cleaned dataset, charts, and two models. Nobody outside the project can use any of that until it's presented clearly. This week covers **Power BI Dashboard (10%)**, **Business Insights & Recommendations (5%)**, and **Documentation & GitHub Hygiene (10%)**, and it is the final impression of the whole project.

**A reassuring note:** Almost no new analysis is needed. Every number on the dashboard already exists in her SQL queries, her Python pipeline, or her model exports. The job is to **present them consistently and clearly**. If a Power BI number differs from a SQL or Python number, that is a bug to fix, not a new finding.

**The PRD's Week 4 plan, day by day:**

| Day | Focus |
|---|---|
| Day 16 | Power BI data model: import the cleaned tables, define relationships and DAX measures |
| Day 17 | Executive Dashboard and Customer Analytics pages |
| Day 18 | Restaurant Analytics, Delivery Analytics, and Sales Dashboard pages |
| Day 19 | ML Dashboard page; write the business insights report |
| Day 20 | Finalize README, GitHub repository, and presentation deck; submit |

**Six things to know first:**

1. **Power BI Desktop only runs on Windows.** If she works on a Mac or Linux laptop, she needs a Windows computer, a college lab PC, or a Windows virtual machine. **Sort this out before Day 16**, not on the day. (The PRD mandates Power BI Desktop; no other BI tool is allowed as a substitute.)
2. **Logic lives in Python and SQL, presentation lives in Power BI.** Things like `is_late`, the composite restaurant score, and the customer segments should be computed once in Python or SQL and exported. If she re-creates the "late delivery" rule separately in DAX, the dashboard and the SQL results will drift apart, which is exactly the inconsistency this project exists to remove. DAX is for *aggregations* (sums, averages, rates).
3. **The file must refresh from the cleaned CSVs without manual re-mapping (NFR-04).** That means a single folder parameter and stable file and column names (Step 2).
4. **Every visual needs a title, axis labels, and a legend where relevant (NFR-06)**, with consistent colours and KPI card formatting on all six pages.
5. **There are two kinds of "city" in this data**: the customer's city and the restaurant's city. The dashboard uses the restaurant's city (the Week 1 decision) for order-level pages. Customer pages use the customer's city. Label slicers clearly (Step 3).
6. **Validate before polishing.** A beautiful dashboard with a wrong revenue number is worse than a plain one with the right number. She reconciles the KPI cards against SQL and Python in Step 12.

**What she needs before starting:**
- Weeks 1–3 finished, with everything committed to Git
- **Power BI Desktop (free, latest version)** on a Windows machine
- PowerPoint or Google Slides for the deck, and Word or Google Docs for the report

**This week's checkpoint (the final submission):** `powerbi/zomato_dashboard.pbix` with 6 pages, `reports/business_insights_report.pdf`, a 10–15 slide deck, a complete `README.md`, and a GitHub repository that matches the PRD's folder structure.

---

## Step 1 (before Day 16): Pre-Flight Check and Last Exports

**What this means:** Confirm everything Power BI needs exists, so Day 16 isn't spent hunting for files.

**1. Confirm Power BI access** (see point 1 above). Open Power BI Desktop once and check it launches.

**2. Check the inputs in `data/cleaned/`:**

| File | Used for |
|---|---|
| `analytical_base_table.csv` | the central order-level fact table (`fact_orders`) |
| `customers.csv`, `restaurants.csv`, `delivery_partners.csv`, `promotions.csv`, `cities.csv`, `menu.csv` | dimension tables |
| `order_items.csv`, `payments.csv`, `customer_feedback.csv` | extra fact tables |
| `ml_delivery_predictions.csv`, `ml_delivery_feature_importance.csv`, `ml_churn_scores_test.csv`, `ml_churn_feature_importance.csv` | the ML page |

**3. Check that the base table has the columns the dashboard needs.** If any are missing, add them **in the Python pipeline and re-run it** (don't patch them in Power BI): `order_id`, `customer_id`, `restaurant_id`, `delivery_partner_id`, `order_date` (a date with no time part), `order_hour`, `order_status`, `final_amount`, `food_cost`, `discount`, `coupon_code`, `payment_method`, `delivery_time_minutes`, **`is_late`** (1 = late, 0 = not late, and **blank** where the delivery time is missing or invalid), `peak_hour`, `restaurant_city`, `traffic_level`, `traffic_score`, `rainfall`, and a rain category (None/Light/Moderate/Heavy).

**4. Create two small extra files** that the PRD pages need:

*a) The restaurant performance score* (User Story 2): export her Week 1 SQL view so Power BI reads the same numbers.
```python
import pandas as pd
from sqlalchemy import create_engine
engine = create_engine("postgresql+psycopg2://postgres:yourpassword@localhost:5432/zomato")
pd.read_sql("SELECT * FROM v_restaurant_performance", engine) \
  .to_csv("data/cleaned/restaurant_performance.csv", index=False)
```
Put this in a small script such as `src/export_sql_views.py`, so it can be re-run.

*b) A customer table with current metrics and segments* (the Customer Analytics page needs CLV, recency, and New / Repeat / At-risk):
```python
import numpy as np
as_of = orders["order_date"].max()
feats = build_customer_features(orders, as_of=as_of)          # Week 2 function

feats["customer_segment"] = np.select(
    [(as_of - feats["first_order"]).dt.days <= 60,            # New: first order in the last 60 days of data
     feats["days_since_last_order"] > 30],                    # At-risk: not new, quiet for over 30 days
    ["New", "At-risk"], default="Repeat")                     # Repeat: everyone else who ordered recently

customers_enriched = customers.merge(feats, on="customer_id", how="left", validate="1:1")
customers_enriched["customer_segment"] = customers_enriched["customer_segment"].fillna("Never ordered")
customers_enriched.to_csv("data/cleaned/dim_customers_enriched.csv", index=False)
```
The thresholds (60 and 30 days) are **her choice**. Write them in `kpi_definitions.md`, and make them consistent with her churn work.

*c) A tiny metrics file for the numbers that DAX can't compute easily* (ROC-AUC). From the model notebooks:
```python
pd.DataFrame([
    {"model": "delivery", "metric": "r2", "value": delivery_metrics["R2"]},
    {"model": "delivery", "metric": "rmse", "value": delivery_metrics["RMSE"]},
    {"model": "churn", "metric": "roc_auc", "value": test_metrics["roc_auc"]},
    {"model": "churn", "metric": "f1", "value": test_metrics["f1"]},
]).to_csv("data/cleaned/ml_test_metrics.csv", index=False)
```

✅ **Done when:** Power BI Desktop opens on her machine, and every file in the table above plus the three new files exists in `data/cleaned/`.

---

## Step 2 (Day 16): Import the Data with a Folder Parameter

**What this means:** Load the CSVs into Power BI in a way that survives moving the project to another computer. That is the "refresh without manual re-mapping" requirement.

**How to do it:**
1. **Home → Transform data** (opens Power Query).
2. **Create a parameter:** Manage Parameters → New Parameter. Name: `DataFolder`, Type: Text, Current value: the full path to `data/cleaned/` **ending with a backslash** (for example `C:\Projects\Zomato\data\cleaned\`).
3. **Load each CSV through the parameter**, not through a hard-coded path. In the Advanced Editor, each query looks like this:
```
let
    Source   = Csv.Document(File.Contents(DataFolder & "analytical_base_table.csv"),
                            [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed    = Table.TransformColumnTypes(Promoted,
                  {{"order_id", type text}, {"customer_id", type text}, {"order_date", type date},
                   {"final_amount", type number}, {"delivery_time_minutes", type number},
                   {"is_late", Int64.Type}}, "en-US")
in
    Typed
```
The `"en-US"` at the end makes dates and decimals parse the same way on every computer, regardless of regional settings.
4. **Name the queries as a model:** `fact_orders` (from the base table), `fact_order_items`, `fact_payments`, `fact_feedback`, `dim_customers` (from `dim_customers_enriched.csv`), `dim_restaurants`, `dim_delivery_partners`, `dim_promotions`, `dim_menu`, `dim_city`, `restaurant_performance`, and the four `ml_*` tables plus `ml_test_metrics`.

**Power Query hygiene (small habits that matter):**
- **Set every column's data type explicitly.** IDs are *Text*, dates are *Date* (not Date/Time), money and minutes are *Decimal*, flags are *Whole number*. A date with a time part will break the date relationship later.
- **Remove columns the dashboard doesn't use** (long text such as `review`, internal helper columns). Smaller models are faster and easier to understand.
- Keep the **same column names** as in the CSVs. Don't rename them in Power Query, or the next refresh may break.

**Test the refresh now:** change `DataFolder` to a different valid path (a copy of the folder), click **Refresh**, and confirm nothing breaks. Then set it back.

✅ **Done when:** All tables load with correct data types, no query has a hard-coded path, and a refresh works.

---

## Step 3 (Day 16): Build the Star-Schema Model

**What this means:** A star schema has one central **fact** table (the events, here: orders) surrounded by **dimension** tables (descriptions: customers, restaurants, dates). Filters flow from the dimensions to the fact table. It's what the PRD means by "a proper star-schema-style data model."

**Open Model view and create these relationships** (each is *one-to-many*, with the "one" on the dimension side, filter direction *single*):

| From (one side) | To (many side) |
|---|---|
| `dim_date[date]` | `fact_orders[order_date]` *(active)* |
| `dim_customers[customer_id]` | `fact_orders[customer_id]` |
| `dim_restaurants[restaurant_id]` | `fact_orders[restaurant_id]` |
| `dim_delivery_partners[delivery_partner_id]` | `fact_orders[delivery_partner_id]` |
| `dim_promotions[coupon_code]` | `fact_orders[coupon_code]` |
| `dim_city[city]` | `fact_orders[restaurant_city]` |
| `fact_orders[order_id]` | `fact_order_items[order_id]`, `fact_payments[order_id]`, `fact_feedback[order_id]` |
| `dim_menu[food_item_id]` | `fact_order_items[food_item_id]` |
| `dim_restaurants[restaurant_id]` | `restaurant_performance[restaurant_id]` (one-to-one) |
| `fact_orders[order_id]` | `ml_delivery_predictions[order_id]` (one-to-one) |
| `dim_customers[customer_id]` | `ml_churn_scores_test[customer_id]` |
| `dim_date[date]` | `dim_customers[registration_date]` **(inactive, dashed line)** |

**The date table.** Don't use the CSV's dates as a calendar; create a proper one (Modeling → New table):
```
dim_date =
VAR MinD = MIN ( MIN ( fact_orders[order_date] ), MIN ( dim_customers[registration_date] ) )
VAR MaxD = MAX ( fact_orders[order_date] )
RETURN
ADDCOLUMNS (
    CALENDAR ( MinD, MaxD ),
    "Year", YEAR ( [Date] ),
    "Month Number", MONTH ( [Date] ),
    "Month", FORMAT ( [Date], "MMM" ),
    "Month Start", DATE ( YEAR ( [Date] ), MONTH ( [Date] ), 1 ),
    "Weekday", WEEKDAY ( [Date], 2 ),
    "Is Weekend", IF ( WEEKDAY ( [Date], 2 ) >= 6, 1, 0 )
)
```
Then **Table tools → Mark as date table**, and set `Month` to *Sort by* `Month Number` so months don't sort alphabetically. (Rename the `Date` column to `date` if you want the names in the table above to match.)

**The inactive relationship** (registration date to dim_date) is for "customer growth over time." A table can have only one *active* relationship to the same date table, so the second is kept inactive and switched on inside a measure with `USERELATIONSHIP` (Step 4). It's a classic example of a "role-playing" dimension.

**Two rules that avoid errors:**
- **No ambiguous paths.** If `dim_city` were related to `dim_customers` *and* to `fact_orders`, there would be two routes from cities to orders, and Power BI would reject one. So `dim_city` connects **only** to `fact_orders[restaurant_city]`. A customer's city stays as a plain column in `dim_customers`.
- **Keep filters single-direction** unless there is a clear need. Bi-directional filters make results hard to predict.

**Two kinds of city, handled honestly:** Pages built on orders (Executive, Restaurant, Delivery, Sales, delivery part of ML) use a slicer on `dim_city[city]` (**restaurant city**). Customer pages (Customer Analytics, churn part of ML) use a slicer on `dim_customers[city]` (**customer city**). Name the slicers "Restaurant city" and "Customer city" so nobody is confused.

✅ **Done when:** Model view shows a clean star with no warning icons, the date table is marked, and a quick test (a table visual with `dim_city[city]` and `COUNT(order_id)`) gives sensible numbers.

---

## Step 4 (Day 16): Write the DAX Measures

**What this means:** A **measure** is a calculation Power BI re-evaluates for whatever filters are active (a city, a month, a slicer). The PRD requires "DAX measures for all KPIs."

**Tips before starting:**
- Create an empty table called `_Measures` (Home → Enter data, name it, load) and keep **all measures there**, organized in display folders. Everything is then easy to find.
- Use **`DIVIDE(a, b)`** instead of `a / b`, because it handles divide-by-zero.
- **The table and column names below are examples.** She must match her own. Test each measure in a simple table visual before using it.

**Core KPIs (use the Week 1 definitions):**
```
Total Revenue      = CALCULATE ( SUM ( fact_orders[final_amount] ), fact_orders[order_status] = "Delivered" )
Total Orders       = DISTINCTCOUNT ( fact_orders[order_id] )
Delivered Orders   = CALCULATE ( [Total Orders], fact_orders[order_status] = "Delivered" )
Cancelled Orders   = CALCULATE ( [Total Orders], fact_orders[order_status] = "Cancelled" )
Cancellation Rate  = DIVIDE ( [Cancelled Orders], [Total Orders] )
Avg Order Value    = DIVIDE ( [Total Revenue], [Delivered Orders] )

Avg Delivery Time  =
CALCULATE ( AVERAGE ( fact_orders[delivery_time_minutes] ),
            fact_orders[order_status] = "Delivered",
            fact_orders[delivery_time_minutes] > 0 )

Late Delivery %    = DIVIDE ( SUM ( fact_orders[is_late] ), COUNT ( fact_orders[is_late] ) )
Avg Rating         = AVERAGE ( fact_feedback[customer_rating] )
```
`Late Delivery %` works because `SUM` and `COUNT` both **ignore blanks**. That is why `is_late` must be blank (not 0) where there is no valid delivery time.

**Active customers (the Week 1 definition: ordered in the 60 days before the end of the selected period):**
```
Active Customers (60d) =
VAR EndDate = MAX ( dim_date[date] )
RETURN
CALCULATE ( DISTINCTCOUNT ( fact_orders[customer_id] ),
            DATESINPERIOD ( dim_date[date], EndDate, -60, DAY ) )
```

**Retention (the trickiest measure: test it by hand on one month):**
```
Customers Prev Month =
CALCULATE ( DISTINCTCOUNT ( fact_orders[customer_id] ), DATEADD ( dim_date[date], -1, MONTH ) )

Retained Customers =
VAR Current  = VALUES ( fact_orders[customer_id] )
VAR Previous = CALCULATETABLE ( VALUES ( fact_orders[customer_id] ), DATEADD ( dim_date[date], -1, MONTH ) )
RETURN COUNTROWS ( INTERSECT ( Current, Previous ) )

Retention Rate = DIVIDE ( [Retained Customers], [Customers Prev Month] )

Avg Monthly Retention = AVERAGEX ( VALUES ( dim_date[Month Start] ), [Retention Rate] )
```
Use `Retention Rate` in monthly charts and `Avg Monthly Retention` in a KPI card (it's robust when the filter covers many months). **Warning:** if the average customer has only 1–2 orders (she saw this in Week 3), month-to-month retention will look low. That's a finding, not a bug. Define it clearly in a card tooltip, and consider also showing a simpler "Repeat customer %" (customers with 2+ orders ÷ customers with at least 1).

**Customer growth (switches on the inactive relationship):**
```
New Customers =
CALCULATE ( COUNTROWS ( dim_customers ), USERELATIONSHIP ( dim_date[date], dim_customers[registration_date] ) )

Cumulative Customers =
CALCULATE ( [New Customers], FILTER ( ALL ( dim_date[date] ), dim_date[date] <= MAX ( dim_date[date] ) ) )
```

**Sales and coupons:**
```
Coupon Orders            = CALCULATE ( [Total Orders], NOT ( ISBLANK ( fact_orders[coupon_code] ) ) )
Coupon Usage %           = DIVIDE ( [Coupon Orders], [Total Orders] )
Total Discount           = SUM ( fact_orders[discount] )
Discount % of Food Value = DIVIDE ( [Total Discount], SUM ( fact_orders[food_cost] ) )
AOV With Coupon          = CALCULATE ( [Avg Order Value], NOT ( ISBLANK ( fact_orders[coupon_code] ) ) )
AOV Without Coupon       = CALCULATE ( [Avg Order Value], ISBLANK ( fact_orders[coupon_code] ) )
```

**Delivery page extras:**
```
P90 Delivery Time =
PERCENTILEX.INC ( FILTER ( fact_orders, fact_orders[delivery_time_minutes] > 0 ),
                  fact_orders[delivery_time_minutes], 0.9 )
```

**ML page (computed live from the exported predictions, so they respond to slicers):**
```
MAE  = AVERAGEX ( ml_delivery_predictions, ABS ( ml_delivery_predictions[actual] - ml_delivery_predictions[predicted] ) )
RMSE = SQRT ( AVERAGEX ( ml_delivery_predictions, ( ml_delivery_predictions[actual] - ml_delivery_predictions[predicted] ) ^ 2 ) )

R2 =
VAR MeanActual = AVERAGE ( ml_delivery_predictions[actual] )
VAR SSE = SUMX ( ml_delivery_predictions, ( ml_delivery_predictions[actual] - ml_delivery_predictions[predicted] ) ^ 2 )
VAR SST = SUMX ( ml_delivery_predictions, ( ml_delivery_predictions[actual] - MeanActual ) ^ 2 )
RETURN 1 - DIVIDE ( SSE, SST )

TP = CALCULATE ( COUNTROWS ( ml_churn_scores_test ), ml_churn_scores_test[actual_label] = 1, ml_churn_scores_test[predicted_label] = 1 )
FP = CALCULATE ( COUNTROWS ( ml_churn_scores_test ), ml_churn_scores_test[actual_label] = 0, ml_churn_scores_test[predicted_label] = 1 )
FN = CALCULATE ( COUNTROWS ( ml_churn_scores_test ), ml_churn_scores_test[actual_label] = 1, ml_churn_scores_test[predicted_label] = 0 )
Precision = DIVIDE ( [TP], [TP] + [FP] )
Recall    = DIVIDE ( [TP], [TP] + [FN] )
F1 Score  = DIVIDE ( 2 * [Precision] * [Recall], [Precision] + [Recall] )
```
**These should reproduce the numbers from her notebooks.** With no slicers applied, Power BI's MAE, RMSE, R², precision, recall, and F1 must match the notebook values. That is a free, strong validation (and a good talking point).

**Formatting:** set each measure's format (₹ for money, % for rates, 0.0 for minutes). For Indian-style amounts, a "₹ lakh" measure is nice: `Revenue (₹ L) = [Total Revenue] / 100000`, formatted as `"₹"0.0" L"`.

✅ **Done when:** All measures exist in `_Measures`, are formatted, and each has been tested in a simple table.

---

## Step 5 (Day 16–17): Set the Design System Before Building Pages

**The PRD requires** a consistent colour theme, consistent KPI card formatting, City and Date slicers wherever applicable, and tooltips for secondary metrics. Decide these once, then copy.

**1. Sketch each page on paper first** (five minutes each): where the title, slicers, KPI cards, and 4–6 visuals go. Aim for **no more than 6–8 visuals per page**. Space is part of readability.

**2. Pick a theme:** a primary accent (for example a red such as `#E23744`), dark grey for text, light grey backgrounds, and one or two secondary colours for contrast. Set it once via **View → Themes → Customize current theme**, so every visual inherits it. Check readability and avoid red-and-green as the *only* distinction (colour-blind viewers).

**3. KPI cards:** build one card (big number, small label, consistent font size, same number format) and **copy it** across pages instead of rebuilding.

**4. Slicers:** add a City slicer and a Date range slicer, then **View → Sync slicers** so a selection on one page carries to the others (for the same field). Customer pages get the *customer city* slicer instead.

**5. Tooltips:** create a **report-page tooltip** (new page → Page size: Tooltip → turn on "Allow use as tooltip"), put 2–3 secondary metrics on it (for example orders, average order value, late %), then choose it in a visual's **Format → Tooltip → Report page**. This keeps the main visuals uncluttered.

**6. Every visual:** a clear title (better: a takeaway such as "Dinner drives the late deliveries"), labelled axes, a legend when there is more than one series, readable font sizes, and sensible sort orders. For ordered categories (traffic level Low → High, rain None → Heavy) set **Column tools → Sort by column** with a numeric order column.

**Tip:** don't style as you go. Get each page's numbers right first, then spend the final hour on alignment and polish.

✅ **Done when:** The theme is set, a reusable KPI card exists, slicers are ready to sync, and each page has a paper sketch.

---

## Step 6 (Day 17): Page 1: Executive Dashboard

**Purpose:** a one-glance health check for leadership.

| Element | Content |
|---|---|
| **KPI cards (6)** | Total Revenue, Total Orders, Avg Delivery Time (min), Avg Rating, Active Customers (60d), Late Delivery % |
| **Slicers** | Restaurant city, Date range |
| **Visual 1** | Line chart: monthly revenue trend |
| **Visual 2** | Bar chart: top 10 cities by revenue |
| **Visual 3** | Column chart: orders by hour (highlight the peak hours) |
| **Visual 4** | Donut or bar: order status split |
| **Tooltip** | Hover on a city: orders, average order value, late % |

**Check:** the six cards, with no slicer selected, should equal the totals from her SQL and Python work (Step 12 makes this formal).

✅ **Done when:** Page 1 shows six correct KPI cards, responds to both slicers, and looks tidy.

---

## Step 7 (Day 17): Page 2: Customer Analytics

**Purpose:** who the customers are, and whether they stay.

| Element | Content |
|---|---|
| **KPI cards** | Customers, Avg Monthly Retention, Repeat customer %, Average CLV |
| **Slicers** | Customer city, Membership, Date range |
| **Visual 1** | Segments: bar or donut of New / Repeat / At-risk (from `customer_segment`) |
| **Visual 2** | Customer growth: columns = New Customers per month, line = Cumulative Customers |
| **Visual 3** | CLV distribution: histogram of `customer_lifetime_value`. Create bins by right-clicking the field → **New group → Bin** and choosing a bin size |
| **Visual 4** | Retention rate by month (line) |

Add one sentence under the segments chart defining each segment and the thresholds used. **Note in a text box** that segments are measured as of the latest date in the data, so they don't change with the date slicer (be honest about what responds to which filter).

✅ **Done when:** Page 2 shows retention, segments, growth over time, and the CLV distribution, with customer-city filtering working.

---

## Step 8 (Day 18): Page 3: Restaurant Analytics

**Purpose:** which restaurants to praise and which to review (User Story 2).

| Element | Content |
|---|---|
| **Slicers** | Restaurant city, Cuisine |
| **Visual 1** | **Top 10 restaurants** by performance score: bar chart with a **Top N filter** (Filters pane → Top N → 10 → by `performance_score`) |
| **Visual 2** | **Bottom 10 restaurants**: the same chart with *Bottom N* |
| **Visual 3** | Cuisine breakdown: combo chart (columns = revenue, line = average rating) |
| **Visual 4** | Bubble scatter: rating vs cancellation rate, bubble size = orders |
| **Tooltip** | Restaurant: orders, cancellation rate, average delivery time |

**Be honest about two things on the page:** (1) the composite score was computed over the *whole period* in SQL, so the date slicer doesn't change it (say so in a small note); and (2) her Week 1 view ranked restaurants **within each city** and required a minimum number of orders. Mention the rule so nobody asks why a restaurant is missing.

✅ **Done when:** Top 10 and Bottom 10 lists appear and change with the city slicer, and the cuisine chart shows both revenue and rating.

---

## Step 9 (Day 18): Page 4: Delivery Analytics

**Purpose:** what makes deliveries slow, and who delivers well (User Story 1).

| Element | Content |
|---|---|
| **Slicers** | Restaurant city, Date range, Vehicle type |
| **KPI cards** | Avg Delivery Time, P90 Delivery Time, Late Delivery % |
| **Visual 1** | **Partner leaderboard:** table with partner, vehicle, deliveries, average time, rating, efficiency. Add data bars or conditional formatting |
| **Visual 2** | **Delivery time trend:** line chart by month (Avg and P90) |
| **Visual 3** | **Traffic impact:** average delivery time by traffic level, in logical order |
| **Visual 4** | **Rain impact:** average delivery time by rain category (None → Heavy) |
| **Extra** | Peak vs non-peak comparison (a small bar chart) |

**Be careful with the leaderboard:** require a minimum number of deliveries (a visual-level filter) before ranking, otherwise a partner with 2 lucky deliveries wins. Describe the traffic and rain effects as *associations* ("deliveries in heavy rain average X minutes longer"), as in her EDA.

✅ **Done when:** The leaderboard, the trend, and the traffic and rain visuals all work and respond to the slicers.

---

## Step 10 (Day 18): Page 5: Sales Dashboard

**Purpose:** revenue over time, the effect of promotions, and how people pay (User Story 4).

| Element | Content |
|---|---|
| **Slicers** | Restaurant city, Date range, Payment method |
| **KPI cards** | Total Revenue, Avg Order Value, Coupon Usage %, Total Discount |
| **Visual 1** | **Revenue trend** (daily and monthly): a line chart on the date hierarchy; use the drill-down arrows (or two bookmarked views) to switch between daily and monthly |
| **Visual 2** | **Monthly revenue by city:** line chart with a legend for the top 5 cities, or **small multiples** |
| **Visual 3** | **Coupon and discount impact:** clustered bar of AOV With vs Without Coupon, plus orders by campaign name |
| **Visual 4** | **Payment method breakdown:** donut or bar, plus the payment failure rate by method (from `fact_payments`) |

Showing all ~25 cities in one line chart is unreadable. Show the top few and let the city slicer handle the rest. The monthly revenue by city view should be a trend visual on this page, which is what User Story 4's acceptance criteria require, and it should match her Week 1 `v_monthly_revenue_by_city` view.

✅ **Done when:** Revenue trends, coupon impact, and payment breakdown are all present and consistent with the SQL numbers.

---

## Step 11 (Day 19): Page 6: ML Dashboard

**Purpose:** show what the two models predict and why, in plain language (User Stories 1 and 3). Use a left/right split: delivery time on the left, churn on the right.

**Left side: Delivery time model**

| Visual | Content |
|---|---|
| KPI cards | MAE, RMSE, R² (from the DAX above), with the PRD targets in the subtitle (R² ≥ 0.75, RMSE ≤ 6 min) |
| Scatter | **Predicted vs actual** (`actual` on X, `predicted` on Y; try the Analytics pane's symmetry shading, if your version has it, for the diagonal) |
| Bar chart | **Feature importance**, top 10 (from `ml_delivery_feature_importance`) |
| Histogram | Residual distribution (optional) |
| **Text box** | 2–3 plain sentences explaining the top drivers, as in her notebook (*"Preparation time and traffic score matter most…"*) |

**Right side: Churn model**

| Visual | Content |
|---|---|
| KPI cards | Precision, Recall, F1 Score, ROC-AUC (from `ml_test_metrics`) |
| Donut/bar | **Risk segments**: customers in Low / Medium / High risk |
| Bar chart | **Top churn drivers**, top 10 (from `ml_churn_feature_importance`) |
| Matrix | **Confusion matrix:** rows `actual_label`, columns `predicted_label`, values = count of customers |
| Table | The 20 highest-risk customers: probability, membership, city (a ready-to-use list for the marketing team) |
| **Text box** | 2–3 sentences: who is at risk and what to do about it |

**Slicers:** *Restaurant city* for the delivery side and *Customer city* plus *Risk segment* for the churn side (label them clearly).

**A note on honesty:** the scores shown are for the **test set** (data the model never trained on), and the page should say so. Add one sentence: "Churn probabilities are for held-out customers; feature importance shows association, not proof of cause."

✅ **Done when:** The ML page reproduces the notebook metrics, shows importance charts with plain-language text, and the confusion matrix matches the notebook's.

---

## Step 12 (Day 19): Test and Validate the Dashboard

**1. KPI reconciliation table.** With no slicers selected, compare the same number across her three sources. They must agree, or she must be able to explain why.

| KPI | Power BI | SQL | Python | Match? |
|---|---|---|---|---|
| Total revenue (delivered) | | | | |
| Total orders | | | | |
| Avg delivery time (valid only) | | | | |
| Late delivery % | | | | |
| Cancellation rate | | | | |
| Active customers (60d) | | | | |
| Number of customers | | | | |

Then spot-check **two cities** and **one month** the same way.

**2. Functional tests:**
- [ ] Every slicer works, and synced slicers carry across pages
- [ ] Clearing all slicers returns the totals
- [ ] No unexplained "(Blank)" categories (null cities, missing sort values)
- [ ] Tooltips appear and show the right numbers
- [ ] Refresh works after changing the `DataFolder` parameter (NFR-04)
- [ ] ML page metrics equal the notebook values (with no slicers)

**3. Presentation checklist (NFR-06):**
- [ ] Every visual has a title; axes are labelled; legends are present where needed
- [ ] Same colour theme and KPI card style on all 6 pages
- [ ] Number formats are consistent (₹, %, minutes)
- [ ] Nothing overlaps or is cut off; text is readable at normal zoom
- [ ] Page names match the PRD: Executive Dashboard, Customer Analytics, Restaurant Analytics, Delivery Analytics, Sales Dashboard, ML Dashboard

**4. Save the file as `powerbi/zomato_dashboard.pbix`** and **take screenshots** of each page for the README (File → Export → PDF also works, then crop). Save them in `images/` (for example `powerbi_01_executive.png`).

✅ **Done when:** The reconciliation table is complete (or any difference is explained), all tests pass, and six page screenshots are saved.

---

## Step 13 (Day 19): Write the Business Insights Report

**What this means:** A short report (about 4–6 pages, `reports/business_insights_report.pdf`) that translates the analysis into **operational recommendations**. It is graded under *Business Insights & Recommendations* (5%), but it's also the document a manager would actually read.

**A structure that works:**
1. **Executive summary (one page):** the 3–5 most important findings and the 3–5 recommended actions, in plain language.
2. **One section per stakeholder** (from the PRD's user stories):

| Stakeholder | What they asked | What the report should say |
|---|---|---|
| City Operations Head | Which factors predict late deliveries? | Top drivers from the delivery model and EDA; **when and where** to add partners (for example peak hours in heavy rain, specific cities) |
| Restaurant Partnerships Manager | Which restaurants are underperforming? | The bottom of the performance score list; what is driving it (cancellations, delays, rating) |
| Growth Marketing Lead | Who will churn in 60 days? | The risk segments, the top churn drivers, and which customers to target with offers |
| Finance Analyst | City revenue trends | Monthly revenue by city, growth and decline, anything to watch next quarter |

3. **Limitations and risks:** what the analysis can't tell them.

**Use this format for every recommendation (it makes them concrete and checkable):**

> **Finding:** (a specific number, with the chart or query it came from) → **Implication:** (why it matters) → **Recommended action:** (who does what) → **How to measure success:** (a metric to watch) → **Confidence / caveat:** (honest limits)

**Example shape (use her real numbers, not these):** *"Late deliveries rise to X% at dinner in heavy rain, versus Y% otherwise (Delivery page, EDA chart 14). → Recommended action: shift N more partners to the affected cities during 7–10 PM on forecast-rain days. → Measure: late delivery % in those windows. → Caveat: this is an association in one 24-month snapshot, not a controlled test."*

**Keep it honest:**
- State what is an **association**, not a **cause** (especially for cancellations, where the data has no reason column).
- Mention data limits: the distance is a proxy (if that was her decision in Week 2), the dataset is a snapshot, and the models' scores are what they are (compared with the KPI targets).
- If she estimates impact (for example revenue at risk from churners), show the assumptions in plain text.

✅ **Done when:** The report has an executive summary, a section for each of the four stakeholders, concrete recommendations in the format above, and a limitations section.

---

## Step 14 (Day 20): Finish the README and the GitHub Repository

**The README is the first thing anyone sees.** The PRD requires these sections:

| Section | What to put there |
|---|---|
| **Project Overview** | 3–4 sentences: the business problem, the data, what was built |
| **Architecture** | One diagram: raw CSVs → PostgreSQL → Python pipeline → models → Power BI |
| **Workflow** | The four weeks in one short list (data/SQL → cleaning/features → EDA/ML → dashboard/reporting) |
| **Dataset Description** | The 12 tables, rough row counts, how they connect (embed the ER diagram) |
| **Installation Instructions** | Python version, `pip install -r requirements.txt`, PostgreSQL setup, how to create the database |
| **Usage Instructions** | The exact commands, in order: build the database, run `python -m src.run_pipeline`, open the notebooks, open the `.pbix` and set the `DataFolder` parameter |
| **SQL Query Highlights** | 3–5 interesting queries with the question and a short snippet or result |
| **EDA Highlights** | 3–5 key findings with embedded charts |
| **Machine Learning Summary** | Both models: features, algorithms compared, final metrics versus the KPI targets, top drivers |
| **Power BI Dashboard Preview** | Screenshots of the 6 pages |
| **Screenshots** | Any other images (ER diagram, key charts) |
| **Future Improvements** | Honest next steps (for example real customer coordinates for true distance, time-based validation, deployment) |
| **License** | e.g. MIT, with a `LICENSE` file |

Add a **"Results at a glance"** table with the PRD's KPIs filled in (Step 16). Reviewers love it.

**Repository clean-up:**
- [ ] The folder structure matches the PRD's Section 26 exactly (NFR-05): `data/raw`, `data/cleaned`, `sql/`, `notebooks/` (01–05), `src/` (ingest, clean, features, model_delivery, model_churn), `models/`, `reports/`, `powerbi/`, `images/`, `documentation/`, `README.md`, `requirements.txt`
- [ ] **No secrets:** no passwords, API keys, or `.env` committed (search the history, too)
- [ ] `.gitignore` covers `__pycache__/`, `.ipynb_checkpoints/`, `.env`, and any huge temporary files
- [ ] `requirements.txt` is complete and pinned (`pip freeze`, then keep only what's used)
- [ ] Notebooks run top to bottom after **Restart & Run All**, with outputs saved so GitHub shows the charts
- [ ] All matplotlib/seaborn charts have titles, axis labels, and legends (NFR-06)
- [ ] Docstrings in the Python modules; no commented-out junk or scratch files
- [ ] Clear commit messages (not "final", "final2", "fix")
- [ ] Files stay under GitHub's 100 MB limit (the `.pbix` is usually well under)
- [ ] If the repo is **public**, ask the mentor whether the dataset and the PRD document (`documentation/prd.docx`) may be shared. If not, keep the repo private

**The fresh-clone test (the most valuable test of the week):** clone the repo into a brand-new folder, create a new virtual environment, and follow the README *literally*:
1. `pip install -r requirements.txt`
2. `python -m src.run_pipeline` and check that it finishes in **under 30 minutes** (NFR-01); write the actual time in the README
3. Open the `.pbix`, set `DataFolder`, click Refresh

Fix every gap the test exposes, such as a missing file, an unexplained step, or a path that only works on her computer.

✅ **Done when:** The README has all 13 sections, the repo matches the folder structure, and a fresh clone runs end to end from the README alone.

---

## Step 15 (Day 20): Build the Final Presentation Deck (10–15 Slides)

**What this means:** A stakeholder readout, about 10–12 minutes. The audience wants the conclusions first, not a tour of the code.

**A slide-by-slide outline (12–13 slides):**

| # | Slide | Content |
|---|---|---|
| 1 | Title | Project name, her name, date |
| 2 | The business problem | Late deliveries, churn, inconsistent KPI definitions (from the PRD) |
| 3 | Approach and architecture | One diagram of the whole pipeline |
| 4 | Data quality | Issues found, cleaning outcome, **% of issues resolved** |
| 5 | SQL highlights | 2 insights from the 20+ queries |
| 6 | EDA: key findings | The two or three most important charts |
| 7 | Delivery time model | Algorithms compared, final R² and RMSE vs target, predicted-vs-actual chart |
| 8 | What drives late deliveries | Top feature importances, in plain language |
| 9 | Churn model | F1, ROC-AUC, confusion matrix, vs baseline and target |
| 10 | Who will churn and why | Risk segments and top drivers |
| 11 | Dashboard tour | 2–3 screenshots (or a short live demo) |
| 12 | Recommendations | 3–5 actions, each with its measure of success |
| 13 | Limitations and next steps | Honest caveats, and what she would do next |

**Slide rules that make a deck look professional:**
- **The slide title states the takeaway** ("Rain at dinner adds X minutes"), not the topic ("EDA results").
- One message per slide; large visuals; about 30 words of text at most.
- The same colours and fonts as the dashboard.
- Put the detail in the speaker notes, and rehearse once aloud with a timer.

**Prepare for the questions she'll likely get** (and have a one-sentence answer for each): *Why this threshold? Why this model and not another? How did you avoid data leakage? What are the limits of the data? What would you do with more time? How do you know the dashboard numbers are right?* (Answer: the reconciliation table.)

✅ **Done when:** The deck has 10–15 slides with takeaway titles, and she has practised it once within the time limit.

---

## Step 16 (Day 20): The Final Check and Submission

**1. The PRD's KPI scoreboard (Section 7).** Fill it with her real results. It belongs in the README, the report, and the deck.

| KPI | Target | Her result | Evidence |
|---|---|---|---|
| Data cleaning completeness | ≥ 95% of known issues resolved | | `cleaning_log.csv`, data-quality log |
| Delivery time model R² | ≥ 0.75 | | Notebook 04, ML page |
| Delivery time RMSE | ≤ 6 minutes | | Notebook 04, ML page |
| Churn model F1 (test set) | ≥ 0.70 | | Notebook 05, ML page |
| SQL query coverage | ≥ 20 queries | | `business_queries.sql` |
| Dashboard completeness | 6 / 6 pages | | `.pbix` |
| Documentation quality | ≥ 90% of rubric items | | README, reports |

If a KPI was missed, **say so plainly** and show what she did to investigate. That reads as strong analytical judgment, not weakness.

**2. The PRD's Final Deliverables Checklist (Section 28):**
- [ ] Cleaned datasets (all 12 tables) with the cleaning log
- [ ] SQL scripts (schema plus 20+ business queries)
- [ ] Python scripts (modular)
- [ ] Jupyter notebooks (cleaning, EDA, feature engineering, both models)
- [ ] EDA report with embedded visuals
- [ ] Delivery time regression model and comparison table
- [ ] Customer churn classification model and comparison table
- [ ] Power BI dashboard (`.pbix`, 6 pages)
- [ ] Business insights report
- [ ] Final presentation deck (10–15 slides)
- [ ] GitHub repository matching the required folder structure
- [ ] Complete `README.md`

**3. A last look at the rubric (100 points):**

| Category | Weight | Quick check |
|---|---|---|
| Data Cleaning | 15% | Every issue in the log, with counts and fixes? |
| SQL Skills | 15% | 20+ queries, all required constructs, views, an index? |
| Python Code Quality | 10% | Modular, docstrings, exception handling, runs end to end? |
| Pandas & NumPy Usage | 10% | Vectorized, merges validated, percentiles, seeded sampling? |
| Exploratory Data Analysis | 10% | All 8 business questions answered, with takeaways? |
| Visualizations (Matplotlib & Seaborn) | 10% | 15+ and 15+, all labelled, no duplicates? |
| Machine Learning (both models) | 15% | Compared, tuned, honest evaluation, importance explained? |
| Power BI Dashboard | 10% | 6 pages, star schema, DAX, slicers, tooltips, consistent design? |
| Business Insights & Recommendations | 5% | Concrete, quantified, honest? |
| Documentation & GitHub Hygiene | 10% | README complete, clean repo, fresh-clone test passed? |

**4. Submit.** Confirm with the mentor *how* the project should be submitted (repository link, a zipped folder, or both) and by when, then submit and keep a copy of everything.

✅ **Done when:** The scoreboard is filled, all 12 deliverables are ticked, and the project is submitted in the format the mentor asked for.

---

## Optional: Presenting the Project Well Afterwards

Once submitted, the project is a strong portfolio piece. Only claim what is real, with her **own numbers**:
- **A resume bullet shape:** *"Built an end-to-end analytics project on a Zomato-style food-delivery dataset: PostgreSQL schema and 20+ SQL analyses, a reproducible Python cleaning and feature pipeline, a delivery-time regression model (R² = __, RMSE = __ min) and a 60-day churn classifier (F1 = __), and a 6-page Power BI dashboard with DAX measures."*
- **A 30-second pitch:** the problem, what she built, one surprising finding, and the recommendation that followed.
- Interviewers usually probe the exact claims on a resume, so she should be ready to explain the leakage decisions, the churn cut-off design, and why a particular threshold or metric was chosen.

---

## Week 4 Checklist: Quick Reference

**Preparation**
- [ ] Power BI Desktop available (Windows machine or VM)
- [ ] Base table has `is_late` (blank where invalid), rain category, traffic score, restaurant city
- [ ] `restaurant_performance.csv`, `dim_customers_enriched.csv`, and `ml_test_metrics.csv` exported

**Data model**
- [ ] All CSVs loaded through a `DataFolder` parameter, with explicit data types
- [ ] Star schema with correct one-to-many relationships; no ambiguous paths
- [ ] Date table created and marked; inactive registration-date relationship added
- [ ] All DAX measures in `_Measures`, formatted and tested

**Design**
- [ ] Theme, KPI card style, synced City/Date slicers, tooltips, sorted categories

**Pages**
- [ ] Page 1: Executive Dashboard (6 KPI cards, city and date slicers)
- [ ] Page 2: Customer Analytics (retention, segments, growth, CLV distribution)
- [ ] Page 3: Restaurant Analytics (top and bottom by composite score, cuisine breakdown)
- [ ] Page 4: Delivery Analytics (leaderboard, trend, traffic and rain impact)
- [ ] Page 5: Sales Dashboard (revenue trend, coupons and discounts, payment methods)
- [ ] Page 6: ML Dashboard (predicted vs actual, importances, risk segments, churn drivers)

**Validation**
- [ ] KPI reconciliation table (Power BI vs SQL vs Python) complete
- [ ] Slicers, tooltips, refresh, and formatting tested; ML metrics match the notebooks
- [ ] `.pbix` saved in `powerbi/`; six page screenshots saved in `images/`

**Reporting and delivery**
- [ ] Business insights report with stakeholder sections and concrete recommendations
- [ ] README with all 13 required sections and a "Results at a glance" table
- [ ] Repository matches the folder structure; no secrets; clean history
- [ ] Fresh-clone test passed; pipeline runtime noted (under 30 minutes)
- [ ] 10–15 slide deck prepared and practised
- [ ] KPI scoreboard filled; 12 deliverables ticked; project submitted

---

## A Few Words of Encouragement

This is the week where four weeks of careful work finally becomes visible, and that is a great feeling. The core idea is the same one that has carried the whole project: **every number should be traceable and consistent.** If the dashboard, the SQL, the notebooks, and the report all agree, the project will look and *be* trustworthy.

If time gets tight, protect these in order: (1) correct, reconciled numbers on all 6 pages, even if the design is plain, (2) the README and a clean, working repository, (3) the business insights report, (4) the deck, (5) visual polish. A plain dashboard with correct numbers beats a beautiful one with a wrong total.

Power BI has a learning curve (DAX especially), and it's normal for a measure to return something strange at first. When it does, test the measure in a plain table, then add one filter at a time until the oddity appears. That small habit solves most DAX problems.

Congratulations on getting to the final week of the final project. Good luck with Week 4! 🎯
