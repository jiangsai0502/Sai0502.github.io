#!/usr/bin/env python3
"""
Backtest MSS/BOS 61.8 with 5-minute signals and 1-minute execution.

The structure signal is generated from 5m bars. After the 5m signal bar closes,
pending limit fills, break-even moves, TP, and SL are simulated on 1m bars.
"""

from __future__ import annotations

import argparse
import csv
from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from backtest_mss_618 import Bar, Signal, entry_for, load_bars
from backtest_mss_618_breakeven import (
    ActiveTrade,
    Trade,
    finish_trade,
    intrabar_path,
    manage_exit_on_path,
)


ROOT = Path(__file__).resolve().parent
DATA_5M = ROOT / "data" / "mgc_5m_history.csv"
DATA_1M = ROOT / "data" / "mgc_1m_history.csv"
REPORT_ROOT = ROOT / "reports" / "hybrid_5m_signal_1m_exec"
PERIODS = list(range(30, 361, 30))
MGC_DOLLARS_PER_POINT = 10.0
QTY = 1
COMMISSION_PER_ROUND_TRIP = 4.0
MAX_PENDING_MINUTES = 360
SIGNAL_CLOSE_MINUTES = 5
BLOCKED_START_HOUR_BEIJING = 4
BLOCKED_END_HOUR_BEIJING = 7


@dataclass
class PendingOrder:
    signal: Signal
    available_from: datetime
    expires_after: datetime


def renumber_bars(bars: list[Bar]) -> list[Bar]:
    return [
        Bar(i, bar.dt, bar.open, bar.high, bar.low, bar.close, bar.volume)
        for i, bar in enumerate(bars)
    ]


def clip_bars(bars: list[Bar], cutoff: datetime) -> list[Bar]:
    clipped = [bar for bar in bars if bar.dt >= cutoff]
    return renumber_bars(clipped)


def signal_available_from(signal: Signal) -> datetime:
    return signal.time + timedelta(minutes=SIGNAL_CLOSE_MINUTES)


def is_blocked_new_entry(dt: datetime) -> bool:
    hour = dt.hour
    start = BLOCKED_START_HOUR_BEIJING
    end = BLOCKED_END_HOUR_BEIJING
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def apply_commission(trade: Trade) -> Trade:
    trade.dollars -= COMMISSION_PER_ROUND_TRIP * QTY
    return trade


def after_entry_path_1m(signal: Signal, bar: Bar) -> list[float]:
    path = intrabar_path(bar)
    for i in range(len(path) - 1):
        start = path[i]
        end = path[i + 1]
        if min(start, end) <= signal.entry <= max(start, end):
            return [signal.entry, end, *path[i + 2 :]]
    return [signal.entry, bar.close]


def fill_pending_on_1m(pending: PendingOrder, bar: Bar, ratio: float | None) -> tuple[ActiveTrade | None, Trade | None]:
    signal = pending.signal
    if not (bar.low <= signal.entry <= bar.high):
        return None, None
    active = ActiveTrade(signal=signal, entry_bar=bar, stop=signal.sl)
    if ratio is None:
        trade = manage_original_exit_on_path(active, bar, after_entry_path_1m(signal, bar), include_start_exit=False)
    else:
        trade = manage_exit_on_path(active, bar, ratio, after_entry_path_1m(signal, bar), include_start_exit=False)
    if trade is not None:
        return None, trade
    return active, None


def manage_original_exit_on_path(active: ActiveTrade, bar: Bar, path: list[float], include_start_exit: bool) -> Trade | None:
    if include_start_exit:
        trade = original_gap_exit_at_path_start(active, bar, path[0])
        if trade is not None:
            return trade
    for start, end in zip(path, path[1:]):
        candidates: list[tuple[str, float]] = []
        if min(start, end) <= active.stop <= max(start, end) and (include_start_exit or active.stop != start):
            candidates.append(("SL", active.stop))
        if min(start, end) <= active.signal.tp <= max(start, end) and (include_start_exit or active.signal.tp != start):
            candidates.append(("TP", active.signal.tp))
        if candidates:
            kind, price = min(candidates, key=lambda item: abs(item[1] - start))
            return finish_trade(active, bar, price, kind)
        include_start_exit = False
    return None


def original_gap_exit_at_path_start(active: ActiveTrade, bar: Bar, price: float) -> Trade | None:
    signal = active.signal
    if signal.direction == "long":
        if price <= active.stop:
            return finish_trade(active, bar, price, "SL")
        if price >= signal.tp:
            return finish_trade(active, bar, price, "TP")
    else:
        if price >= active.stop:
            return finish_trade(active, bar, price, "SL")
        if price <= signal.tp:
            return finish_trade(active, bar, price, "TP")
    return None


def generate_signals(five_bars: list[Bar], break_mode: str) -> list[Signal]:
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
    signals: list[Signal] = []
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
                entry = entry_for("long", last_swing_low, bar.high)
                signals.append(Signal(bar.index, bar.dt, kind, "long", last_swing_low, bar.high, last_swing_low_bar, entry, last_swing_low, bar.high))

        if bear_break:
            kind = "MSS" if bias in (1, 0) else "BOS"
            last_swing_low_broken = True
            bear_wick_extreme = None
            bias = -1
            if last_swing_high is not None:
                entry = entry_for("short", last_swing_high, bar.low)
                signals.append(Signal(bar.index, bar.dt, kind, "short", last_swing_high, bar.low, last_swing_high_bar, entry, last_swing_high, bar.low))

    return signals


