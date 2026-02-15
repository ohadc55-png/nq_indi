"""Signal generation — threshold, cooldown, blocking, day-of-week filters.

LONG ONLY. Matching validated V1 system exactly.
Signal generation checks: score >= threshold, EMA slope, cooldown, blocking, DOW filters.
"""

import logging

import numpy as np

from config import (
    COOLDOWN_BARS, MIN_PRICE_CHANGE,
    WEDNESDAY_LONG_MIN_SCORE, THURSDAY_MIN_SCORE,
    EUROPE_MIN_SCORE,
)

logger = logging.getLogger(__name__)


class CooldownTracker:
    """Tracks cooldown state between trades.

    Cooldown resets when:
    - COOLDOWN_BARS (8) bars have passed since last trade, OR
    - Price has moved >= MIN_PRICE_CHANGE (0.25%) from last entry, OR
    - A bullish shift candle or Supertrend flip fires (override).
    """

    def __init__(self):
        self.last_trade_bar: int = -999
        self.last_trade_price: float = 0.0

    def update(self, bar_idx: int, entry_price: float) -> None:
        """Call when a new trade is entered."""
        self.last_trade_bar = bar_idx
        self.last_trade_price = entry_price

    def is_ready(
        self,
        bar_idx: int,
        close: float,
        is_shift_override: bool = False,
    ) -> bool:
        """Check if cooldown has expired."""
        if is_shift_override:
            return True

        bars_elapsed = bar_idx - self.last_trade_bar
        if bars_elapsed >= COOLDOWN_BARS:
            return True

        if self.last_trade_price > 0:
            pct_move = abs(close - self.last_trade_price) / self.last_trade_price * 100
            if pct_move >= MIN_PRICE_CHANGE:
                return True

        return False


def check_long_signal(
    bar_idx: int,
    long_score: float,
    effective_thresh: float,
    longs_blocked: bool,
    ema_slope_bull: bool,
    et_dow: int,
    cooldown: CooldownTracker,
    close: float,
    is_shift_override: bool = False,
    session: str = "",
) -> bool:
    """Check whether to generate a LONG entry signal at the current bar.

    Criteria (matching validated V1 system):
    1. Score >= effective threshold
    2. Longs not blocked by bearish shift
    3. EMA slope is bullish (trade_mode="with_trend")
    4. Day-of-week filters (Wed >= 9.0, Thu >= 9.0)
    5. Europe session score floor (>= 8.5)
    6. Cooldown has expired
    """
    if np.isnan(long_score) or np.isnan(effective_thresh):
        return False

    if longs_blocked:
        return False

    if not ema_slope_bull:
        return False

    if long_score < effective_thresh:
        return False

    # Day-of-week hard floors
    if et_dow == 2 and long_score < WEDNESDAY_LONG_MIN_SCORE:
        return False
    if et_dow == 3 and long_score < THURSDAY_MIN_SCORE:
        return False

    # Europe session score floor
    if session == "Europe" and long_score < EUROPE_MIN_SCORE:
        return False

    if not cooldown.is_ready(bar_idx, close, is_shift_override):
        return False

    return True
