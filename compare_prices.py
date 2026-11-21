"""
Supplier Price Comparison

Reads offer files from several suppliers (each with its own layout),
standardises them, and builds one comparison table per part number:
best / second / third price, price at the ordered quantity (quantity
breaks), original vs. alternative part numbers and potential savings
against the price currently paid.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

import config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_colnames(df: pd.DataFrame) -> pd.DataFrame:
    """Trim column names and collapse repeated spaces."""
    df = df.copy()
    df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]
    return df


def load_table(path: Path, sheet_name: Optional[str] = None) -> pd.DataFrame:
    """Read an Excel or CSV file."""
    path = Path(path)
    if path.suffix.lower() in {".xlsx", ".xlsm", ".xls"}:
        return pd.read_excel(path, sheet_name=sheet_name or 0)
    if path.suffix.lower() in {".csv", ".txt"}:
        return pd.read_csv(path)
    raise ValueError(f"Unsupported file type: {path}")


def pick_first_existing(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    """Return the first candidate column that exists in df."""
    return next((c for c in candidates if c in df.columns), None)


def normalize_pn(series: pd.Series) -> pd.Series:
    """Part number clean-up: no spaces (incl. non-breaking), upper case, empty for missing."""
    s = series.fillna("").astype(str)
    s = s.str.replace("\u00a0", "", regex=False)
    s = s.str.replace(r"\s+", "", regex=True)
    s = s.str.upper()
    return s.replace({"NAN": "", "NONE": ""})


def to_float(series: pd.Series) -> pd.Series:
    """
    Convert European and US number formats to float:
    '141,35' -> 141.35 · '1 234,56' -> 1234.56 · '1,234.56' -> 1234.56
    """
    s = series.astype(str)
    s = s.str.replace("\u00a0", "", regex=False).str.replace(" ", "", regex=False)
    both = s.str.contains(",", regex=False) & s.str.contains(".", regex=False)
    s = s.where(~both, s.str.replace(",", "", regex=False))   # 1,234.56 -> 1234.56
    s = s.str.replace(",", ".", regex=False)                   # 141,35   -> 141.35
    return pd.to_numeric(s, errors="coerce")


# ---------------------------------------------------------------------------
# 1) Supplier offer -> standard table (one row per part number)
# ---------------------------------------------------------------------------

def build_supplier_df(info: Dict[str, Any], supplier: str) -> pd.DataFrame:
    raw = normalize_colnames(load_table(info["file"], info.get("sheet_name")))

    data = {}
    for target, candidates in info["columns"].items():
        src = pick_first_existing(raw, candidates)
        if src is not None:
            data[target] = raw[src]
    if not data:
        raise ValueError(f"No mapped columns found for supplier '{supplier}'.")
    out = pd.DataFrame(data)

    if "Part Number" in out.columns:
        out["Part Number"] = normalize_pn(out["Part Number"])
    elif "offered PN" in out.columns:
        out["Part Number"] = normalize_pn(out["offered PN"])
    else:
        raise ValueError(f"Supplier '{supplier}' has neither 'Part Number' nor 'offered PN'.")
    out = out[out["Part Number"] != ""]

    # Numeric columns
    for col in out.columns:
        if col == "offered Price" or "Price Break" in col or "Qty Break" in col:
            out[col] = to_float(out[col]).astype("float64")

    # Several offers for one part -> keep the cheapest valid one
    if "offered Price" in out.columns:
        valid = np.isfinite(out["offered Price"]) & (out["offered Price"] > 0)
        out = pd.concat([out[valid].sort_values("offered Price"), out[~valid]])
    out = out.drop_duplicates("Part Number", keep="first").set_index("Part Number")

    return out.rename(columns={c: f"{supplier} {c}" for c in out.columns})


# ---------------------------------------------------------------------------
# 2) Price at the ordered quantity (quantity breaks)
# ---------------------------------------------------------------------------

def price_by_break(df: pd.DataFrame, supplier: str, order_qty: np.ndarray) -> Optional[np.ndarray]:
    """
    Pick the price of the largest break the order quantity reaches.
    Breaks with a missing quantity or price never win. Falls back to the
    base offered price when no break applies.
    """
    pairs = [(f"{supplier} Qty Break {i}", f"{supplier} Price Break {i}") for i in range(1, 30)]
    pairs = [(q, p) for q, p in pairs if q in df.columns and p in df.columns]
    if not pairs:
        return None

    Q = np.column_stack([df[q].to_numpy("float64") for q, _ in pairs])
    P = np.column_stack([df[p].to_numpy("float64") for _, p in pairs])

    usable = np.isfinite(Q) & (Q > 0) & np.isfinite(P) & (P > 0)
    reached = usable & (order_qty[:, None] >= Q)

    Q_reached = np.where(reached, Q, -np.inf)
    best = Q_reached.argmax(axis=1)
    has_break = reached.any(axis=1)
    chosen = P[np.arange(len(df)), best]

    base_col = f"{supplier} offered Price"
    base = df[base_col].to_numpy("float64") if base_col in df.columns else np.full(len(df), np.nan)

    result = np.where(has_break, chosen, base)
    return np.where(np.isfinite(result) & (result > 0), result, np.nan)


def supplier_price(df: pd.DataFrame, supplier: str) -> Optional[np.ndarray]:
    """Price used for ranking: price at ordered quantity if available, else offered price."""
    for col in (f"{supplier} Price by Break", f"{supplier} offered Price"):
        if col in df.columns:
            return df[col].to_numpy("float64")
    return None


# ---------------------------------------------------------------------------
# 3) Original vs. alternative part number
# ---------------------------------------------------------------------------

def is_original(df: pd.DataFrame, supplier: str) -> np.ndarray:
    """True where the supplier offers the exact requested part number."""
    if supplier in config.ALWAYS_ORIGINAL:
        return np.ones(len(df), dtype=bool)
    col = f"{supplier} offered PN"
    if col not in df.columns:
        return np.ones(len(df), dtype=bool)
    offered = normalize_pn(df[col])
    return ((offered == "") | (offered == normalize_pn(df["Part Number"]))).to_numpy()


# ---------------------------------------------------------------------------
# 4) Best / second / third price
# ---------------------------------------------------------------------------

def rank_prices(df: pd.DataFrame, suppliers: List[str], original_only: bool = False) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return price matrix sorted cheapest first, matching supplier names and a validity mask."""
    names, cols = [], []
    for sup in suppliers:
        price = supplier_price(df, sup)
        if price is None:
            continue
        if original_only:
            price = np.where(is_original(df, sup), price, np.nan)
        names.append(sup)
        cols.append(price)

    P = np.column_stack(cols)
    valid = np.isfinite(P) & (P > 0)
    order = np.argsort(np.where(valid, P, np.inf), axis=1)
    rows = np.arange(len(df))[:, None]
    return P[rows, order], np.array(names, dtype=object)[order], valid[rows, order]


