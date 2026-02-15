"""Candle patterns, breakouts, momentum shift, S/R levels.

Pattern detection logic matches the validated Python V1 scoring system
(swing_scalper_data.py):
- Engulfing patterns (bull_engulf / bullish_engulfing)
- Hammer / Shooting Star (pin bar ratio = 2.5)
- Confirmed patterns (hammer_confirm / hammer_confirmation_bull)
- Morning star (3-candle bullish reversal)
- Consolidation breakout (bull_cons_breakout / confirmed_bullish_breakout)
- High/Low breakout (bull_breakout / bullish_breakout, 20-bar lookback)
- Session range breakout (bull_sess_break)
- Momentum shift candle (bull_shift / is_bullish_shift_candle)
- Shift blocking windows (4 bars after shift)
- Fibonacci S/R levels
- Round number S/R
- Daily level proximity (near_daily_level)

Legacy Pine Script column names are preserved as aliases for backward
compatibility with backtest_engine.py.
"""

import logging

import numpy as np
import pandas as pd

from config import (
    PIN_BAR_RATIO,
    CONSOLIDATION_BARS,
    BREAKOUT_VOL_MULTIPLIER,
    FIB_LOOKBACK,
    ROUND_NUMBER_INTERVAL,
    PIVOT_LOOKBACK,
    BREAKOUT_LOOKBACK,
    SHIFT_BLOCK_BARS,
)

logger = logging.getLogger(__name__)


