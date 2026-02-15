"""Indicator engine — imports and runs the nq_scalper pipeline on live data."""

import sys
import logging
from pathlib import Path

import numpy as np
import pandas as pd

# Add nq_scalper to path so we can import its modules
NQ_SCALPER_DIR = str(Path(__file__).resolve().parent.parent.parent / "nq_scalper")
if NQ_SCALPER_DIR not in sys.path:
    sys.path.insert(0, NQ_SCALPER_DIR)

from indicators import compute_15m_indicators
from mtf import build_mtf
from patterns import precompute_patterns
from scoring import precompute_all_scores

logger = logging.getLogger(__name__)


class IndicatorEngine:
    """Runs the full nq_scalper indicator pipeline on live data."""

    def __init__(self):
        self._last_processed = None

    def process(self, df: pd.DataFrame) -> dict | None:
        """Run full indicator pipeline on current data.

        Returns a dict with the latest bar's signal info,
        or None if data is insufficient.
        """
        if df.empty or len(df) < 300:
            logger.warning("Insufficient data for indicators: %d bars", len(df))
            return None

        try:
            # Step 1: 15m indicators
            df = compute_15m_indicators(df)

            # Step 2: Multi-timeframe (resample + merge)
            df = build_mtf(df)

            # Step 3: Patterns
            df = precompute_patterns(df)

            # Step 4: Scoring (scores + thresholds + tech SL)
            df = precompute_all_scores(df)

            # Trim warm-up bars
            df = df.iloc[300:]

            if df.empty:
                return None

            latest = df.iloc[-1]

            return self._extract_signal_data(latest, df)

        except Exception as e:
            logger.error("Indicator processing failed: %s", e, exc_info=True)
            return None

    def process_full(self, df: pd.DataFrame) -> pd.DataFrame | None:
        """Run full pipeline and return enriched DataFrame (for chart data)."""
        if df.empty or len(df) < 300:
            return None

        try:
            df = compute_15m_indicators(df)
            df = build_mtf(df)
            df = precompute_patterns(df)
            df = precompute_all_scores(df)
            return df.iloc[300:]
        except Exception as e:
            logger.error("Full processing failed: %s", e, exc_info=True)
            return None

    def _extract_signal_data(self, bar, df: pd.DataFrame) -> dict:
        """Extract all relevant signal fields from the latest bar."""

        def safe_float(val, default=0.0):
            if val is None or (isinstance(val, float) and np.isnan(val)):
                return default
            return float(val)

        def safe_bool(val, default=False):
            if val is None or (isinstance(val, float) and np.isnan(val)):
                return default
            return bool(val)

        long_score = safe_float(bar.get("long_score"))
        effective_thresh = safe_float(bar.get("effective_thresh"))

        return {
            "timestamp": str(bar.name),
            "close": safe_float(bar.get("Close")),
            "open": safe_float(bar.get("Open")),
            "high": safe_float(bar.get("High")),
            "low": safe_float(bar.get("Low")),
            "volume": safe_float(bar.get("Volume")),
            # Score
            "long_score": long_score,
            "long_threshold": effective_thresh,
            "long_confirms": safe_float(bar.get("long_confirms")),
            "long_thresh_base": safe_float(bar.get("long_thresh")),
            "session_penalty": safe_float(bar.get("session_penalty")),
            "signal": long_score >= effective_thresh,
            # Indicators
            "rsi": safe_float(bar.get("rsi")),
            "adx": safe_float(bar.get("adx")),
            "macd_line": safe_float(bar.get("macd_line")),
            "macd_signal": safe_float(bar.get("macd_signal")),
            "macd_hist": safe_float(bar.get("macd_hist")),
            "ema9": safe_float(bar.get("ema9")),
            "ema21": safe_float(bar.get("ema21")),
            "ema50": safe_float(bar.get("ema50")),
            "ema200": safe_float(bar.get("ema200")),
            "vwap": safe_float(bar.get("vwap")),
            # ATR
            "atr": safe_float(bar.get("atr")),
            "atr_percentile": safe_float(bar.get("atr_pctile")),
            "atr_adj": safe_float(bar.get("atr_adj")),
            # Supertrend
            "supertrend": safe_float(bar.get("st_line")),
            "st_direction": safe_float(bar.get("st_dir")),
            "st_bullish": safe_bool(bar.get("st_bullish")),
            # Flags
            "primary_bull": safe_bool(bar.get("primary_bull")),
            "mtf_bullish": safe_bool(bar.get("mtf_bullish")),
            "mtf4h_bullish": safe_bool(bar.get("mtf4h_bullish")),
            "daily_bullish": safe_bool(bar.get("daily_bullish")),
            "ema_slope_bull": safe_bool(bar.get("ema_slope_bull")),
            "longs_blocked": safe_bool(bar.get("longs_blocked")),
            "vol_above": safe_bool(bar.get("vol_above")),
            "vol_spike": safe_bool(bar.get("vol_spike")),
            # Session
            "session": str(bar.get("session", "Closed")),
            # Tech SL
            "tech_sl": safe_float(bar.get("tech_sl_long")),
        }
