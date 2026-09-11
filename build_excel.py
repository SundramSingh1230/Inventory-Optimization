"""
build_excel.py
---------------
Phase 3 — builds the Excel reporting workbook for stakeholders.

Tabs:
  Products, Suppliers, Warehouses, Inventory   -> raw data
  Reorder_Model                                -> Python model output (data)
  Dashboard                                    -> INDEX/MATCH lookups,
                                                   status flags, conditional
                                                   formatting, KPI formulas, chart
  Supplier_Scorecard                           -> AVERAGEIF/COUNTIF formulas, chart

All cross-sheet numbers on Dashboard / Supplier_Scorecard are live formulas,
not hardcoded Python results, so the workbook recalculates if the raw data
changes.
"""

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.formatting.rule import CellIsRule, ColorScaleRule
from openpyxl.chart import BarChart, Reference
from openpyxl.utils import get_column_letter

FONT_NAME = "Arial"
HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(name=FONT_NAME, bold=True, color="FFFFFF")
TITLE_FONT = Font(name=FONT_NAME, bold=True, size=14, color="1F4E78")
NOTE_FONT = Font(name=FONT_NAME, italic=True, size=9, color="808080")
BASE_FONT = Font(name=FONT_NAME, size=10)
THIN = Side(style="thin", color="D9D9D9")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

# ----------------------------------------------------------------------
# Load source data
# ----------------------------------------------------------------------
products = pd.read_csv("data/products.csv")
suppliers = pd.read_csv("data/suppliers.csv")
warehouses = pd.read_csv("data/warehouses.csv")
inventory = pd.read_csv("data/inventory.csv")
reco = pd.read_csv("output/reorder_recommendations.csv")

wb = Workbook()
wb.remove(wb.active)


def write_data_sheet(name, df, col_widths=None, money_cols=None, pct_cols=None):
    ws = wb.create_sheet(name)
    for c, col in enumerate(df.columns, start=1):
        cell = ws.cell(row=1, column=c, value=col.replace("_", " ").title())
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center")
    for r, row in enumerate(df.itertuples(index=False), start=2):
        for c, val in enumerate(row, start=1):
            cell = ws.cell(row=r, column=c, value=val)
            cell.font = BASE_FONT
            cell.border = BORDER
            colname = df.columns[c - 1]
            if money_cols and colname in money_cols:
                cell.number_format = '$#,##0.00'
            if pct_cols and colname in pct_cols:
                cell.number_format = '0.0%'
    widths = col_widths or [16] * len(df.columns)
    for c, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(c)].width = w
    ws.freeze_panes = "A2"
    return ws


# ----------------------------------------------------------------------
# Raw data tabs
# ----------------------------------------------------------------------
ws_products = write_data_sheet(
    "Products", products,
    col_widths=[12, 26, 18, 12, 12],
    money_cols=["unit_cost", "unit_price"],
)
ws_suppliers = write_data_sheet(
    "Suppliers", suppliers,
    col_widths=[12, 22, 12, 14, 18],
    pct_cols=["on_time_delivery_rate"],
)
ws_warehouses = write_data_sheet("Warehouses", warehouses, col_widths=[14, 18, 12])
ws_inventory = write_data_sheet(
    "Inventory", inventory,
    col_widths=[12, 14, 14, 14, 14],
)
ws_reco = write_data_sheet(
    "Reorder_Model", reco,
    col_widths=[12, 20, 16, 14, 16, 18, 14, 16, 16, 18, 20],
)
note_row = len(reco) + 3
ws_reco.cell(row=note_row, column=1,
             value="Source: analysis.py — 3-mo moving avg / exponential smoothing demand model, "
                   "95% service level (Z=1.65). Recomputed whenever generate_data.py / analysis.py are re-run.")
ws_reco.cell(row=note_row, column=1).font = NOTE_FONT

n_inv = len(inventory) + 1     # last data row on Inventory sheet
n_prod = len(products) + 1
n_wh = len(warehouses) + 1
n_sup = len(suppliers) + 1

# ----------------------------------------------------------------------
# DASHBOARD sheet — lookups + status flags + KPIs, all formula-driven
# ----------------------------------------------------------------------
dash = wb.create_sheet("Dashboard", 0)
dash.sheet_view.showGridLines = False

dash["A1"] = "Supply Chain Inventory Dashboard"
dash["A1"].font = TITLE_FONT
dash["A2"] = "Live workbook — Status and KPIs recalculate from the Inventory / Products / Warehouses tabs"
dash["A2"].font = NOTE_FONT

# ---- KPI cards (row 4-5) --------------------------------------------------
kpi_labels = ["Total SKU-Warehouse Combos", "Combos At/Below Reorder Point",
              "% At Risk", "Avg Days-Equivalent Safety Stock"]
