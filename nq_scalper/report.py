"""Performance reporting and charts.

Generates summary stats, equity curve, year-by-year breakdown,
monthly heatmap, score bucket analysis, session analysis,
day-of-week analysis, and exit reason breakdown.
"""

import logging
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

from config import OUTPUT_DIR, INITIAL_CAPITAL

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# ANALYSIS
# ═══════════════════════════════════════════════════════════════════

def analyze_results(trades: list[dict], equity_curve: list[float]) -> dict:
    """Compute comprehensive backtest statistics."""
    if not trades:
        return {"total_trades": 0}

    df = pd.DataFrame(trades)
    total = len(df)
    wins = len(df[df["total_pnl"] > 0])
    losses = total - wins
    win_rate = 100.0 * wins / total if total > 0 else 0

    # TP1 stats
    tp1_hits = df["tp1_hit"].sum()
    tp1_rate = 100.0 * tp1_hits / total if total > 0 else 0

    # P&L
    total_pnl = df["total_pnl"].sum()
    avg_pnl = df["total_pnl"].mean()
    avg_win = df[df["total_pnl"] > 0]["total_pnl"].mean() if wins > 0 else 0
    avg_loss = df[df["total_pnl"] <= 0]["total_pnl"].mean() if losses > 0 else 0

    # Profit factor
    gross_profit = df[df["total_pnl"] > 0]["total_pnl"].sum()
    gross_loss = abs(df[df["total_pnl"] <= 0]["total_pnl"].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Max drawdown
    cumulative = df["total_pnl"].cumsum()
    running_max = cumulative.cummax()
    drawdown = cumulative - running_max
    max_dd = drawdown.min()

    # Max consecutive losses
    max_consec_loss = 0
    streak = 0
    for pnl in df["total_pnl"]:
        if pnl <= 0:
            streak += 1
            max_consec_loss = max(max_consec_loss, streak)
        else:
            streak = 0

    # Sharpe ratio (annualized)
    if df["total_pnl"].std() > 0:
        sharpe = (df["total_pnl"].mean() / df["total_pnl"].std()) * np.sqrt(252)
    else:
        sharpe = 0.0

    # Total costs
    total_costs = df["costs"].sum()

    # Average R:R
    avg_rr = df["rr_achieved"].mean()

    # Exit reason breakdown
    exit_reasons = df["exit_reason"].value_counts().to_dict()

    # Session breakdown
    session_stats = {}
    for sess in df["entry_session"].unique():
        sdf = df[df["entry_session"] == sess]
        s_wins = len(sdf[sdf["total_pnl"] > 0])
        session_stats[sess] = {
            "trades": len(sdf),
            "pnl": round(sdf["total_pnl"].sum(), 2),
            "win_rate": round(100.0 * s_wins / len(sdf), 1) if len(sdf) > 0 else 0,
        }

    # Trail stage breakdown
    trail_stages = {}
    if tp1_hits > 0:
        trail_stages = df[df["tp1_hit"]]["trail_stage"].value_counts().to_dict()

    return {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 1),
        "tp1_hits": int(tp1_hits),
        "tp1_rate": round(tp1_rate, 1),
        "trail_stages": trail_stages,
        "total_pnl": round(total_pnl, 2),
        "avg_pnl": round(avg_pnl, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2),
        "max_drawdown": round(max_dd, 2),
        "max_consecutive_losses": max_consec_loss,
        "sharpe_ratio": round(sharpe, 2),
        "total_costs": round(total_costs, 2),
        "avg_rr": round(avg_rr, 2),
        "avg_score": round(df["entry_score"].mean(), 2),
        "exit_reasons": exit_reasons,
        "session_stats": session_stats,
        "final_capital": round(INITIAL_CAPITAL + total_pnl, 2),
    }


# ═══════════════════════════════════════════════════════════════════
# TEXT REPORT
# ═══════════════════════════════════════════════════════════════════