def precompute_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """Precompute all candle patterns, breakouts, S/R levels, and shift blocking.

    Column names match scoring.py expectations exactly.
    """
    df = df.copy()

    # ──────────────────────────────────────────────────────────────
    # CANDLE METRICS
    # ──────────────────────────────────────────────────────────────
    df["body"] = (df["Close"] - df["Open"]).abs()
    df["avg_body"] = df["body"].rolling(window=20, min_periods=1).mean()
    df["upper_wick"] = df["High"] - df[["Close", "Open"]].max(axis=1)
    df["lower_wick"] = df[["Close", "Open"]].min(axis=1) - df["Low"]
    df["candle_range"] = df["High"] - df["Low"]
    df["is_green"] = df["Close"] > df["Open"]

    prev_green = df["is_green"].shift(1).fillna(False).infer_objects(copy=False).astype(bool)
    prev_open = df["Open"].shift(1)
    prev_close = df["Close"].shift(1)

    # ──────────────────────────────────────────────────────────────
    # CANDLE PATTERNS
    # ──────────────────────────────────────────────────────────────

    # Bullish Engulfing
    df["bullish_engulfing"] = (
        df["is_green"]
        & ~prev_green
        & (df["Close"] > prev_open)
        & (df["Open"] < prev_close)
        & (df["body"] > 0)
    )
    df["bull_engulf"] = df["bullish_engulfing"]  # Python V1 alias

    # Hammer (pin bar) — Pine: lower_wick >= body * pinBarRatio
    df["hammer"] = (
        (df["body"] > 0)
        & (df["lower_wick"] >= df["body"] * PIN_BAR_RATIO)
        & (df["upper_wick"] < df["body"] * 0.5)
    )

    # Confirmed Hammer — hammer[1] and green and vol_condition
    df["hammer_confirmation_bull"] = (
        df["hammer"].shift(1).fillna(False).infer_objects(copy=False)
        & df["is_green"]
        & df["vol_condition"]
    )
    df["hammer_confirm"] = df["hammer_confirmation_bull"]  # Python V1 alias

    # ──────────────────────────────────────────────────────────────
    # MORNING STAR (3-candle bullish reversal)
    # ──────────────────────────────────────────────────────────────
    body_2 = df["body"].shift(2)
    green_2 = df["is_green"].shift(2).fillna(False).infer_objects(copy=False).astype(bool)
    open_2 = df["Open"].shift(2)
    close_2 = df["Close"].shift(2)
    body_1 = df["body"].shift(1)

    df["morning_star"] = (
        ~green_2  # 1st candle bearish
        & (body_2 > df["avg_body"] * 0.8)  # 1st candle large body
        & (body_1 < df["avg_body"] * 0.4)  # 2nd candle small body
        & df["is_green"]  # 3rd candle bullish
        & (df["Close"] > (open_2 + close_2) / 2)  # closes above midpoint of 1st
        & (df["body"] > df["avg_body"] * 0.6)  # 3rd candle decent body
    )

    # ──────────────────────────────────────────────────────────────
    # BREAKOUT PATTERNS
    # ──────────────────────────────────────────────────────────────

    # All-time high breakout (in lookback window)
    # Pine: close > ta.highest(high, breakoutLookback)[1]
    df["highest_n"] = df["High"].rolling(
        window=BREAKOUT_LOOKBACK, min_periods=1,
    ).max().shift(1)
    df["broke_ath"] = df["Close"] > df["highest_n"]

    # Bullish breakout (with volume confirmation)
    df["bullish_breakout"] = (
        df["broke_ath"] & (df["vol_ratio"] >= BREAKOUT_VOL_MULTIPLIER)
    )
    df["bull_breakout"] = df["bullish_breakout"]  # Python V1 alias

    # Consolidation breakout
    # Pine: 5 consecutive small-body bars, then large body break with volume
    small_body = df["body"] < df["avg_body"] * 0.5
    small_body_count = small_body.rolling(window=CONSOLIDATION_BARS, min_periods=1).sum()
    is_consolidation = small_body_count >= CONSOLIDATION_BARS

    cons_high = df["High"].rolling(
        window=CONSOLIDATION_BARS + 1, min_periods=1,
    ).max()

    df["confirmed_bullish_breakout"] = (
        is_consolidation.shift(1).fillna(False)
        & (df["body"] > df["avg_body"] * 1.5)
        & (df["Close"] > cons_high.shift(1))
        & df["is_green"]
        & (df["vol_ratio"] >= 1.3)
    )
    df["bull_cons_breakout"] = df["confirmed_bullish_breakout"]  # Python V1 alias

    # ──────────────────────────────────────────────────────────────
    # SESSION RANGE BREAKOUT
    # ──────────────────────────────────────────────────────────────
    _precompute_session_ranges(df)

    # Session range breakout: close > prev session high with volume + momentum
    df["bull_sess_break"] = (
        ~np.isnan(df["prev_sess_high"])
        & (df["Close"] > df["prev_sess_high"])
        & df["is_green"]
        & df["vol_above"]
        & ((df["macd_line"] > df["macd_signal"]) | (df["rsi"] > 50))
    )

    # ──────────────────────────────────────────────────────────────
    # MOMENTUM SHIFT
    # ──────────────────────────────────────────────────────────────

    shift_thresh = df["Close"] * 0.5 / 100.0  # 0.5% of price
    df["is_bullish_shift_candle"] = (
        (df["body"] >= shift_thresh) & df["is_green"] & df["vol_spike"]
    )
    df["bull_shift"] = df["is_bullish_shift_candle"]  # Python V1 alias
    df["is_bearish_shift_candle"] = (
        (df["body"] >= shift_thresh) & ~df["is_green"] & df["vol_spike"]
    )

    # Blocking windows — after a bearish shift, block longs for 4 bars
    df["longs_blocked"] = False
    for k in range(1, SHIFT_BLOCK_BARS + 1):
        df["longs_blocked"] = (
            df["longs_blocked"]
            | df["is_bearish_shift_candle"].shift(k).fillna(False)
        )
    df["long_blocked"] = df["longs_blocked"]  # Python V1 alias

    # ──────────────────────────────────────────────────────────────
    # S/R LEVELS & PROXIMITY
    # ──────────────────────────────────────────────────────────────
    _precompute_sr_levels(df)

    return df


