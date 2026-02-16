"""Data feed — fetches NQ futures 15m candles from Yahoo Finance."""

import asyncio
import logging
import time

import pandas as pd
import yfinance as yf

from dashboard_config import TICKER, INTERVAL, FETCH_PERIOD, UPDATE_PERIOD

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds


def _fetch_with_retry(ticker: str, period: str, interval: str) -> pd.DataFrame:
    """Fetch data from yfinance with retry logic and fallback methods."""

    # Method 1: Ticker.history() (default session, let yfinance handle auth)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            nq = yf.Ticker(ticker)
            df = nq.history(period=period, interval=interval)
            if not df.empty:
                logger.info(
                    "Fetched %d bars via Ticker.history() (attempt %d)",
                    len(df), attempt,
                )
                return df
            logger.warning(
                "Ticker.history() returned empty (attempt %d/%d)",
                attempt, MAX_RETRIES,
            )
        except Exception as e:
            logger.warning(
                "Ticker.history() failed (attempt %d/%d): %s",
                attempt, MAX_RETRIES, e,
            )
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY)

    # Method 2: yf.download() fallback
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            df = yf.download(
                ticker,
                period=period,
                interval=interval,
                progress=False,
                timeout=30,
            )
            if not df.empty:
                logger.info(
                    "Fetched %d bars via yf.download() (attempt %d)",
                    len(df), attempt,
                )
                return df
            logger.warning(
                "yf.download() returned empty (attempt %d/%d)",
                attempt, MAX_RETRIES,
            )
        except Exception as e:
            logger.warning(
                "yf.download() failed (attempt %d/%d): %s",
                attempt, MAX_RETRIES, e,
            )
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY)

    logger.error("All fetch methods exhausted for %s", ticker)
    return pd.DataFrame()


def _clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Remove timezone and extra columns from yfinance data."""
    if df.empty:
        return df

    # Remove timezone for consistency
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    # Drop yfinance extra columns if present
    for col in ["Dividends", "Stock Splits", "Capital Gains"]:
        if col in df.columns:
            df.drop(columns=[col], inplace=True)

    # yf.download() with newer versions may return MultiIndex columns
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # Ensure standard column names (yf.download may reorder)
    expected = ["Open", "High", "Low", "Close", "Volume"]
    for col in expected:
        if col not in df.columns:
            logger.warning("Missing expected column: %s", col)

    return df


class DataFeed:
    def __init__(self):
        self.df = pd.DataFrame()
        self.last_update = None
        self.ticker = TICKER

    async def initialize(self):
        """Fetch initial 60 days of 15m data for indicator warm-up."""
        logger.info("Fetching initial data for %s...", self.ticker)

        # Run blocking fetch in thread pool to not block the event loop
        loop = asyncio.get_event_loop()
        self.df = await loop.run_in_executor(
            None, _fetch_with_retry, self.ticker, FETCH_PERIOD, INTERVAL
        )

        self.df = _clean_dataframe(self.df)

        if self.df.empty:
            logger.error(
                "CRITICAL: No data returned from yfinance for %s. "
                "Dashboard will show no data until next successful fetch.",
                self.ticker,
            )
            return

        self.last_update = self.df.index[-1]
        logger.info(
            "Loaded %d bars, last: %s", len(self.df), self.last_update
        )

    async def update(self) -> int:
        """Fetch latest bars since last update. Returns count of new bars."""
        try:
            loop = asyncio.get_event_loop()
            new_data = await loop.run_in_executor(
                None, _fetch_with_retry, self.ticker, UPDATE_PERIOD, INTERVAL
            )
        except Exception as e:
            logger.error("Failed to fetch update: %s", e)
            return 0

        new_data = _clean_dataframe(new_data)

        if new_data.empty:
            logger.warning("Update returned empty data")
            return 0

        # If we had no data before, use the full update
        if self.df.empty:
            self.df = new_data
            self.last_update = self.df.index[-1]
            logger.info(
                "Recovered from empty state: loaded %d bars", len(self.df)
            )
            return len(self.df)

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