def print_summary(stats: dict) -> None:
    """Print a formatted summary to the logger."""
    sep = "=" * 60
    lines = [
        f"\n{sep}",
        "  NQ SWING SCALPER — BACKTEST RESULTS (V1 + Layer 1)",
        sep,
        f"  Total Trades:       {stats['total_trades']}",
        f"  Win Rate:           {stats['win_rate']:.1f}%",
        f"  Profit Factor:      {stats['profit_factor']:.2f}",
        f"  Total P&L:          ${stats['total_pnl']:,.2f}",
        f"  Avg P&L/Trade:      ${stats['avg_pnl']:,.2f}",
        f"  Avg Win:            ${stats['avg_win']:,.2f}",
        f"  Avg Loss:           ${stats['avg_loss']:,.2f}",
        f"  Max Drawdown:       ${stats['max_drawdown']:,.2f}",
        f"  Max Consec Losses:  {stats['max_consecutive_losses']}",
        f"  Sharpe Ratio:       {stats['sharpe_ratio']:.2f}",
        f"  TP1 Hit Rate:       {stats['tp1_rate']:.1f}%",
        f"  Avg R:R Achieved:   {stats['avg_rr']:.2f}",
        f"  Avg Entry Score:    {stats['avg_score']:.2f}",
        f"  Total Costs:        ${stats['total_costs']:,.2f}",
        f"  Final Capital:      ${stats['final_capital']:,.2f}",
        sep,
    ]

    # Exit reasons
    lines.append("\n  Exit Reasons:")
    for reason, count in stats.get("exit_reasons", {}).items():
        lines.append(f"    {reason:<15} {count:>5}")

    # Session stats
    lines.append("\n  Session Breakdown:")
    for sess, s in stats.get("session_stats", {}).items():
        lines.append(
            f"    {sess:<15} {s['trades']:>4} trades  "
            f"WR={s['win_rate']:>5.1f}%  P&L=${s['pnl']:>10,.2f}"
        )

    lines.append(sep)
    print("\n".join(lines))


def print_year_breakdown(trades: list[dict]) -> None:
    """Print year-by-year P&L breakdown."""
    if not trades:
        return
    df = pd.DataFrame(trades)
    df["year"] = pd.to_datetime(df["entry_time"]).dt.year
    sep = "-" * 60

    print(f"\n  Year-by-Year Breakdown:")
    print(f"  {sep}")
    print(f"  {'Year':<6} {'Trades':>7} {'Wins':>6} {'WR':>7} {'PF':>7} {'P&L':>12}")
    print(f"  {sep}")

    for year, grp in df.groupby("year"):
        n = len(grp)
        w = len(grp[grp["total_pnl"] > 0])
        wr = 100.0 * w / n if n > 0 else 0
        gp = grp[grp["total_pnl"] > 0]["total_pnl"].sum()
        gl = abs(grp[grp["total_pnl"] <= 0]["total_pnl"].sum())
        pf = gp / gl if gl > 0 else float("inf")
        pnl = grp["total_pnl"].sum()
        print(f"  {year:<6} {n:>7} {w:>6} {wr:>6.1f}% {pf:>6.2f} ${pnl:>10,.2f}")

    print(f"  {sep}")


def print_score_buckets(trades: list[dict]) -> None:
    """Print score bucket analysis."""
    if not trades:
        return
    df = pd.DataFrame(trades)

    buckets = [
        ("7.0-7.9", 7.0, 7.9999),
        ("8.0-8.2", 8.0, 8.2999),
        ("8.3-8.4", 8.3, 8.4999),
        ("8.5-8.9", 8.5, 8.9999),
        ("9.0+", 9.0, 10.0),
    ]

    sep = "-" * 60
    print(f"\n  Score Bucket Analysis:")
    print(f"  {sep}")
    print(f"  {'Bucket':<10} {'Trades':>7} {'WR':>7} {'PF':>7} {'Avg P&L':>10}")
    print(f"  {sep}")

    for label, lo, hi in buckets:
        grp = df[(df["entry_score"] >= lo) & (df["entry_score"] <= hi)]
        n = len(grp)
        if n == 0:
            continue
        w = len(grp[grp["total_pnl"] > 0])
        wr = 100.0 * w / n
        gp = grp[grp["total_pnl"] > 0]["total_pnl"].sum()
        gl = abs(grp[grp["total_pnl"] <= 0]["total_pnl"].sum())
        pf = gp / gl if gl > 0 else float("inf")
        avg = grp["total_pnl"].mean()
        print(f"  {label:<10} {n:>7} {wr:>6.1f}% {pf:>6.2f} ${avg:>9,.2f}")

    print(f"  {sep}")


def print_dow_analysis(trades: list[dict]) -> None:
    """Print day-of-week analysis."""
    if not trades:
        return
    df = pd.DataFrame(trades)
    df["dow"] = pd.to_datetime(df["entry_time"]).dt.day_name()
    dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

    sep = "-" * 60
    print(f"\n  Day-of-Week Analysis:")
    print(f"  {sep}")
    print(f"  {'Day':<12} {'Trades':>7} {'WR':>7} {'P&L':>12}")
    print(f"  {sep}")

    for day in dow_order:
        grp = df[df["dow"] == day]
        n = len(grp)
        if n == 0:
            continue
        w = len(grp[grp["total_pnl"] > 0])
        wr = 100.0 * w / n
        pnl = grp["total_pnl"].sum()
        print(f"  {day:<12} {n:>7} {wr:>6.1f}% ${pnl:>10,.2f}")

    print(f"  {sep}")


# ═══════════════════════════════════════════════════════════════════
# CHARTS
# ═══════════════════════════════════════════════════════════════════

