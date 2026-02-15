"""Dashboard configuration — loads from .env, references nq_scalper config."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Paths
BASE_DIR = Path(__file__).resolve().parent
NQ_SCALPER_DIR = BASE_DIR.parent.parent / "nq_scalper"
DB_PATH = str(BASE_DIR / "data" / "dashboard.db")

# Email (Resend API)
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
EMAIL_RECIPIENT = os.getenv("EMAIL_RECIPIENT", "ohadc55@gmail.com")

# Data
TICKER = "NQ=F"
INTERVAL = "15m"
FETCH_PERIOD = "60d"
UPDATE_PERIOD = "1d"

# Paper trading
INITIAL_CAPITAL = 100_000.0

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
