"""FastAPI server — REST + WebSocket for the NQ Scalper dashboard."""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from dashboard_config import HOST, PORT, INITIAL_CAPITAL
from data_feed import DataFeed
from indicator_engine import IndicatorEngine
from paper_trader import PaperTrader
from database import Database
from alerts import EmailAlert
from scheduler import TradingScheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Global state
data_feed = DataFeed()
engine = IndicatorEngine()
paper_trader = PaperTrader(initial_capital=INITIAL_CAPITAL)
db = Database()
alerts = EmailAlert()
ws_clients: set[WebSocket] = set()
trading_scheduler: TradingScheduler | None = None
last_signal_data: dict | None = None


async def broadcast_state():
    """Push current state to all connected WebSocket clients."""
    if not ws_clients:
        return

    state = get_current_state()
    dead = set()
    for ws in ws_clients:
        try:
            await ws.send_json(state)
        except Exception:
            dead.add(ws)
    ws_clients -= dead


def get_current_state() -> dict:
    """Build current state snapshot for WebSocket push."""
    global last_signal_data
    return {
        "type": "state_update",
        "timestamp": datetime.now().isoformat(),
        "signal": last_signal_data,
        "position": paper_trader.get_position_dict(),
        "stats": paper_trader.get_stats(),
        "capital": paper_trader.capital,
        "last_bar": data_feed.get_latest_bar(),
        "trade_count": paper_trader.trade_count,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown."""
    global trading_scheduler, last_signal_data

    logger.info("Starting NQ Dashboard...")

    # Restore capital from DB
    saved_capital = db.get_state("capital")
    if saved_capital:
        paper_trader.capital = float(saved_capital)
        logger.info("Restored capital: $%.0f", paper_trader.capital)

    # Load trade history from DB
    closed_trades = db.get_all_trades()
    paper_trader.trade_history = closed_trades
    paper_trader.trade_count = len(closed_trades)
    logger.info("Restored %d trades from database", len(closed_trades))

    # Initialize data feed
    await data_feed.initialize()

    # Run initial indicator pass
    df = data_feed.get_dataframe()
    if not df.empty:
        last_signal_data = engine.process(df)
        if last_signal_data:
            logger.info(
                "Initial signal: score=%.1f thresh=%.1f signal=%s",
                last_signal_data.get("long_score", 0),
                last_signal_data.get("long_threshold", 0),
                last_signal_data.get("signal", False),
            )

    # Start scheduler
    trading_scheduler = TradingScheduler(
        data_feed=data_feed,
        engine=engine,
        paper_trader=paper_trader,
        alerts=alerts,
        database=db,
        broadcast_fn=broadcast_state,
    )
    trading_scheduler.start()

    yield

    # Shutdown
    logger.info("Shutting down...")
    if trading_scheduler:
        trading_scheduler.stop()
    db.set_state("capital", str(paper_trader.capital))
    db.close()


app = FastAPI(title="NQ Swing Scalper Dashboard", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── WebSocket ───────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    ws_clients.add(ws)
    logger.info("WebSocket client connected (%d total)", len(ws_clients))
    try:
        # Send initial state
        await ws.send_json(get_current_state())
        # Keep alive and push updates
        while True:
            # Wait for pings or client messages
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=10)
            except asyncio.TimeoutError:
                # Push state periodically
                await ws.send_json(get_current_state())
    except WebSocketDisconnect:
        pass
    finally:
        ws_clients.discard(ws)
        logger.info("WebSocket client disconnected (%d remaining)", len(ws_clients))


# ─── REST Endpoints ──────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now().isoformat()}


@app.get("/api/candles")
async def get_candles(limit: int = 200):
    """Return last N candles for chart initialization."""
    df = data_feed.get_dataframe()
    if df.empty:
        return []

    # Run indicators to get enriched data
    enriched = engine.process_full(df)
    if enriched is None or enriched.empty:
        # Fallback: raw candles
        df_tail = df.tail(limit)
        candles = []
        for ts, row in df_tail.iterrows():
            candles.append({
                "time": int(ts.timestamp()),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            })
        return candles

    df_tail = enriched.tail(limit)
    candles = []
    for ts, row in df_tail.iterrows():
        candles.append({
            "time": int(ts.timestamp()),
            "open": round(float(row["Open"]), 2),
            "high": round(float(row["High"]), 2),
            "low": round(float(row["Low"]), 2),
            "close": round(float(row["Close"]), 2),
            "volume": int(row["Volume"]),
            "ema50": round(float(row.get("ema50", 0)), 2) if not _is_nan(row.get("ema50")) else None,
            "ema200": round(float(row.get("ema200", 0)), 2) if not _is_nan(row.get("ema200")) else None,
            "supertrend": round(float(row.get("st_line", 0)), 2) if not _is_nan(row.get("st_line")) else None,
            "st_bullish": bool(row.get("st_bullish", False)),
            "vwap": round(float(row.get("vwap", 0)), 2) if not _is_nan(row.get("vwap")) else None,
        })
    return candles


@app.get("/api/trades")
async def get_trades():
    """Return trade history from paper trader."""
    return paper_trader.trade_history


@app.get("/api/stats")
async def get_stats():
    """Return current performance stats."""
    stats = paper_trader.get_stats()
    today = paper_trader.get_today_stats()
    stats.update(today)
    return stats


@app.get("/api/position")
async def get_position():
    """Return current open position or null."""
    return paper_trader.get_position_dict()


@app.get("/api/signal")
async def get_signal():
    """Return latest signal data."""
    return last_signal_data


@app.get("/api/signals-log")
async def get_signals_log(limit: int = 50):
    """Return recent signal log entries."""
    return db.get_recent_signals(limit)


def _is_nan(val) -> bool:
    if val is None:
        return True
    try:
        import math
        return math.isnan(float(val))
    except (ValueError, TypeError):
        return True


# ─── Reports Static Files ────────────────────────────────────

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"

if REPORTS_DIR.is_dir():
    app.mount("/reports", StaticFiles(directory=str(REPORTS_DIR), html=True), name="reports")


# ─── Frontend Static Files ──────────────────────────────────

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if FRONTEND_DIR.is_dir():
    @app.get("/")
    async def serve_root():
        return FileResponse(FRONTEND_DIR / "index.html")

    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=HOST, port=PORT, reload=True)
