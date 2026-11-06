# Zomato Business Intelligence & Delivery Time Prediction

A full-stack analytics project covering database design, SQL profiling, Python EDA, machine learning, and Power BI dashboards — built on a synthetic 24-month Zomato-style dataset across 25 Indian cities.

---

## Project Goal

Identify the operational factors that drive late deliveries, quantify their business impact, and build a predictive model that flags high-risk orders before dispatch. The final output is a Power BI executive dashboard backed by a clean PostgreSQL database.

---

## Week-by-Week Plan

| Week | Focus | Deliverable |
|------|-------|-------------|
| 1 | Database design, SQL profiling, data quality audit | `schema.sql`, `business_queries.sql`, ER diagram, data quality log |
| 2 | Python cleaning, feature engineering, analytical table | Clean CSVs, Jupyter notebooks, `data_cleaning.ipynb` |
| 3 | EDA, statistical analysis, ML model | `eda.ipynb`, `model_training.ipynb`, trained model |
| 4 | Power BI dashboard, final report | `.pbix` file, executive report PDF |

---

## Project Structure

```
Zomato_Business_Intelligence/
├── data/
│   ├── raw/               ← 12 original CSVs — never edit these
│   └── cleaned/           ← Week 2 output: cleaned & merged files
├── sql/
│   ├── schema.sql         ← CREATE TABLE statements, helper functions
│   └── business_queries.sql ← 20+ business queries, views, indexes
├── notebooks/             ← Jupyter notebooks (EDA, cleaning, modelling)
├── src/                   ← Python scripts (ingest.py, clean.py, etc.)
├── models/                ← Saved ML models
├── reports/               ← Generated charts, profiling reports
├── powerbi/               ← Power BI .pbix file
├── images/                ← ER diagram and other visuals
├── documentation/
│   ├── data_notes.md      ← Step 1 inspection notes
│   ├── data_quality_log.csv ← Running log of all data issues found
│   └── kpi_definitions.md ← Business rule definitions
└── requirements.txt       ← Python dependencies
```

---

## Quick Start

### 1 — Database setup (PostgreSQL required)

```bash
# Start Postgres (or use Docker)
docker run --name zomato-db -e POSTGRES_PASSWORD=yourpassword -p 5432:5432 -d postgres

# Create database and run schema
psql -U postgres -c "CREATE DATABASE zomato;"
psql -U postgres -d zomato -f sql/schema.sql
```

### 2 — Load raw data into staging

```bash
pip install -r requirements.txt
python src/ingest.py
```

### 3 — Run business queries

Open `sql/business_queries.sql` in pgAdmin or DBeaver and run the queries against the `zomato` database.

---

## Data Sources

12 CSV files in `data/raw/`:

| Table | Rows | Description |
|-------|------|-------------|
| cities | 25 | 25 Indian cities with population and income data |
| customers | 12,180 | Customer profiles with location and membership |
| restaurants | 1,200 | Restaurant details, cuisine, type, and ratings |
| delivery_partners | 2,000 | Rider profiles, vehicle type, and performance |
| menu | 8,997 | Food items per restaurant with price and calories |
| orders | 20,705 | Core transaction table — 24 months of orders |
| order_items | 42,378 | Line items per order |
| payments | 20,493 | Payment records with status |
| customer_feedback | 14,200 | Ratings and sentiment per order |
| promotions | 300 | Coupon campaigns with date ranges |
| weather | 18,264 | Daily weather by city |
| traffic | 18,335 | Daily traffic level and speed by city |

---

## Key Business Definitions

See `documentation/kpi_definitions.md` for the full list. Key ones:

- **Revenue** = `SUM(final_amount)` for `OrderStatus = 'Delivered'` or `'Delivered Late'`
- **Late delivery** = defined in `kpi_definitions.md` after distribution analysis
- **Active customer** = at least 1 order in the 60 days before the latest order date in the data
- **Reference date** = `SELECT MAX(order_date) FROM orders` — never use `CURRENT_DATE`

---

## Requirements

See `requirements.txt`. Core dependencies: `pandas`, `numpy`, `sqlalchemy`, `psycopg2-binary`, `jupyter`.
