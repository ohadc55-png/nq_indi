"""Backtest execution engine — bar-by-bar walk through 15m data.

LONG ONLY. Walks through each 15m bar:
1. Check time filter (session, EOD close)
2. Manage open position (SL, TP1, trailing stop)
3. Check for new signals

All position management, cost model, and signal logic are delegated
to their respective modules.
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from config import (
    POINT_VALUE, NUM_CONTRACTS, INITIAL_CAPITAL,
    EOD_CLOSE_HOUR, EOD_CLOSE_MINUTE, USE_EOD_CLOSE, TIMEZONE,
)
from signals import CooldownTracker, check_long_signal
from risk_manager import calc_entry, calc_costs
from trailing import TrailingStop

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# TIME UTILITIES
# ═══════════════════════════════════════════════════════════════════

def get_et_time(ts) -> tuple[int, int, int]:
    """Convert a timestamp to ET (hour, minute, day_of_week)."""
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    et = ts.tz_convert(TIMEZONE)
    return et.hour, et.minute, et.dayofweek


def is_eod(hour: int, minute: int) -> bool:
    """Check if we're at EOD close time (16:45 EST)."""
    return hour == EOD_CLOSE_HOUR and minute >= EOD_CLOSE_MINUTE


def is_maintenance(hour: int) -> bool:
    """Check if we're in CME maintenance window."""
    return hour == 17


# ═══════════════════════════════════════════════════════════════════
# POSITION STATE
# ═══════════════════════════════════════════════════════════════════

class Position:
    """Tracks the state of an open LONG position (2-contract split)."""

    def __init__(
        self,
        entry_price: float,
        stop_loss: float,
        sl_distance: float,
        tp1_price: float,
        entry_bar: int,
        entry_time,
        entry_score: float,
        entry_session: str,
    ):
        self.entry_price = entry_price
        self.stop_loss = stop_loss
        self.sl_distance = sl_distance
        self.tp1_price = tp1_price
        self.entry_bar = entry_bar
        self.entry_time = entry_time
        self.entry_score = entry_score
        self.entry_session = entry_session

        self.tp1_hit: bool = False
        self.contracts: int = NUM_CONTRACTS  # 2 initially
        self.trailing: Optional[TrailingStop] = None


# ═══════════════════════════════════════════════════════════════════
# BACKTEST ENGINE
# ═══════════════════════════════════════════════════════════════════