kpi_cells = ["B4", "D4", "F4", "H4"]
for lbl, cell in zip(kpi_labels, kpi_cells):
    col = cell[0]
    lbl_cell = dash[f"{col}3"]
    lbl_cell.value = lbl
    lbl_cell.font = Font(name=FONT_NAME, bold=True, size=9, color="1F4E78")

dash["B4"] = f"=COUNTA(Inventory!A2:A{n_inv})"
dash["D4"] = f"=COUNTIF(J8:J{7 + len(inventory)},\"REORDER\")"
dash["F4"] = "=D4/B4"
dash["F4"].number_format = "0.0%"
dash["H4"] = f"=AVERAGE(Inventory!E2:E{n_inv})"
for cell in ["B4", "D4", "F4", "H4"]:
    dash[cell].font = Font(name=FONT_NAME, bold=True, size=16, color="C00000" if cell == "D4" else "1F4E78")

# ---- Detail table header (row 7) ------------------------------------------
headers = ["Product ID", "Product Name", "Category", "Warehouse ID", "Warehouse Name",
           "Stock on Hand", "Reorder Point", "Safety Stock", "Units Below ROP", "Status"]
header_row = 7
for c, h in enumerate(headers, start=1):
    cell = dash.cell(row=header_row, column=c, value=h)
    cell.font = HEADER_FONT
    cell.fill = HEADER_FILL
    cell.alignment = Alignment(horizontal="center", wrap_text=True)

first_data_row = header_row + 1
for i in range(len(inventory)):
    r = first_data_row + i
    inv_r = r - first_data_row + 2  # corresponding row on Inventory sheet
    dash.cell(row=r, column=1, value=f"=Inventory!A{inv_r}")                                    # product id
    dash.cell(row=r, column=2,
              value=f"=INDEX(Products!$B$2:$B${n_prod},MATCH(A{r},Products!$A$2:$A${n_prod},0))")  # product name
    dash.cell(row=r, column=3,
              value=f"=INDEX(Products!$C$2:$C${n_prod},MATCH(A{r},Products!$A$2:$A${n_prod},0))")  # category
    dash.cell(row=r, column=4, value=f"=Inventory!B{inv_r}")                                     # warehouse id
    dash.cell(row=r, column=5,
              value=f"=INDEX(Warehouses!$B$2:$B${n_wh},MATCH(D{r},Warehouses!$A$2:$A${n_wh},0))")  # warehouse name
    dash.cell(row=r, column=6, value=f"=Inventory!C{inv_r}")                                     # stock on hand
    dash.cell(row=r, column=7, value=f"=Inventory!D{inv_r}")                                     # reorder point
    dash.cell(row=r, column=8, value=f"=Inventory!E{inv_r}")                                     # safety stock
    dash.cell(row=r, column=9, value=f"=MAX(0,G{r}-F{r})")                                       # units below ROP
    dash.cell(row=r, column=10, value=f'=IF(F{r}<=G{r},"REORDER","OK")')                         # status
    for c in range(1, 11):
        dash.cell(row=r, column=c).font = BASE_FONT
        dash.cell(row=r, column=c).border = BORDER

last_data_row = first_data_row + len(inventory) - 1

# conditional formatting: Status column
red_fill = PatternFill("solid", fgColor="F8CBCB")
green_fill = PatternFill("solid", fgColor="C6E8C6")
dash.conditional_formatting.add(
    f"J{first_data_row}:J{last_data_row}",
    CellIsRule(operator="equal", formula=['"REORDER"'], fill=red_fill),
)
dash.conditional_formatting.add(
    f"J{first_data_row}:J{last_data_row}",
    CellIsRule(operator="equal", formula=['"OK"'], fill=green_fill),
)
# color scale on "units below ROP"
dash.conditional_formatting.add(
    f"I{first_data_row}:I{last_data_row}",
    ColorScaleRule(start_type="min", start_color="C6E8C6",
                    end_type="max", end_color="F8696B"),
)

col_widths = [12, 22, 16, 13, 16, 13, 13, 12, 15, 11]
for c, w in enumerate(col_widths, start=1):
    dash.column_dimensions[get_column_letter(c)].width = w
dash.freeze_panes = f"A{first_data_row}"

# ---- Chart: count of REORDER vs OK by warehouse ---------------------------
# helper block (columns L:N) using COUNTIFS, then chart from it
dash["L7"] = "Warehouse"
dash["M7"] = "OK"
dash["N7"] = "REORDER"
for cell in ["L7", "M7", "N7"]:
    dash[cell].font = HEADER_FONT
    dash[cell].fill = HEADER_FILL