def generate_charts(trades: list[dict], equity_curve: list[float], prefix: str = "") -> None:
    """Generate all performance charts and save to output directory."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if not trades:
        logger.warning("No trades to chart.")
        return

    df = pd.DataFrame(trades)

    # --- 1. Equity Curve ---
    _plot_equity_curve(equity_curve, prefix=prefix)

    # --- 2. Monthly P&L Heatmap ---
    _plot_monthly_heatmap(df, prefix=prefix)

    # --- 3. Trade P&L Bars ---
    _plot_trade_pnl(df, prefix=prefix)

    # --- 4. Exit Reason Pie ---
    _plot_exit_reasons(df, prefix=prefix)


def _plot_equity_curve(equity_curve: list[float], prefix: str = "") -> None:
    """Plot and save the equity curve."""
    fig, ax = plt.subplots(figsize=(14, 6))
    ax.plot(equity_curve, linewidth=1, color="#2ecc71")
    ax.axhline(y=INITIAL_CAPITAL, color="gray", linestyle="--", alpha=0.5)
    ax.set_title("Equity Curve — NQ Swing Scalper V1+L1", fontweight="bold")
    ax.set_xlabel("Bar")
    ax.set_ylabel("Equity ($)")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, f"{prefix}equity_curve.png")
    plt.savefig(path, dpi=150)
    plt.close()
    logger.info("Saved: %s", path)


def _plot_monthly_heatmap(df: pd.DataFrame, prefix: str = "") -> None:
    """Plot monthly P&L heatmap."""
    df_c = df.copy()
    df_c["entry_dt"] = pd.to_datetime(df_c["entry_time"])
    df_c["year"] = df_c["entry_dt"].dt.year
    df_c["month"] = df_c["entry_dt"].dt.month

    pivot = df_c.pivot_table(
        values="total_pnl", index="year", columns="month", aggfunc="sum", fill_value=0,
    )

    fig, ax = plt.subplots(figsize=(14, 8))
    im = ax.imshow(pivot.values, cmap="RdYlGn", aspect="auto")
    ax.set_xticks(range(12))
    ax.set_xticklabels(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
         "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    )
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index)

    # Annotate cells
    for i in range(len(pivot.index)):
        for j in range(12):
            if j < pivot.shape[1]:
                val = pivot.values[i, j]
                color = "white" if abs(val) > pivot.values.max() * 0.5 else "black"
                ax.text(j, i, f"${val:,.0f}", ha="center", va="center",
                        fontsize=7, color=color)

    ax.set_title("Monthly P&L Heatmap", fontweight="bold")
    plt.colorbar(im, ax=ax, label="P&L ($)")
    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, f"{prefix}monthly_heatmap.png")
    plt.savefig(path, dpi=150)
    plt.close()
    logger.info("Saved: %s", path)


def _plot_trade_pnl(df: pd.DataFrame, prefix: str = "") -> None:
    """Plot individual trade P&L bars."""
    fig, ax = plt.subplots(figsize=(14, 6))
    colors = ["#2ecc71" if p > 0 else "#e74c3c" for p in df["total_pnl"]]
    ax.bar(range(len(df)), df["total_pnl"], color=colors, width=1.0, alpha=0.8)
    ax.axhline(y=0, color="gray", linestyle="--", alpha=0.5)
    ax.set_title("Individual Trade P&L", fontweight="bold")
    ax.set_xlabel("Trade #")
    ax.set_ylabel("P&L ($)")
    ax.grid(True, alpha=0.3, axis="y")
    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, f"{prefix}trade_pnl.png")
    plt.savefig(path, dpi=150)
    plt.close()
    logger.info("Saved: %s", path)


def _plot_exit_reasons(df: pd.DataFrame, prefix: str = "") -> None:
    """Plot exit reason distribution."""
    reasons = df["exit_reason"].value_counts()
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.pie(
        reasons.values, labels=reasons.index, autopct="%1.1f%%",
        colors=plt.cm.Set3(np.linspace(0, 1, len(reasons))),
    )
    ax.set_title("Exit Reason Distribution", fontweight="bold")
    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, f"{prefix}exit_reasons.png")
    plt.savefig(path, dpi=150)
    plt.close()
    logger.info("Saved: %s", path)


# ═══════════════════════════════════════════════════════════════════
# VERIFICATION TABLE
# ═══════════════════════════════════════════════════════════════════

def print_verification_table(stats: dict) -> None:
    """Compare actual results to expected V1+L1 validated values."""
    expected = {
        "Total Trades": ("total_trades", 282, 10),
        "Win Rate": ("win_rate", 35.8, 15),
        "PF": ("profit_factor", 1.79, 20),
        "Total P&L": ("total_pnl", 184_053, 20),
        "Sharpe": ("sharpe_ratio", 3.82, 25),
        "Max DD": ("max_drawdown", -12_952, 25),
    }

    sep = "=" * 70
    print(f"\n{sep}")
    print("  VERIFICATION — Compare to Known V1+L1 Results")
    print(sep)
    print(f"  {'Metric':<15} {'Expected':>12} {'Actual':>12} {'Diff%':>8} {'Match?':>8}")
    print(f"  {'-'*15} {'-'*12} {'-'*12} {'-'*8} {'-'*8}")

    for label, (key, exp_val, tolerance) in expected.items():
        actual = stats.get(key, 0)
        if exp_val != 0:
            diff_pct = abs(actual - exp_val) / abs(exp_val) * 100
        else:
            diff_pct = 0
        match = "OK" if diff_pct <= tolerance else "REVIEW"

        if isinstance(exp_val, float) and abs(exp_val) < 100:
            print(f"  {label:<15} {exp_val:>12.2f} {actual:>12.2f} {diff_pct:>7.1f}% {match:>8}")
        else:
            print(f"  {label:<15} {exp_val:>12,.0f} {actual:>12,.0f} {diff_pct:>7.1f}% {match:>8}")

    print(sep)
    print("  Note: Differences up to ~20% expected due to scoring/parameter")
    print("  differences between Pine Script and Python implementations.")
    print(sep)


def print_before_after_comparison(stats: dict, trades: list[dict]) -> None:
    """Print before/after comparison table with the known pre-fix values."""
    # Known pre-fix values from diagnostic
    before = {
        "Total Trades": 322,
        "Win Rate": 33.2,
        "PF": 1.67,
        "Total P&L": 176_060,
        "Sharpe": 3.31,
        "Max DD": -23_169,
        "TP1 Hit Rate": "N/A",
    }

    after_map = {
        "Total Trades": stats.get("total_trades", 0),
        "Win Rate": stats.get("win_rate", 0),
        "PF": stats.get("profit_factor", 0),
        "Total P&L": stats.get("total_pnl", 0),
        "Sharpe": stats.get("sharpe_ratio", 0),
        "Max DD": stats.get("max_drawdown", 0),
        "TP1 Hit Rate": stats.get("tp1_rate", 0),
    }

    targets = {
        "Total Trades": "~282",
        "Win Rate": "35-40%",
        "PF": "1.7-1.8",
        "Total P&L": "$180K+",
        "Sharpe": "3.5+",
        "Max DD": "< $15K",
        "TP1 Hit Rate": "17-20%",
    }

    sep = "=" * 80
    print(f"\n{sep}")
    print("  BEFORE/AFTER COMPARISON (3 Fixes Applied)")
    print(f"  1. ATR min_periods: 2000 -> 100")
    print(f"  2. MTF pipeline: S/R levels + weekly resample aligned")
    print(f"  3. TP1 mode: fixed 100pts -> SL x 1.5")
    print(sep)
    print(f"  {'Metric':<15} {'Target':>12} {'Before':>12} {'After':>12} {'Change':>12}")
    print(f"  {'-'*15} {'-'*12} {'-'*12} {'-'*12} {'-'*12}")

    for label in before:
        tgt = targets[label]
        bef = before[label]
        aft = after_map[label]

        if isinstance(bef, str) or isinstance(aft, str):
            print(f"  {label:<15} {tgt:>12} {str(bef):>12} {str(aft):>12}         -")
            continue

        if isinstance(bef, float) and abs(bef) < 100:
            change = aft - bef
            sign = "+" if change >= 0 else ""
            print(f"  {label:<15} {tgt:>12} {bef:>12.2f} {aft:>12.2f} {sign}{change:>10.2f}")
        else:
            change = aft - bef
            sign = "+" if change >= 0 else ""
            print(f"  {label:<15} {tgt:>12} {bef:>12,.0f} {aft:>12,.0f} {sign}{change:>10,.0f}")

    print(sep)

    # Session distribution before/after
    sess_before = {"US": 186, "Europe": 135, "Asia": 1}
    sess_after = stats.get("session_stats", {})

    print(f"\n  SESSION DISTRIBUTION:")
    print(f"  {'Session':<12} {'Target':>10} {'Before':>10} {'After':>10} {'Change':>10}")
    print(f"  {'-'*12} {'-'*10} {'-'*10} {'-'*10} {'-'*10}")

    sess_targets = {"US": "~240", "Europe": "~40", "Asia": "0-1"}
    for sess in ["US", "Europe", "Asia"]:
        tgt = sess_targets.get(sess, "?")
        bef = sess_before.get(sess, 0)
        aft = sess_after.get(sess, {}).get("trades", 0)
        change = aft - bef
        sign = "+" if change >= 0 else ""
        print(f"  {sess:<12} {tgt:>10} {bef:>10} {aft:>10} {sign}{change:>9}")

    print(sep)
