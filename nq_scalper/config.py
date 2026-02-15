"""Configuration — matching the validated Python V1 system exactly.

This is the SINGLE SOURCE OF TRUTH for indicator parameters, risk management,
scoring thresholds, and session timing.  Every magic number lives here.

NOTE: These parameters match swing_scalper_engine.py in nq_trend_system/,
which produced the validated results (282 trades, PF 1.79, $184K).
"""

from pathlib import Path

# ═══════════════════════════════════════════════════════════════════
# PATHS
# ═══════════════════════════════════════════════════════════════════

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = str(BASE_DIR / "nq_data.db")
OUTPUT_DIR = str(BASE_DIR / "output")
TIMEZONE = "US/Eastern"

# ═══════════════════════════════════════════════════════════════════
# CONTRACT SPEC
# ═══════════════════════════════════════════════════════════════════

POINT_VALUE: float = 20.0        # NQ = $20 per point
TICK_SIZE: float = 0.25
TICK_VALUE: float = TICK_SIZE * POINT_VALUE  # $5.00

# ═══════════════════════════════════════════════════════════════════
# INDICATOR PARAMETERS (15-min base chart)
# ═══════════════════════════════════════════════════════════════════

EMA_FAST: int = 9
EMA_SLOW: int = 21
EMA_50: int = 50
EMA_200: int = 200

RSI_LEN: int = 14

MACD_FAST: int = 12
MACD_SLOW: int = 26
MACD_SIGNAL: int = 9

ADX_LEN: int = 14

ATR_LEN: int = 14

ST_PERIOD: int = 10
ST_MULTIPLIER: float = 3.0

VOL_SMA_LEN: int = 20
VOL_MULTIPLIER: float = 1.2       # Above average threshold
VOL_SPIKE_MULTIPLIER: float = 2.0 # Spike threshold

# ═══════════════════════════════════════════════════════════════════
# MTF SETTINGS
# ═══════════════════════════════════════════════════════════════════

HTF1_EMA_FAST: int = 9
HTF1_EMA_SLOW: int = 21

# HTF2 = 1H
HTF2_EMA_50: int = 50
HTF2_EMA_200: int = 200

# HTF3 = 4H
HTF3_EMA_50: int = 50
HTF3_EMA_200: int = 200

# ═══════════════════════════════════════════════════════════════════
# PATTERN PARAMETERS
# ═══════════════════════════════════════════════════════════════════

PIN_BAR_RATIO: float = 2.5
CONSOLIDATION_BARS: int = 5
SHIFT_BODY_MULTIPLIER: float = 2.5
SHIFT_MIN_BARS: int = 5
BREAKOUT_VOL_MULTIPLIER: float = 1.5

# S/R
ROUND_NUMBER_INTERVAL: int = 100
FIB_LOOKBACK: int = 30

# Lookbacks
PIVOT_LOOKBACK: int = 10
BREAKOUT_LOOKBACK: int = 20
SHIFT_BLOCK_BARS: int = 4

# ═══════════════════════════════════════════════════════════════════
# SESSION / TIME (EST)
# ═══════════════════════════════════════════════════════════════════

SESSION_START: int = 9
SESSION_END: int = 16
AVOID_FIRST_MINUTES: int = 5
EOD_CLOSE_HOUR: int = 16
EOD_CLOSE_MINUTE: int = 45
USE_EOD_CLOSE: bool = False    # Validated system does NOT close at EOD

# ═══════════════════════════════════════════════════════════════════
# RISK MANAGEMENT
# ═══════════════════════════════════════════════════════════════════

MAX_RISK_PER_CONTRACT: float = 800.0   # $800 per contract
NUM_CONTRACTS: int = 2
MAX_SL_POINTS: float = MAX_RISK_PER_CONTRACT / POINT_VALUE  # 40 points
TP1_FIXED_PTS: float = 100.0          # Fixed 100pt TP1 (legacy mode)
TP1_MODE: str = "rr"                  # "rr" = sl*mult (matches Pine Script)
RR_RATIO_TP1: float = 1.5             # TP1 = SL × 1.5 (matches Pine Script)
MIN_RR: float = 2.0                   # Cap SL so R:R >= 2.0 (for fixed TP1 only)
COMMISSION_PER_CONTRACT: float = 4.50  # Round-trip per contract
SLIPPAGE_TICKS: int = 1               # 1 tick slippage per fill
SLIPPAGE_COST: float = SLIPPAGE_TICKS * TICK_VALUE  # $5 per fill
INITIAL_CAPITAL: float = 100_000.0

# ═══════════════════════════════════════════════════════════════════
# TRAILING STOP
# ═══════════════════════════════════════════════════════════════════

TRAILING_ATR_MULT: float = 2.0
USE_SUPERTREND_TRAILING: bool = True

# ═══════════════════════════════════════════════════════════════════
# SIGNAL QUALITY
# ═══════════════════════════════════════════════════════════════════

MIN_SIGNAL_SCORE: float = 7.0
MIN_SIGNAL_SCORE_STRICT: float = 8.0
USE_DYNAMIC_SCORE: bool = True

# Day-of-week hard floors (from validated system)
WEDNESDAY_LONG_MIN_SCORE: float = 9.0
THURSDAY_MIN_SCORE: float = 9.0

# Session score floor — filter low-quality Europe signals
EUROPE_MIN_SCORE: float = 8.5   # Europe trades below this score are rejected

# ═══════════════════════════════════════════════════════════════════
# COOLDOWN
# ═══════════════════════════════════════════════════════════════════

COOLDOWN_BARS: int = 8
MIN_PRICE_CHANGE: float = 0.25  # Percent

# ═══════════════════════════════════════════════════════════════════
# ATR PERCENTILE (Layer 1)
# ═══════════════════════════════════════════════════════════════════

ATR_PCTILE_LOOKBACK_DAYS: int = 252
ATR_PCTILE_BARS_PER_DAY: int = 26
ATR_PCTILE_MIN_PERIODS: int = 100   # Match validated system (was 2000)

# ═══════════════════════════════════════════════════════════════════
# WARM-UP
# ═══════════════════════════════════════════════════════════════════

WARM_UP_BARS: int = 300  # EMA200 needs ~200 bars to stabilize

# ═══════════════════════════════════════════════════════════════════
# ADX THRESHOLDS (used in scoring)
# ═══════════════════════════════════════════════════════════════════

ADX_STRONG_TREND: int = 25   # is_strong_trend threshold
ADX_RANGING: int = 20        # is_ranging threshold (below this)
