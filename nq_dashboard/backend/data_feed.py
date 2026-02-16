"""Data feed — fetches NQ futures candles from Yahoo Finance v8 API.

Uses the Yahoo Finance chart endpoint directly (no yfinance library)
and supplements with live-quote synthetic bars when candle data is stale
(e.g. during holiday abbreviated sessions).
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

import pandas as pd
import requests

from dashboard_config import TICKER, INTERVAL, FETCH_PERIOD, UPDATE_PERIOD

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# Yahoo v8 "range" values
_PERIOD_TO_RANGE = {
    "1d": "1d",
    "2d": "2d",
    "5d": "5d",
    "7d": "5d",
    "1mo": "1mo",
    "30d": "1mo",
    "60d": "60d",
    "3mo": "3mo",
    "90d": "3mo",
}

# Interval minutes for synthetic-bar alignment
_INTERVAL_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
}


# ── Low-level fetchers ───────────────────────────────────────

def _v8_fetch(symbol: str, period: str, interval: str) -> tuple[pd.DataFrame, dict]:
    """Fetch candle data + meta from Yahoo v8 chart API with retry.

    Returns (DataFrame, meta_dict).  meta_dict contains the live quote
    fields ``regularMarketPrice`` and ``regularMarketTime``.
    """
    range_str = _PERIOD_TO_RANGE.get(period, period)
    url = f"{YAHOO_CHART_URL}/{symbol}"
    params = {
        "range": range_str,
        "interval": interval,
        "includePrePost": "true",
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=30)
            r.raise_for_status()
            data = r.json()

            results = data.get("chart", {}).get("result")
            if not results:
                logger.warning(
                    "Yahoo v8 returned no result (attempt %d/%d)", attempt, MAX_RETRIES
                )
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
                continue

            result = results[0]
            meta = result.get("meta", {})
            timestamps = result.get("timestamp")
            if not timestamps:
                logger.warning(
                    "Yahoo v8 returned no timestamps (attempt %d/%d)",
                    attempt, MAX_RETRIES,
                )
                return pd.DataFrame(), meta

            quote = result.get("indicators", {}).get("quote", [{}])[0]

            # Build DataFrame — timestamps are UTC epoch seconds.
            index = pd.to_datetime(timestamps, unit="s")
            df = pd.DataFrame(
                {
                    "Open": quote.get("open"),
                    "High": quote.get("high"),
                    "Low": quote.get("low"),
                    "Close": quote.get("close"),
                    "Volume": quote.get("volume"),
                },
                index=index,
            )
            df.dropna(subset=["Close"], inplace=True)
            df["Volume"] = df["Volume"].fillna(0).astype(int)

            logger.info(
                "Fetched %d bars via Yahoo v8 (attempt %d)", len(df), attempt
            )
            return df, meta

        except Exception as e:
            logger.warning(
                "Yahoo v8 failed (attempt %d/%d): %s", attempt, MAX_RETRIES, e
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

    logger.error("All Yahoo v8 fetch attempts exhausted for %s", symbol)
    return pd.DataFrame(), {}


def _fetch_candles(symbol: str, period: str, interval: str) -> pd.DataFrame:
    """Convenience wrapper — returns only the DataFrame."""
    df, _ = _v8_fetch(symbol, period, interval)
    return df


def _get_live_quote(symbol: str) -> dict | None:
    """Return ``{price, time}`` from Yahoo v8 meta (real-time quote)."""
    try:
        url = f"{YAHOO_CHART_URL}/{symbol}"
        params = {"range": "1d", "interval": "1d"}
        r = requests.get(url, params=params, headers=HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
        results = data.get("chart", {}).get("result")
        if not results:
            return None
        meta = results[0].get("meta", {})
        price = meta.get("regularMarketPrice")
        mkt_time = meta.get("regularMarketTime")
        if price is None or mkt_time is None:
            return None
        return {"price": float(price), "time": int(mkt_time)}
    except Exception as e:
        logger.warning("Live quote fetch failed: %s", e)
        return None


def fetch_5m_candles(symbol: str) -> pd.DataFrame:
    """Fetch 5-minute candles (max 5 trading days from Yahoo)."""
    return _fetch_candles(symbol, "5d", "5m")


# ── DataFeed class ────────────────────────────────────────────

class DataFeed:
    def __init__(self):
        self.df = pd.DataFrame()
        self.last_update = None
        self.ticker = TICKER

    async def initialize(self):
        """Fetch initial 60 days of 15m data for indicator warm-up."""
        logger.info("Fetching initial data for %s ...", self.ticker)

        loop = asyncio.get_event_loop()
        self.df = await loop.run_in_executor(
            None, _fetch_candles, self.ticker, FETCH_PERIOD, INTERVAL
        )

        if self.df.empty:
            logger.error(
                "CRITICAL: No data returned for %s. "
                "Dashboard will show no data until next successful fetch.",
                self.ticker,
            )
            return

        self.last_update = self.df.index[-1]
        logger.info("Loaded %d bars, last: %s", len(self.df), self.last_update)

    async def update(self) -> int:
        """Fetch latest bars since last update.  Returns count of new bars."""
        try:
            loop = asyncio.get_event_loop()
            new_data = await loop.run_in_executor(
                None, _fetch_candles, self.ticker, UPDATE_PERIOD, INTERVAL
            )
        except Exception as e:
            logger.error("Failed to fetch update: %s", e)
            return 0

        if new_data.empty:
            logger.warning("Update returned empty candle data — trying live quote")
            return await self._try_synthetic_bar()

        # If we had no data before, use the full fetch.
        if self.df.empty:
            self.df = new_data
            self.last_update = self.df.index[-1]
            logger.info("Recovered from empty state: loaded %d bars", len(self.df))
            return len(self.df)

        # Merge: concat + deduplicate.  Using keep="last" ensures that
        # real candles overwrite earlier synthetic bars at the same time.
        before = len(self.df)
        combined = pd.concat([self.df, new_data])
        combined = combined[~combined.index.duplicated(keep="last")]
        combined.sort_index(inplace=True)
        self.df = combined
        self.last_update = self.df.index[-1]

        # Keep last 60 days.
        cutoff = self.last_update - pd.Timedelta(days=60)
        self.df = self.df[self.df.index >= cutoff]

        added = len(self.df) - before
        if added > 0:
            logger.info("Added %d new bars. Total: %d", added, len(self.df))
        else:
            # Candle API returned data but nothing new — check live quote.
            added = await self._try_synthetic_bar()

        return max(added, 0)

    # ── Synthetic bar from live quote ─────────────────────────

    async def _try_synthetic_bar(self) -> int:
        """Create a synthetic candle from the Yahoo real-time quote.

        This covers holiday / abbreviated sessions where Yahoo returns a
        live ``regularMarketPrice`` but no new intraday candles.
        """
        if self.df.empty:
            return 0

        try:
            loop = asyncio.get_event_loop()
            quote = await loop.run_in_executor(
                None, _get_live_quote, self.ticker
            )
        except Exception:
            return 0

        if not quote:
            return 0

        # Convert Unix epoch → naive-UTC datetime (matching candle index).
        live_dt = datetime.fromtimestamp(quote["time"], tz=timezone.utc).replace(
            tzinfo=None
        )

        interval_min = _INTERVAL_MINUTES.get(INTERVAL, 15)
        gap_minutes = (live_dt - self.last_update).total_seconds() / 60

        if gap_minutes < interval_min:
            return 0  # quote is within the current candle window

        # Align to the interval grid (floor to nearest interval).
        floored_min = live_dt.minute - (live_dt.minute % interval_min)
        bar_time = live_dt.replace(minute=floored_min, second=0, microsecond=0)

        if bar_time <= self.last_update:
            return 0  # already covered

        price = quote["price"]
        synthetic = pd.DataFrame(
            {
                "Open": [price],
                "High": [price],
                "Low": [price],
                "Close": [price],
                "Volume": [0],
            },
            index=pd.DatetimeIndex([bar_time]),
        )

        self.df = pd.concat([self.df, synthetic])
        self.df = self.df[~self.df.index.duplicated(keep="last")]
        self.df.sort_index(inplace=True)
        self.last_update = bar_time

        # Trim.
        cutoff = self.last_update - pd.Timedelta(days=60)
        self.df = self.df[self.df.index >= cutoff]

        logger.info(
            "Synthetic bar at %s  price=%.2f (live quote)", bar_time, price
        )
        return 1

    # ── Accessors ─────────────────────────────────────────────

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
