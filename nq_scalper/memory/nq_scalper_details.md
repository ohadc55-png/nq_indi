# NQ Scalper -- Architecture & File Reference

## Directory: `c:\Ohad\ohad\אפליקציות\trading_indicator\nq_scalper\`

---

## Core Production Files

### `config.py` -- Single Source of Truth
All parameters in one place. Key values:
- **Contract**: NQ $20/point, 2 contracts per trade, $100K initial capital
- **Indicators**: EMA 9/21/50/200, RSI 14, MACD 12/26/9, ADX 14, ATR 14, Supertrend 10/3.0
- **Risk (config.py default)**: MAX_RISK_PER_CONTRACT=$800, MAX_SL_POINTS=40, RR_RATIO_TP1=1.5
- **Risk (B1 production)**: MAX_RISK_PER_CONTRACT=$1,000, MAX_SL_POINTS=50, RR_RATIO_TP1=1.5
- **Costs**: Commission $4.50/contract RT, Slippage 1 tick ($5/fill)
- **Sessions**: US 9-16 EST, Europe, Asia (+2.0 penalty = effectively blocked)
- **Cooldown**: 8 bars or 0.25% price move
- **Layer 1**: ATR percentile lookback 252 days, min 100 periods
- **Warm-up**: 300 bars trimmed

### `data_feed.py` -- Data Loading
- Loads from SQLite `nq_data.db` (table `ohlcv_1m`, resampled to 15min)
- 3,492,884 one-minute bars -> 236,135 fifteen-minute bars
- Date range: 2016-01-03 to 2026-02-11

### `indicators.py` -- Technical Indicators
Computes on 15-min base chart:
- EMA 9, 21, 50, 200 + slope flags (`ema_slope_bull`, `primary_bull`)
- RSI 14
- MACD (12, 26, 9) + line/signal/histogram
- ADX 14 + DI+/DI- (`is_strong_trend`, `is_ranging`)
- ATR 14
- Supertrend (10, 3.0) -> `st_line`, `st_bullish`, `st_buy_signal`
- Volume analysis: `vol_above`, `vol_spike`, `vol_weak`, `vol_declining`
- Session labeling (US/Europe/Asia/Maintenance/Closed)
- `calc_atr_percentile()` -- rolling ATR percentile over 252 trading days

### `mtf.py` -- Multi-Timeframe Data
Resamples 15-min to 1H, 4H, Daily, Weekly. Merges back:
- 1H: EMA 9/21 -> `mtf_bullish`
- 4H: EMA 50/200 -> `mtf4h_bullish`
- Daily: High/Low/Close -> `daily_bullish`, `near_daily_level`
- Weekly: High/Low

### `patterns.py` -- Candlestick & Structure Patterns
Precomputes boolean columns:
- Candles: `hammer_confirm`, `morning_star`, `bull_engulf`, `pin_bar_bull`
- Structure: `bull_breakout`, `bull_cons_breakout`, `near_support`, `near_resist`
- Shift: `bull_shift`, `is_bullish_shift_candle`, `long_blocked`, `longs_blocked`
- S/R: round numbers, Fibonacci levels, pivot highs/lows
- Session breaks: `bull_sess_break`

### `scoring.py` -- Signal Scoring System (V1 Exact + Layer 1)
**`precompute_long_scores(df)`** -- Scores each bar 0-10:
- Trend (max 3.5): primary_bull +1.0, mtf1h +0.8, mtf4h +0.8, supertrend +0.6, daily +0.3
- Volume (max 2.5): spike +2.5 OR above_avg +1.5, weak -0.5
- Structure (max 2.0): breakout+vol +0.8, near_support +0.4, cons_breakout +0.4, near_daily +0.4
- Momentum (max 1.5): RSI 35-65 +0.5, MACD bull +0.5, ADX>20 +0.5
- Events (max ~3.2): hammer +0.7, morning_star +0.7, engulf +0.5, etc.
- Session bonus: US +0.3, Asia -0.3
- Penalties: ADX<20 -0.5, RSI extreme -0.5, blocked -1.5, ST bearish -0.5, resist -0.3, vol_declining -0.3

