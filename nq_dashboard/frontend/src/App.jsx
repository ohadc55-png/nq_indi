import React, { useState, useEffect } from 'react';
import { useWebSocket } from './hooks/useWebSocket';
import Header from './components/Header';
import CandlestickChart from './components/CandlestickChart';
import ScoreGauge from './components/ScoreGauge';
import ATRPercentile from './components/ATRPercentile';
import IndicatorsPanel from './components/IndicatorsPanel';
import ActivePosition from './components/ActivePosition';
import StatsPanel from './components/StatsPanel';
import AlertLog from './components/AlertLog';
import TradeHistory from './components/TradeHistory';

export default function App() {
  const { state, connected } = useWebSocket();
  const [trades, setTrades] = useState([]);

  // Fetch trades on mount and when state updates with new trade count
  useEffect(() => {
    fetch('/api/trades')
      .then(r => r.json())
      .then(data => {
        if (Array.isArray(data)) setTrades(data);
      })
      .catch(() => {});
  }, [state?.trade_count]);

  const signal = state?.signal;
  const position = state?.position;
  const stats = state?.stats;
  const lastBar = state?.last_bar;
  const livePrice = state?.live_price;
  const currentPrice = livePrice ?? lastBar?.Close ?? signal?.close;

  return (
    <div className="dashboard">
      <Header
        connected={connected}
        signal={signal}
        lastBar={lastBar}
      />

      <div className="main-content">
        <CandlestickChart position={position} livePrice={livePrice} />

        <div className="sidebar">
          <ScoreGauge
            score={signal?.long_score}
            threshold={signal?.long_threshold}
          />
          <ATRPercentile
            atr={signal?.atr}
            percentile={signal?.atr_percentile}
          />
          <IndicatorsPanel signal={signal} />
          <ActivePosition
            position={position}
            currentPrice={currentPrice}
          />
        </div>
      </div>

      <div className="bottom-panels">
        <StatsPanel stats={stats} />
        <AlertLog />
      </div>

      <TradeHistory trades={trades} />
    </div>
  );
}
