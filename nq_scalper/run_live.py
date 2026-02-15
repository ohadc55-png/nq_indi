"""(Future) Live trading runner with IB TWS connection.

This file is a STUB — it defines the structure for live trading
so that when IB integration is implemented, the same indicator,
scoring, and signal modules work identically.

indicators.py, scoring.py, signals.py, risk_manager.py, trailing.py
all work IDENTICALLY in backtest and live mode. Only the data source
and order execution change.
"""

import logging

logger = logging.getLogger(__name__)


class LiveRunner:
    """Live trading runner for IB TWS.

    Structure only — not implemented yet.
    """

    def __init__(self, ib_connection):
        # Data source: replaces SQLite/CSV with live IB feed
        # self.data_feed = IBLiveDataFeed(ib_connection)

        # These modules are IDENTICAL to backtest:
        # from indicators import compute_15m_indicators
        # from scoring import precompute_long_scores, ...
        # from signals import check_long_signal, CooldownTracker
        # from risk_manager import calc_entry, calc_costs
        # from trailing import TrailingStop

        # Order execution: new for live
        # self.order_manager = IBOrderManager(ib_connection)

        self.ib = ib_connection
        logger.info("LiveRunner initialized (stub)")

    def on_new_bar(self, bar):
        """Called every 15 minutes with new OHLCV data.

        1. Update indicators (append bar, recompute latest values)
        2. Calculate score
        3. Check for signal
        4. If signal: send alert / place order
        5. Manage open position (trailing stop, TP1, EOD close)
        """
        pass

    def start(self):
        """Start the live trading loop.

        1. Connect to IB TWS
        2. Subscribe to NQ 15m bars
        3. Load recent history for indicator warm-up
        4. Enter main loop: on_new_bar() every 15 min
        """
        raise NotImplementedError("IB connection not yet implemented")


if __name__ == "__main__":
    print("Live trading runner — not yet implemented.")
    print("Use run_backtest.py for backtesting.")
