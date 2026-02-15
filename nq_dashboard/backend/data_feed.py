"""Data feed — fetches NQ futures 15m candles from Yahoo Finance."""

import logging
from datetime import datetime

import pandas as pd
import yfinance as yf

from dashboard_config import TICKER, INTERVAL, FETCH_PERIOD, UPDATE_PERIOD

logger = logging.getLogger(__name__)


class DataFeed:
    def __init__(self):
        self.df = pd.DataFrame()
        self.last_update = None
        self.ticker = TICKER

    async def initialize(self):
        """Fetch initial 60 days of 15m data for indicator warm-up."""
        logger.info("Fetching initial data for %s...", self.ticker)
        nq = yf.Ticker(self.ticker)
        self.df = nq.history(period=FETCH_PERIOD, interval=INTERVAL)

        if self.df.empty:
            logger.warning("No data returned from yfinance for %s", self.ticker)
            return

        # Remove timezone for consistency
        if self.df.index.tz is not None:
            self.df.index = self.df.index.tz_localize(None)

        # Drop yfinance extra columns if present
        for col in ["Dividends", "Stock Splits"]:
            if col in self.df.columns:
                self.df.drop(columns=[col], inplace=True)

        self.last_update = self.df.index[-1]
        logger.info(
            "Loaded %d bars, last: %s", len(self.df), self.last_update
        )

    async def update(self) -> int:
        """Fetch latest bars since last update. Returns count of new bars."""
        try:
            nq = yf.Ticker(self.ticker)
            new_data = nq.history(period=UPDATE_PERIOD, interval=INTERVAL)
        except Exception as e:
            logger.error("Failed to fetch update: %s", e)
            return 0

        if new_data.empty:
            return 0

        if new_data.index.tz is not None:
            new_data.index = new_data.index.tz_localize(None)

        for col in ["Dividends", "Stock Splits"]:
            if col in new_data.columns:
                new_data.drop(columns=[col], inplace=True)

        # Append only new bars
        new_bars = new_data[new_data.index > self.last_update]
        count = len(new_bars)

        if count > 0:
            self.df = pd.concat([self.df, new_bars])
            self.df = self.df[~self.df.index.duplicated(keep="last")]
            self.last_update = self.df.index[-1]

            # Keep last 60 days max
            cutoff = self.last_update - pd.Timedelta(days=60)
            self.df = self.df[self.df.index >= cutoff]

            logger.info("Added %d new bars. Total: %d", count, len(self.df))

        return count

    def get_dataframe(self) -> pd.DataFrame:
        return self.df.copy()

    def get_latest_bar(self) -> dict | None:
        if self.df.empty:
            return None
        bar = self.df.iloc[-1]
        return {
            "timestamp": str(bar.name),
            "Open": float(bar["Open"]),
            "High": float(bar["High"]),
            "Low": float(bar["Low"]),
            "Close": float(bar["Close"]),
            "Volume": int(bar["Volume"]),
        }
