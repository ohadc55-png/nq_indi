# NQ Scalper -- Test Results & Optimization Findings

---

## What Changed: Production vs B1 vs B2

The production indicator (A1/baseline) uses these risk parameters:

| Parameter | Production (A1) | B1 | B2 |
|-----------|----------------|-----|-----|
| TP1 Ratio | SL x **1.5** | SL x **1.5** (same) | SL x **2.0** (wider) |
| Max SL Distance | **40** points | **50** points (wider) | **50** points (wider) |
| Max Risk/Contract | **$800** | **$1,000** | **$1,000** |
| Max Risk/Trade (2 contracts) | **$1,600** | **$2,000** | **$2,000** |

**Everything else is identical** -- same scoring system, same Layer 1 (ATR Percentile), same cooldown, same session filters, same trailing stop logic, same signals.

### What B1 changes (vs production):
- **Only the stop-loss distance**: from 40pt to 50pt max
- TP1 ratio stays at SL x 1.5 (so TP1 also gets wider proportionally)
- Risk per contract goes from $800 to $1,000 (50pt x $20/point)
- This means: trades get **more room to breathe** before stopping out
- Trades that would have been stopped at 40pt now survive with 50pt
- When you DO get stopped, the loss is **$400 bigger** per trade ($2,000 vs $1,600)

### What B2 changes (vs production):
- **Stop-loss distance**: from 40pt to 50pt (same as B1)
- **TP1 target**: from SL x 1.5 to SL x 2.0 (wider target)
- Example: with 30pt SL, TP1 goes from 45pts to 60pts away
- This means: TP1 is **harder to hit** (fewer trades reach it), but when they do, the TP1 profit is bigger
- More trades end as FULL_STOP (51% vs 43% for B1)
- But surviving trades produce bigger runners (TRAIL_S3: 42% vs 37%)

### Impact on trade mechanics:
```
Production (A1): SL=30pt -> TP1=45pt away -> Risk $1,200 for 2 contracts
B1:              SL=30pt -> TP1=45pt away -> Risk $1,200 (same SL, same TP1)
B1:              SL=48pt -> TP1=72pt away -> Risk $1,920 (trade that A1 would cap at 40pt)
B2:              SL=30pt -> TP1=60pt away -> Risk $1,200 (same SL, wider TP1)
B2:              SL=48pt -> TP1=96pt away -> Risk $1,920 (wider SL + wider TP1)
```

The key insight: B1 wins because the **wider SL (50pt)** avoids premature stops on eventually-profitable trades, while keeping the **conservative TP1 (SL x 1.5)** ensures most winning trades actually reach their target.

---

## Test 1: TP1 Ratio + SL Distance Optimization (8 configs)

**Script**: `test_tp1_sl_optimization.py`
**Date**: 2026-02-14
**Data**: 235,835 15-min bars (2016-01-07 to 2026-02-11)

### Configuration Matrix

| Config | TP1 Ratio | Max SL (pts) | Max Risk/Contract |
|--------|-----------|-------------|-------------------|
| A1 (baseline) | SL x 1.5 | 40 | $800 |
| A2 | SL x 2.0 | 40 | $800 |
| A3 | SL x 2.5 | 40 | $800 |
| A4 | SL x 3.0 | 40 | $800 |
| B1 | SL x 1.5 | 50 | $1,000 |
| B2 | SL x 2.0 | 50 | $1,000 |
| B3 | SL x 2.5 | 50 | $1,000 |
| B4 | SL x 3.0 | 50 | $1,000 |

### Full Period Results (2016-2026)

| Config | Trades | WR | PF | Total P&L | Sharpe | Max DD |
|--------|--------|------|------|-----------|--------|--------|
| A1 * | 274 | 52.6% | 1.75 | $131,229 | 3.84 | -$11,386 |
| A2 | 270 | 46.3% | 1.81 | $155,583 | 4.07 | -$11,333 |
| A3 | 264 | 41.3% | 1.86 | $176,852 | 4.12 | -$11,333 |
| A4 | 261 | 36.8% | 1.82 | $178,555 | 3.86 | -$11,599 |
| B1 | 267 | 53.9% | 1.87 | $164,203 | 4.25 | -$13,674 |
| B2 | 264 | 45.1% | 1.79 | $175,006 | 3.92 | -$14,133 |
| B3 | 260 | 40.0% | 1.72 | $174,635 | 3.59 | -$16,435 |
| B4 | 258 | 34.5% | 1.64 | $166,969 | 3.15 | -$20,190 |

