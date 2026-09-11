# Supply Chain Inventory & Demand Analytics System

End-to-end supply chain analytics project: **SQL → Python → Excel**.
Simulates a mid-size distributor with 4 warehouses, 8 suppliers, 25 products,
and 12 months of order history, then answers real supply-chain questions:
stock-out risk, supplier reliability, inventory turnover, demand forecasting,
and reorder-point recommendations.

## Requirements

```bash
pip install pandas numpy matplotlib openpyxl
```

Python 3.9+ recommended. Uses SQLite (built into Python — no server needed).

## How to run (in order)

```bash
# 1. Generate the synthetic dataset -> creates data/*.csv and data/supply_chain.db
python generate_data.py

# 2. Explore the data with SQL (optional, needs the sqlite3 CLI)
sqlite3 data/supply_chain.db < queries.sql
# or run queries.sql through any SQLite GUI (DB Browser for SQLite, DBeaver, etc.)

# 3. Run the Python analysis -> forecasting, safety stock, at-risk SKUs
python analysis.py

# 4. Build the Excel dashboard -> output/Supply_Chain_Dashboard.xlsx
python build_excel.py
```

## Project structure

```
generate_data.py     Creates the synthetic dataset (products, suppliers,
                      warehouses, inventory, orders, shipments) and loads
                      it into data/supply_chain.db

queries.sql           6 SQL queries: stock-out detection, supplier scorecard,
                      inventory turnover (CTE), reorder alerts, fast/slow
                      movers (window function), on-time delivery by carrier

analysis.py           Loads data via pandas, cleans it, runs EDA, forecasts
                      next month's demand per SKU (moving average vs
                      exponential smoothing, picks the better one), computes
                      safety stock / reorder point recommendations, flags
                      at-risk SKU-warehouse combinations

build_excel.py        Builds the Excel dashboard: raw data tabs, a live
                      Dashboard tab (INDEX/MATCH, COUNTIFS, conditional
                      formatting, chart), and a Supplier Scorecard tab
                      (AVERAGEIF/COUNTIF, chart) — fully formula-driven

data/                 Generated CSVs + supply_chain.db (created by step 1)
output/                Generated charts, CSVs, and the final .xlsx (created
                      by steps 3-4)
```

## Key design choices worth mentioning in an interview

- **Reproducible data**: `generate_data.py` uses a fixed random seed, so
  re-running it produces the exact same dataset.
- **Model selection in the forecast**: for each SKU, the script evaluates
  both a 3-month moving average and exponential smoothing on the last 3
  known months and picks whichever had lower error (MAE), rather than
  hardcoding one method.
- **Reorder points are computed at the product × warehouse level**, not
  aggregated — because that's the level at which a real reorder decision
  gets made.
- **The Excel workbook has almost no hardcoded numbers.** Everything on
  the Dashboard and Supplier Scorecard tabs is a live formula referencing
  the raw data tabs, so it recalculates if you change the source data.
- **Cross-validated**: the SQL "reorder alerts" query, the Python
  `at_risk_skus.csv` output, and the Excel Dashboard's REORDER count all
  agree — a good example of checking a pipeline for internal consistency.
