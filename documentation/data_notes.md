# Data Notes — Step 1 Inspection
**Date inspected:** Day 1  
**Analyst:** Sakshi  
**Source folder:** `data/raw/`

---

## 12-File Summary

| # | File | Rows | Columns | Primary Key | ID Format | Notable Issues |
|---|------|------|---------|-------------|-----------|----------------|
| 1 | cities.csv | 25 | 5 | CityID | Plain INT (1–25) | Clean; official city list |
| 2 | customers.csv | 12,180 | 13 | CustomerID | Plain INT | Mixed date formats (5 variants); 120 null Gender, 120 null Membership; city name variants |
| 3 | restaurants.csv | 1,200 | 13 | RestaurantID | Plain INT | 12 null Cuisine; city name variants |
| 4 | delivery_partners.csv | 2,000 | 10 | DeliveryPartnerID | Plain INT | Mixed date formats (5 variants); city name variants |
| 5 | menu.csv | 8,997 | 8 | FoodItemID | Plain INT | Clean; Availability is Yes/No text |
| 6 | orders.csv | 20,705 | 15 | OrderID | INT starting at 100001 | Mixed date formats (4 variants); no promised delivery time column |
| 7 | order_items.csv | 42,378 | 6 | OrderItemID | Plain INT | Large table (~2 items per order avg) |
| 8 | payments.csv | 20,493 | 6 | PaymentID | Plain INT | 212 fewer rows than orders — some orders have no payment |
| 9 | customer_feedback.csv | 14,200 | 7 | FeedbackID | Plain INT | Fewer rows than orders — not all orders have feedback |
| 10 | promotions.csv | 300 | 6 | PromotionID | Plain INT | CouponCode must be UNIQUE for FK from orders |
| 11 | weather.csv | 18,264 | 7 | WeatherID | Plain INT | Mixed date formats (4 variants); 25 cities, clean |
| 12 | traffic.csv | 18,335 | 6 | TrafficID | Plain INT | Mixed date formats (4 variants); 147 null TrafficLevel |

---

## ID Format Notes

All 12 tables use **plain integer IDs** (no prefix like `C00123`). The schema should use `INT` or `BIGINT` for primary keys, not `VARCHAR`, except where the guide recommends VARCHAR as a precaution. Orders start at `100001` rather than `1` — use `INT` (fits comfortably within INT range).

---

## Distinct Values of Category Columns

### orders.csv
- **OrderStatus:** `Delivered` (11517), `Cancelled` (4625), `Food Not Delivered` (2386), `Delivered Late` (2177)
- **PaymentMethod:** `Debit Card`, `Net Banking`, `Cash on Delivery`, `UPI`, `Credit Card`, `Wallet`

### customers.csv
- **Membership:** `Basic` (7174), `Zomato Pro` (2490), `Gold` (2396), NULL (120)
- **Gender:** `Female` (4054), `Other` (4003), `Male` (4001), NULL (122)

### customer_feedback.csv
- **Sentiment:** `Positive` (7842), `Negative` (3601), `Neutral` (2757)

### delivery_partners.csv
- **VehicleType:** `Bike` (1126), `Scooter` (491), `Bicycle` (192), `Car` (191)
- **Gender:** `Male` (1003), `Female` (997)

### restaurants.csv
- **RestaurantType:** `Cloud Kitchen`, `Dine-in`, `Delivery Only`, `QSR`, `Dine-in & Delivery`
- **Cuisine:** 18 distinct cuisines (South Indian, Fast Food, Healthy Food, Street Food, Desserts, Continental, Seafood, Sushi, Pizza, Mughlai, Italian, BBQ, Burgers, Biryani, Mexican, North Indian, Chinese, Bakery, Thai) + 12 NULL

### menu.csv
- **Availability:** `Yes` (8060), `No` (937)

### weather.csv
- **WeatherCondition:** `Clear`, `Cloudy`, `Humid`, `Rainy`, `Foggy`, `Stormy`

### traffic.csv
- **TrafficLevel:** `Moderate`, `High`, `Low`, `Severe`, NULL (147)

### payments.csv
- **PaymentMethod:** same 6 values as orders
- **PaymentStatus:** `Success` (16372), `Failed` (1659), `Refunded` (1641), `Pending` (821)

---

## Date Format Findings

Multiple date formats appear across files — this is the biggest data-loading challenge.

| File | Column | DD-MM-YYYY | MM/DD/YYYY | YYYY.MM.DD | YYYY-MM-DD | DD Mon YYYY | Other |
|------|---------|-----------|-----------|-----------|-----------|------------|-------|
| orders.csv | OrderDate | 4,187 | 8,218 | 4,191 | 4,109 | 0 | 0 |
| customers.csv | RegistrationDate | 2,021 | 4,034 (=DD/MM/YYYY) | 2,052 | 2,030 | 2,043 | 0 |
| delivery_partners.csv | JoiningDate | 327 | 657 (=DD/MM/YYYY) | 346 | 329 | 341 | 0 |
| promotions.csv | StartDate | 61 | 117 | 59 | 63 | 0 | 0 |
| promotions.csv | EndDate | 61 | 118 | 51 | 70 | 0 | 0 |
| weather.csv | Date | 3,674 | 7,337 | 3,645 | 3,608 | 0 | 0 |
| traffic.csv | Date | 3,664 | 7,240 | 3,793 | 3,638 | 0 | 0 |
| payments.csv | PaymentDate | 4,169 | 8,163 | 4,136 | 4,025 | 0 | 0 |

**Important:** `customers` and `delivery_partners` have a 5th format: `DD Mon YYYY` (e.g. `28 Feb 2024`). The `parse_mixed_date()` function in `schema.sql` will need to handle this additional format.

---

## City Name Inconsistencies

`weather.csv` and `traffic.csv` use the **exact same 25 canonical city names** as `cities.csv` — no aliases needed for those two.

`customers.csv`, `restaurants.csv`, and `delivery_partners.csv` have **extensive** city name variants:

| Alias / Variant | Canonical (cities.csv) |
|----------------|------------------------|
| Bangalore, BANGALORE | Bengaluru |
| BENGALURU, bengaluru | Bengaluru |
| Bombay, MUMBAI, mumbai | Mumbai |
| Calcutta | Kolkata |
| Madras | Chennai |
| New Delhi | Delhi |
| Baroda | Vadodara |
| All-caps variants (DELHI, PUNE, etc.) | Title-case match (Delhi, Pune, etc.) |
| All-lowercase variants (delhi, pune, etc.) | Title-case match |

A `city_aliases` table will map all these variants to the canonical name (needed for FK loading).

---

## Observations Worth Noting

1. **No promised delivery time column.** `orders.csv` only has `DeliveryTimeMinutes` (actual). A "late" threshold must be defined by the analyst (see `kpi_definitions.md`).
2. **payments.csv has 212 fewer rows than orders.csv** (20,493 vs 20,705). Some orders — likely cancelled ones — have no payment record. This is expected.
3. **customer_feedback.csv has 6,505 fewer rows than orders.csv** (14,200 vs 20,705). Not every order generates feedback. Normal.
4. **order_items.csv has 42,378 rows for 20,705 orders** — average ~2 items per order.
5. **orders.OrderStatus** uses `Delivered Late` (not `Late`) and `Food Not Delivered` — use these exact strings in queries.
6. **All IDs are integers.** This is simpler than expected from the PRD hint about `C00123`-style IDs. The schema can use `INT` for all primary keys, but `VARCHAR(20)` is still safe and flexible if formats change.