**`precompute_dynamic_thresholds()`**: 4+ confirms=7.0, 3=7.5, 2=8.0, 1=8.5, 0=9.0
**`precompute_session_penalty()`**: US +1.0, Europe +1.0, Asia +2.0
**`precompute_atr_adjustments()`** (Layer 1): ATR>80th pctile +0.5, >65th +0.25, <20th -0.25
**`effective_thresh`** = long_thresh + session_penalty + atr_adj
**`precompute_tech_sl()`**: SL = min(recent_low_10bars, supertrend_or_atr_buffer), capped at MAX_SL_POINTS

### `signals.py` -- Signal Generation
**`CooldownTracker`**: Prevents re-entry within 8 bars or 0.25% price move (shift override bypasses)
**`check_long_signal()`**: Entry criteria:
1. score >= effective_thresh
2. Longs not blocked (no bearish shift)
3. EMA slope bullish
4. Day-of-week: Wed >= 9.0, Thu >= 9.0
5. Europe session: score >= 8.5
6. Cooldown expired

### `risk_manager.py` -- Entry Calculation & Costs
**`calc_entry(close, tech_sl)`**:
- sl_distance = close - tech_sl (capped at MAX_SL_POINTS)
- TP1 (RR mode): tp1_price = close + sl_distance * RR_RATIO_TP1
- Returns: {entry_price, stop_loss, sl_distance, tp1_price}

**`calc_costs(tp1_hit)`**:
- No TP1: 4 half-fills comm ($9) + 2 slippage ($10) = $19
- TP1 hit: 6 half-fills comm ($13.50) + 4 slippage ($20) = $33.50

### `trailing.py` -- 3-Stage Trailing Stop
For the runner contract (1 contract after TP1 hit):
- **Stage 1 (Breakeven)**: trail = entry_price (immediate after TP1)
- **Stage 2 (Partial)**: profit >= SL*1.5 -> trail = entry + SL*0.5
- **Stage 3 (ATR Trail)**: profit >= SL*2.0 -> trail = max(close - ATR*2.0, supertrend_line)
- Trail only ratchets UP, never below entry

### `backtest_engine.py` -- Bar-by-Bar Engine
**`BacktestEngine(df)`**: Walks 235K bars sequentially:
1. Time checks (skip maintenance, Saturday, EOD close if enabled)
2. If position open: manage SL/TP1/trailing
3. If no position: check for new long signal -> calc_entry -> enter

Trade dict keys: `trade_num, direction, entry_time, entry_price, stop_loss, sl_distance_pts, tp1_price, tp1_hit, trail_stage, exit_time, exit_price, exit_reason, entry_score, entry_session, pnl_tp1, pnl_runner, costs, total_pnl, rr_achieved, capital_after`

Exit reasons: `FULL_STOP`, `TRAIL_S1`, `TRAIL_S2`, `TRAIL_S3`, `EOD_CLOSE`

### `run_backtest.py` -- Main Entry Point
Pipeline: load_15m_data -> compute_15m_indicators -> build_mtf -> precompute_patterns -> precompute_all_scores -> BacktestEngine.run() -> export CSV + report + charts

### `report.py` -- Performance Reporting
`analyze_results()`, `print_summary()`, `print_year_breakdown()`, `print_score_buckets()`, `print_dow_analysis()`, `generate_charts()`

### `trade_logger.py` -- CSV Export
Simple CSV writer for trade list.

### `run_live.py` -- Future Live Trading
Placeholder for IB live feed integration (not yet implemented).

---

### `generate_reports.py` -- HTML Report Generator
Generates dark-theme HTML+CSS reports with embedded base64 charts. Full trade log tables. Output in `output/reports/`

---

## Output Structure

```
output/
├── reports/
│   ├── B1_report.html          (full dark-theme 10-year report)
│   └── B1_full_trade_log.csv   (267 trades, 27 columns)
└── b1_oos_trades.csv           (60 OOS trades, 2024-2025)
```
