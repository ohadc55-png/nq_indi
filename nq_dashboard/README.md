# NQ Swing Scalper — Live Dashboard

Real-time paper trading dashboard for the NQ Swing Scalper (B1 config).

## Quick Start

### Backend
```bash
cd backend
pip install -r ../requirements.txt
python app.py
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

## Setup

1. Copy `.env.example` to `.env`
2. (Optional) Add your Resend API key for email alerts
3. Start backend, then frontend

## Architecture

- **Backend**: FastAPI + WebSocket, yfinance data, imports nq_scalper indicator logic
- **Frontend**: React + TradingView Lightweight Charts
- **Database**: SQLite (trades, state, signal log)
- **Alerts**: Resend API (email)
- **Scheduler**: APScheduler (15-min ticks during market hours)
