# How to Rebuild the Database from Scratch

Run these five commands in order from the project root.  
They are fully idempotent — running them again drops and recreates everything cleanly.

```bash
# 1. Create all tables, functions, indexes, and city_aliases in the DB
python src/create_schema.py

# 2. Load all 12 raw CSVs into the staging schema (all columns as TEXT)
python src/ingest.py

# 3. Profile staging data and write data_quality_log.csv
python src/profile.py

# 4. ETL: staging → production (clean, deduplicate, resolve FKs, quarantine orphans)
python src/load_to_production.py

# 5. Run integrity checks and append findings to data_quality_log.csv
python src/integrity_checks.py
```

**Prerequisite:** `DATABASE_URL` must be set in `.env`.

**After step 5**, open `sql/business_queries.sql` in pgAdmin / DBeaver / psql  
to create the 4 views and run the 25 business queries.

## What each script does

| Script | Step | Output |
|--------|------|--------|
| `create_schema.py` | 3 | 13 tables, 3 helper functions, 9 indexes, 31 city aliases |
| `ingest.py` | 4 | `staging` schema with 12 tables, 159,077 rows |
| `profile.py` | 5 | `documentation/data_quality_log.csv`, `data_quality_report.md` |
| `load_to_production.py` | 6 | 12 production tables, 6 quarantine tables, `reconciliation` table |
| `integrity_checks.py` | 7 | `integrity_checks` table in DB, `integrity_checks_report.md` |
| `business_queries.sql` | 9–10 | 4 views, 25 queries (run manually in a SQL client) |

## Expected row counts after a clean rebuild

| Table | Rows |
|-------|------|
| cities | 25 |
| customers | 12,000 |
| restaurants | 1,200 |
| delivery_partners | 2,000 |
| promotions | 300 |
| weather | 18,173 |
| traffic | 18,335 |
| menu | 8,997 |
| orders | 20,475 |
| order_items | 42,361 |
| payments | 20,469 |
| customer_feedback | 14,180 |
