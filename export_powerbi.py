"""
Writes model-ready CSV tables for the Power BI report (star schema).

  fact_po_lines.csv   one row per PO line with offer price, category, overpay
  dim_part.csv        part number, description, best offer and supplier
  dim_company.csv     company and company type
  dim_vendor.csv      vendor
  dim_category.csv    price categories with sort order and colour

CSV instead of Excel: 100,000 rows load in seconds and types stay simple.
"""
from __future__ import annotations

import pandas as pd

import config

CATEGORY_TABLE = pd.DataFrame({
    "Price Category": ["Below >30%", "Below ≤30%", "At offered price", "Above ≤30%", "Above >30%"],
    "Label": ["▼▼ below >30 %", "▼ below ≤30 %", "= at offered price", "▲ above ≤30 %", "▲▲ above >30 %"],
    "Sort": [1, 2, 3, 4, 5],
    "Colour": ["#12705a", "#a3e0cc", "#d9d5ce", "#f0a07b", "#b94a20"],
})


def export(lines: pd.DataFrame) -> None:
    out = config.POWERBI_DATA_DIR
    out.mkdir(parents=True, exist_ok=True)

    fact = lines[[
        "PO Number", "PO Line", "PO Date", "Year-Month", "Company", "Vendor", "Order Priority",
        "Part Number", "Quantity", "Unit Price USD", "Line Value USD",
        "Offer Price USD", "Offer Supplier", "Has Offer", "Deviation", "Price Category",
        "At Offered Price", "From Offer Supplier", "Overpay USD",
    ]].copy()
    fact["PO Date"] = fact["PO Date"].dt.date
    fact["Deviation"] = fact["Deviation"].round(4)
    fact["Overpay USD"] = fact["Overpay USD"].round(2)
    fact.to_csv(out / "fact_po_lines.csv", index=False, encoding="utf-8-sig")

    comparison = pd.read_excel(config.OUTPUT_FILE, sheet_name="Comparison")
    desc_cols = [c for c in comparison.columns if c == "Description" or c.endswith(" Description")]
    part = pd.DataFrame({
        "Part Number": comparison["Part Number"],
        "Description": comparison[desc_cols].bfill(axis=1).iloc[:, 0] if desc_cols else "",
        "Best Offer Price USD": comparison["Best Price (Original PN)"],
        "Best Offer Supplier": comparison["Best Price Supplier (Original PN)"],
        "Offers": comparison[[c for c in comparison.columns if c.endswith(" offered Price")]].notna().sum(axis=1),
    }).drop_duplicates("Part Number")
    part.to_csv(out / "dim_part.csv", index=False, encoding="utf-8-sig")

    lines[["Company", "Company Type"]].drop_duplicates().sort_values(["Company Type", "Company"]) \
        .to_csv(out / "dim_company.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame({"Vendor": sorted(lines["Vendor"].unique())}) \
        .to_csv(out / "dim_vendor.csv", index=False, encoding="utf-8-sig")
    CATEGORY_TABLE.to_csv(out / "dim_category.csv", index=False, encoding="utf-8-sig")

    print(f"Power BI tables: {out}")
