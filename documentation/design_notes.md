# ER Diagram & Database Design Notes — Step 2

**Date:** Day 1  
**ER Diagram file:** `images/er_diagram.svg`

---

## The 12 Tables and Their Relationships

| Table | Primary Key | Foreign Keys (points to) |
|-------|-------------|--------------------------|
| cities | city_id (INT) | — (root table) |
| customers | customer_id (INT) | city → cities(city) |
| restaurants | restaurant_id (INT) | city → cities(city) |
| delivery_partners | delivery_partner_id (INT) | city → cities(city) |
| promotions | promotion_id (INT) | — (coupon_code is UNIQUE for FK target) |
| weather | weather_id (INT) | city → cities(city) |
| traffic | traffic_id (INT) | city → cities(city) |
| menu | food_item_id (INT) | restaurant_id → restaurants(restaurant_id) |
| orders | order_id (INT) | customer_id → customers, restaurant_id → restaurants, delivery_partner_id → delivery_partners, coupon_code → promotions(coupon_code) |
| order_items | order_item_id (INT) | order_id → orders, food_item_id → menu |
| payments | payment_id (INT) | order_id → orders |
| customer_feedback | feedback_id (INT) | order_id → orders |

**Schema load order** (parent before child, required for FK constraints to succeed):
1. cities
2. customers, restaurants, delivery_partners, promotions, weather, traffic  *(all depend on cities)*
3. menu  *(depends on restaurants)*
4. orders  *(depends on customers, restaurants, delivery_partners, promotions)*
5. order_items  *(depends on orders and menu)*
6. payments, customer_feedback  *(both depend on orders)*

---

## Design Decision: cities.city_id vs cities.city as the FK target

**The problem discovered:** The PRD defines `cities.city_id` as the primary key, but every other table stores the city *name* (e.g. `"Mumbai"`, `"Delhi"`) and links to it. A SQL foreign key can only point at a column declared `UNIQUE` or `PRIMARY KEY`. If we link on `city_id`, every child table would need an extra `city_id INT` column that doesn't exist in the raw data — that requires a lookup join during every load.

**Decision: keep `city` as the FK target.** The `cities` table has both:
- `city_id INT PRIMARY KEY` — the integer surrogate key
- `city VARCHAR(60) NOT NULL UNIQUE` — the natural key and FK target

All five tables that reference cities (`customers`, `restaurants`, `delivery_partners`, `weather`, `traffic`) store the city name and declare `FOREIGN KEY (city) REFERENCES cities(city)`.

**Why this is correct:**
- SQL allows a FK to point at any `UNIQUE NOT NULL` column, not just the PK.
- It keeps queries readable — `WHERE city = 'Mumbai'` instead of a join through `city_id`.
- It matches the raw CSV data exactly (the CSVs store city names, not integer IDs).

**What this requires:** City name variants (BANGALORE, Bombay, Calcutta, etc.) must be standardised to the canonical spelling before the FK constraint is enforced. This is done via a `city_aliases` mapping table during the staging → production load (Step 6b).

---

## Why `order_items` is a Separate Table

One order contains multiple food items. If we stored items as columns in `orders` (e.g. `item1`, `item2`, `item3`) we'd need to know the maximum number of items in advance and most columns would be NULL. Separating it into `order_items` (one row per item per order) is **1st Normal Form** — no repeating groups.

This is also what makes queries like "most ordered food item" or "revenue contribution per category" straightforward aggregations.

---

## Why `menu` is a Separate Table

A food item has its own attributes — price, calories, preparation time — that belong to the item, not the restaurant. If we embedded these in `restaurants`, the same item at a restaurant would mean duplicating rows. `menu` links to `restaurants` via `restaurant_id`, making it a clean 1:N relationship (one restaurant, many menu items).

---

## City is the Join Path for "Orders by City"

`orders` has no `city` column. The city of an order is derived through the **restaurant**: `orders.restaurant_id → restaurants.restaurant_id → restaurants.city`. This is the canonical join path to use in all city-level analyses.

An alternative would be via `orders.customer_id → customers.city`, but the customer's registered city may differ from where they actually placed the order. Using the restaurant's city is more reliable for delivery-time analysis.

This decision is documented here and must be applied consistently in Weeks 2–4.

---

## Nullable vs. NOT NULL Decisions

