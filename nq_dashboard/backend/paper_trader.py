"""Paper trader — virtual position management with 2-contract split.

Reuses exact same logic as nq_scalper's backtest_engine.py:
- 2-contract entry, scale out at TP1
- 3-stage trailing stop for runner
- Matching cost model
"""

import sys
import logging
from datetime import datetime
from pathlib import Path

import numpy as np

NQ_SCALPER_DIR = str(Path(__file__).resolve().parent.parent.parent / "nq_scalper")
if NQ_SCALPER_DIR not in sys.path:
    sys.path.insert(0, NQ_SCALPER_DIR)

from config import (
    POINT_VALUE, NUM_CONTRACTS, MAX_SL_POINTS, RR_RATIO_TP1,
    COMMISSION_PER_CONTRACT, SLIPPAGE_COST, TRAILING_ATR_MULT,
    USE_SUPERTREND_TRAILING, COOLDOWN_BARS, MIN_PRICE_CHANGE,
    WEDNESDAY_LONG_MIN_SCORE, THURSDAY_MIN_SCORE, EUROPE_MIN_SCORE,
)

logger = logging.getLogger(__name__)


class TrailingStop:
    """3-stage trailing stop for the runner contract (matches trailing.py)."""

    def __init__(self, entry_price: float, sl_distance: float):
        self.entry_price = entry_price
        self.sl_distance = sl_distance
        self.trail_stop = entry_price  # Stage 1 = breakeven
        self.stage = 1

    def update(self, bar_close: float, atr: float, st_line: float, st_bullish: bool):
        current_profit = bar_close - self.entry_price

        # Stage 2: profit >= SL * 1.5
        if self.stage == 1 and current_profit >= self.sl_distance * 1.5:
            self.stage = 2
            new_trail = self.entry_price + self.sl_distance * 0.5
            self.trail_stop = max(self.trail_stop, new_trail)

        # Stage 3: profit >= SL * 2.0
        if self.stage == 2 and current_profit >= self.sl_distance * 2.0:
            self.stage = 3

        # Stage 3: ATR dynamic trailing
        if self.stage == 3 and not np.isnan(atr):
            atr_trail = bar_close - atr * TRAILING_ATR_MULT
            if USE_SUPERTREND_TRAILING and st_bullish and not np.isnan(st_line):
                st_trail = st_line
            else:
                st_trail = atr_trail
            new_trail = max(atr_trail, st_trail)
            new_trail = max(new_trail, self.entry_price)
            self.trail_stop = max(self.trail_stop, new_trail)

    def is_stopped(self, bar_low: float) -> bool:
        return bar_low <= self.trail_stop

    def to_dict(self) -> dict:
        return {
            "entry_price": self.entry_price,
            "sl_distance": self.sl_distance,
            "trail_stop": self.trail_stop,
            "stage": self.stage,
        }


