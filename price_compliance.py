"""
Price compliance analysis

Compares every purchase order line with the best price offered for the same
(original) part number and answers:
  - How many lines and how much spend were bought at the offered price?
  - Where do we pay more, and how much could we have saved?
  - Which companies and vendors account for the overpayment?
  - Is it getting better month by month?

Input:  data/output/price_comparison.xlsx (from compare_prices.py)
        data/input/purchase_order_lines.xlsx
Output: data/output/price_compliance.xlsx and charts in data/output/charts/
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, PercentFormatter
import numpy as np
import pandas as pd

import config
from dashboard import draw_dashboard
from export_powerbi import export as export_powerbi

CATEGORIES = ["Below >30%", "Below ≤30%", "At offered price", "Above ≤30%", "Above >30%"]
CATEGORY_COLORS = ["#12705a", "#a3e0cc", "#d9d5ce", "#f0a07b", "#b94a20"]


# ---------------------------------------------------------------------------
# Line level
# ---------------------------------------------------------------------------

def classify(deviation: pd.Series) -> pd.Series:
    """Deviation of the paid price from the offer -> price category."""
    tol, far = config.AGREED_TOLERANCE, config.FAR_THRESHOLD
    conditions = [
        deviation < -far,
        deviation < -tol,
        deviation.abs() <= tol,
        deviation <= far,
        deviation > far,
    ]
    return pd.Series(np.select(conditions, CATEGORIES, default=None), index=deviation.index).where(deviation.notna())


def enrich_lines() -> pd.DataFrame:
    lines = pd.read_excel(config.PO_LINES_FILE)
    offers = pd.read_excel(config.OUTPUT_FILE, sheet_name="Comparison",
                           usecols=["Part Number", "Best Price (Original PN)", "Best Price Supplier (Original PN)"])
    offers = offers.rename(columns={"Best Price (Original PN)": "Offer Price USD",
                                    "Best Price Supplier (Original PN)": "Offer Supplier"})

    df = lines.merge(offers, on="Part Number", how="left")
    df["PO Date"] = pd.to_datetime(df["PO Date"])
    df["Year-Month"] = df["PO Date"].dt.strftime("%Y-%m")
    df["Has Offer"] = df["Offer Price USD"].notna()
    df["Deviation"] = (df["Unit Price USD"] - df["Offer Price USD"]) / df["Offer Price USD"]
    df["Price Category"] = classify(df["Deviation"])
    df["At Offered Price"] = df["Price Category"] == "At offered price"
    df["From Offer Supplier"] = df["Vendor"] == df["Offer Supplier"]
    df["Overpay USD"] = ((df["Unit Price USD"] - df["Offer Price USD"]).clip(lower=0) * df["Quantity"]).fillna(0)
    return df


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------

def summarise(df: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Company-style summary table for any grouping."""
    g = df.groupby(by, dropna=False)
    out = pd.DataFrame({
        "Total Spend USD": g["Line Value USD"].sum(),
        "Spend With Offer USD": g.apply(lambda x: x.loc[x["Has Offer"], "Line Value USD"].sum(), include_groups=False),
        "Spend At Offered Price USD": g.apply(lambda x: x.loc[x["At Offered Price"], "Line Value USD"].sum(), include_groups=False),
        "Overpay USD": g["Overpay USD"].sum(),
        "PO": g["PO Number"].nunique(),
        "PO Lines": g.size(),
        "Lines With Offer": g["Has Offer"].sum(),
        "Unique Part Numbers": g["Part Number"].nunique(),
        "Parts With Offer": g.apply(lambda x: x.loc[x["Has Offer"], "Part Number"].nunique(), include_groups=False),
    })
    out["Spend With Offer %"] = out["Spend With Offer USD"] / out["Total Spend USD"]
    out["Offered-Price Spend / Quoted Spend %"] = out["Spend At Offered Price USD"] / out["Spend With Offer USD"]
    out["Overpay % of Quoted Spend"] = out["Overpay USD"] / out["Spend With Offer USD"]
    out["% Lines With Offer"] = out["Lines With Offer"] / out["PO Lines"]
    cols = ["Total Spend USD", "Spend With Offer USD", "Spend With Offer %", "Spend At Offered Price USD",
            "Offered-Price Spend / Quoted Spend %", "Overpay USD", "Overpay % of Quoted Spend",
            "PO", "PO Lines", "% Lines With Offer", "Unique Part Numbers", "Parts With Offer"]
    return out[cols]


