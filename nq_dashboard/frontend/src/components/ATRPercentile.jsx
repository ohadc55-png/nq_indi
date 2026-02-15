import React from 'react';
import { formatNumber } from '../utils/formatters';

export default function ATRPercentile({ atr, percentile }) {
  const pct = percentile ?? 0;
  const color = pct > 80 ? '#ef4444' : pct > 65 ? '#f59e0b' : pct < 20 ? '#3b82f6' : '#10b981';

  return (
    <div className="atr-meter">
      <div className="gauge-label">ATR Percentile</div>
      <div className="atr-value" style={{ color }}>
        {formatNumber(pct, 0)}%
      </div>
      <div className="atr-bar-container">
        <div
          className="atr-fill"
          style={{ width: `${Math.min(pct, 100)}%`, background: color }}
        />
      </div>
      <div className="gauge-sublabel">
        ATR: {formatNumber(atr, 1)} pts
      </div>
    </div>
  );
}
