import React from 'react';
import { formatPrice, formatPnl, formatDate } from '../utils/formatters';

export default function ActivePosition({ position, currentPrice }) {
  return (
    <div className="position-panel">
      <div className="panel-header">Active Position</div>
      {!position ? (
        <div className="position-empty">No open position</div>
      ) : (
        <div className="position-grid">
          <div className="position-item">
            <span className="label">Entry</span>
            <span className="value" style={{ color: '#3b82f6' }}>
              {formatPrice(position.entry_price)}
            </span>
          </div>
          <div className="position-item">
            <span className="label">Score</span>
            <span className="value">{(position.entry_score || 0).toFixed(1)}</span>
          </div>
          <div className="position-item">
            <span className="label">Stop Loss</span>
            <span className="value" style={{ color: '#ef4444' }}>
              {formatPrice(position.sl_price)}
            </span>
          </div>
          <div className="position-item">
            <span className="label">TP1</span>
            <span className="value" style={{ color: '#10b981' }}>
              {formatPrice(position.tp1_price)}
            </span>
          </div>
          <div className="position-item">
            <span className="label">TP1 Hit</span>
            <span className="value" style={{ color: position.tp1_hit ? '#10b981' : '#6b7280' }}>
              {position.tp1_hit ? 'Yes' : 'No'}
            </span>
          </div>
          <div className="position-item">
            <span className="label">Trail</span>
            <span className="value" style={{ color: '#f59e0b' }}>
              {position.tp1_hit ? `S${position.trail_stage} @ ${formatPrice(position.trail_stop)}` : '-'}
            </span>
          </div>
          <div className="position-item">
            <span className="label">Contracts</span>
            <span className="value">{position.contracts}</span>
          </div>
          <div className="position-item">
            <span className="label">Session</span>
            <span className="value">{position.entry_session}</span>
          </div>
          {currentPrice != null && (
            <div className="position-pnl">
              <span className="label">Unrealized P&L</span>
              <UnrealizedPnl position={position} currentPrice={currentPrice} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function UnrealizedPnl({ position, currentPrice }) {
  const pointValue = 20;
  let pnl = 0;

  if (position.tp1_hit) {
    // TP1 already locked in + runner unrealized
    pnl = (position.pnl_tp1 || 0) + (currentPrice - position.entry_price) * pointValue;
  } else {
    // Full 2-contract unrealized
    pnl = (currentPrice - position.entry_price) * pointValue * 2;
  }

  const color = pnl >= 0 ? '#10b981' : '#ef4444';
  return (
    <div className="value" style={{ color }}>
      {formatPnl(pnl)}
    </div>
  );
}