def _precompute_session_ranges(df: pd.DataFrame) -> None:
    """Precompute previous session H/L."""
    sessions = df["session"].values
    highs = df["High"].values
    lows = df["Low"].values
    n = len(df)

    prev_sess_high = np.full(n, np.nan)
    prev_sess_low = np.full(n, np.nan)

    curr_sess = ""
    curr_high = np.nan
    curr_low = np.nan
    last_sess_high = np.nan
    last_sess_low = np.nan

    for i in range(n):
        s = sessions[i]
        if s != curr_sess and s not in ("Maintenance", "Closed", "After Hours"):
            if not np.isnan(curr_high):
                last_sess_high = curr_high
                last_sess_low = curr_low
            curr_sess = s
            curr_high = highs[i]
            curr_low = lows[i]
        elif s == curr_sess:
            if np.isnan(curr_high):
                curr_high = highs[i]
                curr_low = lows[i]
            else:
                curr_high = max(curr_high, highs[i])
                curr_low = min(curr_low, lows[i])

        prev_sess_high[i] = last_sess_high
        prev_sess_low[i] = last_sess_low

    df["prev_sess_high"] = prev_sess_high
    df["prev_sess_low"] = prev_sess_low


def _precompute_sr_levels(df: pd.DataFrame) -> None:
    """Precompute S/R proximity flags for scoring.

    Column names match Python V1: near_support, near_resist, near_daily_level.
    Aligned with validated system (swing_scalper_data.py:717-762).
    """
    # Fibonacci (30-bar lookback)
    df["fib_high"] = df["High"].rolling(window=FIB_LOOKBACK, min_periods=1).max()
    df["fib_low"] = df["Low"].rolling(window=FIB_LOOKBACK, min_periods=1).min()
    fib_range = df["fib_high"] - df["fib_low"]
    df["fib_382"] = df["fib_high"] - fib_range * 0.382
    df["fib_500"] = df["fib_high"] - fib_range * 0.500
    df["fib_618"] = df["fib_high"] - fib_range * 0.618

    # Round numbers (every 100 pts)
    df["round_down"] = np.floor(df["Close"] / ROUND_NUMBER_INTERVAL) * ROUND_NUMBER_INTERVAL
    df["round_up"] = df["round_down"] + ROUND_NUMBER_INTERVAL

    # Proximity threshold = 40% of ATR
    prox = df["atr"] * 0.4

    # Fibonacci proximity (618 + 500)
    near_fib = (
        ((df["Close"] - df["fib_618"]).abs() < prox)
        | ((df["Close"] - df["fib_500"]).abs() < prox)
    )

    # Round number proximity (same for both support and resist — matches validated)
    near_round = (df["Close"] - df["round_down"]).abs() < prox

    # VWAP proximity
    near_vwap = (df["Close"] - df["vwap"]).abs() < prox

    # Prev day proximity components
    near_pdl = pd.Series(False, index=df.index)
    near_pdh = pd.Series(False, index=df.index)
    near_pdc = pd.Series(False, index=df.index)
    if "prev_day_low" in df.columns:
        near_pdl = (df["Close"] - df["prev_day_low"]).abs() < prox
    if "prev_day_high" in df.columns:
        near_pdh = (df["Close"] - df["prev_day_high"]).abs() < prox
    if "prev_day_close" in df.columns:
        near_pdc = (df["Close"] - df["prev_day_close"]).abs() < prox

    # Prev week proximity components
    near_pwl = pd.Series(False, index=df.index)
    near_pwh = pd.Series(False, index=df.index)
    if "prev_week_low" in df.columns:
        near_pwl = (df["Close"] - df["prev_week_low"]).abs() < prox
    if "prev_week_high" in df.columns:
        near_pwh = (df["Close"] - df["prev_week_high"]).abs() < prox

    # near_support — matches validated: near_fib | near_round | near_vwap | near_pdl | near_pwl
    df["near_support"] = near_fib | near_round | near_vwap | near_pdl | near_pwl

    # near_resist — matches validated: near_fib | near_round | near_vwap | near_pdh | near_pwh
    df["near_resist"] = near_fib | near_round | near_vwap | near_pdh | near_pwh

    # near_daily_level — proximity to any prev day level (H/L/C)
    df["near_daily_level"] = near_pdh | near_pdl | near_pdc
