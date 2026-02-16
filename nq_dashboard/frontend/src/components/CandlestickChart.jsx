import React, { useEffect, useRef, useState, useCallback } from 'react';
import { createChart } from 'lightweight-charts';

const TIMEFRAMES = ['5m', '15m', '1H'];

export default function CandlestickChart({ position, livePrice }) {
  const chartRef = useRef(null);
  const chartInstance = useRef(null);
  const candleSeriesRef = useRef(null);
  const ema50Ref = useRef(null);
  const ema200Ref = useRef(null);
  const stRef = useRef(null);
  const priceLines = useRef([]);
  const livePriceLineRef = useRef(null);
  const initialFitDone = useRef(false);
  const [loaded, setLoaded] = useState(false);
  const [timeframe, setTimeframe] = useState('15m');

  const loadCandles = useCallback((chart, candleSeries, ema50, ema200, st, tf) => {
    const interval = tf.toLowerCase();
    fetch(`/api/candles?interval=${interval}&limit=400`)
      .then(r => r.json())
      .then(candles => {
        if (!Array.isArray(candles) || candles.length === 0) return;

        candleSeries.setData(candles.map(c => ({
          time: c.time,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
        })));

        const ema50Data = candles.filter(c => c.ema50 != null).map(c => ({ time: c.time, value: c.ema50 }));
        const ema200Data = candles.filter(c => c.ema200 != null).map(c => ({ time: c.time, value: c.ema200 }));
        const stData = candles.filter(c => c.supertrend != null).map(c => ({ time: c.time, value: c.supertrend }));

        ema50.setData(ema50Data);
        ema200.setData(ema200Data);
        st.setData(stData);

        // Trade markers only on 15m (signal timeframe)
        if (tf === '15m') {
          fetch('/api/trades')
            .then(r => r.json())
            .then(trades => {
              if (!Array.isArray(trades)) return;
              const markers = [];
              for (const trade of trades) {
                if (trade.entry_time) {
                  const entryTs = Math.floor(new Date(trade.entry_time).getTime() / 1000);
                  markers.push({
                    time: entryTs,
                    position: 'belowBar',
                    color: '#10b981',
                    shape: 'arrowUp',
                    text: `L ${(trade.entry_score || 0).toFixed(1)}`,
                  });
                }
                if (trade.exit_time) {
                  const exitTs = Math.floor(new Date(trade.exit_time).getTime() / 1000);
                  markers.push({
                    time: exitTs,
                    position: 'aboveBar',
                    color: trade.total_pnl > 0 ? '#10b981' : '#ef4444',
                    shape: 'arrowDown',
                    text: `$${Math.round(trade.total_pnl || 0)}`,
                  });
                }
              }
              markers.sort((a, b) => a.time - b.time);
              if (markers.length) candleSeries.setMarkers(markers);
            })
            .catch(() => {});
        } else {
          candleSeries.setMarkers([]);
        }

        setLoaded(true);
        if (!initialFitDone.current) {
          initialFitDone.current = true;
          chart.timeScale().fitContent();
        }
      })
      .catch(err => console.error('Failed to load candles:', err));
  }, []);

  // Initialize chart (once)
  useEffect(() => {
    if (!chartRef.current) return;

    const chart = createChart(chartRef.current, {
      width: chartRef.current.clientWidth,
      height: 500,
      layout: {
        background: { color: '#0a0e17' },
        textColor: '#9ca3af',
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: '#1f293744' },
        horzLines: { color: '#1f293744' },
      },
      crosshair: {
        mode: 0,
        vertLine: { color: '#374151', style: 2 },
        horzLine: { color: '#374151', style: 2 },
      },
      timeScale: {
        borderColor: '#374151',
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: {
        borderColor: '#374151',
      },
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#10b981',
      downColor: '#ef4444',
      borderDownColor: '#ef4444',
      borderUpColor: '#10b981',
      wickDownColor: '#ef4444',
      wickUpColor: '#10b981',
    });

    const ema50 = chart.addLineSeries({
      color: '#3b82f680',
      lineWidth: 1,
      lineStyle: 0,
      priceLineVisible: false,
      lastValueVisible: false,
    });

    const ema200 = chart.addLineSeries({
      color: '#f59e0b60',
      lineWidth: 1,
      lineStyle: 0,
      priceLineVisible: false,
      lastValueVisible: false,
    });

    const st = chart.addLineSeries({
      color: '#8b5cf680',
      lineWidth: 1,
      lineStyle: 2,
      priceLineVisible: false,
      lastValueVisible: false,
    });

    chartInstance.current = chart;
    candleSeriesRef.current = candleSeries;
    ema50Ref.current = ema50;
    ema200Ref.current = ema200;
    stRef.current = st;

    // Load initial candles (15m)
    loadCandles(chart, candleSeries, ema50, ema200, st, '15m');

    const handleResize = () => {
      if (chartRef.current) {
        chart.applyOptions({ width: chartRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, [loadCandles]);

  // Reload candles when timeframe changes
  useEffect(() => {
    if (!chartInstance.current || !candleSeriesRef.current) return;
    initialFitDone.current = false;
    loadCandles(
      chartInstance.current,
      candleSeriesRef.current,
      ema50Ref.current,
      ema200Ref.current,
      stRef.current,
      timeframe,
    );
  }, [timeframe, loadCandles]);

  // Auto-refresh candles every 60 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      if (!chartInstance.current || !candleSeriesRef.current) return;
      loadCandles(
        chartInstance.current,
        candleSeriesRef.current,
        ema50Ref.current,
        ema200Ref.current,
        stRef.current,
        timeframe,
      );
    }, 60_000);
    return () => clearInterval(interval);
  }, [timeframe, loadCandles]);

  // Update position lines
  useEffect(() => {
    if (!candleSeriesRef.current || !loaded) return;

    for (const line of priceLines.current) {
      try { candleSeriesRef.current.removePriceLine(line); } catch {}
    }
    priceLines.current = [];

    if (!position) return;

    priceLines.current.push(
      candleSeriesRef.current.createPriceLine({
        price: position.entry_price,
        color: '#3b82f6',
        lineWidth: 1,
        lineStyle: 2,
        title: 'Entry',
      })
    );

    priceLines.current.push(
      candleSeriesRef.current.createPriceLine({
        price: position.sl_price,
        color: '#ef4444',
        lineWidth: 2,
        lineStyle: 0,
        title: `SL -${Math.round(position.sl_distance)}`,
      })
    );

    priceLines.current.push(
      candleSeriesRef.current.createPriceLine({
        price: position.tp1_price,
        color: '#10b981',
        lineWidth: 2,
        lineStyle: 0,
        title: `TP1 +${Math.round(position.tp1_distance)}`,
      })
    );

    if (position.tp1_hit && position.trail_stop) {
      priceLines.current.push(
        candleSeriesRef.current.createPriceLine({
          price: position.trail_stop,
          color: '#f59e0b',
          lineWidth: 1,
          lineStyle: 2,
          title: `Trail S${position.trail_stage}`,
        })
      );
    }
  }, [position, loaded]);

  // Update live price line
  useEffect(() => {
    if (!candleSeriesRef.current || !loaded || !livePrice) return;

    if (livePriceLineRef.current) {
      livePriceLineRef.current.applyOptions({ price: livePrice });
    } else {
      livePriceLineRef.current = candleSeriesRef.current.createPriceLine({
        price: livePrice,
        color: '#22d3ee',
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: '',
      });
    }
  }, [livePrice, loaded]);

  return (
    <div className="panel" style={{ padding: 0 }}>
      <div className="timeframe-bar">
        {TIMEFRAMES.map(tf => (
          <button
            key={tf}
            className={`tf-btn ${timeframe === tf ? 'active' : ''}`}
            onClick={() => setTimeframe(tf)}
          >
            {tf}
          </button>
        ))}
      </div>
      <div ref={chartRef} style={{ width: '100%', minHeight: 500 }} />
    </div>
  );
}