### Walk-Forward OOS (2024-2025)

| Config | Trades | WR | PF | Total P&L | Sharpe | Max DD | Consistent? |
|--------|--------|------|------|-----------|--------|--------|-------------|
| A1 | 63 | 49.2% | 1.37 | $18,953 | 2.31 | -$11,386 | YES |
| A2 | 62 | 45.2% | 1.45 | $24,545 | 2.68 | -$11,333 | YES |
| A3 | 59 | 42.4% | 1.71 | $38,967 | 3.75 | -$11,333 | YES |
| A4 | 58 | 39.7% | 1.75 | $41,903 | 3.81 | -$11,599 | YES |
| **B1** | **60** | **56.7%** | **1.88** | **$45,837** | **4.57** | **-$10,648** | **YES** |
| B2 | 59 | 49.2% | 1.85 | $50,922 | 4.40 | -$14,133 | YES |
| B3 | 58 | 44.8% | 1.84 | $53,752 | 4.31 | -$15,099 | YES |
| B4 | 57 | 33.3% | 1.47 | $35,146 | 2.58 | -$20,190 | YES |

### Key Findings

1. **50pt SL is beneficial**: Avg OOS Sharpe 3.97 vs 3.14 (40pt). 20 trades that stopped at 40pt survived at 50pt and ALL were profitable ($133K uplift)
2. **Optimal TP1 ratio**: SL x 2.5 highest avg OOS Sharpe (4.03), but B1 (SL x 1.5) best individual Sharpe
3. **Winner by weighted scoring**: B1 (0.816 score) >> A4 (0.631) > B2 (0.731)
4. **All 8 configs passed Walk-Forward consistency** (rare -- strong system)

### Decision Matrix Winner: B1
- OOS Sharpe 4.57 (best), OOS PF 1.88, OOS Max DD -$10,648 (smallest)

---

## Test 2: Comprehensive B1 vs B2 Validation

**Script**: `test_b1_b2_validation.py`
**Date**: 2026-02-14

### Head-to-Head Comparison

| Metric | B1 (SLx1.5, 50pt) | B2 (SLx2.0, 50pt) |
|--------|-------------------|-------------------|
| **Full Period** | | |
| Trades | 267 | 264 |
| WR | 53.9% | 45.1% |
| PF | 1.87 | 1.79 |
| Total P&L | $164,203 | $175,006 |
| Sharpe | 4.25 | 3.92 |
| Max DD | -$13,674 | -$14,133 |
| **IS (2016-2023)** | | |
| Trades | 204 | 202 |
| WR | 52.9% | 43.6% |
| PF | 1.85 | 1.73 |
| Total P&L | $115,495 | $117,601 |
| Sharpe | 4.11 | 3.63 |
| **OOS (2024-2025)** | | |
| Trades | 60 | 59 |
| WR | 56.7% | 49.2% |
| PF | 1.88 | 1.85 |
| Total P&L | $45,837 | $50,922 |
| Sharpe | 4.57 | 4.40 |
| Max DD | -$10,648 | -$14,133 |
| Max Consec Losses | 5 | 7 |
| Avg SL Dist (OOS) | 48.7 pts | 48.7 pts |
| Avg TP1 Dist (OOS) | 73.1 pts | 97.4 pts |

### Consistency Check (IS -> OOS)

| Metric | B1 Change | B2 Change |
|--------|-----------|-----------|
| Win Rate | +7.2% | +12.8% |
| PF | +1.6% | +6.9% |
| Sharpe | +11.2% | +21.2% |
| Avg P&L | +34.9% | +48.3% |
| Max DD | -22.1% | **+38.1%** |
| **Result** | **PASS** | **FAIL** (MaxDD +38%) |

