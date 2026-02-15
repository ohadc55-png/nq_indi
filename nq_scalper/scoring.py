"""Signal scoring system — Python V1 exact logic + Layer 1 ATR Percentile.

The scoring weights, components, and thresholds match the validated Python V1
system (swing_scalper_data.py lines 773-883) that produced 282 trades with
PF 1.79. The ONLY addition is the ATR Percentile threshold adjustment
(Layer 1), which was validated with Walk-Forward testing.
"""

import logging

import numpy as np
import pandas as pd

from config import PIVOT_LOOKBACK, MAX_SL_POINTS

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# LONG SCORE — PYTHON V1 EXACT MATCH
# ═══════════════════════════════════════════════════════════════════

def precompute_long_scores(df: pd.DataFrame) -> pd.Series:
    """Vectorized long score calculation.

    EXACT match to swing_scalper_data.py lines 773-810.
    Do NOT change weights or logic — this produced 282 trades with PF 1.79.
    """
    # Session bonus (inside score, not threshold)
    sess_bonus = np.where(df["session"] == "US", 0.3,
                 np.where(df["session"] == "Asia", -0.3, 0.0))

    ls = pd.Series(0.0, index=df.index)

    # === Trend (max 3.5) ===
    ls += np.where(df["primary_bull"], 1.0, 0.0)
    ls += np.where(df["mtf_bullish"], 0.8, 0.0)       # mtf1h_bullish in original
    ls += np.where(df["mtf4h_bullish"], 0.8, 0.0)
    ls += np.where(df["st_bullish"], 0.6, 0.0)
    ls += np.where(df["daily_bullish"], 0.3, 0.0)

    # === Volume (max 2.5) ===
    ls += np.where(df["vol_spike"], 2.5, np.where(df["vol_above"], 1.5, 0.0))
    ls += np.where(df["vol_weak"], -0.5, 0.0)

    # === Structure (max 2.0) ===
    ls += np.where(df["bull_breakout"] & df["vol_above"], 0.8, 0.0)
    ls += np.where(df["near_support"], 0.4, 0.0)
    ls += np.where(df["bull_cons_breakout"], 0.4, 0.0)
    ls += np.where(df["near_daily_level"], 0.4, 0.0)

    # === Momentum (max 1.5) ===
    ls += np.where((df["rsi"] >= 35) & (df["rsi"] <= 65), 0.5, 0.0)
    ls += np.where(df["macd_line"] > df["macd_signal"], 0.5, 0.0)
    ls += np.where((df["adx"] > 20) & (df["di_plus"] > df["di_minus"]), 0.5, 0.0)

    # === Events (max ~3.2) ===
    ls += np.where(df["hammer_confirm"], 0.7, 0.0)
    ls += np.where(df["morning_star"], 0.7, 0.0)
    ls += np.where(df["bull_engulf"], 0.5, 0.0)
    ls += np.where(df["bull_cons_breakout"], 0.4, 0.0)   # NOTE: counted twice (structure + events)
    ls += np.where(df["bull_shift"], 0.4, 0.0)
    ls += np.where(df["st_flip"] & df["st_bullish"], 0.5, 0.0)
    ls += np.where(df["bull_sess_break"], 0.5, 0.0)

    # === Session bonus ===
    ls += sess_bonus

    # === Penalties ===
    ls += np.where(df["adx"] < 20, -0.5, 0.0)
    ls += np.where((df["rsi"] > 75) | (df["rsi"] < 25), -0.5, 0.0)
    ls += np.where(df["long_blocked"], -1.5, 0.0)
    ls += np.where(df["st_bearish"], -0.5, 0.0)
    ls += np.where(df["near_resist"] & ~df["bull_breakout"], -0.3, 0.0)
    ls += np.where(df["vol_declining"], -0.3, 0.0)

    return ls.clip(0.0, 10.0)


# ═══════════════════════════════════════════════════════════════════
# CONFIRMATIONS — PYTHON V1 EXACT MATCH
# ═══════════════════════════════════════════════════════════════════

def precompute_long_confirmations(df: pd.DataFrame) -> pd.Series:
    """Count confirmations for dynamic threshold calculation.

    EXACT match to swing_scalper_data.py lines 846-851.
    Uses ADX > 30 (not 25) and mtf1h OR mtf4h (not just mtf_bullish).
    """
    lc = (
        df["st_bullish"].astype(int)
        + ((df["adx"] > 30) & (df["di_plus"] > df["di_minus"])).astype(int)
        + df["vol_above"].astype(int)
        + (df["mtf_bullish"] | df["mtf4h_bullish"]).astype(int)
    )
    return lc


# ═══════════════════════════════════════════════════════════════════
# DYNAMIC THRESHOLD — EXACT V1 MATCH
# ═══════════════════════════════════════════════════════════════════

