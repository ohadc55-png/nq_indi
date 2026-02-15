"""Trade logging and CSV export."""

import logging
import os

import pandas as pd

from config import OUTPUT_DIR

logger = logging.getLogger(__name__)


def export_trades_csv(trades: list[dict], filename: str = "trades.csv") -> str:
    """Export trade log to CSV. Returns the file path."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, filename)
    df = pd.DataFrame(trades)
    df.to_csv(path, index=False)
    logger.info("Trade log exported to %s (%d trades)", path, len(trades))
    return path
