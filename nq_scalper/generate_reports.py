"""Generate detailed HTML+CSS reports for B1 and B2 strategies,
plus full trade-log CSVs for comparison.

Usage:
    python generate_reports.py
"""

import sys, os, io, time, base64, logging, warnings
from pathlib import Path
from datetime import datetime

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import config as cfg_mod
from data_feed import load_15m_data
from indicators import compute_15m_indicators, calc_atr_percentile
from mtf import build_mtf
from patterns import precompute_patterns
from scoring import (
    precompute_long_scores, precompute_long_confirmations,
    precompute_dynamic_thresholds, precompute_session_penalty,
    precompute_atr_adjustments, precompute_tech_sl,
)
from backtest_engine import BacktestEngine
import risk_manager as rm_mod
import scoring as sc_mod

# ======================================================================
OUT_DIR = str(SCRIPT_DIR / "output" / "reports")
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

CONFIGS = {
    "B1": {"label": "SL x 1.5 / 50pt", "tp1_ratio": 1.5, "max_sl_pts": 50.0, "max_risk": 1000.0},
    "B2": {"label": "SL x 2.0 / 50pt", "tp1_ratio": 2.0, "max_sl_pts": 50.0, "max_risk": 1000.0},
}

IS_YEARS  = set(range(2016, 2024))
OOS_YEARS = set(range(2024, 2026))


def _patch(tp1, sl, risk):
    cfg_mod.RR_RATIO_TP1 = tp1; cfg_mod.MAX_SL_POINTS = sl; cfg_mod.MAX_RISK_PER_CONTRACT = risk
    rm_mod.RR_RATIO_TP1 = tp1; rm_mod.MAX_SL_POINTS = sl; sc_mod.MAX_SL_POINTS = sl

def _restore():
    _patch(1.5, 40.0, 800.0)


def _et(ts):
    t = pd.Timestamp(ts)
    return t.tz_convert("US/Eastern") if t.tzinfo else t


# ======================================================================
# STATS
# ======================================================================

def compute_stats(trades):
    if not trades:
        return dict(trades=0, wins=0, losses=0, wr=0, pf=0, total_pnl=0, avg_pnl=0,
                    avg_win=0, avg_loss=0, max_dd=0, sharpe=0, tp1_hit_pct=0, trail_s3=0,
                    exit_counts={}, max_consec_loss=0, max_consec_win=0,
                    avg_sl_dist=0, avg_tp1_dist=0, median_pnl=0, best_trade=0, worst_trade=0,
                    avg_rr=0, avg_hold_bars=0)

    df = pd.DataFrame(trades)
    n = len(df)
    wins = int((df["total_pnl"] > 0).sum())
    losses = n - wins
    wr = 100.0 * wins / n

    gp = df.loc[df["total_pnl"] > 0, "total_pnl"].sum()
    gl = abs(df.loc[df["total_pnl"] <= 0, "total_pnl"].sum())
    pf = gp / gl if gl > 0 else 999.99

    total_pnl = df["total_pnl"].sum()
    avg_pnl = df["total_pnl"].mean()
    avg_win = df.loc[df["total_pnl"] > 0, "total_pnl"].mean() if wins else 0
    avg_loss = df.loc[df["total_pnl"] <= 0, "total_pnl"].mean() if losses else 0

    cum = df["total_pnl"].cumsum()
    max_dd = float((cum - cum.cummax()).min())

    std = df["total_pnl"].std()
    sharpe = (avg_pnl / std) * np.sqrt(252) if std and std > 0 else 0

    tp1_hits = int(df["tp1_hit"].sum())
    tp1_pct = 100.0 * tp1_hits / n
    trail_s3 = int((df["exit_reason"] == "TRAIL_S3").sum())

    # streaks
    is_win = (df["total_pnl"] > 0).astype(int).values
    is_loss = (df["total_pnl"] <= 0).astype(int).values
    def max_streak(arr):
        mx = cur = 0
        for v in arr:
            if v: cur += 1; mx = max(mx, cur)
            else: cur = 0
        return mx
    max_cw = max_streak(is_win)
    max_cl = max_streak(is_loss)

    return dict(
        trades=n, wins=wins, losses=losses, wr=round(wr, 1),
        pf=round(min(pf, 999.99), 2),
        total_pnl=round(total_pnl, 2), avg_pnl=round(avg_pnl, 2),
        avg_win=round(avg_win, 2), avg_loss=round(avg_loss, 2),
        max_dd=round(max_dd, 2), sharpe=round(sharpe, 2),
        tp1_hit_pct=round(tp1_pct, 1), trail_s3=trail_s3,
        exit_counts=df["exit_reason"].value_counts().to_dict(),
        max_consec_loss=max_cl, max_consec_win=max_cw,
        avg_sl_dist=round(df["sl_distance_pts"].mean(), 2),
        avg_tp1_dist=round((df["tp1_price"] - df["entry_price"]).mean(), 2),
        median_pnl=round(df["total_pnl"].median(), 2),
        best_trade=round(df["total_pnl"].max(), 2),
        worst_trade=round(df["total_pnl"].min(), 2),
        avg_rr=round(df["rr_achieved"].mean(), 2),
        avg_hold_bars=0,  # not tracked in trade dict
    )


def filter_trades(trades, years):
    return [t for t in trades if _et(t["entry_time"]).year in years]


# ======================================================================
# CHART HELPERS (return base64-encoded PNG)
# ======================================================================

def _fig_to_b64(fig):
    from io import BytesIO
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight", facecolor="#1a1a2e")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def _style_ax(ax, title=""):
    ax.set_facecolor("#16213e")
    ax.figure.set_facecolor("#1a1a2e")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for sp in ax.spines.values():
        sp.set_color("#444")
    ax.tick_params(colors="#aaa")
    ax.xaxis.label.set_color("#ccc")
    ax.yaxis.label.set_color("#ccc")
    if title:
        ax.set_title(title, color="white", fontweight="bold", fontsize=12, pad=10)
    ax.grid(alpha=0.15, color="#666")


