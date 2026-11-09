"""
Build the Week 4 Power BI project (steps 2 and 3).

Every table is loaded through the DataFolder parameter. Column names stay
the same as the CSVs. IDs are text, dates are dates, flags are whole numbers,
and amounts are decimal numbers. The date table and the star-schema
relationships are part of the model, not calculated again in each visual.

Run from the project root:
    python powerbi/build_semantic_model.py
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CLEAN = ROOT / "data" / "cleaned"
OUT = Path(__file__).resolve().parent
DATA_FOLDER = str(CLEAN) + "\\"

# Query name -> CSV. dim_date is a DAX table, not a file.
TABLES: list[tuple[str, str]] = [
    ("fact_orders", "analytical_base_table.csv"),
    ("fact_order_items", "order_items.csv"),
    ("fact_payments", "payments.csv"),
    ("fact_feedback", "customer_feedback.csv"),
    ("dim_customers", "dim_customers_enriched.csv"),
    ("dim_restaurants", "restaurants.csv"),
    ("dim_delivery_partners", "delivery_partners.csv"),
    ("dim_promotions", "promotions.csv"),
    ("dim_menu", "menu.csv"),
    ("dim_city", "cities.csv"),
    ("restaurant_performance", "restaurant_performance.csv"),
    ("ml_delivery_predictions", "ml_delivery_predictions.csv"),
    ("ml_delivery_feature_importance", "ml_delivery_feature_importance.csv"),
    ("ml_churn_scores_test", "ml_churn_scores_test.csv"),
    ("ml_churn_feature_importance", "ml_churn_feature_importance.csv"),
    ("ml_test_metrics", "ml_test_metrics.csv"),
]

# Long text and cleaning flags the dashboard does not use.
DROP = {
    "fact_orders": ["review", "city_lat", "city_lon", "tenure_is_negative"],
    "fact_feedback": ["review"],
    "dim_customers": ["age_was_missing", "phone_valid", "email_valid", "pincode_valid"],
    "dim_delivery_partners": ["age_was_missing"],
}

DATE_COLS = {
    "order_date", "registration_date", "first_order", "last_order",
    "joining_date", "start_date", "end_date", "payment_date",
}
TEXT_IDS = {"coupon_code", "transaction_id", "phone", "email", "pincode"}
WHOLE = {
    "is_late", "peak_hour", "weekend_order", "coupon_used", "is_cross_city",
    "is_peak_and_rain", "is_weekend_and_rain", "dt_outlier_flag", "has_review",
    "quantity", "population", "order_hour", "order_minute", "order_dayofweek",
    "order_month", "n_items", "n_distinct_items", "completed_deliveries",
    "total_orders", "orders_to_date", "days_since_last_order",
    "predicted_label", "actual_label", "restaurant_order_count",
    "restaurant_popularity_rank", "calories",
}
MONEY = {
    "final_amount", "food_cost", "delivery_fee", "discount", "gst",
    "basket_value", "average_cost", "price", "unit_price", "total_price",
    "total_revenue", "customer_lifetime_value", "average_basket_value",
    "average_income",
}
NO_SUM = {
    "order_hour", "order_minute", "order_dayofweek", "order_month",
    "predicted_label", "actual_label",
}
KEYS = {
    ("fact_orders", "order_id"),
    ("dim_customers", "customer_id"),
    ("dim_restaurants", "restaurant_id"),
    ("dim_delivery_partners", "delivery_partner_id"),
    ("dim_promotions", "coupon_code"),
    ("dim_menu", "food_item_id"),
    ("dim_city", "city"),
    ("restaurant_performance", "restaurant_id"),
    ("ml_delivery_predictions", "order_id"),
    ("dim_date", "date"),
}


def tag(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "zomato-bi:" + name))


def m_string(path: str) -> str:
    """M text literal. Backslashes are escaped."""
    return '"' + path.replace("\\", "\\\\") + '"'


def classify(name: str, series: pd.Series) -> tuple[str, str]:
    """Return (Power Query type, TMDL dataType)."""
    if name in DATE_COLS or name.endswith("_date"):
        return "type date", "dateTime"
    if name.endswith("_id") or name in TEXT_IDS:
        return "type text", "string"
    if name in WHOLE:
        return "Int64.Type", "int64"
    numeric = pd.to_numeric(series, errors="coerce")
    parsed = numeric.notna().sum()
    non_null = series.notna().sum()
    if non_null and parsed / non_null > 0.9:
        whole = numeric.dropna().mod(1).eq(0).all()
        if whole and name not in MONEY and "minute" not in name and not name.endswith("_time"):
            return "Int64.Type", "int64"
        return "type number", "double"
    return "type text", "string"


def tmdl_name(name: str) -> str:
    if name.replace("_", "").isalnum() and name[0].isalpha():
        return name
    return "'" + name.replace("'", "''") + "'"


def load_columns(query: str, filename: str) -> list[dict]:
    frame = pd.read_csv(CLEAN / filename, low_memory=False)
    drop = [c for c in DROP.get(query, []) if c in frame.columns]
    frame = frame.drop(columns=drop)
    columns = []
    for name in frame.columns:
        pq_type, tmdl_type = classify(name, frame[name])
        columns.append({
            "name": name,
            "pq": pq_type,
            "tmdl": tmdl_type,
            "drop_before": False,
        })
    return columns, drop


def m_query(filename: str, columns: list[dict], drop: list[str]) -> str:
    pairs = ", ".join(f'{{"{c["name"]}", {c["pq"]}}}' for c in columns)
    lines = [
        "let",
        f"    Source = Csv.Document(File.Contents(DataFolder & \"{filename}\"), [Delimiter = \",\", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),",
        "    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),",
    ]
    current = "Promoted"
    if drop:
        dropped = ", ".join(f'"{c}"' for c in drop)
        lines.append(f"    Removed = Table.RemoveColumns({current}, {{{dropped}}}, MissingField.Ignore),")
        current = "Removed"
    lines.append(f"    Typed = Table.TransformColumnTypes({current}, {{{pairs}}}, \"en-US\")")
    final = "Typed"
    if filename == "analytical_base_table.csv":
        lines[-1] += ","
        lines.append(
            '    WithTrafficSort = Table.AddColumn(Typed, "traffic_level_sort", '
            'each if [traffic_level] = "Low" then 1 else if [traffic_level] = "Moderate" then 2 '
            'else if [traffic_level] = "High" then 3 else if [traffic_level] = "Severe" then 4 else null, Int64.Type),'
        )
        lines.append(
            '    WithRainSort = Table.AddColumn(WithTrafficSort, "rain_impact_sort", '
            'each if [rain_impact] = "None" then 0 else if [rain_impact] = "Light" then 1 '
            'else if [rain_impact] = "Moderate" then 2 else if [rain_impact] = "Heavy" then 3 else null, Int64.Type)'
        )
        final = "WithRainSort"
    lines.append("in")
    lines.append(f"    {final}")
    return "\n".join(lines)


def column_block(query: str, column: dict) -> str:
    name = column["name"]
    lines = [
        f"\tcolumn {tmdl_name(name)}",
        f"\t\tdataType: {column['tmdl']}",
        f"\t\tlineageTag: {tag(query + '.' + name)}",
        f"\t\tsourceColumn: {tmdl_name(name)}",
    ]
    if column["tmdl"] == "dateTime":
        lines.insert(2, "\t\tformatString: 'Short Date'")
        lines.append("\t\tsummarizeBy: none")
    elif column["tmdl"] == "string" or name in NO_SUM or (query, name) in KEYS:
        lines.append("\t\tsummarizeBy: none")
    if name in MONEY:
        lines.insert(2, "\t\tformatString: '₹#,0.00'")
    if (query, name) in KEYS:
        lines.append("\t\tisKey")
    if name in SORT_BY:
        lines.append(f"\t\tsortByColumn: {SORT_BY[name]}")
    if name in SORT_BY.values():
        lines.append("\t\tsummarizeBy: none")
        lines.append("\t\tisHidden")
    lines.append("")
    lines.append("\t\tannotation SummarizationSetBy = Automatic")
    lines.append("")
    return "\n".join(lines)


def table_file(query: str, filename: str) -> str:
    columns, drop = load_columns(query, filename)
    body = [
        f"table {query}",
        f"\tlineageTag: {tag(query)}",
        "",
    ]
    source_columns = list(columns)
    if query == "fact_orders":
        columns.extend(
            {"name": name, "pq": "Int64.Type", "tmdl": "int64"}
            for name in ("traffic_level_sort", "rain_impact_sort")
        )
    body.extend(column_block(query, column) for column in columns)
    m_lines = m_query(filename, source_columns, drop).splitlines()
    indented = "\n".join("\t\t\t" + line if line else "" for line in m_lines)
    body.append(f"\tpartition {query} = m")
    body.append("\t\tmode: import")
    body.append("\t\tsource =")
    body.append(indented)
    body.append("")
    body.append("\tannotation PBI_ResultType = Table")
    body.append("")
    return "\n".join(body), columns


DATE_M = """let
    StartDate = #date(2022, 1, 1),
    EndDate = #date(2024, 12, 31),
    Dates = List.Dates(StartDate, Duration.Days(EndDate - StartDate) + 1, #duration(1, 0, 0, 0)),
    AsTable = Table.FromList(Dates, Splitter.SplitByNothing(), {"date"}),
    Typed = Table.TransformColumnTypes(AsTable, {{"date", type date}}),
    WithYear = Table.AddColumn(Typed, "Year", each Date.Year([date]), Int64.Type),
    WithMonthNumber = Table.AddColumn(WithYear, "Month Number", each Date.Month([date]), Int64.Type),
    WithMonth = Table.AddColumn(WithMonthNumber, "Month", each Date.ToText([date], "MMM", "en-US"), type text),
    WithMonthStart = Table.AddColumn(WithMonth, "Month Start", each Date.StartOfMonth([date]), type date),
    WithWeekday = Table.AddColumn(WithMonthStart, "Weekday", each Date.DayOfWeek([date], Day.Monday) + 1, Int64.Type),
    WithWeekend = Table.AddColumn(WithWeekday, "Is Weekend", each if Date.DayOfWeek([date], Day.Monday) >= 5 then 1 else 0, Int64.Type)
in
    WithWeekend"""


def date_table() -> str:
    specs = [
        ("date", "dateTime", True, "'Short Date'", None),
        ("Year", "int64", False, None, "none"),
        ("Month Number", "int64", False, None, "none"),
        ("Month", "string", False, None, "none"),
        ("Month Start", "dateTime", False, "'Short Date'", "none"),
        ("Weekday", "int64", False, None, "none"),
        ("Is Weekend", "int64", False, None, None),
    ]
    lines = [
        "table dim_date",
        f"\tlineageTag: {tag('dim_date')}",
        "\tdataCategory: Time",
        "",
    ]
    for name, dtype, key, fmt, summarize in specs:
        lines.append(f"\tcolumn {tmdl_name(name)}")
        lines.append(f"\t\tdataType: {dtype}")
        if fmt:
            lines.append(f"\t\tformatString: {fmt}")
        lines.append(f"\t\tlineageTag: {tag('dim_date.' + name)}")
        if summarize:
            lines.append(f"\t\tsummarizeBy: {summarize}")
        lines.append(f"\t\tsourceColumn: {tmdl_name(name)}")
        if key:
            lines.append("\t\tisKey")
        if name == "Month":
            lines.append("\t\tsortByColumn: 'Month Number'")
        lines.append("")
        lines.append("\t\tannotation SummarizationSetBy = Automatic")
        lines.append("")
    lines.append("\tpartition dim_date = m")
    lines.append("\t\tmode: import")
    lines.append("\t\tsource =")
    for line in DATE_M.splitlines():
        lines.append("\t\t\t" + line)
    lines.append("")
    lines.append("\tannotation PBI_ResultType = Table")
    lines.append("")
    return "\n".join(lines)


def relationships() -> str:
    """fromColumn is the many side. toColumn is the one side."""
    specs = [
        ("fact_orders.order_date", "dim_date.date", False, False, True),
        ("fact_orders.customer_id", "dim_customers.customer_id", False, False, False),
        ("fact_orders.restaurant_id", "dim_restaurants.restaurant_id", False, False, False),
        ("fact_orders.delivery_partner_id", "dim_delivery_partners.delivery_partner_id", False, False, False),
        ("fact_orders.coupon_code", "dim_promotions.coupon_code", False, False, False),
        ("fact_orders.restaurant_city", "dim_city.city", False, False, False),
        ("fact_order_items.order_id", "fact_orders.order_id", False, False, False),
        ("fact_payments.order_id", "fact_orders.order_id", False, False, False),
        ("fact_feedback.order_id", "fact_orders.order_id", False, False, False),
        ("fact_order_items.food_item_id", "dim_menu.food_item_id", False, False, False),
        ("restaurant_performance.restaurant_id", "dim_restaurants.restaurant_id", True, False, False),
        ("ml_delivery_predictions.order_id", "fact_orders.order_id", True, False, False),
        ("ml_churn_scores_test.customer_id", "dim_customers.customer_id", False, False, False),
        ("dim_customers.registration_date", "dim_date.date", False, True, True),
    ]
    blocks = []
    for many, one, one_to_one, inactive, date_join in specs:
        name = tag(many + "->" + one)
        lines = [f"relationship {name}"]
        if one_to_one:
            lines.append("\tfromCardinality: one")
            lines.append("\ttoCardinality: one")
        if inactive:
            lines.append("\tisActive: false")
        direction = "bothDirections" if one_to_one else "oneDirection"
        lines.append(f"\tcrossFilteringBehavior: {direction}")
        if date_join:
            lines.append("\tjoinOnDateBehavior: datePartOnly")
        lines.append(f"\tfromColumn: {many}")
        lines.append(f"\ttoColumn: {one}")
        lines.append("")
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


SORT_BY = {
    "traffic_level": "traffic_level_sort",
    "rain_impact": "rain_impact_sort",
}


def calculated_columns(query: str) -> str:
    """Sort helpers so traffic and rain visuals do not sort alphabetically."""
    if query != "fact_orders":
        return ""
    blocks = []
    specs = [
        (
            "traffic_level_sort",
            'SWITCH (\n'
            '\t\t\t    fact_orders[traffic_level],\n'
            '\t\t\t    "Low", 1,\n'
            '\t\t\t    "Moderate", 2,\n'
            '\t\t\t    "High", 3,\n'
            '\t\t\t    "Severe", 4\n'
            '\t\t\t)',
        ),
        (
            "rain_impact_sort",
            'SWITCH (\n'
            '\t\t\t    fact_orders[rain_impact],\n'
            '\t\t\t    "None", 0,\n'
            '\t\t\t    "Light", 1,\n'
            '\t\t\t    "Moderate", 2,\n'
            '\t\t\t    "Heavy", 3\n'
            '\t\t\t)',
        ),
    ]
    for name, expr in specs:
        blocks.append(
            f"\tcolumn {name} =\n"
            f"\t\t\t{expr}\n"
            f"\t\tdataType: int64\n"
            f"\t\tlineageTag: {tag('fact_orders.' + name)}\n"
            f"\t\tsummarizeBy: none\n"
            f"\t\tisHidden\n"
            f"\n"
            f"\t\tannotation SummarizationSetBy = Automatic\n"
        )
    return "\n".join(blocks) + "\n"


MEASURES = r'''
measure 'Total Revenue' = ```
		CALCULATE (
		    SUM ( fact_orders[final_amount] ),
		    fact_orders[order_status] IN { "Delivered", "Delivered Late" },
		    fact_orders[final_amount] > 0
		)
	```
	formatString: '₹#,0.00'
	displayFolder: Core
	lineageTag: __TAG__

measure 'Total Orders' = ```
		DISTINCTCOUNT ( fact_orders[order_id] )
	```
	formatString: '#,0'
	displayFolder: Core
	lineageTag: __TAG__

measure 'Delivered Orders' = ```
		CALCULATE (
		    [Total Orders],
		    fact_orders[order_status] IN { "Delivered", "Delivered Late" },
		    fact_orders[final_amount] > 0
		)
	```
	formatString: '#,0'
	displayFolder: Core
	lineageTag: __TAG__

measure 'Cancelled Orders' = ```
		CALCULATE ( [Total Orders], fact_orders[order_status] = "Cancelled" )
	```
	formatString: '#,0'
	displayFolder: Core
	lineageTag: __TAG__

measure 'Cancellation Rate' = ```
		DIVIDE ( [Cancelled Orders], [Total Orders] )
	```
	formatString: '0.0%'
	displayFolder: Core
	lineageTag: __TAG__

measure 'Avg Order Value' = ```
		DIVIDE ( [Total Revenue], [Delivered Orders] )
	```
	formatString: '₹#,0.00'
	displayFolder: Core
	lineageTag: __TAG__

measure 'Avg Delivery Time' = ```
		CALCULATE (
		    AVERAGE ( fact_orders[delivery_time_minutes] ),
		    fact_orders[order_status] IN { "Delivered", "Delivered Late" },
		    fact_orders[delivery_time_minutes] > 0
		)
	```
	formatString: '0.0'
	displayFolder: Core
	lineageTag: __TAG__

measure 'Late Delivery %' = ```
		DIVIDE ( SUM ( fact_orders[is_late] ), COUNT ( fact_orders[is_late] ) )
	```
	formatString: '0.0%'
	displayFolder: Core
	lineageTag: __TAG__

measure 'Avg Rating' = ```
		AVERAGE ( fact_feedback[customer_rating] )
	```
	formatString: '0.00'
	displayFolder: Core
	lineageTag: __TAG__

measure 'Active Customers (60d)' = ```
		VAR EndDate = MAX ( dim_date[date] )
		RETURN
		    CALCULATE (
		        DISTINCTCOUNT ( fact_orders[customer_id] ),
		        dim_date[date] > EndDate - 60,
		        dim_date[date] <= EndDate
		    )
	```
	formatString: '#,0'
	displayFolder: Core
	lineageTag: __TAG__

measure 'Revenue (₹ L)' = ```
		[Total Revenue] / 100000
	```
	formatString: '"₹"0.00" L"'
	displayFolder: Core
	lineageTag: __TAG__

measure 'Customer Rows' = ```
		COUNTROWS ( dim_customers )
	```
	formatString: '#,0'
	displayFolder: Customers
	lineageTag: __TAG__

measure 'Ordering Customers' = ```
		DISTINCTCOUNT ( fact_orders[customer_id] )
	```
	formatString: '#,0'
	displayFolder: Customers
	lineageTag: __TAG__

measure 'Repeat Customers' = ```
		COUNTROWS (
		    FILTER (
		        VALUES ( fact_orders[customer_id] ),
		        CALCULATE ( [Total Orders] ) >= 2
		    )
		)
	```
	formatString: '#,0'
	displayFolder: Customers
	lineageTag: __TAG__

measure 'Repeat Customer %' = ```
		DIVIDE ( [Repeat Customers], [Ordering Customers] )
	```
	formatString: '0.0%'
	displayFolder: Customers
	lineageTag: __TAG__

measure 'Customers Prev Month' = ```
		CALCULATE (
		    DISTINCTCOUNT ( fact_orders[customer_id] ),
		    DATEADD ( dim_date[date], -1, MONTH )
		)
	```
	formatString: '#,0'
	displayFolder: Customers
	lineageTag: __TAG__

measure 'Retained Customers' = ```
		VAR Current = VALUES ( fact_orders[customer_id] )
		VAR Previous =
		    CALCULATETABLE (
		        VALUES ( fact_orders[customer_id] ),
		        DATEADD ( dim_date[date], -1, MONTH )
		    )
		RETURN
		    COUNTROWS ( INTERSECT ( Current, Previous ) )
	```
	formatString: '#,0'
	displayFolder: Customers
	lineageTag: __TAG__

measure 'Retention Rate' = ```
		DIVIDE ( [Retained Customers], [Customers Prev Month] )
	```
	formatString: '0.0%'
	displayFolder: Customers
	lineageTag: __TAG__

measure 'Avg Monthly Retention' = ```
		VAR Months =
		    SUMMARIZE ( dim_date, dim_date[Year], dim_date[Month Number] )
		RETURN
		    AVERAGEX (
		        Months,
		        VAR Y = dim_date[Year]
		        VAR M = dim_date[Month Number]
		        VAR PrevM = IF ( M = 1, 12, M - 1 )
		        VAR PrevY = IF ( M = 1, Y - 1, Y )
		        VAR CurrentIds =
		            CALCULATETABLE (
		                VALUES ( fact_orders[customer_id] ),
		                REMOVEFILTERS ( dim_date ),
		                dim_date[Year] = Y,
		                dim_date[Month Number] = M
		            )
		        VAR PreviousIds =
		            CALCULATETABLE (
		                VALUES ( fact_orders[customer_id] ),
		                REMOVEFILTERS ( dim_date ),
		                dim_date[Year] = PrevY,
		                dim_date[Month Number] = PrevM
		            )
		        RETURN
		            DIVIDE (
		                COUNTROWS ( INTERSECT ( CurrentIds, PreviousIds ) ),
		                COUNTROWS ( PreviousIds )
		            )
		    )
	```
	formatString: '0.0%'
	displayFolder: Customers
	lineageTag: __TAG__

measure 'New Customers' = ```
		CALCULATE (
		    COUNTROWS ( dim_customers ),
		    USERELATIONSHIP ( dim_date[date], dim_customers[registration_date] )
		)
	```
	formatString: '#,0'
	displayFolder: Customers
	lineageTag: __TAG__

measure 'Cumulative Customers' = ```
		CALCULATE (
		    [New Customers],
		    FILTER ( ALL ( dim_date[date] ), dim_date[date] <= MAX ( dim_date[date] ) )
		)
	```
	formatString: '#,0'
	displayFolder: Customers
	lineageTag: __TAG__

measure 'Average CLV' = ```
		AVERAGE ( dim_customers[customer_lifetime_value] )
	```
	formatString: '₹#,0.00'
	displayFolder: Customers
	lineageTag: __TAG__

measure 'Coupon Orders' = ```
		CALCULATE ( [Total Orders], NOT ISBLANK ( fact_orders[coupon_code] ) )
	```
	formatString: '#,0'
	displayFolder: Sales
	lineageTag: __TAG__

measure 'Coupon Usage %' = ```
		DIVIDE ( [Coupon Orders], [Total Orders] )
	```
	formatString: '0.0%'
	displayFolder: Sales
	lineageTag: __TAG__

measure 'Total Discount' = ```
		SUM ( fact_orders[discount] )
	```
	formatString: '₹#,0.00'
	displayFolder: Sales
	lineageTag: __TAG__

measure 'Discount % of Food Value' = ```
		DIVIDE ( [Total Discount], SUM ( fact_orders[food_cost] ) )
	```
	formatString: '0.0%'
	displayFolder: Sales
	lineageTag: __TAG__

measure 'AOV With Coupon' = ```
		CALCULATE ( [Avg Order Value], NOT ISBLANK ( fact_orders[coupon_code] ) )
	```
	formatString: '₹#,0.00'
	displayFolder: Sales
	lineageTag: __TAG__

measure 'AOV Without Coupon' = ```
		CALCULATE ( [Avg Order Value], ISBLANK ( fact_orders[coupon_code] ) )
	```
	formatString: '₹#,0.00'
	displayFolder: Sales
	lineageTag: __TAG__

measure 'Payment Failure Rate' = ```
		DIVIDE (
		    CALCULATE ( COUNTROWS ( fact_payments ), fact_payments[payment_status] = "Failed" ),
		    COUNTROWS ( fact_payments )
		)
	```
	formatString: '0.0%'
	displayFolder: Sales
	lineageTag: __TAG__

measure 'P90 Delivery Time' = ```
		PERCENTILEX.INC (
		    FILTER (
		        fact_orders,
		        fact_orders[order_status] IN { "Delivered", "Delivered Late" }
		            && fact_orders[delivery_time_minutes] > 0
		    ),
		    fact_orders[delivery_time_minutes],
		    0.9
		)
	```
	formatString: '0.0'
	displayFolder: Delivery
	lineageTag: __TAG__

measure 'MAE' = ```
		AVERAGEX (
		    ml_delivery_predictions,
		    ABS ( ml_delivery_predictions[actual_minutes] - ml_delivery_predictions[predicted_minutes] )
		)
	```
	formatString: '0.00'
	displayFolder: ML
	lineageTag: __TAG__

measure 'RMSE' = ```
		SQRT (
		    AVERAGEX (
		        ml_delivery_predictions,
		        ( ml_delivery_predictions[actual_minutes] - ml_delivery_predictions[predicted_minutes] ) ^ 2
		    )
		)
	```
	formatString: '0.00'
	displayFolder: ML
	lineageTag: __TAG__

measure 'R2' = ```
		VAR MeanActual = AVERAGE ( ml_delivery_predictions[actual_minutes] )
		VAR SSE =
		    SUMX (
		        ml_delivery_predictions,
		        ( ml_delivery_predictions[actual_minutes] - ml_delivery_predictions[predicted_minutes] ) ^ 2
		    )
		VAR SST =
		    SUMX (
		        ml_delivery_predictions,
		        ( ml_delivery_predictions[actual_minutes] - MeanActual ) ^ 2
		    )
		RETURN
		    1 - DIVIDE ( SSE, SST )
	```
	formatString: '0.000'
	displayFolder: ML
	lineageTag: __TAG__

measure 'TP' = ```
		CALCULATE (
		    COUNTROWS ( ml_churn_scores_test ),
		    ml_churn_scores_test[actual_label] = 1,
		    ml_churn_scores_test[predicted_label] = 1
		)
	```
	formatString: '#,0'
	displayFolder: 'ML helpers'
	lineageTag: __TAG__

measure 'FP' = ```
		CALCULATE (
		    COUNTROWS ( ml_churn_scores_test ),
		    ml_churn_scores_test[actual_label] = 0,
		    ml_churn_scores_test[predicted_label] = 1
		)
	```
	formatString: '#,0'
	displayFolder: 'ML helpers'
	lineageTag: __TAG__

measure 'FN' = ```
		CALCULATE (
		    COUNTROWS ( ml_churn_scores_test ),
		    ml_churn_scores_test[actual_label] = 1,
		    ml_churn_scores_test[predicted_label] = 0
		)
	```
	formatString: '#,0'
	displayFolder: 'ML helpers'
	lineageTag: __TAG__

measure Precision = ```
		DIVIDE ( [TP], [TP] + [FP] )
	```
	formatString: '0.0%'
	displayFolder: ML
	lineageTag: __TAG__

measure Recall = ```
		DIVIDE ( [TP], [TP] + [FN] )
	```
	formatString: '0.0%'
	displayFolder: ML
	lineageTag: __TAG__

measure 'F1 Score' = ```
		DIVIDE ( 2 * [Precision] * [Recall], [Precision] + [Recall] )
	```
	formatString: '0.000'
	displayFolder: ML
	lineageTag: __TAG__

measure 'ROC-AUC' = ```
		CALCULATE (
		    MAX ( ml_test_metrics[value] ),
		    ml_test_metrics[model] = "churn",
		    ml_test_metrics[metric] = "roc_auc"
		)
	```
	formatString: '0.000'
	displayFolder: ML
	lineageTag: __TAG__

measure 'Saved Delivery R2' = ```
		CALCULATE (
		    MAX ( ml_test_metrics[value] ),
		    ml_test_metrics[model] = "delivery",
		    ml_test_metrics[metric] = "r2"
		)
	```
	formatString: '0.0000'
	displayFolder: ML
	lineageTag: __TAG__

measure 'Performance Score' = ```
		AVERAGE ( restaurant_performance[performance_score] )
	```
	formatString: '0.000'
	displayFolder: Restaurants
	lineageTag: __TAG__

measure 'Feature Importance' = ```
		SUM ( ml_delivery_feature_importance[importance] )
	```
	formatString: '0.0000'
	displayFolder: ML
	lineageTag: __TAG__

measure 'Churn Test Customers' = ```
		COUNTROWS ( ml_churn_scores_test )
	```
	formatString: '#,0'
	displayFolder: ML
	lineageTag: __TAG__

measure 'Saved Delivery RMSE' = ```
		CALCULATE (
		    MAX ( ml_test_metrics[value] ),
		    ml_test_metrics[model] = "delivery",
		    ml_test_metrics[metric] = "rmse"
		)
	```
	formatString: '0.000'
	displayFolder: ML
	lineageTag: __TAG__
'''


def measures_table() -> str:
    body = ["table _Measures", f"\tlineageTag: {tag('_Measures')}", ""]
    for block in MEASURES.strip().split("\nmeasure "):
        block = block.strip()
        if not block:
            continue
        if not block.startswith("measure "):
            block = "measure " + block
        name = block.split("=", 1)[0].replace("measure ", "").strip().strip("'")
        block = block.replace("lineageTag: __TAG__", f"lineageTag: {tag('measure.' + name)}", 1)
        indented = "\n".join("\t" + line if line else "" for line in block.splitlines())
        body.append(indented)
        body.append("")
    body.append("\tcolumn dummy")
    body.append("\t\tdataType: string")
    body.append(f"\t\tlineageTag: {tag('_Measures.dummy')}")
    body.append("\t\tsourceColumn: dummy")
    body.append("\t\tsummarizeBy: none")
    body.append("\t\tisHidden")
    body.append("")
    body.append("\t\tannotation SummarizationSetBy = Automatic")
    body.append("")
    body.append("\tpartition _Measures = m")
    body.append("\t\tmode: import")
    body.append("\t\tsource =")
    body.append('\t\t\tlet')
    body.append('\t\t\t    Source = #table({"dummy"}, {{""}})')
    body.append('\t\t\tin')
    body.append('\t\t\t    Source')
    body.append("")
    body.append("\tannotation PBI_ResultType = Table")
    body.append("")
    return "\n".join(body)


def write_project() -> None:
    model_dir = OUT / "zomato_dashboard.SemanticModel"
    table_dir = model_dir / "definition" / "tables"
    report_dir = OUT / "zomato_dashboard.Report"
    table_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    query_names = ["DataFolder", "_Measures", "dim_date"] + [name for name, _ in TABLES]
    (table_dir / "_Measures.tmdl").write_text(measures_table(), encoding="utf-8")
    print("  _Measures")
    for query, filename in TABLES:
        text, _ = table_file(query, filename)
        (table_dir / f"{query}.tmdl").write_text(text, encoding="utf-8")
        print(f"  {query} <- {filename}")
    (table_dir / "dim_date.tmdl").write_text(date_table(), encoding="utf-8")

    refs = "\n".join(
        f"ref table {name}" for name in ["_Measures", "dim_date"] + [n for n, _ in TABLES]
    )
    order = ", ".join(f'"{name}"' for name in query_names)
    model = f"""model Model
\tculture: en-US
\tdefaultPowerBIDataSourceVersion: powerBI_V3
\tsourceQueryCulture: en-US
\tdataAccessOptions
\t\tlegacyRedirects
\t\treturnErrorValuesAsNull

annotation __PBI_TimeIntelligenceEnabled = 0

annotation PBI_QueryOrder = [{order}]

{refs}
ref expression DataFolder
"""
    definition = model_dir / "definition"
    (definition / "model.tmdl").write_text(model, encoding="utf-8")
    (definition / "database.tmdl").write_text(
        "database\n\tcompatibilityLevel: 1567\n", encoding="utf-8"
    )
    (definition / "relationships.tmdl").write_text(relationships(), encoding="utf-8")
    (definition / "expressions.tmdl").write_text(
        "expression DataFolder =\n"
        f"\t\t{m_string(DATA_FOLDER)} meta [IsParameterQuery=true, Type=\"Text\", IsParameterQueryRequired=true]\n"
        f"\tlineageTag: {tag('DataFolder')}\n"
        "\n"
        "\tannotation PBI_ResultType = Text\n",
        encoding="utf-8",
    )

    (model_dir / "definition.pbism").write_text(
        """{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
  "version": "4.2",
  "settings": {}
}
""",
        encoding="utf-8",
    )
    (model_dir / ".platform").write_text(
        """{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
  "metadata": {
    "type": "SemanticModel",
    "displayName": "Zomato Dashboard"
  },
  "config": {
    "version": "2.0",
    "logicalId": "8f3c1a2e-6b47-4d1a-9c55-2e7b0a4d6f18"
  }
}
""",
        encoding="utf-8",
    )
    (OUT / "zomato_dashboard.pbip").write_text(
        """{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
  "version": "1.0",
  "artifacts": [
    {
      "report": {
        "path": "zomato_dashboard.Report"
      }
    }
  ],
  "settings": {
    "enableAutoRecovery": true
  }
}
""",
        encoding="utf-8",
    )
    (report_dir / "definition.pbir").write_text(
        """{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
  "version": "4.0",
  "datasetReference": {
    "byPath": {
      "path": "../zomato_dashboard.SemanticModel"
    }
  }
}
""",
        encoding="utf-8",
    )
    (report_dir / ".platform").write_text(
        """{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
  "metadata": {
    "type": "Report",
    "displayName": "Zomato Dashboard"
  },
  "config": {
    "version": "2.0",
    "logicalId": "c1d4e5f6-7a8b-4c9d-8e0f-1a2b3c4d5e6f"
  }
}
""",
        encoding="utf-8",
    )
    print(f"DataFolder = {DATA_FOLDER}")


if __name__ == "__main__":
    write_project()
    from build_report import write_report
    write_report()