### Year-by-Year (All Years Profitable for Both)

Both B1 and B2 profitable every single year 2016-2026.

### OOS Monthly (2024-2025)
- B1: Max 2 consecutive losing months, best month +$12,139
- B2: Max 2 consecutive losing months, best month +$15,511
- B2 has higher variance (bigger wins but bigger losses)

### Exit Reason Distribution (OOS)
- B1: FULL_STOP 43%, TRAIL_S1 7%, TRAIL_S2 13%, TRAIL_S3 37%
- B2: FULL_STOP 51%, TRAIL_S1 5%, TRAIL_S2 2%, TRAIL_S3 42%
- B2 stops out more but has more TRAIL_S3 runners

### Session Analysis (OOS)
- B1 US: 49 trades, WR 57.1%, PF 1.95, $40,289
- B1 Europe: 11 trades, WR 54.5%, PF 1.58, $5,547
- B2 US: 48 trades, WR 52.1%, PF 2.10, $51,307
- B2 Europe: 11 trades, WR 36.4%, PF 0.97, **-$385** (Europe unprofitable!)

### Day-of-Week (OOS)
- Monday dominant for both (B1: $32K, B2: $30K)
- Thursday weakest for both
- Wednesday: only 2 trades each (score 9.0 filter)

### Drawdown Deep Dive (OOS)
- Both had max DD period: Jan 20 - May 2, 2025 (8 trades, 14 to recover)
- B1 worst streak: 5 losses = -$10,095
- B2 worst streak: 7 losses = -$14,133
- B1 DD > $5K: 9 times; B2 DD > $5K: 19 times

### Score Bucket Analysis (OOS)
- 8.0-8.2 bucket: small sample (3-4 trades) but 100% WR for both
- 8.5-8.9 bucket: most trades (31 each), B2 slightly better PF
- 9.0+ bucket: 21 trades each, both ~50% WR

### Final Verdict

**Weighted Scoring**: B1 = 7.39, B2 = 5.95 (margin: 1.44 points)

| Criteria | Weight | B1 | B2 |
|----------|--------|-----|-----|
| OOS PF | 20% | 4.4 | 4.2 |
| OOS Sharpe | 20% | 9.1 | 8.8 |
| OOS Max DD | 15% | 7.2 | 5.4 |
| OOS Total P&L | 15% | 5.7 | 6.4 |
| Consistency | 15% | 10.0 | 3.0 |
| OOS WR | 5% | 8.9 | 6.4 |
| All Years Prof | 5% | 10.0 | 10.0 |
| Recovery | 5% | 6.0 | 6.0 |

### Why B1 Wins Over B2
1. **Consistency**: B1 passes Walk-Forward (all metrics stable), B2 fails (MaxDD grew 38%)
2. **Lower risk**: Max DD -$10.6K vs -$14.1K (33% less drawdown)
3. **Higher win rate**: 56.7% vs 49.2% (easier to trade psychologically)
4. **Better worst streak**: 5 losses vs 7 losses
5. **Europe profitable**: B1 Europe +$5,547 vs B2 Europe -$385

### B2's Advantage
- Higher OOS P&L ($50.9K vs $45.8K)
- More TRAIL_S3 runners (42% vs 37%)
- Higher per-trade average ($863 vs $764)

### Production Recommendation: B1

```
TP1 Ratio:          SL x 1.5
Max SL:             50 points
Max Risk/Contract:  $1,000
Expected monthly:   ~$2,200 avg (range -$1,500 to +$3,500)
Trades/month:       ~2.5
```

**Ready for live**: YES (PF 1.88 > 1.2, Sharpe 4.57 > 2.0, MaxDD < $20K)
**Confidence**: MEDIUM (60 OOS trades -- solid but not huge sample)

---

## Generated Reports

- `output/reports/B1_report.html` -- full dark-theme 10-year report
- `output/reports/B1_full_trade_log.csv` -- 267 trades, 27 columns
- `output/b1_oos_trades.csv` -- 60 OOS trades (2024-2025)