def chart_equity_full(trades, name):
    fig, ax = plt.subplots(figsize=(12, 5))
    _style_ax(ax, f"{name} Equity Curve (Full Period)")
    if not trades:
        return _fig_to_b64(fig)
    pnls = [t["total_pnl"] for t in trades]
    cum = np.cumsum(pnls) + 100_000
    dates = [_et(t["entry_time"]) for t in trades]
    ax.plot(dates, cum, color="#00d4aa", linewidth=1.3)
    ax.fill_between(dates, 100_000, cum, alpha=0.15, color="#00d4aa")
    ax.axhline(100_000, color="#666", ls="--", alpha=0.5)
    ax.axvline(pd.Timestamp("2024-01-01", tz="US/Eastern"), color="#ff6b6b", ls="--", alpha=0.6)
    ax.text(pd.Timestamp("2024-01-01", tz="US/Eastern"), max(cum)*0.98, " OOS", color="#ff6b6b", fontsize=9)
    ax.set_ylabel("Equity ($)", color="#ccc")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.xticks(rotation=45)
    return _fig_to_b64(fig)


def chart_equity_oos(trades, name):
    fig, ax = plt.subplots(figsize=(12, 5))
    _style_ax(ax, f"{name} Equity Curve (OOS 2024-2025)")
    oos = filter_trades(trades, OOS_YEARS)
    if not oos:
        return _fig_to_b64(fig)
    pnls = [t["total_pnl"] for t in oos]
    cum = np.cumsum(pnls) + 100_000
    dates = [_et(t["entry_time"]) for t in oos]
    ax.plot(dates, cum, color="#4ecdc4", linewidth=1.5)
    ax.fill_between(dates, 100_000, cum, alpha=0.15, color="#4ecdc4")
    ax.axhline(100_000, color="#666", ls="--", alpha=0.5)
    ax.set_ylabel("Equity ($)", color="#ccc")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.xticks(rotation=45)
    return _fig_to_b64(fig)


def chart_drawdown(trades, name):
    fig, ax = plt.subplots(figsize=(12, 4))
    _style_ax(ax, f"{name} Drawdown Timeline")
    if not trades:
        return _fig_to_b64(fig)
    pnls = [t["total_pnl"] for t in trades]
    cum = np.cumsum(pnls)
    peak = np.maximum.accumulate(cum)
    dd = cum - peak
    dates = [_et(t["entry_time"]) for t in trades]
    ax.fill_between(dates, dd, 0, color="#ff6b6b", alpha=0.4)
    ax.plot(dates, dd, color="#ff6b6b", linewidth=0.8)
    ax.axvline(pd.Timestamp("2024-01-01", tz="US/Eastern"), color="#ffd93d", ls="--", alpha=0.5)
    ax.set_ylabel("Drawdown ($)", color="#ccc")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.xticks(rotation=45)
    return _fig_to_b64(fig)


def chart_monthly_heatmap(trades, name):
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.set_facecolor("#16213e")
    fig.set_facecolor("#1a1a2e")
    if not trades:
        return _fig_to_b64(fig)

    years_set = sorted(set(_et(t["entry_time"]).year for t in trades))
    data = np.full((12, len(years_set)), np.nan)
    for t in trades:
        et = _et(t["entry_time"])
        yi = years_set.index(et.year)
        mi = et.month - 1
        if np.isnan(data[mi, yi]):
            data[mi, yi] = 0
        data[mi, yi] += t["total_pnl"]

    masked = np.ma.masked_invalid(data)
    vmax = max(abs(np.nanmin(data)), abs(np.nanmax(data)), 1)
    im = ax.imshow(masked, cmap="RdYlGn", aspect="auto", vmin=-vmax, vmax=vmax)
    ax.set_xticks(range(len(years_set)))
    ax.set_xticklabels(years_set, color="#ccc")
    ax.set_yticks(range(12))
    ax.set_yticklabels(["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"], color="#ccc")
    for i in range(12):
        for j in range(len(years_set)):
            v = data[i, j]
            if not np.isnan(v):
                tc = "white" if abs(v) > vmax * 0.4 else "black"
                ax.text(j, i, f"${v:,.0f}", ha="center", va="center", fontsize=6.5, color=tc, fontweight="bold")
    ax.set_title(f"{name} Monthly P&L Heatmap", color="white", fontweight="bold", fontsize=12, pad=10)
    cb = plt.colorbar(im, ax=ax)
    cb.ax.yaxis.set_tick_params(color="#ccc")
    plt.setp(plt.getp(cb.ax.axes, "yticklabels"), color="#ccc")
    return _fig_to_b64(fig)


def chart_exit_pie(trades, name, period="Full"):
    fig, ax = plt.subplots(figsize=(6, 5))
    fig.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1a1a2e")
    if not trades:
        return _fig_to_b64(fig)
    reasons = pd.Series([t["exit_reason"] for t in trades]).value_counts()
    colors_map = {"FULL_STOP":"#e74c3c","TRAIL_S1":"#f39c12","TRAIL_S2":"#2ecc71","TRAIL_S3":"#27ae60","EOD_CLOSE":"#95a5a6"}
    cols = [colors_map.get(r, "#777") for r in reasons.index]
    wedges, texts, autotexts = ax.pie(reasons.values, labels=reasons.index, autopct="%1.1f%%",
                                       colors=cols, textprops={"color":"white","fontsize":9})
    for at in autotexts:
        at.set_fontsize(8)
        at.set_color("white")
    ax.set_title(f"{name} Exit Reasons ({period})", color="white", fontweight="bold", fontsize=11)
    return _fig_to_b64(fig)


