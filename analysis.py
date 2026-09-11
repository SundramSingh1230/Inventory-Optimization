"""
analysis.py
-----------
Phase 2 — Python analysis on top of the SQLite database created by
generate_data.py.

What it does:
  1. Loads tables from SQLite into pandas
  2. Cleans / validates the data
  3. EDA: monthly demand trend, demand by category
  4. Forecasts next month's demand per product (simple moving average
     + exponential smoothing, picks whichever fits recent data better)
  5. Recommends safety stock & reorder point per product/warehouse
     based on demand variability and supplier lead time
  6. Flags at-risk SKUs (current stock vs recommended reorder point)
  7. Writes:
       output/monthly_demand_by_category.png
       output/forecast_vs_actual_top_products.png
       output/reorder_recommendations.csv
       output/at_risk_skus.csv

Run:
  python analysis.py
"""

import os
import sqlite3
import warnings

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")

os.makedirs("output", exist_ok=True)

# ----------------------------------------------------------------------
# 1. LOAD
# ----------------------------------------------------------------------
conn = sqlite3.connect("data/supply_chain.db")
orders = pd.read_sql_query("SELECT * FROM orders", conn, parse_dates=["order_date", "ship_date"])
products = pd.read_sql_query("SELECT * FROM products", conn)
inventory = pd.read_sql_query("SELECT * FROM inventory", conn)
suppliers = pd.read_sql_query("SELECT * FROM suppliers", conn)
warehouses = pd.read_sql_query("SELECT * FROM warehouses", conn)
conn.close()

# ----------------------------------------------------------------------
# 2. CLEAN
# ----------------------------------------------------------------------
before = len(orders)
orders = orders.drop_duplicates(subset="order_id")
orders = orders.dropna(subset=["order_date", "product_id", "qty"])
orders = orders[orders["qty"] > 0]
print(f"Cleaning: dropped {before - len(orders)} invalid/duplicate order rows "
      f"({len(orders)} remain)")

fulfilled = orders[orders["status"] == "Fulfilled"].copy()

# ----------------------------------------------------------------------
# 3. EDA — monthly demand by category
# ----------------------------------------------------------------------
fulfilled = fulfilled.merge(products[["product_id", "category", "product_name"]], on="product_id")
fulfilled["order_month"] = fulfilled["order_date"].dt.to_period("M").dt.to_timestamp()

monthly_cat = (
    fulfilled.groupby(["order_month", "category"])["qty"]
    .sum()
    .reset_index()
    .pivot(index="order_month", columns="category", values="qty")
    .fillna(0)
)

ax = monthly_cat.plot(figsize=(10, 6), marker="o")
ax.set_title("Monthly Units Ordered by Category")
ax.set_xlabel("Month")
ax.set_ylabel("Units Ordered")
plt.tight_layout()
plt.savefig("output/monthly_demand_by_category.png", dpi=150)
plt.close()
print("Saved output/monthly_demand_by_category.png")

# ----------------------------------------------------------------------
# 4. FORECAST next month's demand per product
#    Method: 3-month moving average AND simple exponential smoothing,
#    evaluated on the last 3 known months; the better one (lower MAE)
#    is used to project the next month.
# ----------------------------------------------------------------------
monthly_product = (
    fulfilled.groupby(["order_month", "product_id"])["qty"].sum().reset_index()
)

def moving_average_forecast(series, window=3):
    return series.rolling(window).mean()

def exp_smoothing_forecast(series, alpha=0.4):
    result = [series.iloc[0]]
    for val in series.iloc[1:]:
        result.append(alpha * val + (1 - alpha) * result[-1])
    return pd.Series(result, index=series.index)

forecast_rows = []
for pid, grp in monthly_product.groupby("product_id"):
    grp = grp.sort_values("order_month").reset_index(drop=True)
    if len(grp) < 4:
        continue  # not enough history to evaluate a method

    actual = grp["qty"]
    ma = moving_average_forecast(actual)
    es = exp_smoothing_forecast(actual)

    # evaluate on the last 3 periods where both have a prior-period prediction
    eval_idx = actual.index[-3:]
    ma_shifted = ma.shift(1)
    es_shifted = es.shift(1)
    ma_mae = (actual.loc[eval_idx] - ma_shifted.loc[eval_idx]).abs().mean()
    es_mae = (actual.loc[eval_idx] - es_shifted.loc[eval_idx]).abs().mean()

    if np.isnan(ma_mae) or es_mae <= ma_mae:
        method = "exp_smoothing"
        next_forecast = es.iloc[-1]  # last smoothed value = best estimate going forward
        mae = es_mae
    else:
        method = "moving_average"
        next_forecast = actual.tail(3).mean()
        mae = ma_mae

    forecast_rows.append({
        "product_id": pid,
        "method_used": method,
        "avg_monthly_demand_recent": round(actual.tail(3).mean(), 1),
        "forecast_next_month": round(next_forecast, 1),
        "forecast_mae": round(mae, 2) if not np.isnan(mae) else None,
        "demand_std_dev": round(actual.std(), 2),
    })

