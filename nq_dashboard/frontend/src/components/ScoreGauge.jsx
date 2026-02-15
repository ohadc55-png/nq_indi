import React from 'react';
import { formatScore } from '../utils/formatters';

export default function ScoreGauge({ score, threshold }) {
  const s = score ?? 0;
  const t = threshold ?? 8;
  const percentage = (s / 10) * 100;
  const isSignal = s >= t;
  const color = isSignal ? '#10b981' : s > t - 0.5 ? '#f59e0b' : '#6b7280';

  return (
    <div className="score-gauge">
      <div className="gauge-label">Signal Score</div>
      <div className="gauge-value" style={{ color }}>
        {formatScore(s)}
      </div>
      <div className="gauge-bar-container">
        <div
          className="gauge-fill"
          style={{ width: `${Math.min(percentage, 100)}%`, background: color }}
        />
        <div
          className="gauge-threshold"
          style={{ left: `${(t / 10) * 100}%` }}
        />
      </div>
      <div className="gauge-sublabel">
        Threshold: {formatScore(t)}
        {isSignal && <span className="signal-badge">SIGNAL ACTIVE</span>}
      </div>
    </div>
  );
}
