"""
Generates synthetic input files for the Supplier Price Comparison tool.

Everything is random: part numbers, descriptions, suppliers, prices and
quantities. Each supplier file deliberately uses a different layout,
column names and number format - the same problems real offer files have.
"""
from pathlib import Path
import random

import numpy as np
import pandas as pd

SEED = 7
ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "data" / "input"
OFFERS = INPUT / "offers"

rng = np.random.default_rng(SEED)
random.seed(SEED)

DESCRIPTIONS = ["WASHER", "NUT", "SCREW", "BOLT", "PIN", "RIVET", "PACKING", "SEAL",
                "RING", "LAMP", "FILTER ELEMENT", "CLIP", "GROMMET", "SPRING",
                "GASKET", "BUSHING", "O-RING", "FUSE", "SEALANT", "GREASE"]
UOMS = ["EA", "EA", "EA", "EA", "PK", "KT", "CN"]


def eu_number(x: float) -> str:
    """1234.5 -> '1 234,50' (European style text)."""
    s = f"{x:,.2f}"                      # 1,234.50
    return s.replace(",", " ").replace(".", ",")


def make_base(n: int = 20_000) -> pd.DataFrame:
    rows = []
    for i in range(n):
        pn = f"FK-{10000 + i}"
        paid = float(np.round(rng.lognormal(1.8, 1.4), 2))
        qty = int(rng.integers(1, 400))
        rows.append({
            "Part Number": pn,
            "Description": random.choice(DESCRIPTIONS),
            "UOM": random.choice(UOMS),
            "QUANTITY_ORDERED": qty,
            "Unit Price USD": paid,
            "Total Paid Sum, USD": round(paid * qty, 2),
            "Current Vendor": random.choice(["Vendor Alpha", "Vendor Beta", "Vendor Delta", "Other"]),
        })
    return pd.DataFrame(rows)


def offer_price(paid: float) -> float:
    """Offers are spread around the price we currently pay."""
    return float(np.round(paid * rng.uniform(0.75, 1.30), 2))


def pick(base: pd.DataFrame, n: int) -> pd.DataFrame:
    """Random sample of n parts from the base."""
    return base.sample(n=n, random_state=int(rng.integers(0, 10_000)))


def alt_pn(pn: str) -> str:
    return pn.replace("FK-", "ALT-") + random.choice(["A", "B", "-01"])


COMPANIES = {
    "MRO One": ("MRO", 0.30), "MRO Two": ("MRO", 0.20), "MRO Three": ("MRO", 0.10),
    "Airline A": ("Airlines", 0.18), "Airline B": ("Airlines", 0.14), "Airline C": ("Airlines", 0.08),
}
VENDORS = ["Vendor Alpha", "Vendor Beta", "Vendor Gamma", "Vendor Delta", "Vendor Epsilon",
           "Vendor Zeta", "Vendor Eta"]


def make_po_lines(base: pd.DataFrame, offers: dict, n_lines: int = 100_000) -> pd.DataFrame:
    """
    Purchase order lines 2025-01 .. 2026-10 for six companies.
    Part popularity is skewed (a few parts are bought very often).
    Some lines are bought from the cheapest quoting supplier at the quoted
    price; the rest are bought elsewhere at a price around today's paid price.
    Buying discipline improves in 2026.
    """
    # cheapest original offer per part
    best: dict = {}
    for (vendor, pn), price in offers.items():
        if pn not in best or price < best[pn][1]:
            best[pn] = (vendor, price)

    names = list(COMPANIES)
    weights = np.array([COMPANIES[c][1] for c in names])
    discipline = {c: rng.uniform(0.25, 0.55) for c in names}
    days = pd.date_range("2025-01-01", "2026-10-31", freq="D")
    paid = dict(zip(base["Part Number"], base["Unit Price USD"]))
    pns = base["Part Number"].to_numpy()
    quoted_mask = np.array([pn in best for pn in pns])
    pools = {}
    for flag in (True, False):
        pool = pns[quoted_mask == flag]
        w = rng.lognormal(0, 0.8, len(pool))
        pools[flag] = (pool, w / w.sum())
    # companies differ in how much of what they buy is covered by offers
    coverage = {c: rng.uniform(0.30, 0.70) for c in names}

    rows, line_no, order = [], 0, 0
    while line_no < n_lines:
        company = names[rng.choice(len(names), p=weights / weights.sum())]
        date = days[int(rng.integers(0, len(days)))]
        priority = rng.choice(["Routine", "Routine", "Routine", "Urgent", "AOG"])
        default_vendor = random.choice(VENDORS)
        for line in range(int(rng.integers(1, 7))):
            pool, w = pools[bool(rng.random() < coverage[company])]
            pn = pool[rng.choice(len(pool), p=w)]
            quote = best.get(pn)
            progress = 0.12 if date.year == 2026 else 0.0
            if quote and rng.random() < discipline[company] + progress:
                vendor, price = quote
                if rng.random() < 0.15:
                    price *= rng.uniform(1.02, 1.12)          # small price creep
            else:
                vendor = default_vendor if rng.random() < 0.7 else random.choice(VENDORS)
                price = paid[pn] * rng.uniform(0.55, 1.45)
                if priority == "AOG":
                    price *= 1.15                              # urgent orders cost more
            rows.append((f"PO{200000 + order}", line + 1, date.date(), company, COMPANIES[company][0],
                         priority, vendor, pn, int(rng.integers(1, 40)), round(float(price), 2)))
            line_no += 1
        order += 1

    df = pd.DataFrame(rows, columns=["PO Number", "PO Line", "PO Date", "Company", "Company Type",
                                     "Order Priority", "Vendor", "Part Number", "Quantity", "Unit Price USD"])
    df["Line Value USD"] = (df["Quantity"] * df["Unit Price USD"]).round(2)
    return df


