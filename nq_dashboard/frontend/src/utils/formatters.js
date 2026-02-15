export function formatPrice(price) {
  if (price == null) return '-';
  return price.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

export function formatPnl(pnl) {
  if (pnl == null) return '-';
  const sign = pnl >= 0 ? '+' : '';
  return `${sign}$${pnl.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

export function formatPercent(value) {
  if (value == null) return '-';
  return `${value.toFixed(1)}%`;
}

export function formatScore(score) {
  if (score == null) return '-';
  return score.toFixed(1);
}

export function formatDate(dateStr) {
  if (!dateStr) return '-';
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) +
      ' ' + d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
  } catch {
    return dateStr;
  }
}

export function formatTime(dateStr) {
  if (!dateStr) return '-';
  try {
    const d = new Date(dateStr);
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
  } catch {
    return dateStr;
  }
}

export function formatNumber(num, decimals = 2) {
  if (num == null) return '-';
  return num.toFixed(decimals);
}
