"""SQLite database for persistent storage of trades, state, and signal log."""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path

from dashboard_config import DB_PATH

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str = DB_PATH):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        logger.info("Database initialized at %s", db_path)

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_num INTEGER,
                entry_time TEXT NOT NULL,
                exit_time TEXT,
                entry_price REAL NOT NULL,
                exit_price REAL,
                entry_score REAL,
                entry_session TEXT,
                sl_price REAL,
                sl_distance REAL,
                tp1_price REAL,
                tp1_distance REAL,
                tp1_hit INTEGER DEFAULT 0,
                trail_stage INTEGER DEFAULT 0,
                exit_reason TEXT,
                atr_at_entry REAL,
                atr_percentile REAL,
                pnl_tp1 REAL DEFAULT 0,
                pnl_runner REAL DEFAULT 0,
                costs REAL DEFAULT 0,
                total_pnl REAL DEFAULT 0,
                capital_after REAL,
                status TEXT DEFAULT 'OPEN'
            );

            CREATE TABLE IF NOT EXISTS state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS signals_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                close_price REAL,
                long_score REAL,
                long_threshold REAL,
                atr REAL,
                atr_percentile REAL,
                rsi REAL,
                adx REAL,
                session TEXT,
                signal_triggered INTEGER DEFAULT 0,
                notes TEXT
            );
        """)
        self.conn.commit()

    # --- Trades ---

    def insert_trade(self, trade: dict) -> int:
        cursor = self.conn.execute("""
            INSERT INTO trades (trade_num, entry_time, entry_price, entry_score,
                entry_session, sl_price, sl_distance, tp1_price, tp1_distance,
                atr_at_entry, atr_percentile, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN')
        """, (
            trade.get("trade_num"),
            trade.get("entry_time"),
            trade.get("entry_price"),
            trade.get("entry_score"),
            trade.get("entry_session"),
            trade.get("sl_price"),
            trade.get("sl_distance"),
            trade.get("tp1_price"),
            trade.get("tp1_distance"),
            trade.get("atr_at_entry"),
            trade.get("atr_percentile"),
        ))
        self.conn.commit()
        return cursor.lastrowid

    def close_trade(self, trade_id: int, exit_data: dict):
        self.conn.execute("""
            UPDATE trades SET
                exit_time = ?, exit_price = ?, tp1_hit = ?, trail_stage = ?,
                exit_reason = ?, pnl_tp1 = ?, pnl_runner = ?, costs = ?,
                total_pnl = ?, capital_after = ?, status = 'CLOSED'
            WHERE id = ?
        """, (
            exit_data.get("exit_time"),
            exit_data.get("exit_price"),
            1 if exit_data.get("tp1_hit") else 0,
            exit_data.get("trail_stage", 0),
            exit_data.get("exit_reason"),
            exit_data.get("pnl_tp1", 0),
            exit_data.get("pnl_runner", 0),
            exit_data.get("costs", 0),
            exit_data.get("total_pnl", 0),
            exit_data.get("capital_after"),
            trade_id,
        ))
        self.conn.commit()

    def get_open_trade(self) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM trades WHERE status = 'OPEN' LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def get_all_trades(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM trades WHERE status = 'CLOSED' ORDER BY exit_time DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_trade_count(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM trades WHERE status = 'CLOSED'"
        ).fetchone()[0]

    # --- State ---

    def set_state(self, key: str, value: str):
        self.conn.execute(
            "INSERT OR REPLACE INTO state (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, datetime.now().isoformat()),
        )
        self.conn.commit()

    def get_state(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM state WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else default

    # --- Signal Log ---

    def log_signal(self, signal_data: dict):
        self.conn.execute("""
            INSERT INTO signals_log (timestamp, close_price, long_score,
                long_threshold, atr, atr_percentile, rsi, adx, session,
                signal_triggered, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            signal_data.get("timestamp"),
            signal_data.get("close"),
            signal_data.get("long_score"),
            signal_data.get("long_threshold"),
            signal_data.get("atr"),
            signal_data.get("atr_percentile"),
            signal_data.get("rsi"),
            signal_data.get("adx"),
            signal_data.get("session"),
            1 if signal_data.get("signal") else 0,
            signal_data.get("notes", ""),
        ))
        self.conn.commit()

    def get_recent_signals(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM signals_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self.conn.close()