def precompute_dynamic_thresholds(confirmations: pd.Series) -> pd.Series:
    """Calculate dynamic entry threshold from confirmations count.

    Validated Python V1 thresholds (wider steps for quality filtering):
    4+ confirmations = 7.0 (base)
    3 = 7.5
    2 = 8.0
    1 = 8.5
    0 = 9.0 (strict)
    """
    return pd.Series(
        np.select(
            [confirmations >= 4, confirmations == 3, confirmations == 2, confirmations == 1],
            [7.0, 7.5, 8.0, 8.5],
            default=9.0,
        ),
        index=confirmations.index,
    )


# ═══════════════════════════════════════════════════════════════════
# LAYER 1: ATR PERCENTILE THRESHOLD ADJUSTMENT
# ═══════════════════════════════════════════════════════════════════

def atr_threshold_adjustment(atr_percentile: float) -> float:
    """Threshold adjustment based on ATR percentile.

    Validated on Walk-Forward (train 2016-2023, test 2024-2025).
    OOS improvement: PF 1.30→1.44, Sharpe 1.81→2.51.
    """
    if np.isnan(atr_percentile):
        return 0.0
    if atr_percentile > 80:
        return 0.5       # Very high volatility — raise threshold
    elif atr_percentile > 65:
        return 0.25      # Above average volatility
    elif atr_percentile < 20:
        return -0.25     # Very low volatility — lower threshold slightly
    else:
        return 0.0       # Normal — no change


def precompute_atr_adjustments(atr_pctile: pd.Series) -> pd.Series:
    """Vectorized ATR threshold adjustment for entire DataFrame."""
    adj = pd.Series(0.0, index=atr_pctile.index)
    adj[atr_pctile > 80] = 0.5
    adj[(atr_pctile > 65) & (atr_pctile <= 80)] = 0.25
    adj[atr_pctile < 20] = -0.25
    return adj


# ═══════════════════════════════════════════════════════════════════
# TECHNICAL STOP LOSS LEVELS
# ═══════════════════════════════════════════════════════════════════

def precompute_tech_sl(df: pd.DataFrame) -> pd.Series:
    """Precompute technical stop-loss levels for long entries.

    SL = min(recent_low, supertrend_or_atr_buffer), capped at 40 pts from close.
    """
    low_n = df["Low"].rolling(window=PIVOT_LOOKBACK, min_periods=1).min()

    tech_sl = np.minimum(
        low_n.values,
        np.where(
            df["st_bullish"].values,
            df["st_line"].values,
            df["Low"].values - df["atr"].values,
        ),
    )

    # Cap: SL cannot be more than MAX_SL_POINTS below close
    tech_sl = np.maximum(tech_sl, df["Close"].values - MAX_SL_POINTS)

    return pd.Series(tech_sl, index=df.index)


# ═══════════════════════════════════════════════════════════════════
# MASTER SCORING PIPELINE
# ═══════════════════════════════════════════════════════════════════

def precompute_session_penalty(df: pd.DataFrame) -> pd.Series:
    """Session-specific threshold penalty.

    Raises the entry bar for sessions with historically lower win rates:
    - US:     +1.0 (filter to score >= 8.0 sweet spot)
    - Europe: +1.0 (pre-US, lower quality signals)
    - Asia:   +2.0 (very low win rate, effectively blocked)
    - Other:  +1.0
    """
    return pd.Series(
        np.select(
            [
                df["session"] == "Europe",
                df["session"] == "Asia",
                df["session"] == "US",
            ],
            [1.0, 2.0, 1.0],
            default=1.0,
        ),
        index=df.index,
    )


def precompute_all_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all scoring columns on the enriched DataFrame.

    Adds: long_score, long_confirms, long_thresh, session_penalty,
          atr_pctile, atr_adj, effective_thresh, tech_sl_long.
    """
    df = df.copy()

    logger.info("Computing long scores (Python V1 exact)...")
    df["long_score"] = precompute_long_scores(df)

    logger.info("Computing confirmations and dynamic thresholds...")
    df["long_confirms"] = precompute_long_confirmations(df)
    df["long_thresh"] = precompute_dynamic_thresholds(df["long_confirms"])

    logger.info("Computing session penalty...")
    df["session_penalty"] = precompute_session_penalty(df)

    logger.info("Computing ATR percentile (Layer 1)...")
    from indicators import calc_atr_percentile
    df["atr_pctile"] = calc_atr_percentile(df["atr"])
    df["atr_adj"] = precompute_atr_adjustments(df["atr_pctile"])

    # Effective threshold = base V1 + session penalty + Layer 1 ATR adjustment
    df["effective_thresh"] = df["long_thresh"] + df["session_penalty"] + df["atr_adj"]

    logger.info("Computing technical stop-loss levels...")
    df["tech_sl_long"] = precompute_tech_sl(df)

    return df
