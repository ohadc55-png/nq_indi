import React from 'react';
import { formatPnl, formatPercent, formatNumber } from '../utils/formatters';

export default function StatsPanel({ stats }) {
  if (!stats) return null;

  const cards = [
    {
      label: 'Win Rate',
      value: formatPercent(stats.win_rate ?? stats.winRate),
      color: (stats.win_rate ?? stats.winRate ?? 0) > 50 ? 'green' : 'red',
    },
    {
      label: 'Profit Factor',
      value: formatNumber(stats.pf, 2),
      color: (stats.pf ?? 0) > 1.5 ? 'green' : (stats.pf ?? 0) > 1 ? 'amber' : 'red',
    },
    {
      label: 'Total P&L',
      value: formatPnl(stats.total_pnl ?? stats.totalPnl),
      color: (stats.total_pnl ?? stats.totalPnl ?? 0) > 0 ? 'green' : 'red',
    },
    {
      label: 'Trades',
      value: stats.total_trades ?? stats.totalTrades ?? 0,
      color: 'blue',
    },
    {
      label: 'Sharpe',
      value: formatNumber(stats.sharpe, 2),
      color: 'blue',
    },
    {
      label: 'Max DD',
      value: formatPnl(-(stats.max_dd ?? stats.maxDD ?? 0)),
      color: 'red',
    },
    {
      label: 'Avg P&L',
      value: formatPnl(stats.avg_pnl ?? stats.avgPnl),
      color: (stats.avg_pnl ?? stats.avgPnl ?? 0) > 0 ? 'green' : 'red',
    },
    {
      label: 'Streak',
      value: (() => {
        const s = stats.current_streak ?? stats.currentStreak ?? 0;
        return s > 0 ? `${s}W` : s < 0 ? `${Math.abs(s)}L` : '-';
      })(),
      color: (stats.current_streak ?? stats.currentStreak ?? 0) > 0 ? 'green' : 'red',
    },
  ];

  return (
    <div className="panel">
      <div className="panel-header">Performance</div>
      <div className="stats-grid">
        {cards.map(card => (
          <div className="stat-card" key={card.label}>
            <div className="stat-label">{card.label}</div>
            <div className={`stat-value ${card.color}`}>{card.value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
