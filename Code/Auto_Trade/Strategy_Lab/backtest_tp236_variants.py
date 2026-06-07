#!/usr/bin/env python3
"""
Backtest TP at 5m Fib 0.236 variants.
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
from backtest_mss_618_breakeven import ActiveTrade, Trade, finish_trade, intrabar_path
from backtest_mss_618_retracement_engulf_1m import is_engulf_confirmation
from backtest_mss_wave_update_variants import PendingPlan, event_available_from, generate_wave_events, signal_from_event
from backtest_combo_daily_circuit import DAILY_LOSS_LIMIT, DayCircuit, after_entry_path, append_trade, touches_entry


ROOT = Path(__file__).resolve().parent
REPORT_ROOT = ROOT / "reports" / "tp236_variants"


@dataclass
class ArmedSetup:
    signal: Signal
    available_from: datetime
    expires_after: datetime
    armed: bool = False
    armed_time: datetime | None = None


def tp_236(direction: str, start: float, end: float) -> float:
    if direction == "long":
        return end - (end - start) * 0.236
    return end + (start - end) * 0.236


def plan_tp236(event) -> Signal:
    signal = signal_from_event(event, "original")
    return Signal(
        signal.index,
        signal.time,
        signal.kind,
        signal.direction,
        signal.wave_start,
        signal.wave_end,
        signal.wave_start_bar,
        signal.entry,
        signal.sl,
        tp_236(signal.direction, signal.wave_start, signal.wave_end),
    )


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


def fill_limit(signal: Signal, bar: Bar) -> tuple[ActiveTrade | None, Trade | None]:
    if not touches_entry(signal, bar):
        return None, None
    active = ActiveTrade(signal, bar, signal.sl)
    trade = manage_original_exit_on_path(active, bar, after_entry_path(signal, bar), include_start_exit=False)
    if trade is not None:
        return None, trade
    return active, None


def run_tp236(
    five_bars: list[Bar],
    one_bars: list[Bar],
    break_mode: str,
    entry_mode: str,
    engulf_sl_mode: str,
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
    swing_state: dict = {}

    for bar in one_bars:
        update_1m_swings(prev_bar, bar, swing_state)
        while event_index < len(events) and event_times[event_index] <= bar.dt:
            event = events[event_index]
            signal = plan_tp236(event)
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
            trade = manage_original_exit_on_path(active, bar, intrabar_path(bar), include_start_exit=True)
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
                active, trade = fill_limit(pending.signal, bar)
                pending = None
                if trade is not None:
                    append_trade(trades, circuit, trade)
                if trade is not None:
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
                sl = signal.sl
                if engulf_sl_mode == "1m_swing":
                    if signal.direction == "long":
                        sl = swing_state.get("last_low")
                    else:
                        sl = swing_state.get("last_high")
                    if sl is None:
                        skipped.append({"time": bar.dt, "reason": "missing_1m_swing_sl", "direction": signal.direction, "entry": bar.close})
                        setup = None
                        prev_bar = bar
                        continue
                market_signal = Signal(signal.index, signal.time, signal.kind, signal.direction, signal.wave_start, signal.wave_end, signal.wave_start_bar, bar.close, sl, signal.tp)
                active = ActiveTrade(market_signal, bar, market_signal.sl)
                setup = None
                trade = manage_original_exit_on_path(active, bar, [bar.close, bar.close], include_start_exit=False)
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
            "break_mode", "days", "variant", "entry_mode", "sl_mode", "actual_days",
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
        "# TP 0.236 Variants",
        "",
        f"- Daily loss circuit: -${DAILY_LOSS_LIMIT:.0f} realized PnL per Beijing trade day",
        "- Trade day: Beijing 07:00 to next day 04:00",
        f"- Commission: ${COMMISSION_PER_ROUND_TRIP:.2f} round trip per contract",
        f"- Blocked new entries: Beijing {BLOCKED_START_HOUR_BEIJING:02d}:00-{BLOCKED_END_HOUR_BEIJING:02d}:00",
        "- TP: 5m Fib 0.236 level",
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
        ("limit_sl_5m", "limit", "5m_wave_start"),
        ("engulf_sl_1m", "engulf", "1m_swing"),
    ]
    rows = []
    for break_mode in ["Loose", "Strict"]:
        for days in PERIODS:
            cutoff = latest - timedelta(days=days)
            five = clip_bars(five_all, cutoff)
            one = renumber_bars([bar for bar in one_all if bar.dt >= cutoff])
            for variant, entry_mode, sl_mode in variants:
                signals, trades, skipped = run_tp236(five, one, break_mode, entry_mode, sl_mode)
                summary = summarize(trades, signals, skipped)
                period_dir = REPORT_ROOT / break_mode.lower() / f"{days:03d}" / variant
                period_dir.mkdir(parents=True, exist_ok=True)
                write_trades(period_dir / "trades.csv", trades)
                rows.append({
                    "break_mode": break_mode,
                    "days": days,
                    "variant": variant,
                    "entry_mode": entry_mode,
                    "sl_mode": sl_mode,
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
