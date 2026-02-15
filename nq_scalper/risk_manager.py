"""Risk management — SL/TP calculation, position sizing, cost model.

Parameters:
- TP1: SL × 1.5 (RR mode, matches Pine Script) — ~48pts avg with 32pt avg SL
- SL capped at 40pts ($800 risk per contract)
- 2 contracts per trade
- Commission = $4.50 per contract round-trip (split as half-comm per fill)
- Slippage = $5 per fill (1 tick)
"""

import logging

from config import (
    POINT_VALUE,
    NUM_CONTRACTS,
    MAX_SL_POINTS,
    RR_RATIO_TP1,
    TP1_FIXED_PTS,
    TP1_MODE,
    MIN_RR,
    COMMISSION_PER_CONTRACT,
    SLIPPAGE_COST,
)

logger = logging.getLogger(__name__)


def calc_entry(close: float, tech_sl: float) -> dict | None:
    """Calculate entry parameters for a LONG trade."""
    sl_distance = close - tech_sl

    if sl_distance <= 0:
        return None

    # Cap SL at MAX_SL_POINTS (40 pts)
    if sl_distance > MAX_SL_POINTS:
        sl_distance = MAX_SL_POINTS
        tech_sl = close - sl_distance

    if TP1_MODE == "fixed":
        # Fixed TP1 at 100 points
        tp1_dist = TP1_FIXED_PTS
        tp1_price = close + tp1_dist
        # Cap SL so R:R >= MIN_RR (2.0) → SL <= 50pts
        max_sl_dist = tp1_dist / MIN_RR
        if sl_distance > max_sl_dist:
            sl_distance = max_sl_dist
            tech_sl = close - sl_distance
    else:
        # RR-based TP1
        tp1_price = close + sl_distance * RR_RATIO_TP1

    return {
        "entry_price": close,
        "stop_loss": tech_sl,
        "sl_distance": sl_distance,
        "tp1_price": tp1_price,
    }


def calc_costs(tp1_hit: bool) -> float:
    """Calculate round-trip costs (commission + slippage).

    Matching validated V1 cost model:
    - half_comm = $4.50 / 2 = $2.25 per fill
    - No TP1: 4 half-fills comm ($9) + 2 slippage fills ($10) = $19
    - TP1 hit: 6 half-fills comm ($13.50) + 4 slippage fills ($20) = $33.50
    """
    half_comm = COMMISSION_PER_CONTRACT / 2

    if tp1_hit:
        commission = 6 * half_comm
        slippage = 4 * SLIPPAGE_COST
    else:
        commission = 4 * half_comm
        slippage = 2 * SLIPPAGE_COST

    return commission + slippage
