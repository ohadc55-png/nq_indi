# NQ Scalper Project Memory

## Project Location
`c:\Ohad\ohad\אפליקציות\trading_indicator\nq_scalper\`

## Quick Reference
- **Strategy**: NQ Futures Long-Only Swing Scalper, 15-min bars, 2 contracts
- **Data**: 3.5M 1-min bars in SQLite (`nq_data.db`, 432MB), resampled to 236K 15-min bars (2016-2026)
- **Production config (B1)**: TP1=SLx1.5, SL=50pt, Risk=$1,000/contract
- **User language**: Hebrew

## B1 Config (Production)
- Max SL: 50 points ($1,000/contract)
- TP1 Ratio: SL x 1.5
- Wednesday/Thursday: score >= 9.0
- OOS Sharpe: 4.57, PF: 1.88, WR: 56.7%
- All years profitable (2016-2026): YES
- Walk-Forward consistency: PASS (5/6 windows)
- Ready for live: YES (HIGH confidence)

## Validated Decisions
- **SL 50pt > 40pt**: Trades get more room, fewer premature stops
- **Keep Wed/Thu >= 9.0 filter**: Removing adds $9K P&L but Sharpe drops, 2018 becomes losing year
- **B2 (SLx2.0) rejected**: Fails consistency (MaxDD grew 38% in OOS)
- **B2_WED rejected**: Higher P&L ($60K vs $46K OOS) but fails consistency, 2016+2018 losing years

## Architecture
See [nq_scalper_details.md](nq_scalper_details.md) for file-by-file breakdown.

## Key Files
- `config.py` -- all parameters (single source of truth)
- `scoring.py` -- signal score 0-10 + dynamic threshold + Layer 1 ATR
- `backtest_engine.py` -- bar-by-bar engine, trade dict with 20 fields
- `risk_manager.py` -- SL/TP1 calculation, cost model
- `trailing.py` -- 3-stage trailing (breakeven -> partial -> ATR trail)
- `signals.py` -- entry criteria (score, EMA slope, cooldown, DOW, session)
- `generate_reports.py` -- HTML+CSS dark-theme reports with embedded charts

## Output
- `output/reports/B1_report.html` -- full 10-year dark-theme report
- `output/reports/B1_full_trade_log.csv` -- 267 trades, 27 columns
- `output/b1_oos_trades.csv` -- 60 OOS trades (2024-2025)
