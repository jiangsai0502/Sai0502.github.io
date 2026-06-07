#!/usr/bin/env python3
"""
Backtest wave-update-aware MSS/BOS variants.

Variants:
- update_tp_ext_027: 5m structure, wave updates before fill, 61.8 limit entry,
  original SL, TP at 5m fib -0.27.
- update_1m_mss_prev: 61.8 arms setup, then 1m MSS market entry, SL at 1m swing,
  TP at 5m prior swing point.
- update_1m_mss_ext_027: same 1m MSS entry, TP at 5m fib -0.27.
"""

from __future__ import annotations

import argparse
import csv
from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from backtest_mss_618 import Bar, Signal, entry_for, load_bars
from backtest_mss_618_5m_signal_1m_exec import (
    BLOCKED_END_HOUR_BEIJING,
    BLOCKED_START_HOUR_BEIJING,
    COMMISSION_PER_ROUND_TRIP,
    DATA_1M,
    DATA_5M,
    MAX_PENDING_MINUTES,
    PERIODS,
    apply_commission,
    clip_bars,
    is_blocked_new_entry,
    manage_original_exit_on_path,
    renumber_bars,
    summarize,
    write_trades,
)
from backtest_mss_618_breakeven import ActiveTrade, Trade, finish_trade, intrabar_path


ROOT = Path(__file__).resolve().parent
REPORT_ROOT = ROOT / "reports" / "wave_update_variants"
SIGNAL_CLOSE_MINUTES = 5


@dataclass
class WaveEvent:
    index: int
    time: datetime
    event_type: str
    kind: str
    direction: str
    wave_start: float
    wave_end: float
    wave_start_bar: int
    break_level: float
    break_level_bar: int


@dataclass
class PendingPlan:
    signal: Signal
    available_from: datetime
    expires_after: datetime


@dataclass
class ArmedMssSetup:
    signal: Signal
    available_from: datetime
    expires_after: datetime
    armed: bool = False
    armed_time: datetime | None = None
    last_high: float | None = None
    last_low: float | None = None


def event_available_from(event: WaveEvent) -> datetime:
    return event.time + timedelta(minutes=SIGNAL_CLOSE_MINUTES)


def fib_ext_027(direction: str, start: float, end: float) -> float:
    if direction == "long":
        return end + (end - start) * 0.27
    return end - (start - end) * 0.27


def signal_from_event(event: WaveEvent, tp_mode: str) -> Signal:
    entry = entry_for(event.direction, event.wave_start, event.wave_end)
    tp = fib_ext_027(event.direction, event.wave_start, event.wave_end) if tp_mode == "ext_027" else event.wave_end
    return Signal(
        index=event.index,
        time=event.time,
        kind=event.kind,
        direction=event.direction,
        wave_start=event.wave_start,
        wave_end=event.wave_end,
        wave_start_bar=event.wave_start_bar,
        entry=entry,
        sl=event.wave_start,
        tp=tp,
    )


def generate_wave_events(five_bars: list[Bar], break_mode: str) -> list[WaveEvent]:
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
    active_direction = ""
    wave_start = None
    wave_end = None
    wave_start_bar = None
    break_level = None
    break_level_bar = None
    events: list[WaveEvent] = []
    strict = break_mode == "Strict"

    for i, bar in enumerate(five_bars):
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

        prev = five_bars[i - 1] if i > 0 else None
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
                active_direction = "long"
                wave_start = last_swing_low
                wave_start_bar = last_swing_low_bar
                wave_end = bar.high
                break_level = last_swing_high
                break_level_bar = last_swing_high_bar
                events.append(WaveEvent(bar.index, bar.dt, "structure", kind, active_direction, wave_start, wave_end, wave_start_bar, break_level, break_level_bar))

        if bear_break:
            kind = "MSS" if bias in (1, 0) else "BOS"
            last_swing_low_broken = True
            bear_wick_extreme = None
            bias = -1
            if last_swing_high is not None:
                active_direction = "short"
                wave_start = last_swing_high
                wave_start_bar = last_swing_high_bar
                wave_end = bar.low
                break_level = last_swing_low
                break_level_bar = last_swing_low_bar
                events.append(WaveEvent(bar.index, bar.dt, "structure", kind, active_direction, wave_start, wave_end, wave_start_bar, break_level, break_level_bar))

        long_update = active_direction == "long" and not bull_break and not bear_break and wave_end is not None and bar.high > wave_end
        short_update = active_direction == "short" and not bull_break and not bear_break and wave_end is not None and bar.low < wave_end
        if long_update:
            wave_end = bar.high
            events.append(WaveEvent(bar.index, bar.dt, "wave_update", "EXTEND", active_direction, wave_start, wave_end, wave_start_bar, break_level, break_level_bar))
        if short_update:
            wave_end = bar.low
            events.append(WaveEvent(bar.index, bar.dt, "wave_update", "EXTEND", active_direction, wave_start, wave_end, wave_start_bar, break_level, break_level_bar))

    return events