def company_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Companies grouped by type, with a subtotal per type and a grand total."""
    parts = []
    for ctype, sub in df.groupby("Company Type"):
        s = summarise(sub, ["Company"]).sort_values("Total Spend USD", ascending=False)
        s.insert(0, "Company Type", ctype)
        total = summarise(sub.assign(Company="Total"), ["Company"])
        total.insert(0, "Company Type", ctype)
        parts += [s, total]
    grand = summarise(df.assign(Company="Total"), ["Company"])
    grand.insert(0, "Company Type", "All companies")
    return pd.concat(parts + [grand]).reset_index()


def category_by(df: pd.DataFrame, by: str) -> pd.DataFrame:
    """Share of offered lines in each price category."""
    t = pd.crosstab(df[by], df["Price Category"], normalize="index").reindex(columns=CATEGORIES, fill_value=0)
    t.loc["Total"] = df["Price Category"].value_counts(normalize=True).reindex(CATEGORIES, fill_value=0)
    return t


def monthly_kpis(df: pd.DataFrame) -> pd.DataFrame:
    offered = df[df["Has Offer"]]
    g = offered.groupby("Year-Month")
    return pd.DataFrame({
        "Lines at offered price %": g["At Offered Price"].mean(),
        "Spend at offered price %": g.apply(lambda x: x.loc[x["At Offered Price"], "Line Value USD"].sum()
                                            / x["Line Value USD"].sum(), include_groups=False),
        "Lines above offered price %": g["Price Category"].apply(lambda c: c.isin(["Above ≤30%", "Above >30%"]).mean()),
        "Overpay USD": g["Overpay USD"].sum(),
    })


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

usd = FuncFormatter(lambda x, _: f"${x/1000:,.0f}K")
plt.rcParams["text.parse_math"] = False
INK, MUTED, GRID = "#111827", "#6b7280", "#e5e7eb"
GREEN, RED, GREY = "#12705a", "#b94a20", "#6b7280"


def style(ax, title: str) -> None:
    """Shared clean look: no top/right spines, light grid, left-aligned title."""
    ax.set_title(title, loc="left", fontsize=12, weight="bold", color=INK, pad=12)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)


def chart_categories(df: pd.DataFrame, path, year: int) -> None:
    counts = df["Price Category"].value_counts().reindex(CATEGORIES, fill_value=0)
    share = counts / counts.sum()
    fig, ax = plt.subplots(figsize=(10, 1.9))
    left = 0
    text_colours = ["white", INK, INK, INK, "white"]
    for cat, s, n, colour, tc in zip(CATEGORIES, share, counts, CATEGORY_COLORS, text_colours):
        ax.barh(0, s, left=left, color=colour)
        if s > 0.04:
            ax.text(left + s / 2, 0, f"{s:.0%}\n{n:,} lines", ha="center", va="center", fontsize=9, color=tc)
        left += s
    ax.set_xlim(0, 1)
    ax.axis("off")
    ax.legend([plt.Rectangle((0, 0), 1, 1, color=c) for c in CATEGORY_COLORS], CATEGORIES,
              ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.05), frameon=False, fontsize=9)
    ax.set_title(f"PO lines by price category vs. best offered price · {year}", loc="left", fontsize=12,
                 weight="bold", color="#111827")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def chart_overpay_by_company(summary: pd.DataFrame, path, year: int) -> None:
    s = summary[summary["Company"] != "Total"].sort_values("Overpay USD", ascending=False)
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(s["Company"], s["Overpay USD"], color=RED, width=0.6, label="Overpay USD")
    ax.yaxis.set_major_formatter(usd)
    ax2 = ax.twinx()
    ax2.plot(s["Company"], s["Overpay % of Quoted Spend"], color=GREY, marker="o", lw=2,
             label="Overpay % of quoted spend")
    ax2.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    ax2.set_ylim(0, max(0.05, s["Overpay % of Quoted Spend"].max() * 1.4))
    ax2.tick_params(colors=MUTED, labelsize=9)
    for sp in ["top", "right", "left", "bottom"]:
        ax2.spines[sp].set_visible(False)
    for x, v in zip(s["Company"], s["Overpay USD"]):
        ax.text(x, v, f"${v/1000:,.0f}K", ha="center", va="bottom", fontsize=9, color=INK)
    style(ax, f"Overpayment by company · {year}")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, frameon=False, fontsize=9, loc="upper right")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def chart_monthly(kpi: pd.DataFrame, path) -> None:
    fig, ax = plt.subplots(figsize=(10, 3.6))
    ax.plot(kpi.index, kpi["Lines at offered price %"], marker="o", ms=4, lw=2, color=GREEN,
            label="Lines at offered price")
    ax.plot(kpi.index, kpi["Lines above offered price %"], marker="o", ms=4, lw=2, color=RED,
            label="Lines above offered price")
    ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    ax.set_ylim(0, 0.8)
    ax.tick_params(axis="x", rotation=45)
    style(ax, f"Monthly trend – share of offered PO lines · {kpi.index[0]} – {kpi.index[-1]}")
    ax.tick_params(axis="x", labelsize=8)
    ax.legend(frameon=False, fontsize=9, loc="upper right", ncol=2)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def chart_overpay_by_vendor(df: pd.DataFrame, path, year: int) -> None:
    v = df.groupby("Vendor")["Overpay USD"].sum().sort_values()
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.barh(v.index, v.values, color=RED, height=0.6)
    ax.xaxis.set_major_formatter(usd)
    for y, val in enumerate(v.values):
        ax.text(val, y, f"  ${val/1000:,.0f}K", va="center", fontsize=9, color=INK)
    style(ax, f"Overpayment by vendor · {year}")
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, lw=0.8)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    df = enrich_lines()
    offered = df[df["Has Offer"]]

    kpis = pd.DataFrame({
        "Metric": ["Total spend USD", "PO lines", "PO lines with an offer",
                   "Lines at offered price", "Spend at offered price (of quoted spend)",
                   "Lines above offered price", "Potential saving (overpay) USD"],
        "Value": [round(df["Line Value USD"].sum(), 2), len(df), int(df["Has Offer"].sum()),
                  f'{offered["At Offered Price"].mean():.1%}',
                  f'{offered.loc[offered["At Offered Price"], "Line Value USD"].sum() / offered["Line Value USD"].sum():.1%}',
                  f'{offered["Price Category"].isin(["Above ≤30%", "Above >30%"]).mean():.1%}',
                  round(df["Overpay USD"].sum(), 2)],
    })
    companies = company_summary(df)
    categories = category_by(offered, "Company")
    monthly = monthly_kpis(df)
    vendors = summarise(df, ["Vendor"]).sort_values("Overpay USD", ascending=False)

    # Charts: latest year (same period as the dashboards); trend covers all months
    year = int(df["PO Date"].dt.year.max())
    latest = df[df["PO Date"].dt.year == year]
    latest_companies = company_summary(latest)
    config.CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    chart_categories(latest[latest["Has Offer"]], config.CHARTS_DIR / "price_categories.png", year)
    chart_overpay_by_company(latest_companies[latest_companies["Company Type"] != "All companies"],
                             config.CHARTS_DIR / "overpay_by_company.png", year)
    chart_monthly(monthly, config.CHARTS_DIR / "monthly_trend.png")
    chart_overpay_by_vendor(latest, config.CHARTS_DIR / "overpay_by_vendor.png", year)
    draw_dashboard(df, config.CHARTS_DIR / "dashboard.png")
    export_powerbi(df)

    with pd.ExcelWriter(config.COMPLIANCE_FILE) as writer:
        kpis.to_excel(writer, sheet_name="KPIs", index=False)
        companies.round(4).to_excel(writer, sheet_name="Company Summary", index=False)
        categories.round(4).to_excel(writer, sheet_name="Category by Company")
        monthly.round(4).to_excel(writer, sheet_name="Monthly KPIs")
        vendors.round(4).to_excel(writer, sheet_name="Vendors")

    print(kpis.to_string(index=False))
    print(f"\nSaved: {config.COMPLIANCE_FILE}\nCharts: {config.CHARTS_DIR}")


if __name__ == "__main__":
    main()