class BacktestEngine:
    """Full backtest engine for the NQ Swing Scalper (LONG ONLY)."""

    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.position: Optional[Position] = None
        self.cooldown = CooldownTracker()
        self.trades: list[dict] = []
        self.trade_count: int = 0
        self.capital: float = INITIAL_CAPITAL
        self.equity_curve: list[float] = []

    def run(self) -> list[dict]:
        """Execute the full backtest. Returns list of trade dicts."""
        n = len(self.df)
        logger.info("Running backtest on %s bars...", f"{n:,}")

        # Pre-extract numpy arrays for speed
        h = self.df["High"].values
        l = self.df["Low"].values
        c = self.df["Close"].values
        idx = self.df.index

        long_score = self.df["long_score"].values
        effective_thresh = self.df["effective_thresh"].values
        longs_blocked = self.df["longs_blocked"].values
        ema_slope_bull = self.df["ema_slope_bull"].values
        atr = self.df["atr"].values
        st_line = self.df["st_line"].values
        st_bullish = self.df["st_bullish"].values
        st_buy_signal = self.df["st_buy_signal"].values
        is_bullish_shift = self.df["is_bullish_shift_candle"].values
        tech_sl_long = self.df["tech_sl_long"].values
        sessions = self.df["session"].values

        progress_step = max(1, n // 20)

        for i in range(n):
            if i % progress_step == 0:
                pct = int(100 * i / n)
                logger.info("Progress: %d%% (%s/%s bars)", pct, f"{i:,}", f"{n:,}")

            # Skip NaN bars
            if np.isnan(c[i]) or np.isnan(long_score[i]):
                self.equity_curve.append(self.capital)
                continue

            # Time checks
            ts = idx[i]
            et_hour, et_minute, et_dow = get_et_time(ts)
            session = sessions[i]

            # EOD close (disabled in validated system)
            if USE_EOD_CLOSE and is_eod(et_hour, et_minute) and self.position is not None:
                self._close_position(i, c[i], "EOD_CLOSE", idx)
                self.equity_curve.append(self.capital)
                continue

            # Skip maintenance / Saturday
            if is_maintenance(et_hour) or et_dow == 5:
                self.equity_curve.append(self.capital)
                continue

            # Position management
            if self.position is not None:
                self._manage_position(i, h, l, c, idx, atr, st_line, st_bullish)
            else:
                # Check for new entry
                can_trade = session not in ("Maintenance", "Closed")
                if can_trade:
                    shift_override = bool(
                        is_bullish_shift[i] or st_buy_signal[i]
                    ) if not np.isnan(is_bullish_shift[i]) else False

                    if check_long_signal(
                        bar_idx=i,
                        long_score=long_score[i],
                        effective_thresh=effective_thresh[i],
                        longs_blocked=bool(longs_blocked[i]),
                        ema_slope_bull=bool(ema_slope_bull[i]),
                        et_dow=et_dow,
                        cooldown=self.cooldown,
                        close=c[i],
                        is_shift_override=shift_override,
                        session=session,
                    ):
                        entry = calc_entry(c[i], tech_sl_long[i])
                        if entry is not None:
                            self._enter_long(
                                i, entry, long_score[i], idx, session,
                            )

            self.equity_curve.append(self.capital)

        logger.info(
            "Backtest complete. %d trades executed.", self.trade_count,
        )
        return self.trades

    # ───────────────────────────────────────────────────────────────
    # ENTRY
    # ───────────────────────────────────────────────────────────────

    def _enter_long(
        self,
        i: int,
        entry: dict,
        score: float,
        idx,
        session: str,
    ) -> None:
        """Open a new LONG position with 2 contracts."""
        self.position = Position(
            entry_price=entry["entry_price"],
            stop_loss=entry["stop_loss"],
            sl_distance=entry["sl_distance"],
            tp1_price=entry["tp1_price"],
            entry_bar=i,
            entry_time=idx[i],
            entry_score=score,
            entry_session=session,
        )
        self.cooldown.update(i, entry["entry_price"])
        self.trade_count += 1

    # ───────────────────────────────────────────────────────────────
    # POSITION MANAGEMENT
    # ───────────────────────────────────────────────────────────────

    def _manage_position(
        self, i: int, h, l, c, idx, atr, st_line, st_bullish,
    ) -> None:
        """Manage an open LONG position (pre-TP1 or runner)."""
        pos = self.position
        bar_low = l[i]
        bar_high = h[i]
        bar_close = c[i]

        if not pos.tp1_hit:
            # ── Pre-TP1: full 2-contract position ──

            # Check SL
            if bar_low <= pos.stop_loss:
                exit_price = pos.stop_loss
                pnl = (exit_price - pos.entry_price) * POINT_VALUE * NUM_CONTRACTS
                costs = calc_costs(tp1_hit=False)
                self._log_trade(
                    exit_price=exit_price,
                    exit_time=idx[i],
                    exit_reason="FULL_STOP",
                    pnl_tp1=0.0,
                    pnl_runner=pnl,
                    costs=costs,
                    tp1_hit=False,
                    trail_stage=0,
                )
                self.position = None
                return

            # Check TP1
            if bar_high >= pos.tp1_price:
                pos.tp1_hit = True
                pos.contracts = 1  # runner
                pos.trailing = TrailingStop(pos.entry_price, pos.sl_distance)

        else:
            # ── Post-TP1: runner (1 contract) with trailing stop ──
            trail = pos.trailing

            # Update trailing stop
            trail.update(
                bar_close=bar_close,
                atr=atr[i],
                st_line=st_line[i],
                st_bullish=bool(st_bullish[i]),
            )

            # Check trailing stop hit
            if trail.is_stopped(bar_low):
                exit_price = trail.trail_stop
                pnl_tp1 = (pos.tp1_price - pos.entry_price) * POINT_VALUE * 1
                pnl_runner = (exit_price - pos.entry_price) * POINT_VALUE * 1
                costs = calc_costs(tp1_hit=True)
                self._log_trade(
                    exit_price=exit_price,
                    exit_time=idx[i],
                    exit_reason=f"TRAIL_S{trail.stage}",
                    pnl_tp1=pnl_tp1,
                    pnl_runner=pnl_runner,
                    costs=costs,
                    tp1_hit=True,
                    trail_stage=trail.stage,
                )
                self.position = None

    # ───────────────────────────────────────────────────────────────
    # FORCE CLOSE
    # ───────────────────────────────────────────────────────────────

    def _close_position(
        self, i: int, price: float, reason: str, idx,
    ) -> None:
        """Force close at given price (EOD, etc.)."""
        pos = self.position
        if pos.tp1_hit:
            pnl_tp1 = (pos.tp1_price - pos.entry_price) * POINT_VALUE * 1
            pnl_runner = (price - pos.entry_price) * POINT_VALUE * 1
            costs = calc_costs(tp1_hit=True)
            trail_stage = pos.trailing.stage if pos.trailing else 0
        else:
            pnl_tp1 = 0.0
            pnl_runner = (price - pos.entry_price) * POINT_VALUE * NUM_CONTRACTS
            costs = calc_costs(tp1_hit=False)
            trail_stage = 0

        self._log_trade(
            exit_price=price,
            exit_time=idx[i],
            exit_reason=reason,
            pnl_tp1=pnl_tp1,
            pnl_runner=pnl_runner,
            costs=costs,
            tp1_hit=pos.tp1_hit,
            trail_stage=trail_stage,
        )
        self.position = None

    # ───────────────────────────────────────────────────────────────
    # TRADE LOGGING
    # ───────────────────────────────────────────────────────────────

    def _log_trade(
        self,
        exit_price: float,
        exit_time,
        exit_reason: str,
        pnl_tp1: float,
        pnl_runner: float,
        costs: float,
        tp1_hit: bool,
        trail_stage: int,
    ) -> None:
        """Record a completed trade."""
        pos = self.position
        total_pnl = pnl_tp1 + pnl_runner - costs
        self.capital += total_pnl

        rr_achieved = 0.0
        if pos.sl_distance > 0:
            rr_achieved = (exit_price - pos.entry_price) / pos.sl_distance

        trade = {
            "trade_num": self.trade_count,
            "direction": "LONG",
            "entry_time": pos.entry_time,
            "entry_price": round(pos.entry_price, 2),
            "stop_loss": round(pos.stop_loss, 2),
            "sl_distance_pts": round(pos.sl_distance, 2),
            "tp1_price": round(pos.tp1_price, 2),
            "tp1_hit": tp1_hit,
            "trail_stage": trail_stage,
            "exit_time": exit_time,
            "exit_price": round(exit_price, 2),
            "exit_reason": exit_reason,
            "entry_score": round(pos.entry_score, 2),
            "entry_session": pos.entry_session,
            "pnl_tp1": round(pnl_tp1, 2),
            "pnl_runner": round(pnl_runner, 2),
            "costs": round(costs, 2),
            "total_pnl": round(total_pnl, 2),
            "rr_achieved": round(rr_achieved, 2),
            "capital_after": round(self.capital, 2),
        }
        self.trades.append(trade)