def fill_limit_plan(plan: PendingPlan, bar: Bar) -> tuple[ActiveTrade | None, Trade | None]:
    signal = plan.signal
    if not (bar.low <= signal.entry <= bar.high):
        return None, None
    active = ActiveTrade(signal=signal, entry_bar=bar, stop=signal.sl)
    trade = manage_original_exit_on_path(active, bar, after_entry_path(signal, bar), include_start_exit=False)
    if trade is not None:
        return None, trade
    return active, None


def after_entry_path(signal: Signal, bar: Bar) -> list[float]:
    path = intrabar_path(bar)
    for i in range(len(path) - 1):
        if min(path[i], path[i + 1]) <= signal.entry <= max(path[i], path[i + 1]):
            return [signal.entry, path[i + 1], *path[i + 2 :]]
    return [signal.entry, bar.close]


def run_limit_ext_backtest(five_bars: list[Bar], one_bars: list[Bar], break_mode: str) -> tuple[list[Signal], list[Trade], list[dict]]:
    events = generate_wave_events(five_bars, break_mode)
    event_times = [event_available_from(event) for event in events]
    event_index = bisect_left(event_times, one_bars[0].dt) if one_bars else 0
    pending: PendingPlan | None = None
    active: ActiveTrade | None = None
    trades: list[Trade] = []
    skipped: list[dict] = []
    signals: list[Signal] = []

    for bar in one_bars:
        while event_index < len(events) and event_times[event_index] <= bar.dt:
            event = events[event_index]
            signal = signal_from_event(event, "ext_027")
            if event.event_type == "structure":
                signals.append(signal)
            if active is None:
                if is_blocked_new_entry(event_times[event_index]):
                    skipped.append({"time": event.time, "reason": "blocked_new_entry_window", "direction": event.direction, "entry": signal.entry})
                else:
                    pending = PendingPlan(signal, event_times[event_index], event_times[event_index] + timedelta(minutes=MAX_PENDING_MINUTES))
            else:
                skipped.append({"time": event.time, "reason": "event_while_in_position", "direction": event.direction, "entry": signal.entry})
            event_index += 1

        if active is not None:
            trade = manage_original_exit_on_path(active, bar, intrabar_path(bar), include_start_exit=True)
            if trade is not None:
                trades.append(apply_commission(trade))
                active = None

        if active is None and pending is not None:
            if bar.dt < pending.available_from or is_blocked_new_entry(bar.dt):
                continue
            if bar.dt > pending.expires_after:
                skipped.append({"time": bar.dt, "reason": "pending_expired", "direction": pending.signal.direction, "entry": pending.signal.entry})
                pending = None
                continue
            active, trade = fill_limit_plan(pending, bar)
            if trade is not None:
                trades.append(apply_commission(trade))
            if active is not None or trade is not None:
                pending = None

    if active is not None and one_bars:
        trades.append(apply_commission(finish_trade(active, one_bars[-1], one_bars[-1].close, "EOD")))
    return signals, trades, skipped


