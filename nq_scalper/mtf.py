"""Multi-timeframe resampling and merging.

Resamples 15m bars to 1H, 4H, Daily, and Weekly. Computes higher-TF indicators
and merges them onto the 15m base with a 1-bar lag to prevent look-ahead bias.

MTF definitions match the validated Python V1 system:
- 1H: EMA9, EMA21, EMA50 (short-term alignment check)
- 4H: EMA50, EMA200 (trend-following check)
- Daily: EMA50, EMA200 + prev day H/L/C
- Weekly: prev week H/L (for S/R proximity)
"""

import logging

import numpy as np
import pandas as pd
from ta.trend import EMAIndicator

logger = logging.getLogger(__name__)


def compute_1h_mtf(df_1h: pd.DataFrame) -> pd.DataFrame:
    """Compute 1-hour MTF indicators: EMA9, EMA21, EMA50."""
    df_1h = df_1h.copy()
    df_1h["mtf1h_ema9"] = EMAIndicator(close=df_1h["Close"], window=9).ema_indicator()
    df_1h["mtf1h_ema21"] = EMAIndicator(close=df_1h["Close"], window=21).ema_indicator()
    df_1h["mtf1h_ema50"] = EMAIndicator(close=df_1h["Close"], window=50).ema_indicator()
    df_1h["mtf1h_close"] = df_1h["Close"]
    return df_1h


def compute_4h_mtf(df_4h: pd.DataFrame) -> pd.DataFrame:
    """Compute 4-hour MTF indicators: EMA50, EMA200."""
    df_4h = df_4h.copy()
    df_4h["mtf4h_ema50"] = EMAIndicator(close=df_4h["Close"], window=50).ema_indicator()
    df_4h["mtf4h_ema200"] = EMAIndicator(close=df_4h["Close"], window=200).ema_indicator()
    df_4h["mtf4h_close"] = df_4h["Close"]
    return df_4h


def compute_daily_mtf(df_d: pd.DataFrame) -> pd.DataFrame:
    """Compute daily indicators: EMA50, EMA200, prev day H/L/C."""
    df_d = df_d.copy()
    df_d["daily_ema50"] = EMAIndicator(close=df_d["Close"], window=50).ema_indicator()
    df_d["daily_ema200"] = EMAIndicator(close=df_d["Close"], window=200).ema_indicator()
    df_d["prev_day_high"] = df_d["High"].shift(1)
    df_d["prev_day_low"] = df_d["Low"].shift(1)
    df_d["prev_day_close"] = df_d["Close"].shift(1)
    return df_d


def merge_mtf(df_base, df_higher, cols):
    """Merge higher-TF columns onto base bars with 1-bar lag (no look-ahead)."""
    df_lagged = df_higher[cols].shift(1).copy()
    if df_base.index.tz is not None:
        df_base = df_base.copy()
        df_base.index = df_base.index.tz_localize(None)
    if df_lagged.index.tz is not None:
        df_lagged.index = df_lagged.index.tz_localize(None)
    df_base = df_base.sort_index()
    df_lagged = df_lagged.sort_index()
    return pd.merge_asof(df_base, df_lagged, left_index=True, right_index=True, direction="backward")


def compute_mtf_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Compute MTF alignment flags.

    Column names MUST match what scoring.py expects:
    - mtf_bullish: 1H bullish alignment
    - mtf_strong_bull: both 1H AND 4H bullish
    """
    df = df.copy()

    # 1H bullish: EMA9 > EMA21 and close > EMA9
    df["mtf_bullish"] = (
        (df["mtf1h_ema9"] > df["mtf1h_ema21"])
        & (df["mtf1h_close"] > df["mtf1h_ema9"])
    )

    # 4H bullish: close > EMA50 and EMA50 > EMA200
    df["mtf4h_bullish"] = (
        (df["mtf4h_close"] > df["mtf4h_ema50"])
        & (df["mtf4h_ema50"] > df["mtf4h_ema200"])
    )

    # Strong MTF: both 1H and 4H aligned
    df["mtf_strong_bull"] = df["mtf_bullish"] & df["mtf4h_bullish"]

    # Daily trend
    df["daily_bullish"] = df["daily_ema50"] > df["daily_ema200"]

    return df


def build_mtf(df_15m: pd.DataFrame) -> pd.DataFrame:
    """Full MTF pipeline: resample 15m -> 1H/4H/Daily/Weekly, compute, merge."""
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    ohlcv = ["Open", "High", "Low", "Close", "Volume"]

    logger.info("Resampling to 1H...")
    df_1h = df_15m[ohlcv].resample("1h").agg(agg).dropna()
    logger.info("Resampling to 4H...")
    df_4h = df_15m[ohlcv].resample("4h").agg(agg).dropna()
    logger.info("Resampling to Daily...")
    df_d = df_15m[ohlcv].resample("D").agg(agg).dropna()
    logger.info("Resampling to Weekly...")
    df_w = df_15m[ohlcv].resample("W").agg(agg).dropna()
    df_w["prev_week_high"] = df_w["High"].shift(1)
    df_w["prev_week_low"] = df_w["Low"].shift(1)

    logger.info("Computing 1H MTF indicators...")
    df_1h = compute_1h_mtf(df_1h)
    logger.info("Computing 4H MTF indicators...")
    df_4h = compute_4h_mtf(df_4h)
    logger.info("Computing Daily indicators...")
    df_d = compute_daily_mtf(df_d)

    logger.info("Merging 1H MTF onto 15m...")
    df = merge_mtf(df_15m, df_1h, ["mtf1h_ema9", "mtf1h_ema21", "mtf1h_ema50", "mtf1h_close"])
    logger.info("Merging 4H MTF onto 15m...")
    df = merge_mtf(df, df_4h, ["mtf4h_ema50", "mtf4h_ema200", "mtf4h_close"])
    logger.info("Merging Daily levels onto 15m...")
    df = merge_mtf(df, df_d, ["daily_ema50", "daily_ema200", "prev_day_high", "prev_day_low", "prev_day_close"])
    logger.info("Merging Weekly levels onto 15m...")
    df = merge_mtf(df, df_w, ["prev_week_high", "prev_week_low"])

    df = compute_mtf_flags(df)
    return df