for i, wid in enumerate(warehouses["warehouse_id"], start=1):
    r = 7 + i
    dash.cell(row=r, column=12, value=f"=Warehouses!B{i+1}")
    dash.cell(row=r, column=13,
              value=f'=COUNTIFS($D${first_data_row}:$D${last_data_row},Warehouses!A{i+1},'
                    f'$J${first_data_row}:$J${last_data_row},"OK")')
    dash.cell(row=r, column=14,
              value=f'=COUNTIFS($D${first_data_row}:$D${last_data_row},Warehouses!A{i+1},'
                    f'$J${first_data_row}:$J${last_data_row},"REORDER")')
    for c in range(12, 15):
        dash.cell(row=r, column=c).font = BASE_FONT

chart = BarChart()
chart.type = "col"
chart.grouping = "stacked"
chart.overlap = 100
chart.title = "Reorder Status by Warehouse"
chart.y_axis.title = "SKU Count"
chart.x_axis.title = "Warehouse"
cats = Reference(dash, min_col=12, min_row=8, max_row=7 + len(warehouses))
data = Reference(dash, min_col=13, max_col=14, min_row=7, max_row=7 + len(warehouses))
chart.add_data(data, titles_from_data=True)
chart.set_categories(cats)
chart.height, chart.width = 8, 14
dash.add_chart(chart, "L11")

# ----------------------------------------------------------------------
# SUPPLIER SCORECARD sheet — AVERAGEIF/COUNTIF formulas + chart
# ----------------------------------------------------------------------
sc = wb.create_sheet("Supplier_Scorecard")
sc.sheet_view.showGridLines = False
sc["A1"] = "Supplier Scorecard"
sc["A1"].font = TITLE_FONT
sc["A2"] = "Legend: yellow cells are the only inputs (supplier IDs) — everything else recalculates from the Suppliers tab."
sc["A2"].font = NOTE_FONT

sc_headers = ["Supplier ID", "Supplier Name", "Products Supplied", "Avg Lead Time (days)", "Avg On-Time %"]
for c, h in enumerate(sc_headers, start=1):
    cell = sc.cell(row=4, column=c, value=h)
    cell.font = HEADER_FONT
    cell.fill = HEADER_FILL

unique_suppliers = sorted(suppliers["supplier_id"].unique())
yellow = PatternFill("solid", fgColor="FFFF00")
for i, sid in enumerate(unique_suppliers, start=1):
    r = 4 + i
    id_cell = sc.cell(row=r, column=1, value=sid)
    id_cell.fill = yellow
    id_cell.font = Font(name=FONT_NAME, color="0000FF")
    sc.cell(row=r, column=2,
            value=f"=INDEX(Suppliers!$B$2:$B${n_sup},MATCH(A{r},Suppliers!$A$2:$A${n_sup},0))")
    sc.cell(row=r, column=3, value=f"=COUNTIF(Suppliers!$A$2:$A${n_sup},A{r})")
    sc.cell(row=r, column=4,
            value=f"=ROUND(AVERAGEIF(Suppliers!$A$2:$A${n_sup},A{r},Suppliers!$D$2:$D${n_sup}),1)")
    sc.cell(row=r, column=5,
            value=f"=AVERAGEIF(Suppliers!$A$2:$A${n_sup},A{r},Suppliers!$E$2:$E${n_sup})")
    sc.cell(row=r, column=5).number_format = "0.0%"
    for c in range(2, 6):
        sc.cell(row=r, column=c).font = BASE_FONT
        sc.cell(row=r, column=c).border = BORDER

last_sc_row = 4 + len(unique_suppliers)
sc.conditional_formatting.add(
    f"E5:E{last_sc_row}",
    ColorScaleRule(start_type="min", start_color="F8696B", end_type="max", end_color="C6E8C6"),
)

for c, w in zip(range(1, 6), [12, 22, 18, 18, 14]):
    sc.column_dimensions[get_column_letter(c)].width = w

sup_chart = BarChart()
sup_chart.type = "bar"
sup_chart.title = "Average On-Time Delivery % by Supplier"
sup_chart.y_axis.title = "Supplier"
sup_chart.x_axis.title = "On-Time %"
data = Reference(sc, min_col=5, min_row=4, max_row=last_sc_row)
cats = Reference(sc, min_col=2, min_row=5, max_row=last_sc_row)
sup_chart.add_data(data, titles_from_data=True)
sup_chart.set_categories(cats)
sup_chart.height, sup_chart.width = 9, 16
sc.add_chart(sup_chart, "A16")

wb.save("output/Supply_Chain_Dashboard.xlsx")
print("Saved output/Supply_Chain_Dashboard.xlsx")