| Column | Nullable? | Reason |
|--------|-----------|--------|
| orders.delivery_partner_id | NULL allowed | Cancelled orders may have no assigned partner |
| orders.coupon_code | NULL allowed | Most orders have no coupon (only ~300 promotions for 20k orders) |
| orders.order_status | NOT NULL | Every order must have a status |
| orders.customer_id | NOT NULL | Every order must belong to a customer |
| orders.restaurant_id | NOT NULL | Every order must come from a restaurant |
| customers.city | NOT NULL (after alias resolution) | Needed for FK constraint |
| ratings | NULL allowed | Not all feedback rows have all three ratings |

No `CHECK (value > 0)` constraints on numeric columns for now — the data contains intentional negatives and zeroes that need to be *studied*, not rejected. Constraints will be tightened after Week 2 cleaning.

---

## All IDs are Plain Integers

The PRD hint suggested IDs might be text like `C00123`. In reality, all 12 tables use plain integer IDs (confirmed in Step 1). The schema uses `INT` for all primary keys. `orders.order_id` starts at 100001 (not 1), which is fine for `INT`.

---

## dbdiagram.io Source (for regenerating the diagram)

Paste this into [dbdiagram.io](https://dbdiagram.io) to regenerate an editable version:

```
Table cities {
  city_id int [pk]
  city varchar(60) [unique, not null]
  population bigint
  region varchar(40)
  average_income numeric
}

Table customers {
  customer_id int [pk]
  name varchar(100)
  age smallint
  gender varchar(20)
  phone varchar(20)
  email varchar(120)
  city varchar(60) [ref: > cities.city, not null]
  state varchar(60)
  pincode varchar(10)
  registration_date date
  membership varchar(30)
  total_orders int
  preferred_cuisine varchar(60)
}

Table restaurants {
  restaurant_id int [pk]
  restaurant_name varchar(150)
  cuisine varchar(50)
  city varchar(60) [ref: > cities.city, not null]
  area varchar(100)
  opening_time time
  closing_time time
  rating numeric
  average_cost numeric
  owner_name varchar(150)
  restaurant_type varchar(50)
  latitude numeric
  longitude numeric
}

Table delivery_partners {
  delivery_partner_id int [pk]
  name varchar(100)
  age smallint
  gender varchar(20)
  vehicle_type varchar(30)
  joining_date date
  city varchar(60) [ref: > cities.city, not null]
  rating numeric
  completed_deliveries int
  average_delivery_time numeric
}

Table promotions {
  promotion_id int [pk]
  coupon_code varchar(30) [unique, not null]
  discount_percentage smallint
  campaign_name varchar(100)
  start_date date
  end_date date
}

Table menu {
  food_item_id int [pk]
  restaurant_id int [ref: > restaurants.restaurant_id, not null]
  food_name varchar(100)
  category varchar(50)
  price numeric
  preparation_time smallint
  calories smallint
  availability varchar(5)
}

Table orders {
  order_id int [pk]
  customer_id int [ref: > customers.customer_id, not null]
  restaurant_id int [ref: > restaurants.restaurant_id, not null]
  delivery_partner_id int [ref: > delivery_partners.delivery_partner_id]
  order_date date
  order_time time
  delivery_time_minutes numeric
  food_cost numeric
  delivery_fee numeric
  discount numeric
  coupon_code varchar(30) [ref: > promotions.coupon_code]
  gst numeric
  final_amount numeric
  order_status varchar(30)
  payment_method varchar(30)
}

Table order_items {
  order_item_id int [pk]
  order_id int [ref: > orders.order_id, not null]
  food_item_id int [ref: > menu.food_item_id, not null]
  quantity smallint
  unit_price numeric
  total_price numeric
}

Table payments {
  payment_id int [pk]
  order_id int [ref: > orders.order_id, not null]
  payment_method varchar(30)
  payment_status varchar(20)
  transaction_id varchar(30)
  payment_date date
}

Table customer_feedback {
  feedback_id int [pk]
  order_id int [ref: > orders.order_id, not null]
  customer_rating smallint
  delivery_rating smallint
  food_rating smallint
  review text
  sentiment varchar(20)
}

Table weather {
  weather_id int [pk]
  city varchar(60) [ref: > cities.city, not null]
  date date
  temperature numeric
  rainfall numeric
  humidity smallint
  weather_condition varchar(30)
}

Table traffic {
  traffic_id int [pk]
  city varchar(60) [ref: > cities.city, not null]
  date date
  time time
  traffic_level varchar(20)
  average_speed numeric
}
```