def add_rankings(df: pd.DataFrame, suppliers: List[str]) -> pd.DataFrame:
    P, N, V = rank_prices(df, suppliers)
    for k, label in enumerate(["Best", "Second", "Third"]):
        if k < P.shape[1]:
            df[f"{label} Price"] = np.where(V[:, k], P[:, k], np.nan)
            df[f"{label} Price Supplier"] = np.where(V[:, k], N[:, k], None)
        else:
            df[f"{label} Price"], df[f"{label} Price Supplier"] = np.nan, None

    P, N, V = rank_prices(df, suppliers, original_only=True)
    df["Best Price (Original PN)"] = np.where(V[:, 0], P[:, 0], np.nan)
    df["Best Price Supplier (Original PN)"] = np.where(V[:, 0], N[:, 0], None)
    return df


def pn_type(df: pd.DataFrame, supplier_col: str) -> pd.Series:
    """'Original' or 'Alternative' for the supplier named in supplier_col."""
    flags = {sup: is_original(df, sup) for sup in config.SUPPLIERS}
    out = []
    for i, sup in enumerate(df[supplier_col].to_numpy(dtype=object)):
        if sup is None or (isinstance(sup, float) and np.isnan(sup)):
            out.append(None)
        else:
            out.append("Original" if flags[sup][i] else "Alternative")
    return pd.Series(out, index=df.index)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    suppliers = list(config.SUPPLIERS)

    # Base: parts we buy today
    base = normalize_colnames(pd.read_excel(config.BASE_FILE))
    base["Part Number"] = normalize_pn(base["Part Number"])

    # Supplier offers, side by side (index = part number)
    tables, offered_counts = [], {}
    for sup, info in config.SUPPLIERS.items():
        t = build_supplier_df(info, sup)
        tables.append(t)
        offered_counts[sup] = len(t)
    offers = pd.concat(tables, axis=1, join="outer")

    # All base parts + parts that only appear in offers
    df = base.merge(offers, left_on="Part Number", right_index=True, how="left")
    extra = offers.loc[~offers.index.isin(base["Part Number"])].reset_index(names="Part Number")
    df = pd.concat([df, extra], ignore_index=True)
    df["Row Source"] = np.where(df["Part Number"].isin(base["Part Number"]), "In Base", "Offer Only")

    # Price at the quantity we order
    qty_col = pick_first_existing(df, config.ORDER_QTY_CANDIDATES)
    order_qty = to_float(df[qty_col]).fillna(0).to_numpy("float64") if qty_col else np.zeros(len(df))
    for sup in suppliers:
        pbb = price_by_break(df, sup, order_qty)
        if pbb is not None:
            df[f"{sup} Price by Break"] = pbb

    # Rankings and part number type
    df = add_rankings(df, suppliers)
    for label in ["Best", "Second", "Third"]:
        df[f"{label} PN Type"] = pn_type(df, f"{label} Price Supplier")

    # Potential saving vs. the price paid today (original part numbers only)
    paid_col = pick_first_existing(df, config.PAID_PRICE_CANDIDATES)
    if paid_col:
        paid = to_float(df[paid_col])
        best = df["Best Price (Original PN)"]
        unit_saving = (paid - best).where((paid - best) > 0)
        df["Saving per Unit USD"] = unit_saving
        df["Potential Saving USD"] = unit_saving * order_qty

    # Column order: base info, supplier blocks, results
    result_cols = ["Best Price", "Best Price Supplier", "Best PN Type",
                   "Best Price (Original PN)", "Best Price Supplier (Original PN)",
                   "Second Price", "Second Price Supplier", "Second PN Type",
                   "Third Price", "Third Price Supplier", "Third PN Type",
                   "Saving per Unit USD", "Potential Saving USD"]
    supplier_cols = [c for sup in suppliers for c in df.columns if c.startswith(f"{sup} ")]
    base_cols = [c for c in df.columns if c not in supplier_cols + result_cols]
    df = df[base_cols + supplier_cols + [c for c in result_cols if c in df.columns]]
    df = df.sort_values(["Row Source", "Part Number"], kind="mergesort")
    money_cols = [c for c in df.columns
                  if ("Price" in c or "Saving" in c) and pd.api.types.is_numeric_dtype(df[c])]
    df[money_cols] = df[money_cols].round(2)

    # Summary per supplier
    in_base = df["Row Source"] == "In Base"
    summary = pd.DataFrame([{
        "Supplier": sup,
        "Parts offered": offered_counts[sup],
        "Parts matched to base": int((df[f"{sup} offered Price"].notna() & in_base).sum()) if f"{sup} offered Price" in df else 0,
        "Times best price": int((df["Best Price Supplier"] == sup).sum()),
        "Times best (original PN)": int((df["Best Price Supplier (Original PN)"] == sup).sum()),
    } for sup in suppliers])

    overall = pd.DataFrame({
        "Metric": ["Parts in base", "Parts with at least one offer", "Offer-only parts",
                   "Parts with a cheaper original offer", "Potential saving USD"],
        "Value": [int(in_base.sum()),
                  int((in_base & df["Best Price"].notna()).sum()),
                  int((~in_base).sum()),
                  int(df.get("Saving per Unit USD", pd.Series(dtype=float)).notna().sum()),
                  round(float(df.get("Potential Saving USD", pd.Series(dtype=float)).sum()), 2)],
    }).astype({"Value": object})

    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(config.OUTPUT_FILE) as writer:
        df.to_excel(writer, sheet_name="Comparison", index=False)
        summary.to_excel(writer, sheet_name="Supplier Summary", index=False)
        overall.to_excel(writer, sheet_name="Overall", index=False)

    print(summary.to_string(index=False))
    print()
    print(overall.to_string(index=False))
    print(f"\nSaved: {config.OUTPUT_FILE}")


if __name__ == "__main__":
    main()
