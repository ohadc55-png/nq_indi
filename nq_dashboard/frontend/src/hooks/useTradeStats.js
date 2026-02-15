import { useMemo } from 'react';

export function useTradeStats(trades) {
  return useMemo(() => {
    if (!trades || trades.length === 0) {
      return {
        totalTrades: 0,
        winRate: 0,
        pf: 0,
        totalPnl: 0,
        avgPnl: 0,
        avgWin: 0,
        avgLoss: 0,
        maxDD: 0,
        sharpe: 0,
        currentStreak: 0,
      };
    }

    const wins = trades.filter(t => t.total_pnl > 0);
    const losses = trades.filter(t => t.total_pnl <= 0);
    const totalWins = wins.reduce((s, t) => s + t.total_pnl, 0);
    const totalLosses = Math.abs(losses.reduce((s, t) => s + t.total_pnl, 0));
    const totalPnl = trades.reduce((s, t) => s + t.total_pnl, 0);
    const pnls = trades.map(t => t.total_pnl);

    // Max drawdown
    let peak = 100000;
    let maxDD = 0;
    let running = 100000;
    for (const t of trades) {
      running += t.total_pnl;
      peak = Math.max(peak, running);
      maxDD = Math.max(maxDD, peak - running);
    }

    // Sharpe
    let sharpe = 0;
    if (pnls.length > 1) {
      const mean = pnls.reduce((a, b) => a + b, 0) / pnls.length;
      const variance = pnls.reduce((s, v) => s + (v - mean) ** 2, 0) / (pnls.length - 1);
      const std = Math.sqrt(variance);
      if (std > 0) sharpe = (mean / std) * Math.sqrt(252);
    }

    // Current streak
    let streak = 0;
    for (let i = trades.length - 1; i >= 0; i--) {
      if (streak === 0) {
        streak = trades[i].total_pnl > 0 ? 1 : -1;
      } else if (streak > 0 && trades[i].total_pnl > 0) {
        streak++;
      } else if (streak < 0 && trades[i].total_pnl <= 0) {
        streak--;
      } else {
        break;
      }
    }

    return {
      totalTrades: trades.length,
      winRate: (wins.length / trades.length) * 100,
      pf: totalLosses > 0 ? totalWins / totalLosses : Infinity,
      totalPnl,
      avgPnl: totalPnl / trades.length,
      avgWin: wins.length > 0 ? totalWins / wins.length : 0,
      avgLoss: losses.length > 0 ? -totalLosses / losses.length : 0,
      maxDD,
      sharpe,
      currentStreak: streak,
    };
  }, [trades]);
}