def touches_618(signal: Signal, bar: Bar) -> bool:
    return bar.low <= signal.entry <= bar.high


def update_1m_swings(prev: Bar | None, bar: Bar, state: dict) -> None:
    if prev is None:
        return
    if bar.high > prev.high:
        state["candidate_high"] = bar.high
        state["candidate_high_low"] = bar.low
    if bar.low < prev.low:
        state["candidate_low"] = bar.low
        state["candidate_low_high"] = bar.high
    if state.get("candidate_high") is not None and bar.low < state["candidate_high_low"]:
        state["last_high"] = state["candidate_high"]
        state["candidate_high"] = None
    if state.get("candidate_low") is not None and bar.high > state["candidate_low_high"]:
        state["last_low"] = state["candidate_low"]
        state["candidate_low"] = None


def one_m_mss_entry(setup: ArmedMssSetup, bar: Bar, state: dict) -> ActiveTrade | None:
    signal = setup.signal
    if signal.direction == "long" and state.get("last_high") is not None and bar.close > state["last_high"] and state.get("last_low") is not None:
        market = Signal(signal.index, signal.time, signal.kind, signal.direction, signal.wave_start, signal.wave_end, signal.wave_start_bar, bar.close, state["last_low"], signal.tp)
        return ActiveTrade(market, bar, market.sl)
    if signal.direction == "short" and state.get("last_low") is not None and bar.close < state["last_low"] and state.get("last_high") is not None:
        market = Signal(signal.index, signal.time, signal.kind, signal.direction, signal.wave_start, signal.wave_end, signal.wave_start_bar, bar.close, state["last_high"], signal.tp)
        return ActiveTrade(market, bar, market.sl)
    return None


def run_1m_mss_backtest(five_bars: list[Bar], one_bars: list[Bar], break_mode: str, tp_mode: str) -> tuple[list[Signal], list[Trade], list[dict]]:
    events = generate_wave_events(five_bars, break_mode)
    event_times = [event_available_from(event) for event in events]
    event_index = bisect_left(event_times, one_bars[0].dt) if one_bars else 0
    setup: ArmedMssSetup | None = None
    active: ActiveTrade | None = None
    trades: list[Trade] = []
    skipped: list[dict] = []
    signals: list[Signal] = []
    prev_bar: Bar | None = None
    swing_state: dict = {}

    for bar in one_bars:
        update_1m_swings(prev_bar, bar, swing_state)
        while event_index < len(events) and event_times[event_index] <= bar.dt:
            event = events[event_index]
            signal = signal_from_event(event, "original")
            if tp_mode == "ext_027":
                signal = signal_from_event(event, "ext_027")
            elif tp_mode == "prev_swing":
                signal = Signal(signal.index, signal.time, signal.kind, signal.direction, signal.wave_start, signal.wave_end, signal.wave_start_bar, signal.entry, signal.sl, event.break_level)
            if event.event_type == "structure":
                signals.append(signal)
            if active is None:
                if is_blocked_new_entry(event_times[event_index]):
                    skipped.append({"time": event.time, "reason": "blocked_new_entry_window", "direction": event.direction, "entry": signal.entry})
                else:
                    setup = ArmedMssSetup(signal, event_times[event_index], event_times[event_index] + timedelta(minutes=MAX_PENDING_MINUTES), setup.armed if setup else False, setup.armed_time if setup else None)
            else:
                skipped.append({"time": event.time, "reason": "event_while_in_position", "direction": event.direction, "entry": signal.entry})
            event_index += 1

        if active is not None:
            trade = manage_original_exit_on_path(active, bar, intrabar_path(bar), include_start_exit=True)
            if trade is not None:
                trades.append(apply_commission(trade))
                active = None

        if active is None and setup is not None:
            if bar.dt < setup.available_from:
                prev_bar = bar
                continue
            if bar.dt > setup.expires_after:
                skipped.append({"time": bar.dt, "reason": "setup_expired", "direction": setup.signal.direction, "entry": setup.signal.entry})
                setup = None
            elif not setup.armed:
                if not is_blocked_new_entry(bar.dt) and touches_618(setup.signal, bar):
                    setup.armed = True
                    setup.armed_time = bar.dt
            elif not is_blocked_new_entry(bar.dt):
                active = one_m_mss_entry(setup, bar, swing_state)
                if active is not None:
                    setup = None

        prev_bar = bar

    if active is not None and one_bars:
        trades.append(apply_commission(finish_trade(active, one_bars[-1], one_bars[-1].close, "EOD")))
    return signals, trades, skipped


