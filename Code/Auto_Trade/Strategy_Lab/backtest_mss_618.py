#!/usr/bin/env python3
"""
Backtest the current MGC 5m MSS/BOS 61.8 strategy.

This script mirrors the current Pine strategy as closely as practical:
- ICT-style swing confirmation used by mgc_mss_retracement_alerts.pine.
- Loose or Strict break mode.
- Structure signal creates a 61.8 retracement limit order.
- Stop is waveStart, target is waveEnd.

Execution model:
- Signal is known only after the structure-break bar closes.
- The limit order can fill from the next bar onward.
- If no position is open, a new signal replaces any older pending order.
- One active position at a time; no pyramiding.
- If SL and TP are both touched inside the same bar, the pessimistic rule assumes SL first.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean


ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "mgc_5m_last30d.csv"
REPORT_DIR = ROOT / "reports"
TRADES_PATH = REPORT_DIR / "trades.csv"
SIGNALS_PATH = REPORT_DIR / "signals.csv"
SKIPPED_PATH = REPORT_DIR / "skipped.csv"
DAILY_PATH = REPORT_DIR / "daily_summary.csv"
REPORT_PATH = REPORT_DIR / "report.md"

BREAK_MODE = "Loose"
MGC_DOLLARS_PER_POINT = 10.0
QTY = 1
MAX_PENDING_BARS = 72


@dataclass
class Bar:
    index: int
    dt: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None


@dataclass
class Signal:
    index: int
    time: datetime
    kind: str
    direction: str
    wave_start: float
    wave_end: float
    wave_start_bar: int
    entry: float
    sl: float
    tp: float


@dataclass
class PendingOrder:
    signal: Signal
    created_index: int


@dataclass
class Trade:
    signal_time: datetime
    entry_time: datetime
    exit_time: datetime
    kind: str
    direction: str
    entry: float
    sl: float
    tp: float
    exit_price: float
    exit_reason: str
    points: float
    dollars: float
    bars_held: int


def exit_signal_on_bar(signal: Signal, entry_bar: Bar, bar: Bar) -> Trade | None:
    hit_sl = bar.low <= signal.sl if signal.direction == "long" else bar.high >= signal.sl
    hit_tp = bar.high >= signal.tp if signal.direction == "long" else bar.low <= signal.tp
    if not hit_sl and not hit_tp:
        return None
    if hit_sl:
        exit_price = signal.sl
        reason = "SL"
    else:
        exit_price = signal.tp
        reason = "TP"
    points = exit_price - signal.entry if signal.direction == "long" else signal.entry - exit_price
    return Trade(
        signal_time=signal.time,
        entry_time=entry_bar.dt,
        exit_time=bar.dt,
        kind=signal.kind,
        direction=signal.direction,
        entry=signal.entry,
        sl=signal.sl,
        tp=signal.tp,
        exit_price=exit_price,
        exit_reason=reason,
        points=points,
        dollars=points * MGC_DOLLARS_PER_POINT * QTY,
        bars_held=bar.index - entry_bar.index,
    )


def load_bars(path: Path) -> list[Bar]:
    bars: list[Bar] = []
    with path.open("r", encoding="utf-8") as f:
      reader = csv.DictReader(f)
      for i, row in enumerate(reader):
          volume = row.get("volume") or ""
          bars.append(
              Bar(
                  index=i,
                  dt=datetime.strptime(row["time"], "%Y-%m-%d %H:%M:%S"),
                  open=float(row["open"]),
                  high=float(row["high"]),
                  low=float(row["low"]),
                  close=float(row["close"]),
                  volume=float(volume) if volume else None,
              )
          )
    return bars


def entry_for(direction: str, start: float, end: float) -> float:
    if direction == "short":
        return end + (start - end) * 0.618
    return end - (end - start) * 0.618


def run_backtest(bars: list[Bar]) -> tuple[list[Signal], list[Trade], list[dict]]:
    last_swing_high = None
    last_swing_high_bar = None
    last_swing_high_broken = True
    bull_wick_extreme = None

    last_swing_low = None
    last_swing_low_bar = None
    last_swing_low_broken = True
    bear_wick_extreme = None

    candidate_swing_high = None
    candidate_swing_high_low = None
    candidate_swing_high_bar = None

    candidate_swing_low = None
    candidate_swing_low_high = None
    candidate_swing_low_bar = None

    bias = 0
    pending: PendingOrder | None = None
    active: tuple[Signal, Bar] | None = None
    signals: list[Signal] = []
    trades: list[Trade] = []
    skipped: list[dict] = []

    strict = BREAK_MODE == "Strict"

    for i, bar in enumerate(bars):
        if active is not None:
            signal, entry_bar = active
            trade = exit_signal_on_bar(signal, entry_bar, bar)
            if trade is not None:
                trades.append(trade)
                active = None

        if active is None and pending is not None:
            if bar.index <= pending.created_index:
                pass
            elif bar.index - pending.created_index > MAX_PENDING_BARS:
                skipped.append({"time": bar.dt, "reason": "pending_expired", "direction": pending.signal.direction, "entry": pending.signal.entry})
                pending = None
            else:
                signal = pending.signal
                filled = bar.low <= signal.entry <= bar.high
                if filled:
                    pending = None
                    trade = exit_signal_on_bar(signal, bar, bar)
                    if trade is not None:
                        trades.append(trade)
                    else:
                        active = (signal, bar)

        new_swing_high = False
        new_swing_low = False

        if candidate_swing_high is not None and bar.index > candidate_swing_high_bar and bar.low < candidate_swing_high_low:
            last_swing_high = candidate_swing_high
            last_swing_high_bar = candidate_swing_high_bar
            last_swing_high_broken = False
            bull_wick_extreme = None
            new_swing_high = True
            candidate_swing_high = None
            candidate_swing_high_low = None
            candidate_swing_high_bar = None

        if candidate_swing_low is not None and bar.index > candidate_swing_low_bar and bar.high > candidate_swing_low_high:
            last_swing_low = candidate_swing_low
            last_swing_low_bar = candidate_swing_low_bar
            last_swing_low_broken = False
            bear_wick_extreme = None
            new_swing_low = True
            candidate_swing_low = None
            candidate_swing_low_high = None
            candidate_swing_low_bar = None

        prev = bars[i - 1] if i > 0 else None
        if prev and bar.high > prev.high:
            candidate_swing_high = bar.high
            candidate_swing_high_low = bar.low
            candidate_swing_high_bar = bar.index

        if prev and bar.low < prev.low:
            candidate_swing_low = bar.low
            candidate_swing_low_high = bar.high
            candidate_swing_low_bar = bar.index

        bull_loose = last_swing_high is not None and not last_swing_high_broken and bar.close > last_swing_high
        bear_loose = last_swing_low is not None and not last_swing_low_broken and bar.close < last_swing_low
        bull_break = bull_loose and ((bull_wick_extreme is None or bar.close > bull_wick_extreme) if strict else True)
        bear_break = bear_loose and ((bear_wick_extreme is None or bar.close < bear_wick_extreme) if strict else True)

        if not bull_break and last_swing_high is not None and not last_swing_high_broken and bar.high > last_swing_high:
            bull_wick_extreme = bar.high if bull_wick_extreme is None else max(bull_wick_extreme, bar.high)

        if not bear_break and last_swing_low is not None and not last_swing_low_broken and bar.low < last_swing_low:
            bear_wick_extreme = bar.low if bear_wick_extreme is None else min(bear_wick_extreme, bar.low)

        if bull_break:
            kind = "MSS" if bias in (-1, 0) else "BOS"
            last_swing_high_broken = True
            bull_wick_extreme = None
            bias = 1
            if last_swing_low is not None:
                entry = entry_for("long", last_swing_low, bar.high)
                signal = Signal(bar.index, bar.dt, kind, "long", last_swing_low, bar.high, last_swing_low_bar, entry, last_swing_low, bar.high)
                signals.append(signal)
                if active is None:
                    pending = PendingOrder(signal, bar.index)
                else:
                    skipped.append({"time": bar.dt, "reason": "signal_while_in_position", "direction": signal.direction, "entry": signal.entry})

        if bear_break:
            kind = "MSS" if bias in (1, 0) else "BOS"
            last_swing_low_broken = True
            bear_wick_extreme = None
            bias = -1
            if last_swing_high is not None:
                entry = entry_for("short", last_swing_high, bar.low)
                signal = Signal(bar.index, bar.dt, kind, "short", last_swing_high, bar.low, last_swing_high_bar, entry, last_swing_high, bar.low)
                signals.append(signal)
                if active is None:
                    pending = PendingOrder(signal, bar.index)
                else:
                    skipped.append({"time": bar.dt, "reason": "signal_while_in_position", "direction": signal.direction, "entry": signal.entry})

    if active is not None:
        signal, entry_bar = active
        final = bars[-1]
        exit_price = final.close
        points = exit_price - signal.entry if signal.direction == "long" else signal.entry - exit_price
        trades.append(
            Trade(
                signal_time=signal.time,
                entry_time=entry_bar.dt,
                exit_time=final.dt,
                kind=signal.kind,
                direction=signal.direction,
                entry=signal.entry,
                sl=signal.sl,
                tp=signal.tp,
                exit_price=exit_price,
                exit_reason="EOD",
                points=points,
                dollars=points * MGC_DOLLARS_PER_POINT * QTY,
                bars_held=final.index - entry_bar.index,
            )
        )

    return signals, trades, skipped


def write_outputs(bars: list[Bar], signals: list[Signal], trades: list[Trade], skipped: list[dict]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with SIGNALS_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "kind", "direction", "entry", "sl", "tp", "wave_start", "wave_end", "wave_start_bar"])
        for s in signals:
            writer.writerow([s.time, s.kind, s.direction, round(s.entry, 1), round(s.sl, 1), round(s.tp, 1), round(s.wave_start, 1), round(s.wave_end, 1), s.wave_start_bar])

    with TRADES_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["signal_time", "entry_time", "exit_time", "kind", "direction", "entry", "sl", "tp", "exit_price", "exit_reason", "points", "dollars", "bars_held"])
        for t in trades:
            writer.writerow([t.signal_time, t.entry_time, t.exit_time, t.kind, t.direction, round(t.entry, 1), round(t.sl, 1), round(t.tp, 1), round(t.exit_price, 1), t.exit_reason, round(t.points, 1), round(t.dollars, 2), t.bars_held])

    with SKIPPED_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "reason", "direction", "entry"])
        for row in skipped:
            writer.writerow([row.get("time"), row.get("reason"), row.get("direction"), row.get("entry")])

    wins = [t for t in trades if t.dollars > 0]
    losses = [t for t in trades if t.dollars < 0]
    total = sum(t.dollars for t in trades)
    gross_profit = sum(t.dollars for t in wins)
    gross_loss = sum(t.dollars for t in losses)
    profit_factor = gross_profit / abs(gross_loss) if gross_loss else None
    avg_win = mean([t.dollars for t in wins]) if wins else 0
    avg_loss = mean([t.dollars for t in losses]) if losses else 0
    max_drawdown = 0.0
    equity = 0.0
    peak = 0.0
    for t in trades:
        equity += t.dollars
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity - peak)

    daily: dict[str, dict] = {}
    for t in trades:
        key = t.exit_time.date().isoformat()
        row = daily.setdefault(key, {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0})
        row["trades"] += 1
        row["wins"] += 1 if t.dollars > 0 else 0
        row["losses"] += 1 if t.dollars < 0 else 0
        row["pnl"] += t.dollars

    with DAILY_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "trades", "wins", "losses", "pnl"])
        for day in sorted(daily):
            row = daily[day]
            writer.writerow([day, row["trades"], row["wins"], row["losses"], round(row["pnl"], 2)])

    report = [
        "# MGC 5m MSS/BOS 61.8 Backtest Report",
        "",
        f"- Data file: `{DATA_PATH.name}`",
        f"- Data range: {bars[0].dt} to {bars[-1].dt} Beijing time",
        f"- Bars: {len(bars)}",
        f"- Break mode: {BREAK_MODE}",
        f"- Entry: 61.8 retracement limit, next bar onward",
        f"- Stop/target: waveStart / waveEnd",
        f"- Contract assumption: MGC ${MGC_DOLLARS_PER_POINT:.0f}/point, qty {QTY}",
        f"- Pending order expiry: {MAX_PENDING_BARS} bars",
        f"- Same-bar SL/TP ambiguity: pessimistic, SL first",
        "",
        "## Summary",
        "",
        f"- Signals: {len(signals)}",
        f"- Filled trades: {len(trades)}",
        f"- Skipped/expired records: {len(skipped)}",
        f"- Wins: {len(wins)}",
        f"- Losses: {len(losses)}",
        f"- Win rate: {(len(wins) / len(trades) * 100) if trades else 0:.2f}%",
        f"- Net PnL: ${total:.2f}",
        f"- Gross profit: ${gross_profit:.2f}",
        f"- Gross loss: ${gross_loss:.2f}",
        f"- Profit factor: {profit_factor:.2f}" if profit_factor is not None else "- Profit factor: n/a",
        f"- Average win: ${avg_win:.2f}",
        f"- Average loss: ${avg_loss:.2f}",
        f"- Max drawdown: ${max_drawdown:.2f}",
        f"- Winning days: {sum(1 for row in daily.values() if row['pnl'] > 0)}",
        f"- Losing days: {sum(1 for row in daily.values() if row['pnl'] < 0)}",
        "",
        "## Files",
        "",
        f"- Signals: `{SIGNALS_PATH.name}`",
        f"- Trades: `{TRADES_PATH.name}`",
        f"- Skipped: `{SKIPPED_PATH.name}`",
        f"- Daily summary: `{DAILY_PATH.name}`",
    ]
    REPORT_PATH.write_text("\n".join(report) + "\n", encoding="utf-8")


def main() -> int:
    if not DATA_PATH.exists():
        print(f"Missing data file: {DATA_PATH}")
        print("Run Strategy_Lab/fetch_mgc_30d.py first.")
        return 2
    bars = load_bars(DATA_PATH)
    if len(bars) < 10:
        print("Not enough bars.")
        return 2
    signals, trades, skipped = run_backtest(bars)
    write_outputs(bars, signals, trades, skipped)
    print(REPORT_PATH.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
