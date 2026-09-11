"""
generate_data.py
-----------------
Creates a synthetic (but realistic) supply chain dataset for the
"Inventory & Order Fulfillment Analytics" practice project.

Outputs:
  data/products.csv
  data/suppliers.csv
  data/warehouses.csv
  data/inventory.csv
  data/orders.csv
  data/shipments.csv
  data/supply_chain.db   (SQLite database with all tables loaded)

Run:
  python generate_data.py
"""

import sqlite3
from datetime import timedelta, date

import numpy as np
import pandas as pd

RNG = np.random.default_rng(42)  # fixed seed -> reproducible dataset

# ----------------------------------------------------------------------
# 1. PRODUCTS
# ----------------------------------------------------------------------
categories = ["Electronics", "Home & Kitchen", "Office Supplies", "Apparel", "Tools"]

product_names = [
    "Wireless Mouse", "USB-C Hub", "Bluetooth Speaker", "LED Desk Lamp", "Noise-Cancel Headphones",
    "Stainless Steel Water Bottle", "Non-Stick Frying Pan", "Ceramic Mug Set", "Electric Kettle", "Blender",
    "A4 Notebook Pack", "Gel Pens (12-pack)", "Sticky Notes", "Desk Organizer", "Stapler",
    "Cotton T-Shirt", "Denim Jacket", "Running Shoes", "Wool Socks (3-pack)", "Baseball Cap",
    "Cordless Drill", "Hammer", "Tool Box", "Measuring Tape", "Screwdriver Set",
]

products = pd.DataFrame({
    "product_id": [f"P{str(i+1).zfill(3)}" for i in range(len(product_names))],
    "product_name": product_names,
    "category": [categories[i % len(categories)] for i in range(len(product_names))],
})
products["unit_cost"] = RNG.uniform(4, 80, size=len(products)).round(2)
products["unit_price"] = (products["unit_cost"] * RNG.uniform(1.3, 2.2, size=len(products))).round(2)

# ----------------------------------------------------------------------
# 2. SUPPLIERS (each product sourced from one primary supplier)
# ----------------------------------------------------------------------
supplier_names = [
    "Global Parts Co", "Northline Trading", "Pacific Sourcing Ltd", "Union Freight Supply",
    "Meridian Wholesale", "Crestpoint Industries", "Harbor & Co", "Silverline Distributors",
]

suppliers_master = pd.DataFrame({
    "supplier_id": [f"S{str(i+1).zfill(2)}" for i in range(len(supplier_names))],
    "supplier_name": supplier_names,
})
suppliers_master["base_lead_time"] = RNG.integers(4, 21, size=len(suppliers_master))
suppliers_master["base_otd_rate"] = RNG.uniform(0.75, 0.99, size=len(suppliers_master)).round(3)

# assign a supplier to each product
sup_assignment = RNG.choice(suppliers_master["supplier_id"], size=len(products))
suppliers = products[["product_id"]].copy()
suppliers["supplier_id"] = sup_assignment
suppliers = suppliers.merge(suppliers_master, on="supplier_id")
# add a little product-level jitter around the supplier's baseline
suppliers["lead_time_days"] = (suppliers["base_lead_time"] + RNG.integers(-2, 3, size=len(suppliers))).clip(lower=2)
suppliers["on_time_delivery_rate"] = (suppliers["base_otd_rate"] + RNG.normal(0, 0.03, size=len(suppliers))).clip(0.5, 1.0).round(3)
suppliers = suppliers[["supplier_id", "supplier_name", "product_id", "lead_time_days", "on_time_delivery_rate"]]

# ----------------------------------------------------------------------
# 3. WAREHOUSES
# ----------------------------------------------------------------------
warehouses = pd.DataFrame({
    "warehouse_id": ["W1", "W2", "W3", "W4"],
    "warehouse_name": ["North DC", "South DC", "East DC", "West DC"],
    "region": ["North", "South", "East", "West"],
})

# ----------------------------------------------------------------------
# 4. INVENTORY (one row per product/warehouse combo)
# ----------------------------------------------------------------------
inv_rows = []
for _, p in products.iterrows():
    for _, w in warehouses.iterrows():
        avg_daily_demand = RNG.uniform(1, 15)
        lt = suppliers.loc[suppliers.product_id == p.product_id, "lead_time_days"].values[0]
        safety_stock = round(avg_daily_demand * RNG.uniform(3, 7))
        reorder_point = round(avg_daily_demand * lt + safety_stock)
        stock_on_hand = int(max(0, RNG.normal(reorder_point * 1.3, reorder_point * 0.5)))
        inv_rows.append({
            "product_id": p.product_id,
            "warehouse_id": w.warehouse_id,
            "stock_on_hand": stock_on_hand,
            "reorder_point": int(reorder_point),
            "safety_stock": int(safety_stock),
        })
