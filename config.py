"""
Configuration: where the files are and how each supplier's columns map
to the standard names used by the tool.

Adding a new supplier = adding one block to SUPPLIERS. No code changes.
For every standard field you can list several possible source column
names; the first one found in the file is used.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INPUT_DIR = ROOT / "data" / "input"
OFFERS_DIR = INPUT_DIR / "offers"
OUTPUT_DIR = ROOT / "data" / "output"

BASE_FILE = INPUT_DIR / "base_purchases.xlsx"
OUTPUT_FILE = OUTPUT_DIR / "price_comparison.xlsx"

# Suppliers that only quote the exact requested part number
ALWAYS_ORIGINAL = {"Vendor Gamma", "Vendor Delta"}

# Column in the base file with the quantity we usually order
ORDER_QTY_CANDIDATES = ["QUANTITY_ORDERED", "Quantity Ordered", "ORDERED QTY", "QTY"]

# Column in the base file with the unit price we currently pay
PAID_PRICE_CANDIDATES = ["Unit Price USD", "Paid Price USD"]

SUPPLIERS = {
    "Vendor Alpha": {
        "file": OFFERS_DIR / "offer_vendor_alpha.xlsx",
        "sheet_name": "Offer",
        "columns": {
            "Part Number": ["Requested Part Number"],
            "offered PN": ["Offered Part Number"],
            "Description": ["Description"],
            "UOM": ["UoM", "UOM"],
            "MOQ": ["MOQ"],
            "Lead Time": ["Lead_Time"],
            "offered Price": ["Price USD"],
        },
    },
    "Vendor Beta": {
        "file": OFFERS_DIR / "offer_vendor_beta.xlsx",
        "sheet_name": "Beta Offer",
        "columns": {
            "Part Number": ["PartNumber"],
            "offered PN": ["Offered PN"],
            "Description": ["DESCRIPTION"],
            "offered Price": ["Sales Price"],
        },
    },
    "Vendor Gamma": {
        "file": OFFERS_DIR / "offer_vendor_gamma.xlsx",
        "sheet_name": "pricelist",
        "columns": {
            "Part Number": ["PNR"],
            "Description": ["KWD"],
            "offered Price": ["UNP"],
            "UOM": ["UM", "UOM"],
            "MOQ": ["MSQ", "MOQ"],
            "Qty Break 1": ["Qty1"], "Price Break 1": ["Price1"],
            "Qty Break 2": ["Qty2"], "Price Break 2": ["Price2"],
            "Qty Break 3": ["Qty3"], "Price Break 3": ["Price3"],
        },
    },
    "Vendor Delta": {
        "file": OFFERS_DIR / "offer_vendor_delta.xlsx",
        "sheet_name": "Sheet2",
        "columns": {
            "Part Number": ["P/N"],
            "Description": ["Description"],
            "EUR Price": ["Price unit (EUR)"],
            "offered Price": ["Price USD"],
            "Cur": ["Currency", "Cur"],
            "UOM": ["UOM"],
            "MOQ": ["MOQ"],
        },
    },
    "Vendor Epsilon": {
        "file": OFFERS_DIR / "offer_vendor_epsilon.xlsx",
        "sheet_name": "Quote",
        "columns": {
            "Part Number": ["Cust Req'd Part"],
            "offered PN": ["Part supplied"],
            "Description": ["Supplied Desc"],
            "offered Price": ["Price (USD)"],
            "UOM": ["Supplied UOM"],
        },
    },
}

# --- Price compliance analysis -------------------------------------------
PO_LINES_FILE = INPUT_DIR / "purchase_order_lines.xlsx"
COMPLIANCE_FILE = OUTPUT_DIR / "price_compliance.xlsx"
CHARTS_DIR = OUTPUT_DIR / "charts"

# A PO line counts as "at agreed price" when it is within this share of the
# best offered price (0.005 = 0.5 %, absorbs rounding)
AGREED_TOLERANCE = 0.005
# Deviation that splits "slightly" from "far" above/below the offer
FAR_THRESHOLD = 0.30

# --- Power BI -------------------------------------------------------------
POWERBI_DATA_DIR = OUTPUT_DIR / "powerbi"          # CSV tables the report reads
POWERBI_TEMPLATE = ROOT / "powerbi" / "price_compliance.pbit"