def chart_pnl_distribution(trades, name):
    fig, ax = plt.subplots(figsize=(10, 4))
    _style_ax(ax, f"{name} Trade P&L Distribution")
    if not trades:
        return _fig_to_b64(fig)
    pnls = [t["total_pnl"] for t in trades]
    colors_arr = ["#2ecc71" if p > 0 else "#e74c3c" for p in pnls]
    ax.bar(range(len(pnls)), pnls, color=colors_arr, width=1.0, edgecolor="none")
    ax.axhline(0, color="#666", linewidth=0.5)
    ax.set_xlabel("Trade #", color="#ccc")
    ax.set_ylabel("P&L ($)", color="#ccc")
    return _fig_to_b64(fig)


def chart_yearly_bars(trades, name):
    fig, ax = plt.subplots(figsize=(10, 5))
    _style_ax(ax, f"{name} Yearly P&L")
    if not trades:
        return _fig_to_b64(fig)
    yearly = {}
    for t in trades:
        yr = _et(t["entry_time"]).year
        yearly[yr] = yearly.get(yr, 0) + t["total_pnl"]
    years = sorted(yearly.keys())
    vals = [yearly[y] for y in years]
    cols = ["#2ecc71" if v > 0 else "#e74c3c" for v in vals]
    bars = ax.bar(years, vals, color=cols, edgecolor="#333", linewidth=0.5)
    for b, v in zip(bars, vals):
        ax.text(b.get_x()+b.get_width()/2, v + (max(vals)*0.02 if v>=0 else -max(abs(min(vals)),1)*0.08),
                f"${v:,.0f}", ha="center", va="bottom", color="white", fontsize=7, fontweight="bold")
    ax.axhline(0, color="#666", linewidth=0.5)
    ax.set_ylabel("P&L ($)", color="#ccc")
    return _fig_to_b64(fig)


def chart_rolling_wr(trades, name, window=10):
    fig, ax = plt.subplots(figsize=(12, 4))
    _style_ax(ax, f"{name} Rolling {window}-Trade Win Rate")
    if len(trades) < window:
        return _fig_to_b64(fig)
    wins = [1 if t["total_pnl"] > 0 else 0 for t in trades]
    rwr = pd.Series(wins).rolling(window).mean() * 100
    dates = [_et(t["entry_time"]) for t in trades]
    ax.plot(dates, rwr.values, color="#4ecdc4", linewidth=1.2)
    ax.axhline(50, color="#ffd93d", ls="--", alpha=0.5)
    ax.set_ylabel("Win Rate (%)", color="#ccc")
    ax.set_ylim(0, 100)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.xticks(rotation=45)
    return _fig_to_b64(fig)


def chart_score_vs_pnl(trades, name):
    fig, ax = plt.subplots(figsize=(8, 5))
    _style_ax(ax, f"{name} Entry Score vs P&L")
    if not trades:
        return _fig_to_b64(fig)
    df = pd.DataFrame(trades)
    wins = df[df["total_pnl"] > 0]
    losses = df[df["total_pnl"] <= 0]
    ax.scatter(wins["entry_score"], wins["total_pnl"], c="#2ecc71", alpha=0.6, s=30, edgecolors="none", label="Win")
    ax.scatter(losses["entry_score"], losses["total_pnl"], c="#e74c3c", alpha=0.6, s=30, edgecolors="none", label="Loss")
    ax.axhline(0, color="#666", linewidth=0.5)
    ax.set_xlabel("Entry Score", color="#ccc")
    ax.set_ylabel("P&L ($)", color="#ccc")
    ax.legend(facecolor="#16213e", edgecolor="#444", labelcolor="white")
    return _fig_to_b64(fig)


def chart_session_bars(trades, name):
    fig, ax = plt.subplots(figsize=(6, 4))
    _style_ax(ax, f"{name} P&L by Session")
    if not trades:
        return _fig_to_b64(fig)
    sess_pnl = {}
    for t in trades:
        s = t["entry_session"]
        sess_pnl[s] = sess_pnl.get(s, 0) + t["total_pnl"]
    sessions = sorted(sess_pnl.keys())
    vals = [sess_pnl[s] for s in sessions]
    cols = ["#2ecc71" if v > 0 else "#e74c3c" for v in vals]
    ax.bar(sessions, vals, color=cols, edgecolor="#333")
    ax.axhline(0, color="#666", linewidth=0.5)
    ax.set_ylabel("P&L ($)", color="#ccc")
    return _fig_to_b64(fig)


def chart_dow_bars(trades, name):
    fig, ax = plt.subplots(figsize=(8, 4))
    _style_ax(ax, f"{name} P&L by Day of Week")
    if not trades:
        return _fig_to_b64(fig)
    dow_pnl = {i: 0 for i in range(5)}
    for t in trades:
        d = _et(t["entry_time"]).dayofweek
        if d < 5:
            dow_pnl[d] += t["total_pnl"]
    labels = DAYS[:5]
    vals = [dow_pnl[i] for i in range(5)]
    cols = ["#2ecc71" if v > 0 else "#e74c3c" for v in vals]
    ax.bar(labels, vals, color=cols, edgecolor="#333")
    ax.axhline(0, color="#666", linewidth=0.5)
    ax.set_ylabel("P&L ($)", color="#ccc")
    return _fig_to_b64(fig)


# ======================================================================
# HTML GENERATION
# ======================================================================

