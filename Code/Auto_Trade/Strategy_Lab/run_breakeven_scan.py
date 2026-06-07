#!/usr/bin/env python3
"""
Compare break-even variants against the original MSS/BOS 61.8 backtest.
"""

from __future__ import annotations

import csv
from datetime import timedelta
from pathlib import Path
from statistics import mean

from backtest_mss_618 import Bar, Signal, Trade as OriginalTrade, load_bars, run_backtest
from backtest_mss_618_breakeven import Trade as BETrade, run_backtest_breakeven


ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "mgc_5m_history.csv"
REPORT_ROOT = ROOT / "reports" / "breakeven_scan"
PERIODS = list(range(30, 361, 30))
VARIANTS = [
    ("original", None, "Original: SL at waveStart until TP/SL"),
    ("be_236", 0.236, "Move SL to entry after touching 23.6%"),
    ("be_500", 0.5, "Move SL to entry after touching 50.0%"),
]


def renumber_bars(bars: list[Bar]) -> list[Bar]:
    return [
        Bar(i, bar.dt, bar.open, bar.high, bar.low, bar.close, bar.volume)
        for i, bar in enumerate(bars)
    ]


def dollars_of(trade) -> float:
    return float(trade.dollars)


def exit_reason_of(trade) -> str:
    return str(trade.exit_reason)


def summarize(trades: list, signals: list[Signal], skipped: list[dict]) -> dict:
    wins = [t for t in trades if dollars_of(t) > 0]
    losses = [t for t in trades if dollars_of(t) < 0]
    total = sum(dollars_of(t) for t in trades)
    gross_profit = sum(dollars_of(t) for t in wins)
    gross_loss = sum(dollars_of(t) for t in losses)
    profit_factor = gross_profit / abs(gross_loss) if gross_loss else None
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    daily = {}
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
        "be_exits": sum(1 for t in trades if exit_reason_of(t) == "BE"),
        "win_rate": len(wins) / len(trades) * 100 if trades else 0.0,
        "net_pnl": total,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": profit_factor,
        "avg_win": mean([dollars_of(t) for t in wins]) if wins else 0.0,
        "avg_loss": mean([dollars_of(t) for t in losses]) if losses else 0.0,
        "max_drawdown": max_drawdown,
        "winning_days": sum(1 for value in daily.values() if value > 0),
        "losing_days": sum(1 for value in daily.values() if value < 0),
        "skipped": len(skipped),
    }


def write_trades(path: Path, trades: list) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "signal_time", "entry_time", "exit_time", "kind", "direction", "entry",
            "sl", "final_sl", "tp", "break_even_moved", "break_even_time",
            "exit_price", "exit_reason", "points", "dollars", "bars_held",
        ])
        for trade in trades:
            original_sl = getattr(trade, "original_sl", getattr(trade, "sl", ""))
            final_sl = getattr(trade, "final_sl", getattr(trade, "sl", ""))
            be_moved = getattr(trade, "break_even_moved", False)
            be_time = getattr(trade, "break_even_time", "")
            writer.writerow([
                trade.signal_time, trade.entry_time, trade.exit_time, trade.kind, trade.direction,
                round(trade.entry, 1), round(original_sl, 1), round(final_sl, 1), round(trade.tp, 1),
                be_moved, be_time, round(trade.exit_price, 1), trade.exit_reason,
                round(trade.points, 1), round(trade.dollars, 2), trade.bars_held,
            ])


def main() -> int:
    all_bars = load_bars(DATA_PATH)
    latest = all_bars[-1].dt
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    rows = []

    for days in PERIODS:
        cutoff = latest - timedelta(days=days)
        window = renumber_bars([bar for bar in all_bars if bar.dt >= cutoff])
        for name, ratio, description in VARIANTS:
            if ratio is None:
                signals, trades, skipped = run_backtest(window)
            else:
                signals, trades, skipped = run_backtest_breakeven(window, ratio)
            summary = summarize(trades, signals, skipped)
            period_dir = REPORT_ROOT / f"{days:03d}d" / name
            period_dir.mkdir(parents=True, exist_ok=True)
            write_trades(period_dir / "trades.csv", trades)
            (period_dir / "report.md").write_text(
                "\n".join(
                    [
                        f"# {name} - {days}d",
                        "",
                        f"- Description: {description}",
                        f"- Data range: {window[0].dt} to {window[-1].dt}",
                        f"- Trades: {summary['trades']}",
                        f"- Win rate: {summary['win_rate']:.2f}%",
                        f"- Net PnL: ${summary['net_pnl']:.2f}",
                        f"- Profit factor: {summary['profit_factor']:.2f}" if summary["profit_factor"] is not None else "- Profit factor: n/a",
                        f"- Max drawdown: ${summary['max_drawdown']:.2f}",
                        f"- BE exits: {summary['be_exits']}",
                    ]
                ) + "\n",
                encoding="utf-8",
            )
            rows.append(
                {
                    "days": days,
                    "variant": name,
                    "description": description,
                    "actual_days": (window[-1].dt - window[0].dt).total_seconds() / 86400,
                    **summary,
                }
            )

    summary_csv = REPORT_ROOT / "summary.csv"
    with summary_csv.open("w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "days", "variant", "description", "actual_days", "signals", "trades",
            "wins", "losses", "be_exits", "win_rate", "net_pnl", "gross_profit",
            "gross_loss", "profit_factor", "avg_win", "avg_loss", "max_drawdown",
            "winning_days", "losing_days", "skipped",
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
        "# Break-even Variant Scan",
        "",
        "| Days | Variant | Trades | BE Exits | Win Rate | Net PnL | PF | Max DD |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        pf = f"{row['profit_factor']:.2f}" if row["profit_factor"] is not None else "n/a"
        lines.append(
            f"| {row['days']} | {row['variant']} | {row['trades']} | {row['be_exits']} | "
            f"{row['win_rate']:.2f}% | ${row['net_pnl']:.2f} | {pf} | ${row['max_drawdown']:.2f} |"
        )
    summary_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(summary_md.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
