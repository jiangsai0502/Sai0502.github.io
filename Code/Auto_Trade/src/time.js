export function beijingParts(date = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  }).formatToParts(date).reduce((acc, p) => {
    if (p.type !== 'literal') acc[p.type] = p.value;
    return acc;
  }, {});
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    hour: Number(parts.hour),
    minute: Number(parts.minute),
    second: Number(parts.second)
  };
}

export function isBlockedTradingWindow(config, date = new Date()) {
  const { hour } = beijingParts(date);
  const start = Number(config.strategy.blockedStartHourBeijing);
  const end = Number(config.strategy.blockedEndHourBeijing);
  if (start < end) return hour >= start && hour < end;
  return hour >= start || hour < end;
}

export function signalAgeSeconds(signal) {
  const raw = signal.time || signal.barTime || signal.timestamp;
  if (!raw) return 0;
  const t = Number(raw);
  const ms = Number.isFinite(t) ? (t > 10_000_000_000 ? t : t * 1000) : Date.parse(raw);
  if (!Number.isFinite(ms)) return 0;
  return Math.max(0, Math.floor((Date.now() - ms) / 1000));
}
