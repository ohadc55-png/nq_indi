import React from 'react';
import { formatPrice, formatTime } from '../utils/formatters';

export default function Header({ connected, signal, lastBar }) {
  const session = signal?.session || '-';
  const lastUpdate = lastBar?.timestamp ? formatTime(lastBar.timestamp) : '-';
  const price = lastBar?.Close ?? signal?.close;

  return (
    <div className="header">
      <div className="header-title">
        NQ <span>Swing Scalper</span> B1
      </div>
      <div className="header-info">
        <div className="header-item">
          <span className={`status-dot ${connected ? 'connected' : 'disconnected'}`} />
          {connected ? 'Live' : 'Offline'}
        </div>
        <div className="header-item">
          <span className="label">Session</span>
          {session}
        </div>
        <div className="header-item">
          <span className="label">Last</span>
          {lastUpdate}
        </div>
        {price != null && (
          <div className="header-item">
            <span className="label">NQ</span>
            <strong>{formatPrice(price)}</strong>
          </div>
        )}
      </div>
    </div>
  );
}
