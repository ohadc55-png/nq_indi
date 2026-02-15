"""Data loading — historical CSV/SQLite; future: live IB feed.

Provides a clean interface for loading 15-minute NQ OHLCV data.
In backtest mode, reads from the existing SQLite database (nq_data.db).
The same interface will later accept a live IB feed.
"""

import logging
import sqlite3

import pandas as pd

from config import DB_PATH, TIMEZONE

logger = logging.getLogger(__name__)


def load_ohlcv(db_path: str, table: str) -> pd.DataFrame:
    """Load OHLCV data from SQLite *table*. Returns DataFrame with DatetimeIndex."""
    con = sqlite3.connect(db_path)
    df = pd.read_sql(f"SELECT * FROM {table} ORDER BY datetime", con)
    con.close()
    if df.empty:
        return df
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.set_index("datetime")
    df = df.drop(columns=["fetched_at"], errors="ignore")
    df.columns = [c.capitalize() for c in df.columns]
    return df


def load_15m_data(db_path: str = DB_PATH) -> pd.DataFrame:
    """Load 15-minute NQ data from the best available source.

    Priority: 1m resample → existing 15m table.
    Matches the Pine Script base timeframe (15 min).
    """
    # Try 1: Resample existing 1m data (gives most history)
    try:
        df_1m = load_ohlcv(db_path, "ohlcv_1m")
        if not df_1m.empty and len(df_1m) > 10_000:
            logger.info("Found %s 1m bars in SQLite. Resampling to 15m...", f"{len(df_1m):,}")
            agg = {
                "Open": "first",
                "High": "max",
                "Low": "min",
                "Close": "last",
                "Volume": "sum",
            }
            df_15m = df_1m.resample("15min").agg(agg).dropna()
            logger.info(
                "Resampled to %s 15m bars (%s → %s)",
                f"{len(df_15m):,}", df_15m.index[0], df_15m.index[-1],
            )
            return df_15m
    except Exception:
        pass

    # Try 2: Existing 15m data
    try:
        df_15m = load_ohlcv(db_path, "ohlcv_15m")
        if not df_15m.empty:
            logger.info(
                "Found %s 15m bars in SQLite (%s → %s)",
                f"{len(df_15m):,}", df_15m.index[0], df_15m.index[-1],
            )
            return df_15m
    except Exception:
        pass

    raise ValueError(
        f"No 15m or 1m data found in {db_path}. "
        "Ensure the database has been populated first."
    )
