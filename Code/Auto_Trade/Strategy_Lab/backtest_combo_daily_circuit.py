#!/usr/bin/env python3
"""
Scan 5m MSS/BOS strategy combinations with daily loss circuit breaker.
"""

from __future__ import annotations

import argparse
import csv
from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from backtest_mss_618 import Bar, Signal, load_bars
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
from backtest_mss_618_breakeven import ActiveTrade, Trade, finish_trade, intrabar_path, manage_exit_on_path
from backtest_mss_618_retracement_engulf_1m import is_engulf_confirmation
from backtest_mss_wave_update_variants import (
    PendingPlan,
    WaveEvent,
    event_available_from,
    fib_ext_027,
    generate_wave_events,
    signal_from_event,
)


ROOT = Path(__file__).resolve().parent
REPORT_ROOT = ROOT / "reports" / "combo_daily_circuit"
DAILY_LOSS_LIMIT = 300.0


@dataclass
class ArmedSetup:
    signal: Signal
    available_from: datetime
    expires_after: datetime
    armed: bool = False
    armed_time: datetime | None = None


def trading_day(dt: datetime) -> str:
    if dt.hour < 7:
        return (dt - timedelta(days=1)).date().isoformat()
    return dt.date().isoformat()


class DayCircuit:
    def __init__(self, limit: float):
        self.limit = abs(limit)
        self.pnl_by_day: dict[str, float] = {}
        self.blocked_days: set[str] = set()

    def can_open(self, dt: datetime) -> bool:
        day = trading_day(dt)
        return day not in self.blocked_days and self.pnl_by_day.get(day, 0.0) > -self.limit

    def record(self, trade: Trade) -> None:
        day = trading_day(trade.exit_time)
        self.pnl_by_day[day] = self.pnl_by_day.get(day, 0.0) + trade.dollars
        if self.pnl_by_day[day] <= -self.limit:
            self.blocked_days.add(day)


def plan_from_event(event: WaveEvent, tp_mode: str) -> Signal:
    signal = signal_from_event(event, "ext_027" if tp_mode == "ext_027" else "original")
    if tp_mode == "wave_end":
        signal = Signal(signal.index, signal.time, signal.kind, signal.direction, signal.wave_start, signal.wave_end, signal.wave_start_bar, signal.entry, signal.sl, signal.wave_end)
    elif tp_mode == "ext_027":
        tp = fib_ext_027(signal.direction, signal.wave_start, signal.wave_end)
        signal = Signal(signal.index, signal.time, signal.kind, signal.direction, signal.wave_start, signal.wave_end, signal.wave_start_bar, signal.entry, signal.sl, tp)
    return signal


def after_entry_path(signal: Signal, bar: Bar) -> list[float]:
    path = intrabar_path(bar)
    for i in range(len(path) - 1):
        if min(path[i], path[i + 1]) <= signal.entry <= max(path[i], path[i + 1]):
            return [signal.entry, path[i + 1], *path[i + 2 :]]
    return [signal.entry, bar.close]


def touches_entry(signal: Signal, bar: Bar) -> bool:
    return bar.low <= signal.entry <= bar.high


def exit_active(active: ActiveTrade, bar: Bar, be_ratio: float | None) -> Trade | None:
    if be_ratio is None:
        return manage_original_exit_on_path(active, bar, intrabar_path(bar), include_start_exit=True)
    return manage_exit_on_path(active, bar, be_ratio, intrabar_path(bar), include_start_exit=True)


def exit_after_fill(active: ActiveTrade, bar: Bar, be_ratio: float | None) -> Trade | None:
    if be_ratio is None:
        return manage_original_exit_on_path(active, bar, after_entry_path(active.signal, bar), include_start_exit=False)
    return manage_exit_on_path(active, bar, be_ratio, after_entry_path(active.signal, bar), include_start_exit=False)


def append_trade(trades: list[Trade], circuit: DayCircuit, trade: Trade) -> None:
    trade = apply_commission(trade)
    trades.append(trade)
    circuit.record(trade)


