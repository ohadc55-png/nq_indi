import React from 'react';
import { formatNumber } from '../utils/formatters';

export default function IndicatorsPanel({ signal }) {
  if (!signal) return null;

  const items = [
    { label: 'RSI', value: formatNumber(signal.rsi, 1), color: signal.rsi > 75 || signal.rsi < 25 ? '#ef4444' : null },
    { label: 'ADX', value: formatNumber(signal.adx, 1), color: signal.adx > 25 ? '#10b981' : null },
    { label: 'MACD', value: formatNumber(signal.macd_hist, 2), color: signal.macd_hist > 0 ? '#10b981' : '#ef4444' },
    { label: 'ST Dir', value: signal.st_bullish ? 'Bull' : 'Bear', color: signal.st_bullish ? '#10b981' : '#ef4444' },
    { label: 'Trend', value: signal.primary_bull ? 'Bull' : 'Bear', color: signal.primary_bull ? '#10b981' : '#ef4444' },
    { label: 'MTF 1H', value: signal.mtf_bullish ? 'Bull' : 'Bear', color: signal.mtf_bullish ? '#10b981' : '#ef4444' },
    { label: 'MTF 4H', value: signal.mtf4h_bullish ? 'Bull' : 'Bear', color: signal.mtf4h_bullish ? '#10b981' : '#ef4444' },
    { label: 'Vol', value: signal.vol_spike ? 'Spike' : signal.vol_above ? 'Above' : 'Normal', color: signal.vol_spike ? '#f59e0b' : signal.vol_above ? '#10b981' : null },
  ];

  return (
    <div className="indicators-grid">
      <div className="panel-header" style={{ gridColumn: '1 / -1' }}>Indicators</div>
      {items.map(item => (
        <div className="indicator-item" key={item.label}>
          <span className="indicator-label">{item.label}</span>
          <span className="indicator-value" style={item.color ? { color: item.color } : {}}>
            {item.value}
          </span>
        </div>
      ))}
    </div>
  );
}
