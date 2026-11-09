# Zomato Business Intelligence & Delivery Time Prediction

## Project Overview

This project asks why food-delivery orders arrive late, which customers go quiet, and whether the same KPI means the same thing in SQL, Python, and a dashboard. The data is a synthetic 24-month Zomato-style extract: 12 tables, 25 Indian cities, and 20,475 cleaned orders from 1 January 2023 to 31 December 2024. What was built is a PostgreSQL schema with business queries, a one-command Python cleaning pipeline, two models (delivery time and 60-day churn), and a six-page Power BI model with the measures written to the Week 1 definitions.

## Results at a glance

| KPI | Target | Result | Evidence |
|---|---|---|---|
| Data cleaning completeness | ≥ 95% of known issues resolved | **100%** | `documentation/validation_report.md` |
| Delivery time model R² | ≥ 0.75 | **−0.0022** (missed) | `models/model_metadata.json` |
| Delivery time RMSE | ≤ 6 minutes | **9.774 min** (missed) | `models/model_metadata.json` |
| Churn model F1 (test set) | ≥ 0.70 | **0.9326** (met, equal to the predict-all baseline) | `documentation/churn_model_report.md` |
| SQL query coverage | ≥ 20 queries | **Met** — views plus Q01 onward in `sql/business_queries.sql` | `sql/business_queries.sql` |
| Dashboard completeness | 6 / 6 pages | **6 pages in the Power BI project** | `powerbi/zomato_dashboard.pbip` |
| Documentation quality | README, reports, definitions | Report, model write-ups, KPI definitions, this file | `reports/`, `documentation/` |

The two model misses are properties of the data. Delivery time has no usable signal. Churn is so common (87.4%) that flagging everyone scores the same F1. Both are written up in `reports/business_insights_report.md`.

## Architecture

```
data/raw CSVs
    → PostgreSQL (sql/schema.sql, sql/business_queries.sql)
    → Python clean + features (src/run_pipeline.py) → data/cleaned
    → models (src/model_delivery.py, src/model_churn.py)
    → Power BI (powerbi/zomato_dashboard.pbip, DataFolder parameter)
```

The entity diagram is `images/er_diagram.svg`. An order's city is the restaurant's city. The customer's city stays on the customer table. Those two are never given two paths into the same fact table.

## Workflow

1. **Week 1 — data and SQL.** Schema, quality log, KPI definitions, business queries.
2. **Week 2 — cleaning and features.** One command rebuilds the cleaned tables and the analytical base table.
3. **Week 3 — EDA and models.** Charts, a delivery-time regression, a 60-day churn classifier.
4. **Week 4 — dashboard and reporting.** Star schema, DAX, six pages, insights report, this README, the slide deck.

## Dataset Description

Twelve raw tables in `data/raw/`. Cleaned row counts are after duplicate and orphan removal.

| Table | Raw rows | Cleaned rows | What it is |
|---|---:|---:|---|
| cities | 25 | 25 | City, population, income |
| customers | 12,180 | 12,000 | Profiles, membership, registration |
| restaurants | 1,200 | 1,200 | Cuisine, type, rating, city |
| delivery_partners | 2,000 | 2,000 | Vehicle, rating, historical speed |
| menu | 8,997 | 8,997 | Item, price, prep time |
| orders | 20,705 | 20,475 | One row per order |
| order_items | 42,378 | 42,361 | Lines on an order |
| payments | 20,493 | 20,469 | Method and status |
| customer_feedback | 14,200 | 14,180 | Ratings after delivery |
| promotions | 300 | 300 | Coupon code and campaign |
| weather | 18,264 | 18,173 | Daily weather by city |
| traffic | 18,335 | 18,335 | Traffic level by city, date, and hour |

Orders connect to customers, restaurants, partners, coupons, items, payments, and feedback. Weather and traffic attach on the restaurant's city. See `images/er_diagram.svg`.

## Installation Instructions

- Python 3.12 (developed on 3.12)
- PostgreSQL 14+ (local install or Docker)
- Power BI Desktop on Windows, for the dashboard

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Create `.env` in the project root (it is gitignored):

```
DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/zomato
```

Database:

```bash
docker run --name zomato-db -e POSTGRES_PASSWORD=yourpassword -p 5432:5432 -d postgres
psql -U postgres -c "CREATE DATABASE zomato;"
python src/create_schema.py
python src/ingest.py
python src/load_to_production.py
```

`python src/ingest.py` and `python src/load_to_production.py` need `DATABASE_URL`. The cleaning pipeline does not.

## Usage Instructions

From the project root, in order:

```bash
python src/run_pipeline.py
python src/validate.py
python src/export_sql_views.py
python src/model_delivery.py
python src/model_churn.py
python src/churn_analysis.py
python powerbi/build_semantic_model.py
```

On this machine the cleaning pipeline finished in about 30 seconds, inside the 30-minute limit.

Notebooks, after the pipeline:

- `notebooks/01_data_cleaning.ipynb`
- `notebooks/03_feature_engineering.ipynb`
- `notebooks/02_eda.ipynb`
- `notebooks/04_delivery_time_model.ipynb`
- `notebooks/05_churn_model.ipynb`

