"""3-stage trailing stop logic.

Implements the exact V1 trailing stop system for the runner contract:

Stage 1 (Breakeven):  Trail stop = entry price.
Stage 2 (Partial):    When profit >= SL × 1.5, trail = entry + SL × 0.5.
Stage 3 (ATR Trail):  When profit >= SL × 2.0, trail = max(close - ATR × 1.2,
                       Supertrend line).

Trail ONLY moves UP, never down.
"""

import logging

import numpy as np

from config import TRAILING_ATR_MULT, USE_SUPERTREND_TRAILING

logger = logging.getLogger(__name__)


class TrailingStop:
    """Manages the 3-stage trailing stop for a LONG runner position."""

    def __init__(self, entry_price: float, sl_distance: float):
        self.entry_price = entry_price
        self.sl_distance = sl_distance
        self.trail_stop: float = entry_price  # Stage 1 starts at breakeven
        self.stage: int = 1

    def update(
        self,
        bar_close: float,
        atr: float,
        st_line: float,
        st_bullish: bool,
    ) -> None:
        """Update trailing stop based on current bar data.

        Call this once per bar while the runner position is open.
        The trail stop only ratchets UP, never down.
        """
        current_profit = bar_close - self.entry_price

        # Stage 2 transition: profit >= SL × 1.5
        if self.stage == 1 and current_profit >= self.sl_distance * 1.5:
            self.stage = 2
            new_trail = self.entry_price + self.sl_distance * 0.5
            self.trail_stop = max(self.trail_stop, new_trail)

        # Stage 3 transition: profit >= SL × 2.0
        if self.stage == 2 and current_profit >= self.sl_distance * 2.0:
            self.stage = 3

        # Stage 3: ATR trailing (dynamic)
        if self.stage == 3 and not np.isnan(atr):
            atr_trail = bar_close - atr * TRAILING_ATR_MULT

            if USE_SUPERTREND_TRAILING and st_bullish and not np.isnan(st_line):
                st_trail = st_line
            else:
                st_trail = atr_trail

            new_trail = max(atr_trail, st_trail)
            # Never below entry price
            new_trail = max(new_trail, self.entry_price)
            # Only ratchet up
            self.trail_stop = max(self.trail_stop, new_trail)

    def is_stopped(self, bar_low: float) -> bool:
        """Check if the runner's trailing stop was hit."""
        return bar_low <= self.trail_stop
