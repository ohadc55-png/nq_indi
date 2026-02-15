"""Indicator calculations — EMA, RSI, MACD, ADX, ATR, Supertrend, VWAP.

Column names and derived flags match the validated Python V1 scoring system
(swing_scalper_data.py). Legacy Pine Script aliases are preserved for
backward compatibility with backtest_engine.py.
"""

import logging

import numpy as np
import pandas as pd
from ta.trend import EMAIndicator, ADXIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange

from config import (
    EMA_FAST, EMA_SLOW, EMA_50, EMA_200,
    RSI_LEN,
    MACD_FAST, MACD_SLOW, MACD_SIGNAL,
    ADX_LEN, ADX_STRONG_TREND, ADX_RANGING,
    ATR_LEN,
    ST_PERIOD, ST_MULTIPLIER,
    VOL_SMA_LEN, VOL_MULTIPLIER, VOL_SPIKE_MULTIPLIER,
    ATR_PCTILE_LOOKBACK_DAYS, ATR_PCTILE_BARS_PER_DAY, ATR_PCTILE_MIN_PERIODS,
    TIMEZONE,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# SUPERTREND (matches Pine Script ta.supertrend)
# ═══════════════════════════════════════════════════════════════════

def calc_supertrend(
    df: pd.DataFrame, period: int = ST_PERIOD, multiplier: float = ST_MULTIPLIER,
) -> tuple[pd.Series, pd.Series]:
    """Calculate Supertrend indicator.

    Returns (st_line, st_direction).
    Direction: -1 = bullish (price above), +1 = bearish (price below).
    Matches: Pine Script ta.supertrend(multiplier, period).
    """
    high = df["High"].values
    low = df["Low"].values
    close = df["Close"].values
    n = len(df)

    # True Range
    tr = np.maximum(
        high[1:] - low[1:],
        np.maximum(
            np.abs(high[1:] - close[:-1]),
            np.abs(low[1:] - close[:-1]),
        ),
    )
    tr = np.insert(tr, 0, high[0] - low[0])
    atr = pd.Series(tr).rolling(window=period, min_periods=1).mean().values

    hl2 = (high + low) / 2.0
    basic_upper = hl2 + multiplier * atr
    basic_lower = hl2 - multiplier * atr

    final_upper = basic_upper.copy()
    final_lower = basic_lower.copy()
    st_line = np.full(n, np.nan)
    direction = np.zeros(n, dtype=int)

    st_line[0] = basic_upper[0]
    direction[0] = 1  # start bearish

    for i in range(1, n):
        if basic_upper[i] < final_upper[i - 1] or close[i - 1] > final_upper[i - 1]:
            final_upper[i] = basic_upper[i]
        else:
            final_upper[i] = final_upper[i - 1]

        if basic_lower[i] > final_lower[i - 1] or close[i - 1] < final_lower[i - 1]:
            final_lower[i] = basic_lower[i]
        else:
            final_lower[i] = final_lower[i - 1]

        if st_line[i - 1] == final_upper[i - 1]:
            if close[i] <= final_upper[i]:
                st_line[i] = final_upper[i]
                direction[i] = 1
            else:
                st_line[i] = final_lower[i]
                direction[i] = -1
        else:
            if close[i] >= final_lower[i]:
                st_line[i] = final_lower[i]
                direction[i] = -1
            else:
                st_line[i] = final_upper[i]
                direction[i] = 1

    return (
        pd.Series(st_line, index=df.index),
        pd.Series(direction, index=df.index),
    )


# ═══════════════════════════════════════════════════════════════════
# SESSION-ANCHORED VWAP
# ═══════════════════════════════════════════════════════════════════

def calc_session_vwap(df: pd.DataFrame) -> pd.Series:
    """Session-anchored VWAP that resets at 18:00 ET each day.

    Matches: Pine Script ta.vwap(hlc3) with session anchor.
    """
    idx = df.index
    if idx.tz is None:
        idx = idx.tz_localize("UTC").tz_convert(TIMEZONE)
    else:
        idx = idx.tz_convert(TIMEZONE)

    hours = idx.hour
    dates = idx.date
    session_ids = pd.Series(dates, index=df.index)
    mask_evening = hours >= 18
    session_ids[mask_evening] = pd.Series(
        [d + pd.Timedelta(days=1) for d in np.array(dates)[mask_evening]],
        index=session_ids.index[mask_evening],
    )

    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3.0
    tp_vol = typical_price * df["Volume"]
    cum_tp_vol = tp_vol.groupby(session_ids).cumsum()
    cum_vol = df["Volume"].groupby(session_ids).cumsum()
    vwap = cum_tp_vol / cum_vol
    vwap = vwap.replace([np.inf, -np.inf], np.nan).ffill()
    return vwap


# ═══════════════════════════════════════════════════════════════════
# SESSION LABELS
# ═══════════════════════════════════════════════════════════════════

def get_session_labels(df: pd.DataFrame) -> pd.Series:
    """Assign session labels: Asia, Europe, US, After Hours, Maintenance."""
    idx = df.index
    if idx.tz is None:
        idx = idx.tz_localize("UTC").tz_convert(TIMEZONE)
    else:
        idx = idx.tz_convert(TIMEZONE)

    hours = idx.hour
    minutes = idx.minute

    sessions = pd.Series("Closed", index=df.index)
    sessions[(hours >= 18) | (hours < 2)] = "Asia"
    sessions[(hours >= 2) & ((hours < 9) | ((hours == 9) & (minutes < 30)))] = "Europe"
    sessions[((hours == 9) & (minutes >= 30)) | ((hours >= 10) & (hours < 16))] = "US"
    sessions[(hours >= 16) & (hours < 17)] = "After Hours"
    sessions[hours == 17] = "Maintenance"

    return sessions


def get_et_components(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (ET_hour, ET_minute, day_of_week) arrays for all bars."""
    idx = df.index
    if idx.tz is None:
        idx = idx.tz_localize("UTC").tz_convert(TIMEZONE)
    else:
        idx = idx.tz_convert(TIMEZONE)
    return idx.hour.values, idx.minute.values, idx.dayofweek.values


# ═══════════════════════════════════════════════════════════════════
# 15-MINUTE INDICATORS (base chart)
# ═══════════════════════════════════════════════════════════════════

def compute_15m_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all 15-minute indicators on the base chart.

    Matches Pine Script indicator block for chart timeframe.
    """
    df = df.copy()

    # ── EMAs ──
    # Pine: emaFast = ta.ema(close, 9), emaSlow = ta.ema(close, 21), etc.
    df["ema9"] = EMAIndicator(close=df["Close"], window=EMA_FAST).ema_indicator()
    df["ema21"] = EMAIndicator(close=df["Close"], window=EMA_SLOW).ema_indicator()
    df["ema50"] = EMAIndicator(close=df["Close"], window=EMA_50).ema_indicator()
    df["ema200"] = EMAIndicator(close=df["Close"], window=EMA_200).ema_indicator()

    # ── VWAP ──
    df["vwap"] = calc_session_vwap(df)

    # ── RSI ──
    # Pine: rsiVal = ta.rsi(close, rsiLen)
    df["rsi"] = RSIIndicator(close=df["Close"], window=RSI_LEN).rsi()

    # ── MACD ──
    # Pine: [macdLine, signalLine, histLine] = ta.macd(close, 12, 26, 9)
    macd = MACD(
        close=df["Close"],
        window_slow=MACD_SLOW,
        window_fast=MACD_FAST,
        window_sign=MACD_SIGNAL,
    )
    df["macd_line"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"] = macd.macd_diff()

    # ── ADX / DI ──
    # Pine: [diPlus, diMinus, adxVal] = ta.dmi(adxLen, adxLen)
    adx_ind = ADXIndicator(
        high=df["High"], low=df["Low"], close=df["Close"], window=ADX_LEN,
    )
    df["adx"] = adx_ind.adx()
    df["plus_di"] = adx_ind.adx_pos()
    df["minus_di"] = adx_ind.adx_neg()

    # ── ATR ──
    # Pine: atrVal = ta.atr(atrLen)
    df["atr"] = AverageTrueRange(
        high=df["High"], low=df["Low"], close=df["Close"], window=ATR_LEN,
    ).average_true_range()

    # ── Supertrend ──
    # Pine: [stVal, stDir] = ta.supertrend(stMult, stPeriod)
    df["st_line"], df["st_dir"] = calc_supertrend(df, ST_PERIOD, ST_MULTIPLIER)

    # ── Volume ──
    # Pine: volSma = ta.sma(volume, volSmaLen)
    df["vol_ma"] = df["Volume"].rolling(window=VOL_SMA_LEN, min_periods=1).mean()
    df["vol_ratio"] = np.where(df["vol_ma"] > 0, df["Volume"] / df["vol_ma"], 0.0)

    # ── Derived flags ──
    # Trend alignment: close > ema50 and ema50 > ema200
    df["main_trend_bull"] = (df["Close"] > df["ema50"]) & (df["ema50"] > df["ema200"])
    df["primary_bull"] = df["main_trend_bull"]  # Alias for Python V1 scoring

    # Supertrend flags
    df["st_bullish"] = df["st_dir"] == -1
    df["st_bearish"] = df["st_dir"] == 1
    df["st_buy_signal"] = df["st_bullish"] & (~df["st_bullish"].shift(1).fillna(True).infer_objects(copy=False))
    # Supertrend direction change (flip), not just buy signal
    df["st_flip"] = df["st_bullish"] != df["st_bullish"].shift(1)

    # Volume flags
    df["vol_spike"] = df["vol_ratio"] >= VOL_SPIKE_MULTIPLIER  # >= 2.0
    df["volume_spike"] = df["vol_spike"]  # Legacy alias
    df["vol_above"] = df["vol_ratio"] >= VOL_MULTIPLIER        # >= 1.2
    df["vol_condition"] = df["vol_above"]  # Legacy alias
    df["vol_weak"] = df["vol_ratio"] < 0.8
    df["volume_weak"] = df["vol_weak"]  # Legacy alias
    df["vol_declining"] = (
        (df["Volume"] < df["Volume"].shift(1))
        & (df["Volume"].shift(1) < df["Volume"].shift(2))
    )

    # DI aliases (plus_di/minus_di kept for backward compat, di_plus/di_minus for Python V1)
    df["di_plus"] = df["plus_di"]
    df["di_minus"] = df["minus_di"]

    # Trend strength flags
    df["is_strong_trend"] = df["adx"] > ADX_STRONG_TREND
    df["is_ranging"] = df["adx"] < ADX_RANGING

    # EMA slope (for trend filter)
    df["ema_slope_bull"] = df["ema50"] > df["ema50"].shift(1)

    # Sessions
    df["session"] = get_session_labels(df)

    return df


# ═══════════════════════════════════════════════════════════════════
# ATR PERCENTILE (Layer 1)
# ═══════════════════════════════════════════════════════════════════

def calc_atr_percentile(atr_series: pd.Series) -> pd.Series:
    """Calculate rolling ATR percentile rank.

    Where does the current ATR sit vs the last 252 trading days?
    Validated on Walk-Forward: OOS improvement PF 1.30→1.44, Sharpe 1.81→2.51.
    """
    window = ATR_PCTILE_LOOKBACK_DAYS * ATR_PCTILE_BARS_PER_DAY
    return atr_series.rolling(
        window=window, min_periods=ATR_PCTILE_MIN_PERIODS,
    ).rank(pct=True) * 100
