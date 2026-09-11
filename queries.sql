-- =====================================================================
-- queries.sql
-- Supply Chain Analytics — Phase 1 SQL
-- Database: data/supply_chain.db (SQLite)
-- Run with:  sqlite3 data/supply_chain.db < queries.sql
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. STOCK-OUT RISK
-- Orders placed for a product/warehouse where the order quantity
-- exceeds what is currently on hand at that warehouse.
-- ---------------------------------------------------------------------
SELECT
    o.order_id,
    o.order_date,
    p.product_name,
    o.warehouse_id,
    o.qty            AS order_qty,
    i.stock_on_hand,
    (o.qty - i.stock_on_hand) AS shortfall
FROM orders o
JOIN products  p ON p.product_id = o.product_id
JOIN inventory i ON i.product_id = o.product_id
                 AND i.warehouse_id = o.warehouse_id
WHERE o.qty > i.stock_on_hand
  AND o.status = 'Fulfilled'
ORDER BY shortfall DESC
LIMIT 25;


-- ---------------------------------------------------------------------
-- 2. SUPPLIER SCORECARD
-- Average lead time and on-time delivery rate per supplier,
-- plus how many distinct products they supply.
-- ---------------------------------------------------------------------
SELECT
    s.supplier_id,
    s.supplier_name,
    COUNT(DISTINCT s.product_id)          AS products_supplied,
    ROUND(AVG(s.lead_time_days), 1)       AS avg_lead_time_days,
    ROUND(AVG(s.on_time_delivery_rate)*100, 1) AS avg_on_time_pct
FROM suppliers s
GROUP BY s.supplier_id, s.supplier_name
ORDER BY avg_on_time_pct ASC;         -- worst performers first


-- ---------------------------------------------------------------------
-- 3. INVENTORY TURNOVER & DAYS OF SUPPLY (per product)
-- Turnover = annual units shipped / avg stock on hand
-- Days of supply = 365 / turnover
-- Uses a CTE to first aggregate shipped quantity by product.
-- ---------------------------------------------------------------------
WITH shipped AS (
    SELECT
        o.product_id,
        SUM(o.qty) AS units_shipped_ytd
    FROM orders o
    WHERE o.status = 'Fulfilled'
    GROUP BY o.product_id
),
avg_stock AS (
    SELECT
        product_id,
        AVG(stock_on_hand) AS avg_stock_on_hand
    FROM inventory
    GROUP BY product_id
)
SELECT
    p.product_id,
    p.product_name,
    sh.units_shipped_ytd,
    ROUND(av.avg_stock_on_hand, 1)                          AS avg_stock_on_hand,
    ROUND(1.0 * sh.units_shipped_ytd / NULLIF(av.avg_stock_on_hand, 0), 2) AS inventory_turnover,
    ROUND(365.0 / NULLIF(1.0 * sh.units_shipped_ytd / NULLIF(av.avg_stock_on_hand, 0), 0), 1) AS days_of_supply
FROM products p
JOIN shipped   sh ON sh.product_id = p.product_id
JOIN avg_stock av ON av.product_id = p.product_id
ORDER BY inventory_turnover DESC;


-- ---------------------------------------------------------------------
-- 4. REORDER ALERTS
-- Product/warehouse combinations currently at or below reorder point.
-- ---------------------------------------------------------------------
SELECT
    i.product_id,
    p.product_name,
    i.warehouse_id,
    w.warehouse_name,
    i.stock_on_hand,
    i.reorder_point,
    i.safety_stock,
    (i.reorder_point - i.stock_on_hand) AS units_below_reorder_point
FROM inventory i
JOIN products   p ON p.product_id = i.product_id
JOIN warehouses w ON w.warehouse_id = i.warehouse_id
WHERE i.stock_on_hand <= i.reorder_point
ORDER BY units_below_reorder_point DESC;


-- ---------------------------------------------------------------------
-- 5. FAST-MOVING vs SLOW-MOVING SKUs (window function + ranking)
-- Ranks products by total units ordered; flags top/bottom 5.
-- ---------------------------------------------------------------------
WITH product_volume AS (
    SELECT
        p.product_id,
        p.product_name,
        p.category,
        SUM(o.qty) AS total_units_ordered,
        RANK() OVER (ORDER BY SUM(o.qty) DESC) AS rank_fast,
        RANK() OVER (ORDER BY SUM(o.qty) ASC)  AS rank_slow
    FROM orders o
    JOIN products p ON p.product_id = o.product_id
    WHERE o.status = 'Fulfilled'
    GROUP BY p.product_id, p.product_name, p.category
)
SELECT product_id, product_name, category, total_units_ordered,
       CASE WHEN rank_fast <= 5 THEN 'FAST-MOVING'
            WHEN rank_slow  <= 5 THEN 'SLOW-MOVING'
            ELSE NULL END AS movement_tag
FROM product_volume
WHERE rank_fast <= 5 OR rank_slow <= 5
ORDER BY total_units_ordered DESC;


-- ---------------------------------------------------------------------
-- 6. ON-TIME DELIVERY PERFORMANCE (shipments vs promised date)
-- ---------------------------------------------------------------------
SELECT
    sh.carrier,
    COUNT(*)                                                     AS shipments,
    SUM(CASE WHEN sh.delivery_date <= sh.promised_date THEN 1 ELSE 0 END) AS on_time_shipments,
    ROUND(100.0 * SUM(CASE WHEN sh.delivery_date <= sh.promised_date THEN 1 ELSE 0 END) / COUNT(*), 1) AS on_time_pct
FROM shipments sh
GROUP BY sh.carrier
ORDER BY on_time_pct DESC;