class PaperTrader:
    """Virtual position management — mimics real trading exactly."""

    def __init__(self, initial_capital: float = 100_000.0):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.position = None  # Current open position dict
        self.trade_history = []  # Completed trades
        self.trade_count = 0
        self._cooldown_bar = -999
        self._cooldown_price = 0.0
        self._bar_counter = 0  # Simulated bar counter for cooldown

    def check_entry(self, signal_data: dict) -> bool:
        """Check if we should enter a new position."""
        if self.position is not None:
            return False

        if not signal_data.get("signal", False):
            return False

        if signal_data.get("longs_blocked", False):
            return False

        if not signal_data.get("ema_slope_bull", False):
            return False

        score = signal_data.get("long_score", 0)

        # Session filter
        session = signal_data.get("session", "")
        if session in ("Maintenance", "Closed"):
            return False
        if session == "Europe" and score < EUROPE_MIN_SCORE:
            return False

        # Day-of-week filters
        try:
            ts = signal_data.get("timestamp", "")
            if ts:
                from datetime import datetime as dt
                parsed = dt.fromisoformat(str(ts).replace("Z", "+00:00"))
                dow = parsed.weekday()
                if dow == 2 and score < WEDNESDAY_LONG_MIN_SCORE:
                    return False
                if dow == 3 and score < THURSDAY_MIN_SCORE:
                    return False
        except Exception:
            pass

        # Cooldown check
        self._bar_counter += 1
        bars_elapsed = self._bar_counter - self._cooldown_bar
        if bars_elapsed < COOLDOWN_BARS:
            close = signal_data.get("close", 0)
            if self._cooldown_price > 0:
                pct_move = abs(close - self._cooldown_price) / self._cooldown_price * 100
                if pct_move < MIN_PRICE_CHANGE:
                    return False

        return True

    def enter_position(self, signal_data: dict) -> dict:
        """Enter a new virtual position (2 contracts)."""
        entry_price = signal_data["close"]
        tech_sl = signal_data.get("tech_sl", entry_price - 30)

        sl_distance = entry_price - tech_sl
        if sl_distance <= 0:
            sl_distance = 30
            tech_sl = entry_price - sl_distance

        # Cap SL at MAX_SL_POINTS (40 pts)
        if sl_distance > MAX_SL_POINTS:
            sl_distance = MAX_SL_POINTS
            tech_sl = entry_price - sl_distance

        tp1_price = entry_price + sl_distance * RR_RATIO_TP1

        self.position = {
            "entry_time": signal_data["timestamp"],
            "entry_price": entry_price,
            "entry_score": signal_data.get("long_score", 0),
            "entry_session": signal_data.get("session", "US"),
            "contracts": NUM_CONTRACTS,
            "sl_price": tech_sl,
            "sl_distance": sl_distance,
            "tp1_price": tp1_price,
            "tp1_distance": sl_distance * RR_RATIO_TP1,
            "tp1_hit": False,
            "trailing": None,
            "trail_stage": 0,
            "trail_stop": tech_sl,
            "highest_since_entry": entry_price,
            "atr_at_entry": signal_data.get("atr", 0),
            "atr_percentile": signal_data.get("atr_percentile", 0),
            "pnl_tp1": 0.0,
        }

        self._cooldown_bar = self._bar_counter
        self._cooldown_price = entry_price
        self.trade_count += 1

        logger.info(
            "ENTRY: price=%.1f SL=%.1f TP1=%.1f score=%.1f",
            entry_price, tech_sl, tp1_price, signal_data.get("long_score", 0),
        )

        return self.position.copy()

    def update_position(self, signal_data: dict) -> dict | None:
        """Update open position with new bar data. Returns exit event or None."""
        if self.position is None:
            return None

        self._bar_counter += 1

        high = signal_data.get("high", signal_data.get("close", 0))
        low = signal_data.get("low", signal_data.get("close", 0))
        close = signal_data.get("close", 0)
        atr = signal_data.get("atr", 0)
        st_line = signal_data.get("supertrend", 0)
        st_bullish = signal_data.get("st_bullish", False)

        pos = self.position

        # Track highest
        if high > pos["highest_since_entry"]:
            pos["highest_since_entry"] = high

        if not pos["tp1_hit"]:
            # Pre-TP1: 2-contract position

            # Check stop loss
            if low <= pos["sl_price"]:
                return self._exit(
                    exit_price=pos["sl_price"],
                    exit_reason="FULL_STOP",
                    timestamp=signal_data["timestamp"],
                )

            # Check TP1
            if high >= pos["tp1_price"]:
                pos["tp1_hit"] = True
                pos["contracts"] = 1
                pos["pnl_tp1"] = (pos["tp1_price"] - pos["entry_price"]) * POINT_VALUE
                pos["trailing"] = TrailingStop(pos["entry_price"], pos["sl_distance"])
                pos["trail_stage"] = 1
                pos["trail_stop"] = pos["entry_price"]
                logger.info("TP1 HIT at %.1f, runner trailing from %.1f", pos["tp1_price"], pos["entry_price"])

        else:
            # Post-TP1: runner (1 contract) with trailing stop
            trail = pos["trailing"]
            trail.update(close, atr, st_line, st_bullish)
            pos["trail_stage"] = trail.stage
            pos["trail_stop"] = trail.trail_stop

            if trail.is_stopped(low):
                return self._exit(
                    exit_price=trail.trail_stop,
                    exit_reason=f"TRAIL_S{trail.stage}",
                    timestamp=signal_data["timestamp"],
                )

        return None

    def _exit(self, exit_price: float, exit_reason: str, timestamp: str) -> dict:
        """Close position and record trade."""
        pos = self.position

        if pos["tp1_hit"]:
            pnl_tp1 = pos["pnl_tp1"]
            pnl_runner = (exit_price - pos["entry_price"]) * POINT_VALUE
            # TP1 hit cost model: 6 half-fills comm + 4 slippage fills
            half_comm = COMMISSION_PER_CONTRACT / 2
            costs = 6 * half_comm + 4 * SLIPPAGE_COST
        else:
            pnl_tp1 = 0.0
            pnl_runner = (exit_price - pos["entry_price"]) * POINT_VALUE * NUM_CONTRACTS
            # No TP1 cost model: 4 half-fills comm + 2 slippage fills
            half_comm = COMMISSION_PER_CONTRACT / 2
            costs = 4 * half_comm + 2 * SLIPPAGE_COST

        total_pnl = pnl_tp1 + pnl_runner - costs
        self.capital += total_pnl

        trade = {
            "trade_num": self.trade_count,
            "entry_time": pos["entry_time"],
            "exit_time": timestamp,
            "entry_price": round(pos["entry_price"], 2),
            "exit_price": round(exit_price, 2),
            "entry_score": round(pos["entry_score"], 2),
            "entry_session": pos["entry_session"],
            "sl_price": round(pos["sl_price"], 2),
            "sl_distance": round(pos["sl_distance"], 2),
            "tp1_price": round(pos["tp1_price"], 2),
            "tp1_distance": round(pos["sl_distance"] * RR_RATIO_TP1, 2),
            "tp1_hit": pos["tp1_hit"],
            "trail_stage": pos.get("trail_stage", 0),
            "exit_reason": exit_reason,
            "atr_at_entry": round(pos.get("atr_at_entry", 0), 2),
            "atr_percentile": round(pos.get("atr_percentile", 0), 2),
            "pnl_tp1": round(pnl_tp1, 2),
            "pnl_runner": round(pnl_runner, 2),
            "costs": round(costs, 2),
            "total_pnl": round(total_pnl, 2),
            "capital_after": round(self.capital, 2),
        }
        self.trade_history.append(trade)
        self.position = None

        logger.info(
            "EXIT %s: price=%.1f pnl=$%.0f capital=$%.0f",
            exit_reason, exit_price, total_pnl, self.capital,
        )

        return trade

    def get_position_dict(self) -> dict | None:
        """Get current position as a serializable dict."""
        if self.position is None:
            return None
        pos = self.position.copy()
        if pos.get("trailing"):
            pos["trailing"] = pos["trailing"].to_dict()
        return pos

    def get_stats(self) -> dict:
        """Calculate performance stats from trade history."""
        trades = self.trade_history
        if not trades:
            return {
                "total_trades": 0, "win_rate": 0, "pf": 0,
                "total_pnl": 0, "avg_pnl": 0, "avg_win": 0, "avg_loss": 0,
                "max_dd": 0, "sharpe": 0, "current_streak": 0,
                "capital": self.capital,
            }

        wins = [t for t in trades if t["total_pnl"] > 0]
        losses = [t for t in trades if t["total_pnl"] <= 0]
        total_wins = sum(t["total_pnl"] for t in wins)
        total_losses = abs(sum(t["total_pnl"] for t in losses))
        total_pnl = sum(t["total_pnl"] for t in trades)
        pnls = [t["total_pnl"] for t in trades]

        # Max drawdown
        equity = []
        running = self.initial_capital
        peak = running
        max_dd = 0
        for t in trades:
            running += t["total_pnl"]
            equity.append(running)
            peak = max(peak, running)
            dd = peak - running
            max_dd = max(max_dd, dd)

        # Sharpe (annualized, assuming ~252 trading days, ~4 trades/week)
        import statistics
        sharpe = 0.0
        if len(pnls) > 1:
            mean_pnl = statistics.mean(pnls)
            std_pnl = statistics.stdev(pnls)
            if std_pnl > 0:
                sharpe = (mean_pnl / std_pnl) * (252 ** 0.5)

        # Current streak
        streak = 0
        for t in reversed(trades):
            if streak == 0:
                streak = 1 if t["total_pnl"] > 0 else -1
            elif streak > 0 and t["total_pnl"] > 0:
                streak += 1
            elif streak < 0 and t["total_pnl"] <= 0:
                streak -= 1
            else:
                break

        return {
            "total_trades": len(trades),
            "win_rate": len(wins) / len(trades) * 100 if trades else 0,
            "pf": total_wins / total_losses if total_losses > 0 else float("inf"),
            "total_pnl": round(total_pnl, 2),
            "avg_pnl": round(total_pnl / len(trades), 2) if trades else 0,
            "avg_win": round(total_wins / len(wins), 2) if wins else 0,
            "avg_loss": round(-total_losses / len(losses), 2) if losses else 0,
            "max_dd": round(max_dd, 2),
            "sharpe": round(sharpe, 2),
            "current_streak": streak,
            "capital": round(self.capital, 2),
        }

    def get_today_stats(self) -> dict:
        """Get stats for today's trades only."""
        today = datetime.now().strftime("%Y-%m-%d")
        today_trades = [
            t for t in self.trade_history
            if str(t.get("exit_time", "")).startswith(today)
        ]
        today_pnl = sum(t["total_pnl"] for t in today_trades)
        return {
            "today_pnl": round(today_pnl, 2),
            "today_trades": len(today_trades),
        }
