"""Scheduler — runs the trading loop every 15 minutes."""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)


class TradingScheduler:
    def __init__(self, data_feed, engine, paper_trader, alerts, database, broadcast_fn):
        self.scheduler = AsyncIOScheduler()
        self.data_feed = data_feed
        self.engine = engine
        self.paper_trader = paper_trader
        self.alerts = alerts
        self.db = database
        self.broadcast = broadcast_fn
        self._open_trade_id = None  # DB trade ID for current open position

    def start(self):
        # Run every 15 minutes during futures market hours
        self.scheduler.add_job(
            self.tick,
            "cron",
            day_of_week="mon,tue,wed,thu,fri,sun",
            minute="0,15,30,45",
            timezone="US/Eastern",
            id="main_tick",
            misfire_grace_time=120,
        )

        # Daily summary at 16:15 ET
        self.scheduler.add_job(
            self.send_daily_summary,
            "cron",
            day_of_week="mon-fri",
            hour=16,
            minute=15,
            timezone="US/Eastern",
            id="daily_summary",
            misfire_grace_time=300,
        )

        self.scheduler.start()
        logger.info("Scheduler started — ticking every 15 minutes")

    def stop(self):
        self.scheduler.shutdown(wait=False)

    async def tick(self):
        """Main loop — runs every 15 minutes."""
        try:
            # Recovery: if data feed is empty, re-initialize with full history
            if self.data_feed.get_dataframe().empty:
                logger.info("Data feed empty — attempting full re-initialize...")
                await self.data_feed.initialize()

            # 1. Fetch new data
            new_bars = await self.data_feed.update()
            logger.info("Tick: %d new bars fetched", new_bars)

            # 2. Run indicators
            df = self.data_feed.get_dataframe()
            signal_data = self.engine.process(df)

            if signal_data is None:
                logger.warning("No signal data produced")
                return

            # 3. Log signal
            self.db.log_signal(signal_data)

            # 4. Update open position (if any)
            if self.paper_trader.position is not None:
                exit_event = self.paper_trader.update_position(signal_data)
                if exit_event:
                    # Close trade in DB
                    if self._open_trade_id:
                        self.db.close_trade(self._open_trade_id, exit_event)
                        self._open_trade_id = None
                    # Send alert
                    await self.alerts.send_exit(exit_event)
                    # Update DB state
                    self.db.set_state("capital", str(self.paper_trader.capital))

            # 5. Check for new entry
            if self.paper_trader.check_entry(signal_data):
                entry = self.paper_trader.enter_position(signal_data)
                # Save to DB
                trade_data = {
                    "trade_num": self.paper_trader.trade_count,
                    "entry_time": entry["entry_time"],
                    "entry_price": entry["entry_price"],
                    "entry_score": entry["entry_score"],
                    "entry_session": entry["entry_session"],
                    "sl_price": entry["sl_price"],
                    "sl_distance": entry["sl_distance"],
                    "tp1_price": entry["tp1_price"],
                    "tp1_distance": entry["tp1_distance"],
                    "atr_at_entry": entry.get("atr_at_entry", 0),
                    "atr_percentile": entry.get("atr_percentile", 0),
                }
                self._open_trade_id = self.db.insert_trade(trade_data)
                # Send alert with SL/TP info
                alert_data = {**signal_data, **entry}
                await self.alerts.send_signal(alert_data)

            # 6. Broadcast to WebSocket clients
            await self.broadcast()

        except Exception as e:
            logger.error("Tick failed: %s", e, exc_info=True)

    async def send_daily_summary(self):
        """Send daily performance summary email."""
        try:
            stats = self.paper_trader.get_stats()
            today_stats = self.paper_trader.get_today_stats()
            stats.update(today_stats)
            await self.alerts.send_daily_summary(stats)
        except Exception as e:
            logger.error("Daily summary failed: %s", e)

    async def run_initial_tick(self):
        """Run one tick immediately on startup (for initial state)."""
        await self.tick()