CSS = """
:root {
    --bg-primary: #0f0f1a;
    --bg-card: #1a1a2e;
    --bg-card-alt: #16213e;
    --accent: #00d4aa;
    --accent2: #4ecdc4;
    --red: #ff6b6b;
    --green: #2ecc71;
    --yellow: #ffd93d;
    --text: #e0e0e0;
    --text-dim: #888;
    --border: #2a2a4a;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    background: var(--bg-primary);
    color: var(--text);
    line-height: 1.6;
    padding: 20px;
}
.container { max-width: 1400px; margin: 0 auto; }

/* HEADER */
.header {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 40px;
    margin-bottom: 30px;
    text-align: center;
}
.header h1 { font-size: 2.2em; color: var(--accent); margin-bottom: 8px; }
.header .subtitle { color: var(--text-dim); font-size: 1.1em; }
.header .config-badge {
    display: inline-block; margin-top: 15px; padding: 8px 24px;
    background: rgba(0,212,170,0.15); border: 1px solid var(--accent);
    border-radius: 30px; font-size: 1em; color: var(--accent); font-weight: 600;
}

/* KPI ROW */
.kpi-row {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 16px; margin-bottom: 30px;
}
.kpi-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    text-align: center;
}
.kpi-card .kpi-value {
    font-size: 1.8em; font-weight: 700; margin-bottom: 4px;
}
.kpi-card .kpi-label { font-size: 0.85em; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.kpi-green .kpi-value { color: var(--green); }
.kpi-red .kpi-value { color: var(--red); }
.kpi-accent .kpi-value { color: var(--accent); }
.kpi-yellow .kpi-value { color: var(--yellow); }

/* SECTIONS */
.section {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 30px;
    margin-bottom: 24px;
}
.section h2 {
    font-size: 1.4em; color: var(--accent2); margin-bottom: 20px;
    padding-bottom: 10px; border-bottom: 1px solid var(--border);
}
.section h3 { font-size: 1.1em; color: var(--yellow); margin: 18px 0 10px 0; }

/* TABLES */
table {
    width: 100%; border-collapse: collapse; margin: 10px 0;
    font-size: 0.9em;
}
th {
    background: var(--bg-card-alt); color: var(--accent2);
    padding: 10px 14px; text-align: left; font-weight: 600;
    border-bottom: 2px solid var(--border);
}
td {
    padding: 8px 14px; border-bottom: 1px solid var(--border);
}
tr:hover td { background: rgba(78, 205, 196, 0.05); }
.num { text-align: right; font-variant-numeric: tabular-nums; font-family: 'Consolas', monospace; }
.pos { color: var(--green); }
.neg { color: var(--red); }

/* GRID LAYOUTS */
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px; }
@media (max-width: 900px) {
    .grid-2, .grid-3 { grid-template-columns: 1fr; }
}

/* CHART */
.chart-container { margin: 16px 0; text-align: center; }
.chart-container img {
    max-width: 100%; border-radius: 8px; border: 1px solid var(--border);
}

/* BADGE */
.badge {
    display: inline-block; padding: 3px 10px; border-radius: 12px;
    font-size: 0.8em; font-weight: 600;
}
.badge-green { background: rgba(46,204,113,0.2); color: var(--green); }
.badge-red { background: rgba(231,76,60,0.2); color: var(--red); }
.badge-yellow { background: rgba(255,217,61,0.2); color: var(--yellow); }

/* FOOTER */
.footer {
    text-align: center; padding: 20px; color: var(--text-dim); font-size: 0.85em;
    margin-top: 30px;
}

/* PERIOD COMPARISON */
.period-box {
    background: var(--bg-card-alt); border-radius: 8px; padding: 16px;
    border: 1px solid var(--border);
}
.period-box h4 { color: var(--accent); margin-bottom: 8px; font-size: 1em; }
"""


def _pnl_class(v):
    return "pos" if v > 0 else ("neg" if v < 0 else "")


def _pnl_html(v, fmt=",.0f"):
    cls = _pnl_class(v)
    return f'<span class="{cls}">${v:{fmt}}</span>'


def _pct_html(v):
    cls = "pos" if v > 0 else ("neg" if v < 0 else "")
    return f'<span class="{cls}">{v:.1f}%</span>'


def build_kpi_row(s, period="Full"):
    total_cls = "kpi-green" if s["total_pnl"] > 0 else "kpi-red"
    return f"""
    <div class="kpi-row">
        <div class="kpi-card {total_cls}"><div class="kpi-value">${s['total_pnl']:,.0f}</div><div class="kpi-label">Total P&L</div></div>
        <div class="kpi-card kpi-accent"><div class="kpi-value">{s['trades']}</div><div class="kpi-label">Total Trades</div></div>
        <div class="kpi-card kpi-accent"><div class="kpi-value">{s['wr']:.1f}%</div><div class="kpi-label">Win Rate</div></div>
        <div class="kpi-card kpi-accent"><div class="kpi-value">{s['pf']:.2f}</div><div class="kpi-label">Profit Factor</div></div>
        <div class="kpi-card kpi-yellow"><div class="kpi-value">{s['sharpe']:.2f}</div><div class="kpi-label">Sharpe Ratio</div></div>
        <div class="kpi-card kpi-red"><div class="kpi-value">${s['max_dd']:,.0f}</div><div class="kpi-label">Max Drawdown</div></div>
    </div>
    """


def build_stats_table(s, label=""):
    rows = [
        ("Total Trades",      f"{s['trades']}"),
        ("Wins / Losses",     f"{s['wins']} / {s['losses']}"),
        ("Win Rate",          f"{s['wr']:.1f}%"),
        ("Profit Factor",     f"{s['pf']:.2f}"),
        ("Total P&L",         f"${s['total_pnl']:,.0f}"),
        ("Avg P&L / Trade",   f"${s['avg_pnl']:,.0f}"),
        ("Median P&L",        f"${s['median_pnl']:,.0f}"),
        ("Avg Win",           f"${s['avg_win']:,.0f}"),
        ("Avg Loss",          f"${s['avg_loss']:,.0f}"),
        ("Best Trade",        f"${s['best_trade']:,.0f}"),
        ("Worst Trade",       f"${s['worst_trade']:,.0f}"),
        ("Max Drawdown",      f"${s['max_dd']:,.0f}"),
        ("Sharpe Ratio",      f"{s['sharpe']:.2f}"),
        ("Avg R:R Achieved",  f"{s['avg_rr']:.2f}"),
        ("TP1 Hit Rate",      f"{s['tp1_hit_pct']:.1f}%"),
        ("Trail S3 (Runners)",f"{s['trail_s3']}"),
        ("Max Consec Wins",   f"{s['max_consec_win']}"),
        ("Max Consec Losses", f"{s['max_consec_loss']}"),
        ("Avg SL Distance",   f"{s['avg_sl_dist']:.1f} pts"),
        ("Avg TP1 Distance",  f"{s['avg_tp1_dist']:.1f} pts"),
    ]
    html = f"<table><thead><tr><th>Metric</th><th class='num'>{label}</th></tr></thead><tbody>"
    for lbl, val in rows:
        html += f"<tr><td>{lbl}</td><td class='num'>{val}</td></tr>"
    html += "</tbody></table>"
    return html


