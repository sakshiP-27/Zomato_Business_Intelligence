"""Six Week 4 dashboard pages for zomato_dashboard.pbip.

Pages are written in the enhanced report format (a definition folder).
Power BI Desktop from September 2026 onward opens that format.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

OUT = Path(__file__).resolve().parent / "zomato_dashboard.Report"

REPORT_CONFIG = {
    "version": "5.43",
    "themeCollection": {"baseTheme": {"name": "CY24SU06", "type": 2}},
    "activeSectionIndex": 0,
    "defaultDrillFilterOtherVisuals": True,
    "settings": {
        "useStylableVisualContainerHeader": True,
        "exportDataMode": 1,
        "useEnhancedTooltips": True,
    },
    "objects": {},
}


def literal(text: str) -> dict:
    escaped = text.replace("'", "''")
    return {"expr": {"Literal": {"Value": f"'{escaped}'"}}}


def title_objects(title: str) -> dict:
    return {
        "title": [{
            "properties": {
                "show": {"expr": {"Literal": {"Value": "true"}}},
                "text": literal(title),
            }
        }]
    }


def measure_select(alias: str, entity: str, name: str) -> dict:
    return {
        "Measure": {
            "Expression": {"SourceRef": {"Source": alias}},
            "Property": name,
        },
        "Name": f"{entity}.{name}",
        "NativeReferenceName": name,
    }


def column_select(alias: str, entity: str, name: str) -> dict:
    return {
        "Column": {
            "Expression": {"SourceRef": {"Source": alias}},
            "Property": name,
        },
        "Name": f"{entity}.{name}",
        "NativeReferenceName": name,
    }


def visual(name, x, y, w, h, z, visual_type, bindings, title=None, text=None, font_size="12px"):
    """bindings: list of (role, kind, entity, field). kind is 'm' or 'c'."""
    single = {"visualType": visual_type, "drillFilterOtherVisuals": True}
    if text is not None:
        single["objects"] = {
            "general": [{
                "properties": {
                    "paragraphs": [{
                        "textRuns": [{
                            "value": text,
                            "textStyle": {"fontFamily": "Segoe UI", "fontSize": font_size},
                        }]
                    }]
                }
            }]
        }
    else:
        aliases = {}
        from_list = []
        selects = []
        projections = {}
        for role, kind, entity, field in bindings:
            if entity not in aliases:
                aliases[entity] = f"e{len(aliases)}"
                from_list.append({"Name": aliases[entity], "Entity": entity, "Type": 0})
            alias = aliases[entity]
            if kind == "m":
                selects.append(measure_select(alias, entity, field))
            else:
                selects.append(column_select(alias, entity, field))
            projections.setdefault(role, []).append({"queryRef": f"{entity}.{field}"})
        single["projections"] = projections
        single["prototypeQuery"] = {"Version": 2, "From": from_list, "Select": selects}
        if title:
            single["vcObjects"] = title_objects(title)
    config = {
        "name": name,
        "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": z, "width": w, "height": h}}],
        "singleVisual": single,
    }
    return {
        "config": json.dumps(config, ensure_ascii=False),
        "filters": "[]",
        "x": x, "y": y, "z": z, "width": w, "height": h,
    }


def card(name, x, measure, title):
    return visual(name, x, 48, 200, 88, 1, "card", [("Values", "m", "_Measures", measure)], title)


def slicer(name, x, y, entity, field, title, w=220):
    return visual(name, x, y, w, 70, 2, "slicer", [("Values", "c", entity, field)], title)


def page(name, display, visuals):
    return {
        "name": name,
        "displayName": display,
        "displayOption": 1,
        "height": 840,
        "width": 1280,
        "ordinal": 0,
        "visualContainers": visuals,
    }


def object_name(seed: str) -> str:
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:20]


def prototype_to_query_state(single: dict) -> dict:
    query = single["prototypeQuery"]
    alias_entity = {item["Name"]: item["Entity"] for item in query["From"]}
    role_by_ref = {
        item["queryRef"]: role
        for role, items in single["projections"].items()
        for item in items
    }
    state = {}
    for selected in query["Select"]:
        ref = selected["Name"]
        role = role_by_ref[ref]
        if "Measure" in selected:
            node = selected["Measure"]
            kind = "Measure"
        else:
            node = selected["Column"]
            kind = "Column"
        entity = alias_entity[node["Expression"]["SourceRef"]["Source"]]
        state.setdefault(role, {"projections": []})
        state[role]["projections"].append({
            "field": {
                kind: {
                    "Expression": {"SourceRef": {"Entity": entity}},
                    "Property": node["Property"],
                }
            },
            "queryRef": ref,
            "nativeQueryRef": selected["NativeReferenceName"],
        })
    return state


def write_report() -> None:
    pages = []

    pages.append(page("ExecutiveDashboard", "Executive Dashboard", [
        visual("ex_title", 16, 8, 900, 32, 0, "textbox", [], text="Executive Dashboard  ·  completed orders only for revenue"),
        card("ex_rev", 16, "Total Revenue", "Total revenue"),
        card("ex_ord", 224, "Total Orders", "Total orders"),
        card("ex_dt", 432, "Avg Delivery Time", "Avg delivery time (min)"),
        card("ex_rate", 640, "Avg Rating", "Avg rating"),
        card("ex_act", 848, "Active Customers (60d)", "Active customers, 60 days"),
        card("ex_late", 1056, "Late Delivery %", "Late delivery %"),
        slicer("ex_city", 16, 148, "dim_city", "city", "Restaurant city"),
        slicer("ex_date", 250, 148, "dim_date", "date", "Order date", 280),
        visual("ex_hour", 16, 232, 420, 466, 3, "clusteredColumnChart", [
            ("Category", "c", "fact_orders", "order_hour"),
            ("Y", "m", "_Measures", "Total Orders"),
        ], "Orders by hour"),
        visual("ex_citybar", 448, 232, 420, 466, 3, "clusteredBarChart", [
            ("Category", "c", "dim_city", "city"),
            ("Y", "m", "_Measures", "Total Revenue"),
        ], "Revenue by restaurant city"),
        visual("ex_status", 880, 232, 380, 466, 3, "donutChart", [
            ("Category", "c", "fact_orders", "order_status"),
            ("Y", "m", "_Measures", "Total Orders"),
        ], "Orders by status"),
        visual("ex_note", 16, 710, 1240, 110, 4, "textbox", [], font_size="10px", text=(
            "Revenue is final amount on Delivered and Delivered Late orders with a positive amount "
            "(Week 1 definition): ₹52.36 lakh across 13,351 orders. Cancellation rate is 22.3%. "
            "Late delivery % uses is_late and ignores blank times. Active customers ordered after 2024-11-01. "
            "Hover titles are the takeaway; axis names come from the fields."
        )),
    ]))

    pages.append(page("CustomerAnalytics", "Customer Analytics", [
        visual("cu_title", 16, 8, 1000, 32, 0, "textbox", [], text="Customer Analytics  ·  segments are as of 2024-12-31 and do not follow the date slicer"),
        card("cu_n", 16, "Customer Rows", "Registered customers"),
        card("cu_rep", 224, "Repeat Customer %", "Customers with 2+ orders"),
        card("cu_ret", 432, "Avg Monthly Retention", "Avg monthly retention"),
        card("cu_clv", 640, "Average CLV", "Average CLV"),
        slicer("cu_city", 16, 148, "dim_customers", "city", "Customer city"),
        slicer("cu_mem", 250, 148, "dim_customers", "membership", "Membership"),
        slicer("cu_date", 484, 148, "dim_date", "date", "Registration / order date", 280),
        visual("cu_seg", 16, 232, 620, 466, 3, "clusteredBarChart", [
            ("Category", "c", "dim_customers", "customer_segment"),
            ("Y", "m", "_Measures", "Customer Rows"),
        ], "New, Repeat, and At-risk"),
        visual("cu_growth", 652, 232, 600, 466, 3, "clusteredColumnChart", [
            ("Category", "c", "dim_date", "Month"),
            ("Y", "m", "_Measures", "New Customers"),
        ], "New registrations by month"),
        visual("cu_note", 16, 710, 1240, 110, 4, "textbox", [], font_size="10px", text=(
            "New = first order within 60 days of 31 Dec 2024. At-risk = not new, and quiet for more than 30 days. "
            "Repeat = ordered within the last 30 days and is not new. Never ordered = no non-cancelled order. "
            "Counts on the rebuilt file: At-risk 7,979, Never ordered 3,182, Repeat 479, New 360. "
            "At-risk starts earlier than the 60-day churn label."
        )),
    ]))

    pages.append(page("RestaurantAnalytics", "Restaurant Analytics", [
        visual("re_title", 16, 8, 1100, 32, 0, "textbox", [], text="Restaurant Analytics  ·  score is from the SQL view, ranked inside each city, minimum 10 orders"),
        slicer("re_city", 16, 48, "restaurant_performance", "city", "Restaurant city (score table)"),
        slicer("re_cui", 250, 48, "dim_restaurants", "cuisine", "Cuisine"),
        visual("re_score", 16, 132, 620, 566, 3, "clusteredBarChart", [
            ("Category", "c", "restaurant_performance", "restaurant_name"),
            ("Y", "m", "_Measures", "Performance Score"),
        ], "Performance score by restaurant"),
        visual("re_rev", 652, 132, 600, 566, 3, "clusteredColumnChart", [
            ("Category", "c", "fact_orders", "restaurant_cuisine"),
            ("Y", "m", "_Measures", "Total Revenue"),
        ], "Revenue by cuisine"),
        visual("re_note", 16, 710, 1240, 110, 4, "textbox", [], font_size="10px", text=(
            "The date slicer does not change the score: it was calculated once for the whole period in v_restaurant_performance. "
            "Filter this page with the score table's city, not dim_city. dim_city is linked only to orders, so a second city path would be ambiguous. "
            "Lowest scores on the export include Royal Grill (Delhi, score 0.054, cancel rate 37.5%) and Royal Kitchen (Visakhapatnam, 0.084, 40%). "
            "Highest include Green Corner (Chandigarh, 0.988, cancel rate 9.1%). Apply a Top N filter of 10 in Desktop for the short list."
        )),
    ]))

    pages.append(page("DeliveryAnalytics", "Delivery Analytics", [
        visual("de_title", 16, 8, 1000, 32, 0, "textbox", [], text="Delivery Analytics  ·  completed orders with a positive delivery time"),
        card("de_avg", 16, "Avg Delivery Time", "Avg delivery time (min)"),
        card("de_p90", 224, "P90 Delivery Time", "P90 delivery time (min)"),
        card("de_late", 432, "Late Delivery %", "Late delivery %"),
        slicer("de_city", 16, 148, "dim_city", "city", "Restaurant city"),
        slicer("de_date", 250, 148, "dim_date", "date", "Order date", 260),
        slicer("de_veh", 524, 148, "fact_orders", "vehicle_type", "Vehicle type"),
        visual("de_month", 16, 232, 620, 466, 3, "lineChart", [
            ("Category", "c", "dim_date", "Month"),
            ("Y", "m", "_Measures", "Avg Delivery Time"),
        ], "Average delivery time by month"),
        visual("de_rain", 652, 232, 600, 466, 3, "clusteredBarChart", [
            ("Category", "c", "fact_orders", "rain_impact"),
            ("Y", "m", "_Measures", "Avg Delivery Time"),
        ], "Average delivery time by rain"),
        visual("de_note", 16, 710, 1240, 110, 4, "textbox", [], font_size="10px", text=(
            "On completed orders the average is 40.1 minutes and the 90th percentile is 61 minutes. "
            "24.9% of those orders exceed 45 minutes. The is_late card is wider: 20.7% of every order that has a usable time. "
            "EDA found no significant delivery-time difference by city, traffic, or weather. Traffic matched only 5.1% of valid deliveries. "
            "Do not staff extra partners from this chart alone. Rain is sorted None, Light, Moderate, Heavy."
        )),
    ]))

    pages.append(page("SalesDashboard", "Sales Dashboard", [
        visual("sa_title", 16, 8, 900, 32, 0, "textbox", [], text="Sales Dashboard  ·  revenue uses Delivered and Delivered Late"),
        card("sa_rev", 16, "Total Revenue", "Total revenue"),
        card("sa_aov", 224, "Avg Order Value", "Avg order value"),
        card("sa_coup", 432, "Coupon Usage %", "Coupon usage %"),
        card("sa_disc", 640, "Total Discount", "Total discount"),
        card("sa_fail", 848, "Payment Failure Rate", "Payment failure rate"),
        slicer("sa_city", 16, 148, "dim_city", "city", "Restaurant city"),
        slicer("sa_date", 250, 148, "dim_date", "date", "Order date", 260),
        slicer("sa_pay", 524, 148, "fact_orders", "payment_method", "Payment method"),
        visual("sa_month", 16, 232, 620, 466, 3, "lineChart", [
            ("Category", "c", "dim_date", "Month"),
            ("Y", "m", "_Measures", "Total Revenue"),
        ], "Monthly revenue"),
        visual("sa_method", 652, 232, 600, 466, 3, "donutChart", [
            ("Category", "c", "fact_orders", "payment_method"),
            ("Y", "m", "_Measures", "Total Orders"),
        ], "Orders by payment method"),
        visual("sa_note", 16, 710, 1240, 110, 4, "textbox", [], font_size="10px", text=(
            "Delivered revenue is flat: monthly totals sit between ₹1.60 lakh and ₹2.06 lakh, and 2024 is +0.4% versus 2023. "
            "Kolkata leads delivered revenue at ₹2.02 lakh. South Indian leads cuisine at ₹3.07 lakh. "
            "Payment methods each hold about 16–17% of orders. Failed payments are 1,655 of 20,469 (8.1%). "
            "Coupon codes are present on 35.2% of orders."
        )),
    ]))

    pages.append(page("MLDashboard", "ML Dashboard", [
        visual("ml_title", 16, 8, 1200, 32, 0, "textbox", [], text="ML Dashboard  ·  test set only  ·  association, not cause"),
        card("ml_mae", 16, "MAE", "Delivery MAE (min)"),
        card("ml_rmse", 224, "RMSE", "Delivery RMSE (min)"),
        card("ml_r2", 432, "R2", "Delivery R²"),
        card("ml_f1", 640, "F1 Score", "Churn F1"),
        card("ml_auc", 848, "ROC-AUC", "Churn ROC-AUC"),
        card("ml_rec", 1056, "Recall", "Churn recall"),
        slicer("ml_city", 16, 148, "dim_city", "city", "Restaurant city (delivery)"),
        slicer("ml_ccity", 250, 148, "dim_customers", "city", "Customer city (churn)"),
        slicer("ml_risk", 484, 148, "ml_churn_scores_test", "risk_segment", "Risk segment"),
        visual("ml_imp", 16, 232, 620, 466, 3, "clusteredBarChart", [
            ("Category", "c", "ml_delivery_feature_importance", "feature"),
            ("Y", "m", "_Measures", "Feature Importance"),
        ], "Delivery feature importance (test RMSE)"),
        visual("ml_riskbar", 652, 232, 600, 466, 3, "clusteredBarChart", [
            ("Category", "c", "ml_churn_scores_test", "risk_segment"),
            ("Y", "m", "_Measures", "Churn Test Customers"),
        ], "Test customers by churn risk band"),
        visual("ml_note", 16, 710, 1240, 110, 4, "textbox", [], font_size="10px", text=(
            "Delivery model: Random Forest, test R² −0.0022, RMSE 9.774 minutes, target was R² ≥ 0.75 and RMSE ≤ 6. "
            "It does not beat predicting the mean. Shuffling any feature changes RMSE by at most a few thousandths of a minute. "
            "Churn model: 87.4% of customers have no order in the 60 days after 1 Nov 2024. Test F1 is 0.9326, the same as predicting that everyone churns. "
            "ROC-AUC is 0.514. Risk bands do not separate churners (about 86–89% in every band). Do not run a win-back campaign from these scores."
        )),
    ]))

    for i, item in enumerate(pages):
        item["ordinal"] = i

    definition = OUT / "definition"
    if definition.exists():
        shutil.rmtree(definition)
    pages_dir = definition / "pages"
    pages_dir.mkdir(parents=True)
    page_ids = []
    for item in pages:
        page_id = object_name(item["name"])
        page_ids.append(page_id)
        page_dir = pages_dir / page_id
        visuals_dir = page_dir / "visuals"
        visuals_dir.mkdir(parents=True)
        page_json = {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json",
            "name": page_id,
            "displayName": item["displayName"],
            "displayOption": "FitToPage",
            "height": item["height"],
            "width": item["width"],
        }
        (page_dir / "page.json").write_text(
            json.dumps(page_json, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        for container in item["visualContainers"]:
            config = json.loads(container["config"])
            single = config["singleVisual"]
            visual_id = object_name(config["name"])
            visual_body = {
                "visualType": single["visualType"],
                "drillFilterOtherVisuals": True,
            }
            if "objects" in single:
                visual_body["objects"] = single["objects"]
            if "prototypeQuery" in single:
                visual_body["query"] = {"queryState": prototype_to_query_state(single)}
            if "vcObjects" in single:
                visual_body["visualContainerObjects"] = single["vcObjects"]
            position = config["layouts"][0]["position"]
            visual_json = {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.7.0/schema.json",
                "name": visual_id,
                "position": {
                    "x": position["x"],
                    "y": position["y"],
                    "z": position["z"],
                    "height": position["height"],
                    "width": position["width"],
                    "tabOrder": position["z"],
                },
                "visual": visual_body,
            }
            visual_dir = visuals_dir / visual_id
            visual_dir.mkdir()
            (visual_dir / "visual.json").write_text(
                json.dumps(visual_json, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    (definition / "version.json").write_text(
        json.dumps({
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
            "version": "2.0.0",
        }, indent=2),
        encoding="utf-8",
    )
    (definition / "report.json").write_text(
        json.dumps({
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.2.0/schema.json",
            "themeCollection": {
                "baseTheme": {
                    "name": "CY24SU06",
                    "reportVersionAtImport": {
                        "visual": "2.7.0",
                        "report": "3.2.0",
                        "page": "2.1.0",
                    },
                    "type": "SharedResources",
                }
            },
            "resourcePackages": [{
                "name": "SharedResources",
                "type": "SharedResources",
                "items": [{
                    "name": "CY24SU06",
                    "path": "BaseThemes/CY24SU06.json",
                    "type": "BaseTheme",
                }],
            }],
            "settings": {
                "useStylableVisualContainerHeader": True,
                "exportDataMode": "AllowSummarized",
                "defaultDrillFilterOtherVisuals": True,
                "useEnhancedTooltips": True,
            },
        }, indent=2),
        encoding="utf-8",
    )
    (pages_dir / "pages.json").write_text(
        json.dumps({
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json",
            "pageOrder": page_ids,
            "activePageName": page_ids[0],
        }, indent=2),
        encoding="utf-8",
    )
    legacy = OUT / "report.json"
    if legacy.exists():
        legacy.unlink()
    print(f"  definition/  ({len(pages)} pages)")


if __name__ == "__main__":
    write_report()
