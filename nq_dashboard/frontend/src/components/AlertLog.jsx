import React, { useState, useEffect } from 'react';
import { formatTime, formatScore } from '../utils/formatters';

export default function AlertLog() {
  const [signals, setSignals] = useState([]);

  useEffect(() => {
    fetch('/api/signals-log?limit=30')
      .then(r => r.json())
      .then(data => {
        if (Array.isArray(data)) setSignals(data);
      })
      .catch(() => {});

    const interval = setInterval(() => {
      fetch('/api/signals-log?limit=30')
        .then(r => r.json())
        .then(data => {
          if (Array.isArray(data)) setSignals(data);
        })
        .catch(() => {});
    }, 30000);

    return () => clearInterval(interval);
  }, []);

  return (
    <div className="panel">
      <div className="panel-header">Signal Log</div>
      <div className="alert-log">
        {signals.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>No signals yet</div>
        ) : (
          signals.map((s, i) => (
            <div className="alert-entry" key={s.id || i}>
              <span className="alert-time">{formatTime(s.timestamp)}</span>
              <span className={s.signal_triggered ? 'alert-signal' : 'alert-msg'}>
                {s.signal_triggered ? 'SIGNAL' : 'Check'}
              </span>
              <span className="alert-msg">
                Score {formatScore(s.long_score)}/{formatScore(s.long_threshold)}
                {' | '}
                {s.session}
                {' | '}
                ATR {(s.atr_percentile || 0).toFixed(0)}%
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