def build_yearly_table(trades):
    yearly = {}
    for t in trades:
        yr = _et(t["entry_time"]).year
        if yr not in yearly:
            yearly[yr] = []
        yearly[yr].append(t)

    html = "<table><thead><tr><th>Year</th><th class='num'>Trades</th><th class='num'>Win Rate</th><th class='num'>PF</th><th class='num'>Total P&L</th><th class='num'>Avg P&L</th><th class='num'>Max DD</th></tr></thead><tbody>"
    for yr in sorted(yearly.keys()):
        s = compute_stats(yearly[yr])
        oos_badge = ' <span class="badge badge-yellow">OOS</span>' if yr >= 2024 else ""
        html += f"<tr><td>{yr}{oos_badge}</td><td class='num'>{s['trades']}</td><td class='num'>{s['wr']:.1f}%</td>"
        html += f"<td class='num'>{s['pf']:.2f}</td><td class='num {_pnl_class(s['total_pnl'])}'>${s['total_pnl']:,.0f}</td>"
        html += f"<td class='num {_pnl_class(s['avg_pnl'])}'>${s['avg_pnl']:,.0f}</td>"
        html += f"<td class='num neg'>${s['max_dd']:,.0f}</td></tr>"
    html += "</tbody></table>"
    return html


def build_monthly_table(trades, year):
    monthly = {m: [] for m in range(1, 13)}
    for t in trades:
        et = _et(t["entry_time"])
        if et.year == year:
            monthly[et.month].append(t)

    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    html = "<table><thead><tr><th>Month</th><th class='num'>Trades</th><th class='num'>WR</th><th class='num'>PF</th><th class='num'>P&L</th></tr></thead><tbody>"
    for m in range(1, 13):
        s = compute_stats(monthly[m])
        if s["trades"] == 0:
            html += f"<tr><td>{months[m-1]}</td><td class='num'>0</td><td class='num'>-</td><td class='num'>-</td><td class='num'>-</td></tr>"
        else:
            html += f"<tr><td>{months[m-1]}</td><td class='num'>{s['trades']}</td><td class='num'>{s['wr']:.0f}%</td>"
            html += f"<td class='num'>{s['pf']:.2f}</td><td class='num {_pnl_class(s['total_pnl'])}'>${s['total_pnl']:,.0f}</td></tr>"
    html += "</tbody></table>"
    return html


def build_exit_table(trades, label=""):
    reasons = ["FULL_STOP","TRAIL_S1","TRAIL_S2","TRAIL_S3","EOD_CLOSE"]
    s = compute_stats(trades)
    html = f"<table><thead><tr><th>Exit Reason</th><th class='num'>Count</th><th class='num'>%</th><th class='num'>Avg P&L</th></tr></thead><tbody>"
    for r in reasons:
        cnt = s["exit_counts"].get(r, 0)
        pct = 100 * cnt / max(s["trades"], 1)
        r_trades = [t for t in trades if t["exit_reason"] == r]
        avg_pnl = np.mean([t["total_pnl"] for t in r_trades]) if r_trades else 0
        html += f"<tr><td>{r}</td><td class='num'>{cnt}</td><td class='num'>{pct:.1f}%</td><td class='num {_pnl_class(avg_pnl)}'>${avg_pnl:,.0f}</td></tr>"
    html += "</tbody></table>"
    return html


def build_session_table(trades):
    sessions = {}
    for t in trades:
        s = t["entry_session"]
        if s not in sessions:
            sessions[s] = []
        sessions[s].append(t)

    html = "<table><thead><tr><th>Session</th><th class='num'>Trades</th><th class='num'>WR</th><th class='num'>PF</th><th class='num'>Avg P&L</th><th class='num'>Total P&L</th></tr></thead><tbody>"
    for sess in sorted(sessions.keys()):
        s = compute_stats(sessions[sess])
        html += f"<tr><td>{sess}</td><td class='num'>{s['trades']}</td><td class='num'>{s['wr']:.1f}%</td>"
        html += f"<td class='num'>{s['pf']:.2f}</td><td class='num {_pnl_class(s['avg_pnl'])}'>${s['avg_pnl']:,.0f}</td>"
        html += f"<td class='num {_pnl_class(s['total_pnl'])}'>${s['total_pnl']:,.0f}</td></tr>"
    html += "</tbody></table>"
    return html


def build_dow_table(trades):
    dow = {i: [] for i in range(5)}
    for t in trades:
        d = _et(t["entry_time"]).dayofweek
        if d < 5:
            dow[d].append(t)

    html = "<table><thead><tr><th>Day</th><th class='num'>Trades</th><th class='num'>WR</th><th class='num'>PF</th><th class='num'>Avg P&L</th><th class='num'>Total P&L</th></tr></thead><tbody>"
    for d in range(5):
        s = compute_stats(dow[d])
        if s["trades"] == 0:
            html += f"<tr><td>{DAYS[d]}</td><td class='num'>0</td><td class='num'>-</td><td class='num'>-</td><td class='num'>-</td><td class='num'>-</td></tr>"
        else:
            html += f"<tr><td>{DAYS[d]}</td><td class='num'>{s['trades']}</td><td class='num'>{s['wr']:.1f}%</td>"
            html += f"<td class='num'>{s['pf']:.2f}</td><td class='num {_pnl_class(s['avg_pnl'])}'>${s['avg_pnl']:,.0f}</td>"
            html += f"<td class='num {_pnl_class(s['total_pnl'])}'>${s['total_pnl']:,.0f}</td></tr>"
    html += "</tbody></table>"
    return html