def run_hybrid_backtest(five_bars: list[Bar], one_bars: list[Bar], ratio: float | None, break_mode: str) -> tuple[list[Signal], list[Trade], list[dict]]:
    signals = generate_signals(five_bars, break_mode)
    signal_times = [signal_available_from(signal) for signal in signals]
    signal_index = 0
    pending: PendingOrder | None = None
    active: ActiveTrade | None = None
    trades: list[Trade] = []
    skipped: list[dict] = []

    if one_bars:
        signal_index = bisect_left(signal_times, one_bars[0].dt)

    for bar in one_bars:
        while signal_index < len(signals) and signal_times[signal_index] <= bar.dt:
            signal = signals[signal_index]
            available_from = signal_times[signal_index]
            new_pending = PendingOrder(
                signal=signal,
                available_from=available_from,
                expires_after=available_from + timedelta(minutes=MAX_PENDING_MINUTES),
            )
            if active is None:
                if is_blocked_new_entry(available_from):
                    skipped.append({"time": signal.time, "reason": "blocked_new_entry_window", "direction": signal.direction, "entry": signal.entry})
                else:
                    pending = new_pending
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

        if active is None and pending is not None:
            if bar.dt < pending.available_from:
                continue
            if is_blocked_new_entry(bar.dt):
                continue
            if bar.dt > pending.expires_after:
                skipped.append({"time": bar.dt, "reason": "pending_expired", "direction": pending.signal.direction, "entry": pending.signal.entry})
                pending = None
                continue
            active, trade = fill_pending_on_1m(pending, bar, ratio)
            if trade is not None:
                trades.append(apply_commission(trade))
            if active is not None or trade is not None:
                pending = None

    if active is not None and one_bars:
        final = one_bars[-1]
        exit_price = final.close
        reason = "EOD"
        trades.append(apply_commission(finish_trade(active, final, exit_price, reason)))

    return signals, trades, skipped


def dollars_of(trade: Trade) -> float:
    return float(trade.dollars)


def summarize(trades: list[Trade], signals: list[Signal], skipped: list[dict]) -> dict:
    wins = [t for t in trades if dollars_of(t) > 0]
    losses = [t for t in trades if dollars_of(t) < 0]
    total = sum(dollars_of(t) for t in trades)
    gross_profit = sum(dollars_of(t) for t in wins)
    gross_loss = sum(dollars_of(t) for t in losses)
    profit_factor = gross_profit / abs(gross_loss) if gross_loss else None
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    daily: dict[str, float] = {}
    for trade in trades:
        equity += dollars_of(trade)
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity - peak)
        day = trade.exit_time.date().isoformat()
        daily[day] = daily.get(day, 0.0) + dollars_of(trade)
    return {
        "signals": len(signals),
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "be_exits": sum(1 for t in trades if t.exit_reason == "BE"),
        "win_rate": len(wins) / len(trades) * 100 if trades else 0.0,
        "net_pnl": total,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": profit_factor,
        "max_drawdown": max_drawdown,
        "winning_days": sum(1 for value in daily.values() if value > 0),
        "losing_days": sum(1 for value in daily.values() if value < 0),
        "skipped": len(skipped),
    }


def write_trades(path: Path, trades: list[Trade]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "signal_time", "entry_time", "exit_time", "kind", "direction", "entry",
            "sl", "final_sl", "tp", "break_even_moved", "break_even_time",
            "exit_price", "exit_reason", "points", "dollars", "bars_held",
        ])
        for trade in trades:
            writer.writerow([
                trade.signal_time,
                trade.entry_time,
                trade.exit_time,
                trade.kind,
                trade.direction,
                round(trade.entry, 1),
                round(trade.original_sl, 1),
                round(trade.final_sl, 1),
                round(trade.tp, 1),
                trade.break_even_moved,
                trade.break_even_time or "",
                round(trade.exit_price, 1),
                trade.exit_reason,
                round(trade.points, 1),
                round(trade.dollars, 2),
                trade.bars_held,
            ])


def run_scan(data_5m: Path, data_1m: Path) -> Path:
    five_all = load_bars(data_5m)
    one_all = load_bars(data_1m)
    latest = min(five_all[-1].dt, one_all[-1].dt)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    variants = [
        ("original_1m_exec", None, "Original TP/SL, 5m signal and 1m execution"),
        ("be_236_1m_exec", 0.236, "Move SL to entry after touching 23.6%, 1m execution"),
        ("be_500_1m_exec", 0.5, "Move SL to entry after touching 50.0%, 1m execution"),
    ]
    rows = []

    for break_mode in ["Loose", "Strict"]:
        for days in PERIODS:
            cutoff = latest - timedelta(days=days)
            five = clip_bars(five_all, cutoff)
            one = clip_bars(one_all, cutoff)
            for name, ratio, description in variants:
                signals, trades, skipped = run_hybrid_backtest(five, one, ratio, break_mode)
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
        "# Hybrid 5m Signal / 1m Execution Scan",
        "",
        f"- Commission: ${COMMISSION_PER_ROUND_TRIP:.2f} round trip per contract",
        f"- Blocked new entries: Beijing {BLOCKED_START_HOUR_BEIJING:02d}:00-{BLOCKED_END_HOUR_BEIJING:02d}:00",
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
