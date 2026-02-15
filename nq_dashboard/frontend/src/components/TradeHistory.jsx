import React from 'react';
import { formatPrice, formatPnl, formatDate, formatScore } from '../utils/formatters';

export default function TradeHistory({ trades }) {
  if (!trades || trades.length === 0) {
    return (
      <div className="trade-table-container">
        <div className="panel-header">Trade History</div>
        <div style={{ color: 'var(--text-muted)', fontSize: 12, textAlign: 'center', padding: 20 }}>
          No trades yet
        </div>
      </div>
    );
  }

  // Show newest first
  const sorted = [...trades].reverse();

  return (
    <div className="trade-table-container">
      <div className="panel-header">Trade History ({trades.length} trades)</div>
      <table className="trade-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Date</th>
            <th>Score</th>
            <th>Entry</th>
            <th>Exit</th>
            <th>SL</th>
            <th>TP1</th>
            <th>TP1 Hit</th>
            <th>Trail</th>
            <th>Exit Reason</th>
            <th>P&L</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((trade, i) => (
            <tr
              key={trade.trade_num || i}
              className={trade.total_pnl > 0 ? 'row-win' : 'row-loss'}
            >
              <td>{trade.trade_num || sorted.length - i}</td>
              <td>{formatDate(trade.entry_time)}</td>
              <td>{formatScore(trade.entry_score)}</td>
              <td>{formatPrice(trade.entry_price)}</td>
              <td>{formatPrice(trade.exit_price)}</td>
              <td>{formatPrice(trade.sl_price)}</td>
              <td>{formatPrice(trade.tp1_price)}</td>
              <td style={{ color: trade.tp1_hit ? '#10b981' : '#ef4444' }}>
                {trade.tp1_hit ? 'Yes' : 'No'}
              </td>
              <td>S{trade.trail_stage || 0}</td>
              <td>{trade.exit_reason}</td>
              <td className={trade.total_pnl > 0 ? 'pnl-positive' : 'pnl-negative'}>
                {formatPnl(trade.total_pnl)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