def build_score_table(trades):
    buckets = [(8.0,8.2,"8.0-8.2"),(8.3,8.4,"8.3-8.4"),(8.5,8.9,"8.5-8.9"),(9.0,99,"9.0+")]
    html = "<table><thead><tr><th>Score Bucket</th><th class='num'>Trades</th><th class='num'>WR</th><th class='num'>PF</th><th class='num'>Avg P&L</th><th class='num'>Total P&L</th></tr></thead><tbody>"
    for lo, hi, lbl in buckets:
        bt = [t for t in trades if lo <= t["entry_score"] <= hi]
        s = compute_stats(bt)
        if s["trades"] == 0:
            html += f"<tr><td>{lbl}</td><td class='num'>0</td><td colspan='4' class='num'>-</td></tr>"
        else:
            html += f"<tr><td>{lbl}</td><td class='num'>{s['trades']}</td><td class='num'>{s['wr']:.1f}%</td>"
            html += f"<td class='num'>{s['pf']:.2f}</td><td class='num {_pnl_class(s['avg_pnl'])}'>${s['avg_pnl']:,.0f}</td>"
            html += f"<td class='num {_pnl_class(s['total_pnl'])}'>${s['total_pnl']:,.0f}</td></tr>"
    html += "</tbody></table>"
    return html


def build_trade_log_table(trades):
    """Full trade log as HTML table."""
    html = """<table><thead><tr>
        <th>#</th><th>Entry Time</th><th>Exit Time</th><th>Session</th><th>Day</th>
        <th class='num'>Score</th><th class='num'>Entry</th><th class='num'>Exit</th>
        <th class='num'>SL Dist</th><th class='num'>TP1 Dist</th>
        <th>TP1 Hit</th><th>Exit Reason</th>
        <th class='num'>P&L TP1</th><th class='num'>P&L Runner</th><th class='num'>Costs</th>
        <th class='num'>Total P&L</th><th class='num'>Capital</th>
    </tr></thead><tbody>"""

    for t in trades:
        et = _et(t["entry_time"])
        xt = _et(t["exit_time"])
        tp1_dist = t["tp1_price"] - t["entry_price"]
        day = DAYS[et.dayofweek] if et.dayofweek < 5 else "Wknd"
        tp1_badge = '<span class="badge badge-green">YES</span>' if t["tp1_hit"] else '<span class="badge badge-red">NO</span>'
        pnl_cls = _pnl_class(t["total_pnl"])

        html += f"""<tr>
            <td>{t['trade_num']}</td>
            <td style="font-size:0.82em">{et.strftime('%Y-%m-%d %H:%M')}</td>
            <td style="font-size:0.82em">{xt.strftime('%Y-%m-%d %H:%M')}</td>
            <td>{t['entry_session']}</td><td>{day}</td>
            <td class='num'>{t['entry_score']:.1f}</td>
            <td class='num'>{t['entry_price']:,.2f}</td><td class='num'>{t['exit_price']:,.2f}</td>
            <td class='num'>{t['sl_distance_pts']:.1f}</td><td class='num'>{tp1_dist:.1f}</td>
            <td>{tp1_badge}</td><td>{t['exit_reason']}</td>
            <td class='num'>${t['pnl_tp1']:,.0f}</td><td class='num'>${t['pnl_runner']:,.0f}</td>
            <td class='num'>${t['costs']:,.0f}</td>
            <td class='num {pnl_cls}' style="font-weight:bold">${t['total_pnl']:,.0f}</td>
            <td class='num'>${t['capital_after']:,.0f}</td>
        </tr>"""

    html += "</tbody></table>"
    return html


def generate_html_report(name, cfg, trades, charts):
    all_trades = trades
    is_trades = filter_trades(trades, IS_YEARS)
    oos_trades = filter_trades(trades, OOS_YEARS)

    s_full = compute_stats(all_trades)
    s_is   = compute_stats(is_trades)
    s_oos  = compute_stats(oos_trades)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{name} Strategy Report</title>
    <style>{CSS}</style>
</head>
<body>
<div class="container">

<!-- HEADER -->
<div class="header">
    <h1>NQ Scalper Strategy Report</h1>
    <div class="subtitle">Comprehensive Walk-Forward Validation | Generated {now}</div>
    <div class="config-badge">{name} &mdash; TP1 = SL &times; {cfg['tp1_ratio']} | Max SL = {cfg['max_sl_pts']:.0f}pt | Risk = ${cfg['max_risk']:,.0f}/contract</div>
</div>

<!-- FULL PERIOD KPIs -->
<div class="section">
    <h2>Full Period Overview (2016-2026) &mdash; {s_full['trades']} Trades</h2>
    {build_kpi_row(s_full)}
</div>

<!-- WALK-FORWARD SPLIT -->
<div class="section">
    <h2>Walk-Forward Split</h2>
    <div class="grid-2">
        <div class="period-box">
            <h4>In-Sample (2016-2023) &mdash; {s_is['trades']} Trades</h4>
            {build_kpi_row(s_is)}
            {build_stats_table(s_is, "IS Value")}
        </div>
        <div class="period-box">
            <h4>Out-of-Sample (2024-2025) &mdash; {s_oos['trades']} Trades</h4>
            {build_kpi_row(s_oos)}
            {build_stats_table(s_oos, "OOS Value")}
        </div>
    </div>