def write_summary(rows: list[dict], path: Path) -> None:
    with (path / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "break_mode", "days", "variant", "description", "actual_days", "signals", "trades",
            "wins", "losses", "be_exits", "win_rate", "net_pnl", "gross_profit",
            "gross_loss", "profit_factor", "max_drawdown", "winning_days", "losing_days", "skipped",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out = row.copy()
            for key, value in list(out.items()):
                if isinstance(value, float):
                    out[key] = round(value, 2)
            writer.writerow(out)
    lines = [
        "# Wave Update Variants",
        "",
        f"- Commission: ${COMMISSION_PER_ROUND_TRIP:.2f} round trip per contract",
        f"- Blocked new entries: Beijing {BLOCKED_START_HOUR_BEIJING:02d}:00-{BLOCKED_END_HOUR_BEIJING:02d}:00",
        "",
        "| Mode | Days | Variant | Trades | Win Rate | Net PnL | PF | Max DD |",
        "|---|---:|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        pf = f"{row['profit_factor']:.2f}" if row["profit_factor"] is not None else "n/a"
        lines.append(f"| {row['break_mode']} | {row['days']} | {row['variant']} | {row['trades']} | {row['win_rate']:.2f}% | ${row['net_pnl']:.2f} | {pf} | ${row['max_drawdown']:.2f} |")
    (path / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_scan(data_5m: Path, data_1m: Path) -> Path:
    five_all = load_bars(data_5m)
    one_all = load_bars(data_1m)
    latest = min(five_all[-1].dt, one_all[-1].dt)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    variants = [
        ("update_tp_ext_027", "limit_ext", "61.8 limit, wave update, SL waveStart, TP fib -0.27"),
        ("update_1m_mss_prev", "mss_prev", "61.8 arms, 1m MSS market entry, SL 1m swing, TP 5m prior swing"),
        ("update_1m_mss_ext_027", "mss_ext", "61.8 arms, 1m MSS market entry, SL 1m swing, TP fib -0.27"),
    ]
    rows = []
    for break_mode in ["Loose", "Strict"]:
        for days in PERIODS:
            cutoff = latest - timedelta(days=days)
            five = clip_bars(five_all, cutoff)
            one = renumber_bars([bar for bar in one_all if bar.dt >= cutoff])
            for name, kind, description in variants:
                if kind == "limit_ext":
                    signals, trades, skipped = run_limit_ext_backtest(five, one, break_mode)
                elif kind == "mss_prev":
                    signals, trades, skipped = run_1m_mss_backtest(five, one, break_mode, "prev_swing")
                else:
                    signals, trades, skipped = run_1m_mss_backtest(five, one, break_mode, "ext_027")
                summary = summarize(trades, signals, skipped)
                period_dir = REPORT_ROOT / break_mode.lower() / f"{days:03d}d" / name
                period_dir.mkdir(parents=True, exist_ok=True)
                write_trades(period_dir / "trades.csv", trades)
                rows.append({"break_mode": break_mode, "days": days, "variant": name, "description": description, "actual_days": (one[-1].dt - one[0].dt).total_seconds() / 86400 if one else 0, **summary})
    write_summary(rows, REPORT_ROOT)
    return REPORT_ROOT / "summary.md"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-5m", default=str(DATA_5M))
    parser.add_argument("--data-1m", default=str(DATA_1M))
    args = parser.parse_args()
    summary = run_scan(Path(args.data_5m), Path(args.data_1m))
    print(summary.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