forecast_df = pd.DataFrame(forecast_rows).merge(
    products[["product_id", "product_name", "category"]], on="product_id"
)

# quick visual: forecast vs actual for the 4 highest-volume products
top4 = (
    monthly_product.groupby("product_id")["qty"].sum().sort_values(ascending=False).head(4).index
)
fig, axes = plt.subplots(2, 2, figsize=(11, 7))
for ax, pid in zip(axes.ravel(), top4):
    grp = monthly_product[monthly_product.product_id == pid].sort_values("order_month")
    name = products.loc[products.product_id == pid, "product_name"].values[0]
    ax.plot(grp["order_month"], grp["qty"], marker="o", label="Actual")
    ax.plot(grp["order_month"], moving_average_forecast(grp["qty"].reset_index(drop=True)).values,
             linestyle="--", label="3-mo Moving Avg")
    ax.set_title(name, fontsize=10)
    ax.tick_params(axis="x", rotation=45)
    ax.legend(fontsize=8)
plt.tight_layout()
plt.savefig("output/forecast_vs_actual_top_products.png", dpi=150)
plt.close()
print("Saved output/forecast_vs_actual_top_products.png")

# ----------------------------------------------------------------------
# 5. SAFETY STOCK & REORDER POINT RECOMMENDATIONS
#    Computed at product x warehouse level, since that's the level at
#    which reorder decisions actually get made.
#    Safety stock = Z * std_dev(daily demand) * sqrt(lead_time_days)
#    Reorder point = (avg_daily_demand * lead_time_days) + safety_stock
#    Z = 1.65 for ~95% service level
# ----------------------------------------------------------------------
Z = 1.65

fulfilled["order_day"] = fulfilled["order_date"].dt.date
daily_demand = (
    fulfilled.groupby(["product_id", "warehouse_id", "order_day"])["qty"].sum().reset_index()
    .rename(columns={"qty": "daily_qty"})
)
demand_stats = daily_demand.groupby(["product_id", "warehouse_id"])["daily_qty"].agg(
    avg_daily_demand="mean", std_daily_demand="std"
).reset_index()
demand_stats["std_daily_demand"] = demand_stats["std_daily_demand"].fillna(0)

reco = demand_stats.merge(suppliers[["product_id", "supplier_name", "lead_time_days"]], on="product_id")
reco["recommended_safety_stock"] = (
    Z * reco["std_daily_demand"] * np.sqrt(reco["lead_time_days"])
).round(0)
reco["recommended_reorder_point"] = (
    reco["avg_daily_demand"] * reco["lead_time_days"] + reco["recommended_safety_stock"]
).round(0)
reco = reco.merge(products[["product_id", "product_name", "category"]], on="product_id")
reco = reco.merge(warehouses[["warehouse_id", "warehouse_name"]], on="warehouse_id")
reco = reco[[
    "product_id", "product_name", "category", "warehouse_id", "warehouse_name",
    "supplier_name", "lead_time_days", "avg_daily_demand", "std_daily_demand",
    "recommended_safety_stock", "recommended_reorder_point",
]].sort_values("recommended_reorder_point", ascending=False)

reco.to_csv("output/reorder_recommendations.csv", index=False)
print("Saved output/reorder_recommendations.csv")

# ----------------------------------------------------------------------
# 6. AT-RISK SKUs — compare current stock (per product/warehouse) against
#    the RECOMMENDED reorder point, to find gaps the current static
#    reorder_point in `inventory` is missing.
# ----------------------------------------------------------------------
at_risk = reco.merge(
    inventory[["product_id", "warehouse_id", "stock_on_hand"]],
    on=["product_id", "warehouse_id"],
)
at_risk["gap_vs_recommended_rop"] = at_risk["recommended_reorder_point"] - at_risk["stock_on_hand"]
at_risk = at_risk[at_risk["gap_vs_recommended_rop"] > 0].sort_values(
    "gap_vs_recommended_rop", ascending=False
)
at_risk.to_csv("output/at_risk_skus.csv", index=False)
print(f"Saved output/at_risk_skus.csv ({len(at_risk)} product/warehouse combos flagged)")

print("\nTop 5 at-risk product/warehouse combos:")
print(at_risk[["product_name", "warehouse_name", "stock_on_hand",
                "recommended_reorder_point", "gap_vs_recommended_rop"]]
      .head(5).to_string(index=False))
