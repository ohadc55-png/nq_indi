"""Main backtest runner — NQ Swing Scalper V1 + Layer 1.

Usage:
    python run_backtest.py [--db PATH] [--no-charts]

This is the entry point for backtesting. It:
1. Loads 15m data from SQLite
2. Computes all indicators + MTF + patterns + scoring
3. Runs the bar-by-bar backtest engine
4. Exports trade log CSV
5. Generates performance report and charts
6. Compares results to validated V1+L1 benchmarks
"""

import argparse
import logging
import os
import sys
import io
import time

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Ensure the nq_scalper package is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DB_PATH, OUTPUT_DIR, WARM_UP_BARS
from data_feed import load_15m_data
from indicators import compute_15m_indicators
from mtf import build_mtf
from patterns import precompute_patterns
from scoring import precompute_all_scores
from backtest_engine import BacktestEngine
from trade_logger import export_trades_csv
from report import (
    analyze_results,
    print_summary,
    print_year_breakdown,
    print_score_buckets,
    print_dow_analysis,
    generate_charts,
    print_verification_table,
    print_before_after_comparison,
)


def setup_logging() -> None:
    """Configure logging to console and file."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(
                os.path.join(OUTPUT_DIR, "backtest.log"),
                mode="w",
                encoding="utf-8",
            ),
        ],
    )


def prepare_data(db_path: str) -> "pd.DataFrame":
    """Full data preparation pipeline: load → indicators → MTF → patterns → scoring."""
    import pandas as pd

    logger = logging.getLogger(__name__)

    # 1. Load raw 15m data
    logger.info("[1/5] Loading 15m data from %s...", db_path)
    df_15m = load_15m_data(db_path)
    if df_15m.empty:
        logger.error("No data available. Exiting.")
        sys.exit(1)
    logger.info(
        "Loaded %s raw 15m bars (%s to %s)",
        f"{len(df_15m):,}", df_15m.index[0], df_15m.index[-1],
    )

    # 2. Compute 15m indicators
    logger.info("[2/5] Computing 15m indicators...")
    df_15m = compute_15m_indicators(df_15m)

    # 3. Build MTF (resample + merge)
    logger.info("[3/5] Building multi-timeframe data...")
    df = build_mtf(df_15m)

    # 4. Precompute patterns
    logger.info("[4/5] Precomputing patterns...")
    df = precompute_patterns(df)

    # 5. Precompute scoring
    logger.info("[5/5] Computing scores and thresholds...")
    df = precompute_all_scores(df)

    # Trim warm-up bars
    df = df.iloc[WARM_UP_BARS:]
    logger.info(
        "Final dataset: %s bars (%s to %s)",
        f"{len(df):,}", df.index[0], df.index[-1],
    )

    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="NQ Swing Scalper Backtest")
    parser.add_argument("--db", default=DB_PATH, help="Path to SQLite database")
    parser.add_argument("--no-charts", action="store_true", help="Skip chart generation")
    args = parser.parse_args()

    setup_logging()
    logger = logging.getLogger(__name__)

    print("\n" + "=" * 60)
    print("  NQ SWING SCALPER — BACKTEST (V1 + Layer 1)")
    print("  LONG ONLY | 15min | 2-Contract Split")
    print("=" * 60)

    t_start = time.time()

    # Prepare data
    df = prepare_data(args.db)

    t_prep = time.time()
    logger.info("Data preparation took %.1f seconds", t_prep - t_start)

    # Run backtest
    engine = BacktestEngine(df)
    trades = engine.run()
    equity_curve = engine.equity_curve

    t_backtest = time.time()
    logger.info("Backtest execution took %.1f seconds", t_backtest - t_prep)

    if not trades:
        logger.warning("No trades generated. Check parameters and data.")
        return

    # Export trade log (fixed version)
    csv_path = export_trades_csv(trades, filename="trades_fixed.csv")

    # Analyze and report
    stats = analyze_results(trades, equity_curve)
    print_summary(stats)
    print_year_breakdown(trades)
    print_score_buckets(trades)
    print_dow_analysis(trades)
    print_verification_table(stats)
    print_before_after_comparison(stats, trades)

    # Generate charts (fixed versions)
    if not args.no_charts:
        logger.info("Generating charts...")
        generate_charts(trades, equity_curve, prefix="fixed_")

    t_end = time.time()
    print(f"\n  Total runtime: {t_end - t_start:.1f} seconds")
    print(f"  Trade log: {csv_path}")
    print(f"  Charts: {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