</div>

<!-- CONSISTENCY -->
<div class="section">
    <h2>IS vs OOS Consistency</h2>
    <table>
        <thead><tr><th>Metric</th><th class='num'>IS</th><th class='num'>OOS</th><th class='num'>Change</th><th>Status</th></tr></thead>
        <tbody>"""

    # consistency rows
    for label, key, fmt, is_dd in [
        ("Win Rate", "wr", ".1f", False),
        ("Profit Factor", "pf", ".2f", False),
        ("Sharpe Ratio", "sharpe", ".2f", False),
        ("Avg P&L", "avg_pnl", ",.0f", False),
        ("Max Drawdown", "max_dd", ",.0f", True),
    ]:
        v_is = s_is[key]
        v_oos = s_oos[key]
        if is_dd:
            chg = ((abs(v_oos) - abs(v_is)) / max(abs(v_is), 0.01)) * 100
            ok = chg <= 30
        else:
            chg = ((v_oos - v_is) / max(abs(v_is), 0.01)) * 100
            ok = chg >= -30

        badge = '<span class="badge badge-green">PASS</span>' if ok else '<span class="badge badge-red">FAIL</span>'
        prefix = "$" if "pnl" in key or "dd" in key else ""
        suffix = "%" if key == "wr" else ""
        html += f"""<tr><td>{label}</td><td class='num'>{prefix}{v_is:{fmt}}{suffix}</td>
            <td class='num'>{prefix}{v_oos:{fmt}}{suffix}</td>
            <td class='num {_pnl_class(-chg if is_dd else chg)}'>{chg:+.1f}%</td><td>{badge}</td></tr>"""

    html += """</tbody></table></div>

<!-- EQUITY CURVES -->
<div class="section">
    <h2>Equity Curves</h2>
    <div class="chart-container"><img src="data:image/png;base64,""" + charts["equity_full"] + """" alt="Full Equity"></div>
    <div class="chart-container"><img src="data:image/png;base64,""" + charts["equity_oos"] + """" alt="OOS Equity"></div>
</div>

<!-- DRAWDOWN -->
<div class="section">
    <h2>Drawdown Analysis</h2>
    <div class="chart-container"><img src="data:image/png;base64,""" + charts["drawdown"] + """" alt="Drawdown"></div>
</div>

<!-- P&L DISTRIBUTION -->
<div class="section">
    <h2>Trade P&L Distribution</h2>
    <div class="chart-container"><img src="data:image/png;base64,""" + charts["pnl_dist"] + """" alt="P&L Distribution"></div>
</div>

<!-- YEARLY -->
<div class="section">
    <h2>Year-by-Year Breakdown</h2>
    <div class="chart-container"><img src="data:image/png;base64,""" + charts["yearly_bars"] + """" alt="Yearly P&L"></div>
    """ + build_yearly_table(all_trades) + """
</div>

<!-- MONTHLY HEATMAP -->
<div class="section">
    <h2>Monthly P&L Heatmap</h2>
    <div class="chart-container"><img src="data:image/png;base64,""" + charts["monthly_heatmap"] + """" alt="Monthly Heatmap"></div>
    <div class="grid-2">
        <div><h3>2024 Monthly</h3>""" + build_monthly_table(all_trades, 2024) + """</div>
        <div><h3>2025 Monthly</h3>""" + build_monthly_table(all_trades, 2025) + """</div>
    </div>
</div>

<!-- EXIT REASONS -->
<div class="section">
    <h2>Exit Reason Analysis</h2>
    <div class="grid-2">
        <div class="chart-container"><img src="data:image/png;base64,""" + charts["exit_pie_is"] + """" alt="Exit IS"></div>
        <div class="chart-container"><img src="data:image/png;base64,""" + charts["exit_pie_oos"] + """" alt="Exit OOS"></div>
    </div>
    <div class="grid-2">
        <div><h3>In-Sample</h3>""" + build_exit_table(is_trades) + """</div>
        <div><h3>Out-of-Sample</h3>""" + build_exit_table(oos_trades) + """</div>
    </div>
</div>

<!-- SESSION -->
<div class="section">
    <h2>Session Analysis</h2>
    <div class="grid-2">
        <div class="chart-container"><img src="data:image/png;base64,""" + charts["session_bars"] + """" alt="Session"></div>
        <div>
            <h3>Full Period</h3>""" + build_session_table(all_trades) + """
            <h3>OOS Only</h3>""" + build_session_table(oos_trades) + """
        </div>
    </div>
</div>

<!-- DAY OF WEEK -->
<div class="section">
    <h2>Day-of-Week Analysis</h2>
    <div class="grid-2">
        <div class="chart-container"><img src="data:image/png;base64,""" + charts["dow_bars"] + """" alt="DoW"></div>
        <div>
            <h3>Full Period</h3>""" + build_dow_table(all_trades) + """
            <h3>OOS Only</h3>""" + build_dow_table(oos_trades) + """
        </div>
    </div>
</div>

<!-- SCORE BUCKETS -->
<div class="section">
    <h2>Score Bucket Analysis</h2>
    <div class="chart-container"><img src="data:image/png;base64,""" + charts["score_pnl"] + """" alt="Score vs PnL"></div>
    <div class="grid-2">
        <div><h3>Full Period</h3>""" + build_score_table(all_trades) + """</div>
        <div><h3>OOS Only</h3>""" + build_score_table(oos_trades) + """</div>
    </div>
</div>

<!-- ROLLING WR -->
<div class="section">
    <h2>Rolling Win Rate</h2>
    <div class="chart-container"><img src="data:image/png;base64,""" + charts["rolling_wr"] + """" alt="Rolling WR"></div>
</div>

<!-- FULL TRADE LOG -->
<div class="section">
    <h2>Complete Trade Log ({s_full['trades']} Trades)</h2>
    <div style="overflow-x:auto; font-size:0.82em;">
    """ + build_trade_log_table(all_trades) + """
    </div>
</div>

<!-- FOOTER -->
<div class="footer">
    NQ Scalper &mdash; {name} Strategy Report | Generated {now} | Walk-Forward: Train 2016-2023, Test 2024-2025
</div>

</div>
</body>
</html>"""

    return html


