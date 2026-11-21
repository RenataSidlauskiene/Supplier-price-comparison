"""
One-page overview of price compliance, drawn with Matplotlib.
Layout: KPI cards · price categories · monthly trend · category by company,
overpay by vendor and offer coverage by company.
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import pandas as pd

plt.rcParams["text.parse_math"] = False   # "$" signs are plain text

CATEGORIES = ["Below >30%", "Below ≤30%", "At offered price", "Above ≤30%", "Above >30%"]
LABELS = ["▼▼ below >30 %", "▼ below ≤30 %", "= at offered price", "▲ above ≤30 %", "▲▲ above >30 %"]
COLORS = ["#12705a", "#a3e0cc", "#d9d5ce", "#f0a07b", "#b94a20"]
TEXT_ON = ["white", "#1f2937", "#1f2937", "#1f2937", "white"]
INK, MUTED, RED, GREEN, CARD, BG = "#111827", "#6b7280", "#b94a20", "#12705a", "white", "#f3f4f6"


def money(v: float) -> str:
    if abs(v) >= 1e6:
        return f"${v/1e6:,.2f}M"
    if abs(v) >= 1e3:
        return f"${v/1e3:,.0f}K"
    return f"${v:,.0f}"


def card(fig, x, y, w, h):
    fig.patches.append(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.008",
                                      transform=fig.transFigure, facecolor=CARD, edgecolor="#e5e7eb", lw=1,
                                      zorder=-10))


def kpi(fig, x, y, w, h, title, value, sub, colour=INK):
    card(fig, x, y, w, h)
    fig.text(x + 0.012, y + h - 0.022, title, fontsize=10, color=MUTED, va="top")
    fig.text(x + 0.012, y + h - 0.045, value, fontsize=22, color=colour, va="top", weight="bold")
    fig.text(x + 0.012, y + 0.012, sub, fontsize=8.5, color=MUTED, va="bottom", wrap=True)


def draw_dashboard(df: pd.DataFrame, path, year: int | None = None) -> None:
    year = year or int(df["PO Date"].dt.year.max())
    d = df[df["PO Date"].dt.year == year]
    o = d[d["Has Offer"]]
    first, last = d["Year-Month"].min(), d["Year-Month"].max()

    fig = plt.figure(figsize=(16, 15.5), facecolor=BG)
    fig.text(0.03, 0.975, "Purchase price compliance", fontsize=20, weight="bold", color=INK, va="top")
    fig.text(0.03, 0.952, f"PO lines vs lowest offered price · {first} – {last} · all companies · synthetic data",
             fontsize=11, color=MUTED, va="top")

    # ---- KPI cards --------------------------------------------------------
    total, quoted = d["Line Value USD"].sum(), o["Line Value USD"].sum()
    at_lines, at_spend = int(o["At Offered Price"].sum()), o.loc[o["At Offered Price"], "Line Value USD"].sum()
    above = int(o["Price Category"].isin(CATEGORIES[3:]).sum())
    overpay = d["Overpay USD"].sum()
    w, gap, y, h = 0.148, 0.008, 0.82, 0.105
    cards = [
        ("Total purchase value", money(total),
         f'{d["PO Number"].nunique():,} POs · {len(d):,} lines\n{d["Part Number"].nunique():,} part numbers', INK),
        ("Offer coverage", f"{len(o)/len(d):.0%}", f"{len(o):,} of {len(d):,} lines\nhave an offer", INK),
        ("Lines at offered price", f"{at_lines/len(o):.0%}", f"{at_lines:,} of {len(o):,}\nlines with offer", INK),
        ("Spend at offered price", f"{at_spend/quoted:.1%}", f"{money(at_spend)} of {money(quoted)}\nquoted", INK),
        ("Lines above offered price", f"{above/len(o):.0%}", f"{above:,} of {len(o):,}\nlines with offer", RED),
        ("Overpaid amount", money(overpay), f"{overpay/total:.1%} of total\non {money(quoted)} quoted spend", RED),
    ]
    for i, (t, v, s, c) in enumerate(cards):
        kpi(fig, 0.03 + i * (w + gap), y, w, h, t, v, s, c)

    # ---- Price categories -------------------------------------------------
    card(fig, 0.03, 0.665, 0.936, 0.14)
    fig.text(0.042, 0.792, "Lines by price category", fontsize=13, weight="bold", color=INK, va="top")
    fig.text(0.955, 0.792, f"{len(o):,} lines with offer · {len(d)-len(o):,} lines without offer excluded",
             fontsize=9, color=MUTED, va="top", ha="right")
    counts = o["Price Category"].value_counts().reindex(CATEGORIES, fill_value=0)
    share = counts / counts.sum()
    ax = fig.add_axes([0.042, 0.718, 0.912, 0.04])
    lefts = share.cumsum().values - share.values
    centers = list(lefts + share.values / 2)
    for i in range(len(centers)):                      # keep labels from overlapping
        lo = 0.06 if i == 0 else centers[i - 1] + 0.12
        centers[i] = max(centers[i], lo)
    for left, s, n, c, tc, lab, cx in zip(lefts, share, counts, COLORS, TEXT_ON, LABELS, centers):
        ax.barh(0, s, left=left, color=c, height=1)
        if s > 0.03:
            ax.text(left + s / 2, 0, f"{s:.0%}", ha="center", va="center", color=tc, fontsize=11, weight="bold")
        fig.text(0.042 + cx * 0.912, 0.704, f"{n:,}", ha="center", va="top", fontsize=13, color=INK)
        fig.text(0.042 + cx * 0.912, 0.684, lab, ha="center", va="top", fontsize=9, color=MUTED)
    ax.set_xlim(0, 1)
    ax.axis("off")

    # ---- Monthly trend sparklines ----------------------------------------
    card(fig, 0.03, 0.445, 0.936, 0.205)
    fig.text(0.042, 0.637, "Monthly trend", fontsize=13, weight="bold", color=INK, va="top")
    fig.text(0.955, 0.637, f"{first} – {last} · change vs previous month", fontsize=9, color=MUTED, va="top", ha="right")
    g = o.groupby("Year-Month")
    m = pd.DataFrame({
        "lines_at": g["At Offered Price"].mean(),
        "spend_at": g.apply(lambda x: x.loc[x["At Offered Price"], "Line Value USD"].sum() / x["Line Value USD"].sum(),
                            include_groups=False),
        "above": g["Price Category"].apply(lambda c: c.isin(CATEGORIES[3:]).mean()),
        "overpay": d.groupby("Year-Month")["Overpay USD"].sum(),
    })
    specs = [("Lines at offered price", "lines_at", True, True),
             ("Spend at offered price", "spend_at", True, True),
             ("Lines above offered price", "above", True, False),
             ("Overpaid amount", "overpay", False, False)]
    sw, sgap = 0.222, 0.008
    for i, (title, col, is_pct, up_good) in enumerate(specs):
        x0 = 0.042 + i * (sw + sgap)
        card(fig, x0, 0.457, sw, 0.155)
        series = m[col]
        cur, prev = series.iloc[-1], series.iloc[-2]
        delta = cur - prev
        good = (delta >= 0) == up_good
        arrow = "▲" if delta >= 0 else "▼"
        value = f"{cur:.1%}" if is_pct else money(cur)
        dtxt = f"{arrow} {delta*100:+.1f} pp" if is_pct else f"{arrow} {'+' if delta >= 0 else '−'}{money(abs(delta))}"
        fig.text(x0 + 0.01, 0.6, title, fontsize=10, color=MUTED, va="top")
        fig.text(x0 + 0.01, 0.578, value, fontsize=18, color=INK, va="top", weight="bold")
        fig.text(x0 + 0.01 + 0.075, 0.572, dtxt, fontsize=10, color=GREEN if good else RED, va="top")
        sax = fig.add_axes([x0 + 0.01, 0.478, sw - 0.02, 0.06])
        sax.plot(range(len(series)), series.values, color=GREEN if up_good else RED, lw=1.8)
        sax.axis("off")
        fig.text(x0 + 0.01, 0.462, series.index[0][-2:] + "/" + series.index[0][:4], fontsize=8, color=MUTED)
        fig.text(x0 + sw - 0.01, 0.462, series.index[-1][-2:] + "/" + series.index[-1][:4], fontsize=8,
                 color=MUTED, ha="right")

    # ---- Price category by company ---------------------------------------
    card(fig, 0.03, 0.03, 0.63, 0.4)
    fig.text(0.042, 0.417, "Price category by company", fontsize=13, weight="bold", color=INK, va="top")
    fig.text(0.65, 0.417, "% of PO lines with offer · sorted by order value", fontsize=9, color=MUTED,
             va="top", ha="right")
    value_by_co = d.groupby("Company")["Line Value USD"].sum().sort_values(ascending=False)
    mix = pd.crosstab(o["Company"], o["Price Category"], normalize="index").reindex(columns=CATEGORIES, fill_value=0)
    mix = mix.loc[value_by_co.index]
    mix.loc["Total"] = share.values
    values = list(value_by_co.values) + [total]
    names = list(mix.index)
    bax = fig.add_axes([0.2, 0.06, 0.45, 0.32])
    for r, (name, row) in enumerate(mix.iterrows()):
        yy = len(names) - 1 - r - (0.4 if name == "Total" else 0)
        left = 0
        for s, c, tc in zip(row.values, COLORS, TEXT_ON):
            bax.barh(yy, s, left=left, color=c, height=0.62)
            if s > 0.06:
                bax.text(left + s / 2, yy, f"{s:.0%}", ha="center", va="center", color=tc, fontsize=9, weight="bold")
            left += s
        bax.text(-0.02, yy, money(values[r]), ha="right", va="center", fontsize=10, color=INK)
        bax.text(-0.36, yy, name, ha="left", va="center", fontsize=10.5, color=INK,
                 weight="bold" if name == "Total" else "normal")
    bax.set_xlim(0, 1)
    bax.set_ylim(-1, len(names))
    bax.axis("off")

    # ---- Overpaid by vendor -----------------------------------------------
    card(fig, 0.67, 0.245, 0.296, 0.185)
    fig.text(0.682, 0.417, "Overpaid by vendor", fontsize=13, weight="bold", color=INK, va="top")
    fig.text(0.955, 0.417, "Top 7", fontsize=9, color=MUTED, va="top", ha="right")
    v = d.groupby("Vendor")["Overpay USD"].sum().sort_values(ascending=False).head(7)
    hbar(fig, [0.682, 0.255, 0.27, 0.13], v, lambda x: money(x), RED)

    # ---- Offer coverage by company ---------------------------------------
    card(fig, 0.67, 0.03, 0.296, 0.2)
    fig.text(0.682, 0.217, "Offer coverage by company", fontsize=13, weight="bold", color=INK, va="top")
    fig.text(0.955, 0.217, "% of lines with an offer", fontsize=9, color=MUTED, va="top", ha="right")
    cov = d.groupby("Company")["Has Offer"].mean().sort_values(ascending=False)
    hbar(fig, [0.682, 0.045, 0.27, 0.145], cov, lambda x: f"{x:.1%}", "#6b7280", max_value=1)

    fig.savefig(path, dpi=130, facecolor=BG)
    plt.close(fig)


def hbar(fig, rect, series: pd.Series, fmt, colour, max_value=None):
    ax = fig.add_axes(rect)
    top = max_value or series.max()
    n = len(series)
    for i, (name, val) in enumerate(series.items()):
        yy = n - 1 - i
        ax.barh(yy, top, left=0, color="#eef0f3", height=0.55)
        ax.barh(yy, val, left=0, color=colour, height=0.55)
        ax.text(-0.04 * top, yy, name, ha="right", va="center", fontsize=10, color=INK)
        ax.text(top * 1.03, yy, fmt(val), ha="left", va="center", fontsize=10, color=INK)
    ax.set_xlim(-0.55 * top, top * 1.28)
    ax.set_ylim(-0.6, n - 0.4)
    ax.axis("off")