Open `powerbi/zomato_dashboard.pbip` in Power BI Desktop. The parameter `DataFolder` is already set to this project's `data\cleaned\` folder and must end with a backslash. Home → Transform data → edit `DataFolder` if the project moves, then Refresh.

## SQL Query Highlights

Definitions live in `documentation/kpi_definitions.md`. The reference date is `MAX(order_date)`, which is 2024-12-31, never today's date.

- **Revenue.** Delivered-only revenue is ₹44,06,359.55 in both SQL and Python. Delivered Late adds ₹8,29,976.05. The dashboard's Total Revenue includes both, because a late order was still received.
- **Slowest cities.** Average delivery time by restaurant city, valid times only, is the query pattern in `sql/business_queries.sql` (Q03). City differences in the EDA were not statistically significant.
- **Restaurant score.** `v_restaurant_performance` ranks inside the city with weights 40% rating, 30% cancellation, 30% speed, and drops restaurants under 10 orders. Power BI reads that view from `data/cleaned/restaurant_performance.csv`.

## EDA Highlights

Full write-up: `reports/eda_report.md`. Charts: `images/` and `documentation/eda_chart_register.csv` (38 charts, 18 Matplotlib and 20 Seaborn).

- Kolkata leads delivered revenue at ₹2.02 lakh. South Indian leads cuisine at ₹3.07 lakh. Monthly revenue has no real trend (+0.4% in 2024 versus 2023).
- The busiest hour is 19:00. The 19:00–22:00 window holds 22.2% of orders.
- Median delivery on the EDA delivered subset is 34 minutes. City, traffic, and weather differences are not significant. Traffic matches only 5.1% of valid deliveries.
- 22.3% of orders are cancelled. There is no reason column. 47.9% of customers have a single non-cancelled order.

## Machine Learning Summary

**Delivery time** (`src/model_delivery.py`). Target `delivery_time_minutes`. Compared a mean baseline, ridge, a decision tree, random forest, and gradient boosting. Tuned the top two. Winner: Random Forest. Test set, opened once: R² **−0.0022**, RMSE **9.774** minutes, MAE 7.84. Targets were R² ≥ 0.75 and RMSE ≤ 6. Permutation importance is inside the noise. Feedback ratings and the broken distance feature are not inputs.

**Churn** (`src/model_churn.py`, `src/churn_analysis.py`). Label: no order in the 60 days after 1 November 2024. Features use only orders on or before that date. Compared a majority baseline, logistic regression, a decision tree, random forest, and gradient boosting. Winner: Random Forest. Test F1 **0.9326** (baseline 0.9326), ROC-AUC **0.514**, recall 1.0 at the chosen threshold. The F1 target is met only because the baseline already clears it. Risk bands do not separate churners.

## Power BI Dashboard Preview

Project file: `powerbi/zomato_dashboard.pbip` (open this; a `.pbix` save is still outstanding).

| Page | What it shows |
|---|---|
| Executive Dashboard | Revenue, orders, delivery time, rating, active customers, late %, hour, city, status |
| Customer Analytics | Segments, registrations by month, repeat rate, retention, CLV. Customer city slicer |
| Restaurant Analytics | Performance score from the SQL view, revenue by cuisine |
| Delivery Analytics | Average, P90, late %, month trend, rain |
| Sales Dashboard | Revenue, AOV, coupons, discount, payment failure, monthly revenue |
| ML Dashboard | MAE, RMSE, R², F1, ROC-AUC, importance, risk bands |

Measures sit on `_Measures`. Revenue follows the Week 1 rule: Delivered and Delivered Late, amount > 0. `is_late` is blank when the delivery time is missing or not positive.

Screenshots of the six pages are in `images/powerbi_01_executive.png` through `images/powerbi_06_ml.png`.

## Screenshots

- Power BI pages: `images/powerbi_01_executive.png`, `images/powerbi_02_customer.png`, `images/powerbi_03_restaurant.png`, `images/powerbi_04_delivery.png`, `images/powerbi_05_sales.png`, `images/powerbi_06_ml.png`
- Entity diagram: `images/er_diagram.svg`
- EDA charts: `images/m01_revenue_by_city.png` and the rest listed in `documentation/eda_chart_register.csv`
- Model charts: `images/delivery_residuals.png`, `images/delivery_feature_importance.png`, `images/churn_roc_curve.png`, `images/churn_confusion_matrix.png`

## Future Improvements

- Real customer and restaurant coordinates, so distance is a distance.
- A cancellation reason, otherwise the 22% rate cannot be acted on.
- A churn label that is not "almost everyone," or a model that beats predicting everyone.
- Time-based validation instead of a random split for delivery time.
- Save `powerbi/zomato_dashboard.pbix` after a successful refresh. The six page screenshots are already in `images/`.

## License

MIT. See `LICENSE`.

## Still to do in Power BI Desktop

The project file has the parameter, types, star schema, date table, measures, and six pages. These clicks are not done:

- Refresh, including a second refresh after pointing `DataFolder` at a copy of `data\cleaned\`
- Confirm every visual renders, then set Top N = 10 on the restaurant score chart
- Sync the restaurant-city and date slicers across the order pages
- Add a report-page tooltip
- Save as `powerbi/zomato_dashboard.pbix`
- Fresh-clone test of this README, and submission in whatever form the mentor wants
