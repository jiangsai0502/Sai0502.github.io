#!/usr/bin/env python3
"""
Backtest MSS/BOS 61.8 retracement armed entry with 1m engulf confirmation.

Flow:
- 5m bars generate MSS/BOS structure signals.
- After price touches the 61.8 retracement level, the setup is armed.
- Entry is market at the close of a 1m engulf confirmation candle.
  Long: current 1m close > previous 1m high.
  Short: current 1m close < previous 1m low.
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
    QTY,
    apply_commission,
    clip_bars,
    generate_signals,
    is_blocked_new_entry,
    manage_original_exit_on_path,
    renumber_bars,
    signal_available_from,
    summarize,
    write_trades,
)
from backtest_mss_618_breakeven import ActiveTrade, Trade, finish_trade, intrabar_path, manage_exit_on_path


ROOT = Path(__file__).resolve().parent
REPORT_ROOT = ROOT / "reports" / "retracement_engulf_1m"


@dataclass
class ArmedSetup:
    signal: Signal
    available_from: datetime
    expires_after: datetime
    armed: bool = False
    armed_time: datetime | None = None


def touches_618(signal: Signal, bar: Bar) -> bool:
    return bar.low <= signal.entry <= bar.high


def is_bullish_engulf(prev: Bar, bar: Bar) -> bool:
    return bar.close > prev.high


def is_bearish_engulf(prev: Bar, bar: Bar) -> bool:
    return bar.close < prev.low


def is_engulf_confirmation(signal: Signal, prev: Bar | None, bar: Bar) -> bool:
    if prev is None:
        return False
    if signal.direction == "long":
        return is_bullish_engulf(prev, bar)
    return is_bearish_engulf(prev, bar)


def make_market_entry_trade(signal: Signal, entry_bar: Bar) -> ActiveTrade:
    market_signal = Signal(
        index=signal.index,
        time=signal.time,
        kind=signal.kind,
        direction=signal.direction,
        wave_start=signal.wave_start,
        wave_end=signal.wave_end,
        wave_start_bar=signal.wave_start_bar,
        entry=entry_bar.close,
        sl=signal.sl,
        tp=signal.tp,
    )
    return ActiveTrade(signal=market_signal, entry_bar=entry_bar, stop=market_signal.sl)


def run_engulf_backtest(
    five_bars: list[Bar],
    one_bars: list[Bar],
    ratio: float | None,
    break_mode: str,
) -> tuple[list[Signal], list[Trade], list[dict]]:
    signals = generate_signals(five_bars, break_mode)
    signal_times = [signal_available_from(signal) for signal in signals]
    signal_index = bisect_left(signal_times, one_bars[0].dt) if one_bars else 0
    setup: ArmedSetup | None = None
    active: ActiveTrade | None = None
    trades: list[Trade] = []
    skipped: list[dict] = []
    prev_bar: Bar | None = None

    for bar in one_bars:
        while signal_index < len(signals) and signal_times[signal_index] <= bar.dt:
            signal = signals[signal_index]
            available_from = signal_times[signal_index]
            new_setup = ArmedSetup(
                signal=signal,
                available_from=available_from,
                expires_after=available_from + timedelta(minutes=MAX_PENDING_MINUTES),
            )
            if active is None:
                if is_blocked_new_entry(available_from):
                    skipped.append({"time": signal.time, "reason": "blocked_new_entry_window", "direction": signal.direction, "entry": signal.entry})
                else:
                    setup = new_setup
            else:
                skipped.append({"time": signal.time, "reason": "signal_while_in_position", "direction": signal.direction, "entry": signal.entry})
            signal_index += 1

        if active is not None:
            if ratio is None:
                trade = manage_original_exit_on_path(active, bar, intrabar_path(bar), include_start_exit=True)
            else:
                trade = manage_exit_on_path(active, bar, ratio, intrabar_path(bar), include_start_exit=True)
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
            elif not is_blocked_new_entry(bar.dt) and is_engulf_confirmation(setup.signal, prev_bar, bar):
                active = make_market_entry_trade(setup.signal, bar)
                setup = None
                if ratio is None:
                    trade = manage_original_exit_on_path(active, bar, [bar.close, bar.close], include_start_exit=False)
                else:
                    trade = manage_exit_on_path(active, bar, ratio, [bar.close, bar.close], include_start_exit=False)
                if trade is not None:
                    trades.append(apply_commission(trade))
                    active = None

        prev_bar = bar

    if active is not None and one_bars:
        final = one_bars[-1]
        trades.append(apply_commission(finish_trade(active, final, final.close, "EOD")))

    return signals, trades, skipped


def run_scan(data_5m: Path, data_1m: Path) -> Path:
    five_all = load_bars(data_5m)
    one_all = load_bars(data_1m)
    latest = min(five_all[-1].dt, one_all[-1].dt)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    variants = [
        ("engulf_original", None, "61.8 arms setup, 1m engulf market entry, original TP/SL"),
        ("engulf_be_236", 0.236, "61.8 arms setup, 1m engulf market entry, BE at 23.6"),
        ("engulf_be_500", 0.5, "61.8 arms setup, 1m engulf market entry, BE at 50.0"),
    ]
    rows = []

    for break_mode in ["Loose", "Strict"]:
        for days in PERIODS:
            cutoff = latest - timedelta(days=days)
            five = clip_bars(five_all, cutoff)
            one = renumber_bars([bar for bar in one_all if bar.dt >= cutoff])
            for name, ratio, description in variants:
                signals, trades, skipped = run_engulf_backtest(five, one, ratio, break_mode)
                summary = summarize(trades, signals, skipped)
                period_dir = REPORT_ROOT / break_mode.lower() / f"{days:03d}d" / name
                period_dir.mkdir(parents=True, exist_ok=True)
                write_trades(period_dir / "trades.csv", trades)
                rows.append(
                    {
                        "break_mode": break_mode,
                        "days": days,
                        "variant": name,
                        "description": description,
                        "actual_days": (one[-1].dt - one[0].dt).total_seconds() / 86400 if one else 0,
                        **summary,
                    }
                )

    summary_csv = REPORT_ROOT / "summary.csv"
    with summary_csv.open("w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "break_mode", "days", "variant", "description", "actual_days", "signals", "trades",
            "wins", "losses", "be_exits", "win_rate", "net_pnl", "gross_profit",
            "gross_loss", "profit_factor", "max_drawdown", "winning_days",
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

    summary_md = REPORT_ROOT / "summary.md"
    lines = [
        "# 61.8 Retracement Armed / 1m Engulf Entry Scan",
        "",
        f"- Commission: ${COMMISSION_PER_ROUND_TRIP:.2f} round trip per contract",
        f"- Blocked new entries: Beijing {BLOCKED_START_HOUR_BEIJING:02d}:00-{BLOCKED_END_HOUR_BEIJING:02d}:00",
        "- Long confirmation: current 1m close > previous 1m high",
        "- Short confirmation: current 1m close < previous 1m low",
        "",
        "| Mode | Days | Variant | Trades | BE Exits | Win Rate | Net PnL | PF | Max DD |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        pf = f"{row['profit_factor']:.2f}" if row["profit_factor"] is not None else "n/a"
        lines.append(
            f"| {row['break_mode']} | {row['days']} | {row['variant']} | {row['trades']} | {row['be_exits']} | "
            f"{row['win_rate']:.2f}% | ${row['net_pnl']:.2f} | {pf} | ${row['max_drawdown']:.2f} |"
        )
    summary_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary_md


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