def run_combo(
    five_bars: list[Bar],
    one_bars: list[Bar],
    break_mode: str,
    entry_mode: str,
    tp_mode: str,
    be_ratio: float | None,
) -> tuple[list[Signal], list[Trade], list[dict]]:
    events = generate_wave_events(five_bars, break_mode)
    event_times = [event_available_from(event) for event in events]
    event_index = bisect_left(event_times, one_bars[0].dt) if one_bars else 0
    pending: PendingPlan | None = None
    setup: ArmedSetup | None = None
    active: ActiveTrade | None = None
    trades: list[Trade] = []
    skipped: list[dict] = []
    signals: list[Signal] = []
    circuit = DayCircuit(DAILY_LOSS_LIMIT)
    prev_bar: Bar | None = None

    for bar in one_bars:
        while event_index < len(events) and event_times[event_index] <= bar.dt:
            event = events[event_index]
            signal = plan_from_event(event, tp_mode)
            available_from = event_times[event_index]
            if event.event_type == "structure":
                signals.append(signal)
            if active is not None:
                skipped.append({"time": event.time, "reason": "event_while_in_position", "direction": event.direction, "entry": signal.entry})
            elif is_blocked_new_entry(available_from) or not circuit.can_open(available_from):
                skipped.append({"time": event.time, "reason": "entry_blocked", "direction": event.direction, "entry": signal.entry})
            elif entry_mode == "limit":
                pending = PendingPlan(signal, available_from, available_from + timedelta(minutes=MAX_PENDING_MINUTES))
                setup = None
            else:
                if setup is not None and setup.armed:
                    setup.signal = signal
                    setup.expires_after = available_from + timedelta(minutes=MAX_PENDING_MINUTES)
                else:
                    setup = ArmedSetup(signal, available_from, available_from + timedelta(minutes=MAX_PENDING_MINUTES))
                pending = None
            event_index += 1

        if active is not None:
            trade = exit_active(active, bar, be_ratio)
            if trade is not None:
                append_trade(trades, circuit, trade)
                active = None

        if active is None and pending is not None:
            if bar.dt < pending.available_from:
                prev_bar = bar
                continue
            if bar.dt > pending.expires_after:
                skipped.append({"time": bar.dt, "reason": "pending_expired", "direction": pending.signal.direction, "entry": pending.signal.entry})
                pending = None
            elif is_blocked_new_entry(bar.dt) or not circuit.can_open(bar.dt):
                pass
            elif touches_entry(pending.signal, bar):
                active = ActiveTrade(pending.signal, bar, pending.signal.sl)
                pending = None
                trade = exit_after_fill(active, bar, be_ratio)
                if trade is not None:
                    append_trade(trades, circuit, trade)
                    active = None

        if active is None and setup is not None:
            if bar.dt < setup.available_from:
                prev_bar = bar
                continue
            if bar.dt > setup.expires_after:
                skipped.append({"time": bar.dt, "reason": "setup_expired", "direction": setup.signal.direction, "entry": setup.signal.entry})
                setup = None
            elif not setup.armed:
                if not is_blocked_new_entry(bar.dt) and circuit.can_open(bar.dt) and touches_entry(setup.signal, bar):
                    setup.armed = True
                    setup.armed_time = bar.dt
            elif not is_blocked_new_entry(bar.dt) and circuit.can_open(bar.dt) and is_engulf_confirmation(setup.signal, prev_bar, bar):
                signal = setup.signal
                market_signal = Signal(signal.index, signal.time, signal.kind, signal.direction, signal.wave_start, signal.wave_end, signal.wave_start_bar, bar.close, signal.sl, signal.tp)
                active = ActiveTrade(market_signal, bar, market_signal.sl)
                setup = None
                trade = manage_original_exit_on_path(active, bar, [bar.close, bar.close], include_start_exit=False) if be_ratio is None else manage_exit_on_path(active, bar, be_ratio, [bar.close, bar.close], include_start_exit=False)
                if trade is not None:
                    append_trade(trades, circuit, trade)
                    active = None

        prev_bar = bar

    if active is not None and one_bars:
        append_trade(trades, circuit, finish_trade(active, one_bars[-1], one_bars[-1].close, "EOD"))
    return signals, trades, skipped


def write_summary(rows: list[dict], path: Path) -> None:
    with (path / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "break_mode", "days", "variant", "entry_mode", "tp_mode", "be_mode", "actual_days",
            "signals", "trades", "wins", "losses", "be_exits", "win_rate", "net_pnl",
            "gross_profit", "gross_loss", "profit_factor", "max_drawdown", "winning_days",
            "losing_days", "skipped",
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
        "# Combo Scan With Daily Circuit",
        "",
        f"- Daily loss circuit: -${DAILY_LOSS_LIMIT:.0f} realized PnL per Beijing trade day",
        "- Trade day: Beijing 07:00 to next day 04:00",
        f"- Commission: ${COMMISSION_PER_ROUND_TRIP:.2f} round trip per contract",
        f"- Blocked new entries: Beijing {BLOCKED_START_HOUR_BEIJING:02d}:00-{BLOCKED_END_HOUR_BEIJING:02d}:00",
        "",
        "| Mode | Days | Variant | Trades | BE | Win Rate | Net PnL | PF | Max DD |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        pf = f"{row['profit_factor']:.2f}" if row["profit_factor"] is not None else "n/a"
        lines.append(
            f"| {row['break_mode']} | {row['days']} | {row['variant']} | {row['trades']} | {row['be_exits']} | "
            f"{row['win_rate']:.2f}% | ${row['net_pnl']:.2f} | {pf} | ${row['max_drawdown']:.2f} |"
        )
    (path / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_scan(data_5m: Path, data_1m: Path) -> Path:
    five_all = load_bars(data_5m)
    one_all = load_bars(data_1m)
    latest = min(five_all[-1].dt, one_all[-1].dt)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    be_modes = [("no_be", None), ("be_236", 0.236), ("be_500", 0.5)]
    setup_modes = [
        ("limit_wave_end", "limit", "wave_end"),
        ("limit_ext_027", "limit", "ext_027"),
        ("engulf_wave_end", "engulf", "wave_end"),
        ("engulf_ext_027", "engulf", "ext_027"),
    ]
    rows = []
    for break_mode in ["Loose", "Strict"]:
        for days in PERIODS:
            cutoff = latest - timedelta(days=days)
            five = clip_bars(five_all, cutoff)
            one = renumber_bars([bar for bar in one_all if bar.dt >= cutoff])
            for setup_name, entry_mode, tp_mode in setup_modes:
                for be_name, be_ratio in be_modes:
                    variant = f"{setup_name}_{be_name}"
                    signals, trades, skipped = run_combo(five, one, break_mode, entry_mode, tp_mode, be_ratio)
                    summary = summarize(trades, signals, skipped)
                    period_dir = REPORT_ROOT / break_mode.lower() / f"{days:03d}d" / variant
                    period_dir.mkdir(parents=True, exist_ok=True)
                    write_trades(period_dir / "trades.csv", trades)
                    rows.append({
                        "break_mode": break_mode,
                        "days": days,
                        "variant": variant,
                        "entry_mode": entry_mode,
                        "tp_mode": tp_mode,
                        "be_mode": be_name,
                        "actual_days": (one[-1].dt - one[0].dt).total_seconds() / 86400 if one else 0,
                        **summary,
                    })
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