# ======================================================================
# TRADE LOG CSV
# ======================================================================

def export_full_trade_csv(trades, name, cfg):
    rows = []
    cum_pnl = 0.0
    peak = 0.0
    for t in trades:
        cum_pnl += t["total_pnl"]
        peak = max(peak, cum_pnl)
        dd = cum_pnl - peak
        et = _et(t["entry_time"])
        xt = _et(t["exit_time"])
        rows.append({
            "trade_num":     t["trade_num"],
            "direction":     t["direction"],
            "entry_time":    et.strftime("%Y-%m-%d %H:%M"),
            "exit_time":     xt.strftime("%Y-%m-%d %H:%M"),
            "entry_price":   t["entry_price"],
            "exit_price":    t["exit_price"],
            "stop_loss":     t["stop_loss"],
            "tp1_price":     t["tp1_price"],
            "entry_score":   t["entry_score"],
            "entry_session": t["entry_session"],
            "day_of_week":   DAYS[et.dayofweek] if et.dayofweek < 7 else "?",
            "year":          et.year,
            "month":         et.month,
            "sl_distance_pts": t["sl_distance_pts"],
            "tp1_distance_pts": round(t["tp1_price"] - t["entry_price"], 2),
            "tp1_hit":       t["tp1_hit"],
            "trail_stage":   t["trail_stage"],
            "exit_reason":   t["exit_reason"],
            "rr_achieved":   t["rr_achieved"],
            "pnl_tp1":       t["pnl_tp1"],
            "pnl_runner":    t["pnl_runner"],
            "costs":         t["costs"],
            "total_pnl":     t["total_pnl"],
            "cumulative_pnl": round(cum_pnl, 2),
            "capital_after":  t["capital_after"],
            "drawdown":      round(dd, 2),
            "period":        "IS" if et.year < 2024 else "OOS",
        })

    path = os.path.join(OUT_DIR, f"{name}_full_trade_log.csv")
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


# ======================================================================
# MAIN
# ======================================================================

def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])

    print("\n" + "=" * 70)
    print("  GENERATING HTML REPORTS + TRADE LOGS: B1 & B2")
    print("=" * 70)

    t0 = time.time()

    # Data prep
    print("\n[1] Preparing data...")
    log = logging.getLogger("rpt")
    df_15m = load_15m_data(cfg_mod.DB_PATH)
    df_15m = compute_15m_indicators(df_15m)
    df = build_mtf(df_15m)
    df = precompute_patterns(df)
    df = df.copy()
    df["long_score"]       = precompute_long_scores(df)
    df["long_confirms"]    = precompute_long_confirmations(df)
    df["long_thresh"]      = precompute_dynamic_thresholds(df["long_confirms"])
    df["session_penalty"]  = precompute_session_penalty(df)
    df["atr_pctile"]       = calc_atr_percentile(df["atr"])
    df["atr_adj"]          = precompute_atr_adjustments(df["atr_pctile"])
    df["effective_thresh"] = df["long_thresh"] + df["session_penalty"] + df["atr_adj"]
    df = df.iloc[cfg_mod.WARM_UP_BARS:]

    # Tech SL 50pt
    sc_mod.MAX_SL_POINTS = 50.0
    tech_sl = precompute_tech_sl(df)
    _restore()

    # Run backtests
    print("[2] Running backtests...")
    results = {}
    for name, cfg in CONFIGS.items():
        print(f"  {name}...", end=" ", flush=True)
        _patch(cfg["tp1_ratio"], cfg["max_sl_pts"], cfg["max_risk"])
        d = df.copy()
        d["tech_sl_long"] = tech_sl
        engine = BacktestEngine(d)
        trades = engine.run()
        _restore()
        results[name] = trades
        print(f"{len(trades)} trades")

    # Generate reports
    print("[3] Generating charts & HTML reports...")
    for name, cfg in CONFIGS.items():
        trades = results[name]
        is_trades  = filter_trades(trades, IS_YEARS)
        oos_trades = filter_trades(trades, OOS_YEARS)

        print(f"  {name}: generating charts...", end=" ", flush=True)
        charts = {
            "equity_full":     chart_equity_full(trades, name),
            "equity_oos":      chart_equity_oos(trades, name),
            "drawdown":        chart_drawdown(trades, name),
            "pnl_dist":        chart_pnl_distribution(trades, name),
            "yearly_bars":     chart_yearly_bars(trades, name),
            "monthly_heatmap": chart_monthly_heatmap(trades, name),
            "exit_pie_is":     chart_exit_pie(is_trades, name, "IS"),
            "exit_pie_oos":    chart_exit_pie(oos_trades, name, "OOS"),
            "session_bars":    chart_session_bars(trades, name),
            "dow_bars":        chart_dow_bars(trades, name),
            "score_pnl":       chart_score_vs_pnl(trades, name),
            "rolling_wr":      chart_rolling_wr(trades, name),
        }
        print("HTML...", end=" ", flush=True)

        html = generate_html_report(name, cfg, trades, charts)
        html_path = os.path.join(OUT_DIR, f"{name}_report.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)

        csv_path = export_full_trade_csv(trades, name, cfg)
        print(f"done.")
        print(f"    HTML: {html_path}")
        print(f"    CSV:  {csv_path}")

    elapsed = time.time() - t0
    print(f"\n  All done in {elapsed:.1f}s")
    print(f"  Output: {OUT_DIR}/")


if __name__ == "__main__":
    main()
