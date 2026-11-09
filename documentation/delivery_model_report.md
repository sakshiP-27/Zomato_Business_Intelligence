# Delivery Time Model Report — Week 3

**Generated:** 2026-11-08 12:10  
**Target:** `delivery_time_minutes`  
**KPI targets:** R² ≥ 0.75  |  RMSE ≤ 6.0 min  

---

## Dataset

| | |
|---|---|
| Rows (model_df) | 11,193 |
| Train (80%) | 8,954 |
| Test  (20%) | 2,239 |
| Numeric features | 23 |
| Categorical features | 6 |

## Feature List

**Numeric:**  
`order_hour`, `order_dayofweek`, `peak_hour`, `weekend_order`, `n_items`, `avg_prep_time`, `max_prep_time`, `basket_value`, `discount_pct`, `coupon_used`, `restaurant_rating`, `restaurant_popularity_rank`, `partner_rating`, `delivery_efficiency`, `partner_avg_delivery_time`, `completed_deliveries`, `is_cross_city`, `customer_tenure_days`, `rainfall`, `temperature`, `humidity`, `traffic_score`, `is_peak_and_rain`

**Categorical:**  
`restaurant_city`, `restaurant_cuisine`, `vehicle_type`, `weather_condition`, `membership`, `payment_method`

**Excluded (with reasons):**  
- `feedback_customer_rating`: post-delivery — unknown at order time
- `feedback_delivery_rating`: post-delivery — unknown at order time
- `feedback_food_rating`: post-delivery — unknown at order time
- `average_rating`: post-delivery — unknown at order time
- `sentiment`: post-delivery — unknown at order time
- `review`: post-delivery — free text
- `order_status`: every row is 'Delivered'; zero variance
- `order_id`: identifier — not a predictor
- `customer_id`: identifier — use customer attributes instead
- `restaurant_id`: identifier — use restaurant attributes instead
- `delivery_partner_id`: identifier — use partner attributes instead
- `final_amount`: future value: depends on delivery completing
- `distance_to_city_centre_km`: restaurant coordinates do not sit in their cities (median ~950 km from centre)

## Cross-Validation Comparison (training set, 5-fold)

| Model | CV MAE | CV RMSE | CV RMSE std | CV R² |
|---|---|---|---|---|
| Baseline (predict mean) | 7.979 | 9.944 | 0.067 | -0.0003 |
| Ridge Regression | 8.019 | 10.007 | 0.069 | -0.013 |
| Random Forest | 8.046 | 10.037 | 0.051 | -0.0191 |
| Gradient Boosting | 8.155 | 10.179 | 0.123 | -0.0482 |
| Decision Tree (depth=8) | 8.235 | 10.338 | 0.054 | -0.0813 |

## Hyperparameter Tuning

### Random Forest

- Before tuning: CV RMSE = 10.037
- After tuning:  CV RMSE = 9.951
- Best params: `{'model__n_estimators': 100, 'model__min_samples_leaf': 3, 'model__max_features': 'sqrt', 'model__max_depth': 8}`

### Gradient Boosting

- Before tuning: CV RMSE = 10.179
- After tuning:  CV RMSE = 9.956
- Best params: `{'model__subsample': 0.7, 'model__n_estimators': 100, 'model__min_samples_leaf': 5, 'model__max_depth': 3, 'model__learning_rate': 0.03}`


## Test Set Results

**Winner: Random Forest**  

| Metric | Value | KPI Target | Status |
|---|---|---|---|
| MAE | 7.84 min | — | On average prediction is off by 7.8 min |
| RMSE | 9.774 min | ≤ 6.0 min | ⚠️ below target |
| R² | -0.0022 | ≥ 0.75 | ⚠️ below target |

## Interpretation

On the test set the model is off by **7.8 minutes** on average (MAE), RMSE is **9.8 min** (does not meet the ≤6.0-minute target) and it explains **-0.2%** of the variation (R²). It does not beat the predict-the-mean baseline, so it has found no usable structure, linear or non-linear. Its predictions cluster around the mean (standard deviation 0.4 min, versus 9.8 min for actual delivery times).

### Error analysis (test set)

| Segment | Mean absolute error by group (min) | Difference between groups |
|---|---|---|
| peak_hour | 0: 7.8, 1: 7.9 | not significant (p=0.74) |
| vehicle_type | Car: 7.2, Bicycle: 7.6, Scooter: 7.7, Bike: 8.0 | not significant (p=0.31) |
| weather_condition | Rainy: 7.5, Foggy: 7.7, Cloudy: 7.9, Clear: 8.1, Humid: 8.4, Stormy: 8.5 | not significant (p=0.64) |
| restaurant_city | Delhi 6.9 (best) to Coimbatore 9.6 (worst) | not significant (p=0.28) |

The largest 5% of errors exceed 19 minutes. They come from deliveries far from the mean, which a model that predicts close to the mean misses.

### Feature importance (permutation, test set)

| Feature | Importance (RMSE min) | ± std | Direction | Beyond noise? |
|---|---|---|---|---|
| payment_method | 0.0050 | 0.0016 | categorical - no single direction | yes |
| restaurant_popularity_rank | 0.0048 | 0.0015 | no meaningful relationship (r=0.008) | yes |
| basket_value | 0.0037 | 0.0024 | no meaningful relationship (r=0.008) | no |
| restaurant_city | 0.0037 | 0.0020 | categorical - no single direction | no |
| partner_avg_delivery_time | 0.0034 | 0.0013 | higher values go with shorter delivery (r=-0.021) | yes |
| restaurant_cuisine | 0.0032 | 0.0020 | categorical - no single direction | no |
| humidity | 0.0027 | 0.0016 | no meaningful relationship (r=-0.012) | no |
| vehicle_type | 0.0018 | 0.0016 | categorical - no single direction | no |
| weather_condition | 0.0014 | 0.0009 | categorical - no single direction | no |
| partner_rating | 0.0011 | 0.0013 | no meaningful relationship (r=0.010) | no |

In plain language: shuffling any single feature changes test RMSE by at most 0.005 minutes, and only 3 of 29 features rise above noise. No feature can be named as a driver of delivery time on this dataset, so no operational recommendation is made from this model.

## Saved artefacts

- `models/delivery_time_model.joblib`
- `data/cleaned/ml_model_comparison_delivery.csv`
- `data/cleaned/ml_delivery_test_results.csv`
- `images/delivery_residuals.png`
- `images/delivery_feature_importance.png`