inventory = pd.DataFrame(inv_rows)

# ----------------------------------------------------------------------
# 5. ORDERS (12 months of order history)
# ----------------------------------------------------------------------
start_date = date(2025, 9, 1)
n_days = 365
n_orders = 6000

order_dates = [start_date + timedelta(days=int(d)) for d in RNG.integers(0, n_days, size=n_orders)]
order_products = RNG.choice(products["product_id"], size=n_orders)
order_warehouses = RNG.choice(warehouses["warehouse_id"], size=n_orders)
order_qty = RNG.integers(1, 25, size=n_orders)
customer_ids = [f"C{str(i).zfill(4)}" for i in RNG.integers(1, 800, size=n_orders)]

orders = pd.DataFrame({
    "order_id": [f"O{str(i+1).zfill(5)}" for i in range(n_orders)],
    "customer_id": customer_ids,
    "product_id": order_products,
    "warehouse_id": order_warehouses,
    "order_date": order_dates,
})
orders = orders.merge(suppliers[["product_id", "lead_time_days"]], on="product_id", how="left")
orders["qty"] = order_qty

# ship_date = order_date + processing delay (sometimes late)
processing_days = RNG.integers(1, 5, size=n_orders)
late_flag = RNG.random(n_orders) < 0.12  # 12% of orders slip
processing_days = processing_days + np.where(late_flag, RNG.integers(3, 10, size=n_orders), 0)
orders["ship_date"] = orders["order_date"] + pd.to_timedelta(processing_days, unit="D")

# a small % of orders are cancelled / backordered
status_roll = RNG.random(n_orders)
orders["status"] = np.select(
    [status_roll < 0.03, status_roll < 0.08],
    ["Cancelled", "Backordered"],
    default="Fulfilled",
)
orders.loc[orders["status"] != "Fulfilled", "ship_date"] = pd.NaT
orders = orders.drop(columns=["lead_time_days"])

# ----------------------------------------------------------------------
# 6. SHIPMENTS (one per fulfilled order)
# ----------------------------------------------------------------------
carriers = ["FastFreight", "MetroLogistics", "BlueArrow Shipping", "RapidRoute"]
fulfilled = orders[orders["status"] == "Fulfilled"].copy()

transit_days = RNG.integers(1, 6, size=len(fulfilled))
fulfilled["delivery_date"] = fulfilled["ship_date"] + pd.to_timedelta(transit_days, unit="D")
fulfilled["promised_date"] = fulfilled["order_date"] + pd.to_timedelta(RNG.integers(5, 12, size=len(fulfilled)), unit="D")

shipments = pd.DataFrame({
    "shipment_id": [f"SH{str(i+1).zfill(5)}" for i in range(len(fulfilled))],
    "order_id": fulfilled["order_id"].values,
    "carrier": RNG.choice(carriers, size=len(fulfilled)),
    "ship_date": fulfilled["ship_date"].values,
    "delivery_date": fulfilled["delivery_date"].values,
    "promised_date": fulfilled["promised_date"].values,
})

# ----------------------------------------------------------------------
# SAVE CSVs + SQLite DB
# ----------------------------------------------------------------------
products.to_csv("data/products.csv", index=False)
suppliers.to_csv("data/suppliers.csv", index=False)
warehouses.to_csv("data/warehouses.csv", index=False)
inventory.to_csv("data/inventory.csv", index=False)
orders.to_csv("data/orders.csv", index=False)
shipments.to_csv("data/shipments.csv", index=False)

conn = sqlite3.connect("data/supply_chain.db")
products.to_sql("products", conn, if_exists="replace", index=False)
suppliers.to_sql("suppliers", conn, if_exists="replace", index=False)
warehouses.to_sql("warehouses", conn, if_exists="replace", index=False)
inventory.to_sql("inventory", conn, if_exists="replace", index=False)
orders.to_sql("orders", conn, if_exists="replace", index=False)
shipments.to_sql("shipments", conn, if_exists="replace", index=False)
conn.close()

print("Done. Rows created:")
print(f"  products:   {len(products)}")
print(f"  suppliers:  {len(suppliers)}")
print(f"  warehouses: {len(warehouses)}")
print(f"  inventory:  {len(inventory)}")
print(f"  orders:     {len(orders)}")
print(f"  shipments:  {len(shipments)}")