def main() -> None:
    OFFERS.mkdir(parents=True, exist_ok=True)
    base = make_base()
    base.to_excel(INPUT / "base_purchases.xlsx", index=False)

    # Vendor Alpha - clean US numbers, offers alternatives, lead time
    a = pick(base, 3_000)
    alpha = pd.DataFrame({
        "Requested Part Number": a["Part Number"],
        "Offered Part Number": [alt_pn(p) if rng.random() < 0.15 else p for p in a["Part Number"]],
        "Description": a["Description"],
        "UoM": a["UOM"],
        "MOQ": rng.choice([1, 1, 5, 10, 25], len(a)),
        "Lead_Time": rng.integers(3, 60, len(a)),
        "Price USD": [offer_price(p) for p in a["Unit Price USD"]],
    })
    alpha.to_excel(OFFERS / "offer_vendor_alpha.xlsx", sheet_name="Offer", index=False)
    orig = alpha[alpha["Offered Part Number"] == alpha["Requested Part Number"]]
    offers = {("Vendor Alpha", pn): pr for pn, pr in zip(orig["Requested Part Number"], orig["Price USD"])}

    # Vendor Beta - European number format as text, messy part numbers
    b = pick(base, 2_800)
    messy = [p.lower() if rng.random() < 0.2 else (f" {p} " if rng.random() < 0.2 else p) for p in b["Part Number"]]
    beta_prices = [offer_price(p) for p in b["Unit Price USD"]]
    offers.update({("Vendor Beta", pn): pr for pn, pr in zip(b["Part Number"], beta_prices)})
    beta = pd.DataFrame({
        "PartNumber": messy,
        "Offered PN": messy,
        "DESCRIPTION": b["Description"],
        "Sales Price": [eu_number(p) for p in beta_prices],
    })
    beta.to_excel(OFFERS / "offer_vendor_beta.xlsx", sheet_name="Beta Offer", index=False)

    # Vendor Gamma - price list with quantity breaks
    g = pick(base, 2_500)
    rows = []
    for _, r in g.iterrows():
        p1 = offer_price(r["Unit Price USD"])
        offers[("Vendor Gamma", r["Part Number"])] = p1
        rows.append({
            "PNR": r["Part Number"], "KWD": r["Description"], "UNP": p1, "UM": r["UOM"], "MSQ": 1,
            "Qty1": 1, "Price1": p1,
            "Qty2": 50, "Price2": round(p1 * 0.92, 2),
            "Qty3": 200 if rng.random() < 0.7 else None, "Price3": round(p1 * 0.85, 2) if rng.random() < 0.7 else None,
        })
    pd.DataFrame(rows).to_excel(OFFERS / "offer_vendor_gamma.xlsx", sheet_name="pricelist", index=False)

    # Vendor Delta - EUR and USD, 1,234.56 style text
    d = pick(base, 2_000)
    usd = [offer_price(p) for p in d["Unit Price USD"]]
    offers.update({("Vendor Delta", pn): pr for pn, pr in zip(d["Part Number"], usd)})
    delta = pd.DataFrame({
        "P/N": d["Part Number"],
        "Description": d["Description"],
        "Price unit (EUR)": [f"{u / 1.08:,.2f}" for u in usd],
        "Price USD": [f"{u:,.2f}" for u in usd],
        "Currency": "USD",
        "UOM": d["UOM"],
        "MOQ": rng.choice([1, 2, 5], len(d)),
    })
    delta.to_excel(OFFERS / "offer_vendor_delta.xlsx", sheet_name="Sheet2", index=False)

    # Vendor Epsilon - several offers per part, alternatives, parts we never bought
    e = pick(base, 1_900)
    rows = []
    for _, r in e.iterrows():
        for _ in range(int(rng.integers(1, 3))):
            supplied = alt_pn(r["Part Number"]) if rng.random() < 0.25 else r["Part Number"]
            price = offer_price(r["Unit Price USD"])
            if supplied == r["Part Number"]:
                key = ("Vendor Epsilon", r["Part Number"])
                offers[key] = min(price, offers.get(key, price))
            rows.append({"Cust Req'd Part": r["Part Number"], "Part supplied": supplied,
                         "Supplied Desc": r["Description"], "Price (USD)": price,
                         "Supplied UOM": r["UOM"]})
    for i in range(300):  # offer-only parts
        rows.append({"Cust Req'd Part": f"FK-{90000 + i}", "Part supplied": f"FK-{90000 + i}",
                     "Supplied Desc": random.choice(DESCRIPTIONS),
                     "Price (USD)": float(np.round(rng.lognormal(1.8, 1.2), 2)), "Supplied UOM": "EA"})
    pd.DataFrame(rows).to_excel(OFFERS / "offer_vendor_epsilon.xlsx", sheet_name="Quote", index=False)

    make_po_lines(base, offers).to_excel(INPUT / "purchase_order_lines.xlsx", index=False)
    print(f"Sample data written to {INPUT}")


if __name__ == "__main__":
    main()
