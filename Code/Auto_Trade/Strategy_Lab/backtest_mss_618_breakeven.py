#!/usr/bin/env python3
"""
Backtest MSS/BOS 61.8 with intrabar break-even stop management.

Variants:
- be_236: after entry, touching the 23.6% retracement level moves SL to entry.
- be_500: after entry, touching the 50.0% retracement level moves SL to entry.

The trigger is modeled intrabar with OHLC high/low, not candle close.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from backtest_mss_618 import Bar, PendingOrder, Signal, entry_for, load_bars


ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "mgc_5m_history.csv"
BREAK_MODE = "Loose"
MGC_DOLLARS_PER_POINT = 10.0
QTY = 1
MAX_PENDING_BARS = 72


@dataclass
class ActiveTrade:
    signal: Signal
    entry_bar: Bar
    stop: float
    break_even_moved: bool = False
    break_even_time: datetime | None = None


@dataclass
class Trade:
    signal_time: datetime
    entry_time: datetime
    exit_time: datetime
    kind: str
    direction: str
    entry: float
    original_sl: float
    final_sl: float
    tp: float
    break_even_moved: bool
    break_even_time: datetime | None
    exit_price: float
    exit_reason: str
    points: float
    dollars: float
    bars_held: int


def break_even_trigger(signal: Signal, ratio: float) -> float:
    if signal.direction == "long":
        return signal.wave_end - (signal.wave_end - signal.wave_start) * ratio
    return signal.wave_end + (signal.wave_start - signal.wave_end) * ratio


def intrabar_path(bar: Bar) -> list[float]:
    if bar.close >= bar.open:
        return [bar.open, bar.low, bar.high, bar.close]
    return [bar.open, bar.high, bar.low, bar.close]


def segment_touches(start: float, end: float, price: float) -> bool:
    return min(start, end) <= price <= max(start, end)


def after_entry_path(signal: Signal, bar: Bar) -> list[float]:
    path = intrabar_path(bar)
    for i in range(len(path) - 1):
        start = path[i]
        end = path[i + 1]
        if segment_touches(start, end, signal.entry):
            return [signal.entry, end, *path[i + 2 :]]
    return [signal.entry, bar.close]


def finish_trade(active: ActiveTrade, bar: Bar, exit_price: float, reason: str) -> Trade:
    signal = active.signal
    points = exit_price - signal.entry if signal.direction == "long" else signal.entry - exit_price
    return Trade(
        signal_time=signal.time,
        entry_time=active.entry_bar.dt,
        exit_time=bar.dt,
        kind=signal.kind,
        direction=signal.direction,
        entry=signal.entry,
        original_sl=signal.sl,
        final_sl=active.stop,
        tp=signal.tp,
        break_even_moved=active.break_even_moved,
        break_even_time=active.break_even_time,
        exit_price=exit_price,
        exit_reason=reason,
        points=points,
        dollars=points * MGC_DOLLARS_PER_POINT * QTY,
        bars_held=bar.index - active.entry_bar.index,
    )


def point_on_segment(start: float, end: float, price: float, include_start: bool) -> bool:
    if not segment_touches(start, end, price):
        return False
    return include_start or price != start


def next_price_event(
    active: ActiveTrade,
    start: float,
    end: float,
    ratio: float,
    include_start: bool,
) -> tuple[str, float] | None:
    signal = active.signal
    trigger = break_even_trigger(signal, ratio)
    candidates: list[tuple[str, float]] = []
    if not active.break_even_moved and point_on_segment(start, end, trigger, include_start):
        candidates.append(("TRIGGER", trigger))
    if point_on_segment(start, end, active.stop, include_start):
        candidates.append(("STOP", active.stop))
    if point_on_segment(start, end, signal.tp, include_start):
        candidates.append(("TP", signal.tp))
    if not candidates:
        return None
    return min(candidates, key=lambda item: abs(item[1] - start))


def gap_exit_at_path_start(active: ActiveTrade, bar: Bar, ratio: float, price: float) -> Trade | None:
    signal = active.signal
    trigger = break_even_trigger(signal, ratio)
    if signal.direction == "long":
        if not active.break_even_moved and price >= trigger:
            active.stop = signal.entry
            active.break_even_moved = True
            active.break_even_time = bar.dt
        if price <= active.stop:
            reason = "BE" if active.break_even_moved and active.stop == signal.entry else "SL"
            return finish_trade(active, bar, price, reason)
        if price >= signal.tp:
            return finish_trade(active, bar, price, "TP")
    else:
        if not active.break_even_moved and price <= trigger:
            active.stop = signal.entry
            active.break_even_moved = True
            active.break_even_time = bar.dt
        if price >= active.stop:
            reason = "BE" if active.break_even_moved and active.stop == signal.entry else "SL"
            return finish_trade(active, bar, price, reason)
        if price <= signal.tp:
            return finish_trade(active, bar, price, "TP")
    return None


def manage_exit_on_path(active: ActiveTrade, bar: Bar, ratio: float, path: list[float], include_start_exit: bool) -> Trade | None:
    if include_start_exit:
        trade = gap_exit_at_path_start(active, bar, ratio, path[0])
        if trade is not None:
            return trade
    for start, end in zip(path, path[1:]):
        cursor = start
        include_start = include_start_exit
        while True:
            event = next_price_event(active, cursor, end, ratio, include_start)
            if event is None:
                break
            kind, price = event
            if kind == "TRIGGER":
                active.stop = active.signal.entry
                active.break_even_moved = True
                active.break_even_time = bar.dt
                cursor = price
                include_start = False
                continue
            if kind == "STOP":
                reason = "BE" if active.break_even_moved and active.stop == active.signal.entry else "SL"
                return finish_trade(active, bar, active.stop, reason)
            if kind == "TP":
                return finish_trade(active, bar, active.signal.tp, "TP")
        include_start_exit = False
    return None


def manage_exit_on_bar(active: ActiveTrade, bar: Bar, ratio: float) -> Trade | None:
    return manage_exit_on_path(active, bar, ratio, intrabar_path(bar), include_start_exit=True)


def run_backtest_breakeven(bars: list[Bar], ratio: float) -> tuple[list[Signal], list[Trade], list[dict]]:
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
    active: ActiveTrade | None = None
    signals: list[Signal] = []
    trades: list[Trade] = []
    skipped: list[dict] = []
    strict = BREAK_MODE == "Strict"

    for i, bar in enumerate(bars):
        if active is not None:
            trade = manage_exit_on_bar(active, bar, ratio)
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
                if bar.low <= signal.entry <= bar.high:
                    pending = None
                    active = ActiveTrade(signal=signal, entry_bar=bar, stop=signal.sl)
                    trade = manage_exit_on_path(active, bar, ratio, after_entry_path(signal, bar), include_start_exit=False)
                    if trade is not None:
                        trades.append(trade)
                        active = None

        if candidate_swing_high is not None and bar.index > candidate_swing_high_bar and bar.low < candidate_swing_high_low:
            last_swing_high = candidate_swing_high
            last_swing_high_bar = candidate_swing_high_bar
            last_swing_high_broken = False
            bull_wick_extreme = None
            candidate_swing_high = None
            candidate_swing_high_low = None
            candidate_swing_high_bar = None

        if candidate_swing_low is not None and bar.index > candidate_swing_low_bar and bar.high > candidate_swing_low_high:
            last_swing_low = candidate_swing_low
            last_swing_low_bar = candidate_swing_low_bar
            last_swing_low_broken = False
            bear_wick_extreme = None
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
        signal = active.signal
        final = bars[-1]
        exit_price = final.close
        points = exit_price - signal.entry if signal.direction == "long" else signal.entry - exit_price
        trades.append(
            Trade(
                signal_time=signal.time,
                entry_time=active.entry_bar.dt,
                exit_time=final.dt,
                kind=signal.kind,
                direction=signal.direction,
                entry=signal.entry,
                original_sl=signal.sl,
                final_sl=active.stop,
                tp=signal.tp,
                break_even_moved=active.break_even_moved,
                break_even_time=active.break_even_time,
                exit_price=exit_price,
                exit_reason="EOD",
                points=points,
                dollars=points * MGC_DOLLARS_PER_POINT * QTY,
                bars_held=final.index - active.entry_bar.index,
            )
        )

    return signals, trades, skipped


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ratio", type=float, required=True, help="Break-even trigger retracement ratio, e.g. 0.236 or 0.5")
    parser.add_argument("--data", default=str(DATA_PATH))
    args = parser.parse_args()
    bars = load_bars(Path(args.data))
    signals, trades, skipped = run_backtest_breakeven(bars, args.ratio)
    total = sum(t.dollars for t in trades)
    wins = [t for t in trades if t.dollars > 0]
    losses = [t for t in trades if t.dollars < 0]
    be = [t for t in trades if t.exit_reason == "BE"]
    print(f"ratio={args.ratio} signals={len(signals)} trades={len(trades)} wins={len(wins)} losses={len(losses)} be={len(be)} net=${total:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
