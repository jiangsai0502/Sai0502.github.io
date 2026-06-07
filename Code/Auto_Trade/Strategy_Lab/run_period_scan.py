#!/usr/bin/env python3
"""
Run rolling-window backtests for 30, 60, 90 ... 360 days.
"""

from __future__ import annotations

import csv
from datetime import timedelta
from pathlib import Path
from statistics import mean

from backtest_mss_618 import (
    BREAK_MODE,
    MAX_PENDING_BARS,
    MGC_DOLLARS_PER_POINT,
    QTY,
    Bar,
    Signal,
    Trade,
    load_bars,
    run_backtest,
)


ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "mgc_5m_history.csv"
REPORT_ROOT = ROOT / "reports" / "period_scan"
SUMMARY_CSV = REPORT_ROOT / "summary.csv"
SUMMARY_MD = REPORT_ROOT / "summary.md"
PERIODS = list(range(30, 361, 30))
DATA_SOURCE_NOTE = "Databento GLBX.MDP3 MGC.c.0 continuous futures, ohlcv-1m aggregated to 5m."


def renumber_bars(bars: list[Bar]) -> list[Bar]:
    return [
        Bar(
            index=i,
            dt=bar.dt,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
        )
        for i, bar in enumerate(bars)
    ]


def summarize(trades: list[Trade], signals: list[Signal], skipped: list[dict]) -> dict:
    wins = [t for t in trades if t.dollars > 0]
    losses = [t for t in trades if t.dollars < 0]
    total = sum(t.dollars for t in trades)
    gross_profit = sum(t.dollars for t in wins)
    gross_loss = sum(t.dollars for t in losses)
    profit_factor = gross_profit / abs(gross_loss) if gross_loss else None
    avg_win = mean([t.dollars for t in wins]) if wins else 0.0
    avg_loss = mean([t.dollars for t in losses]) if losses else 0.0
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for trade in trades:
        equity += trade.dollars
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity - peak)

    daily: dict[str, float] = {}
    for trade in trades:
        key = trade.exit_time.date().isoformat()
        daily[key] = daily.get(key, 0.0) + trade.dollars

    return {
        "signals": len(signals),
        "trades": len(trades),
        "skipped": len(skipped),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (len(wins) / len(trades) * 100) if trades else 0.0,
        "net_pnl": total,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": profit_factor,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "max_drawdown": max_drawdown,
        "winning_days": sum(1 for value in daily.values() if value > 0),
        "losing_days": sum(1 for value in daily.values() if value < 0),
    }


def write_period_outputs(period_dir: Path, bars: list[Bar], signals: list[Signal], trades: list[Trade], skipped: list[dict], summary: dict) -> None:
    period_dir.mkdir(parents=True, exist_ok=True)

    with (period_dir / "signals.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "kind", "direction", "entry", "sl", "tp", "wave_start", "wave_end", "wave_start_bar"])
        for signal in signals:
            writer.writerow([signal.time, signal.kind, signal.direction, round(signal.entry, 1), round(signal.sl, 1), round(signal.tp, 1), round(signal.wave_start, 1), round(signal.wave_end, 1), signal.wave_start_bar])

    with (period_dir / "trades.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["signal_time", "entry_time", "exit_time", "kind", "direction", "entry", "sl", "tp", "exit_price", "exit_reason", "points", "dollars", "bars_held"])
        for trade in trades:
            writer.writerow([trade.signal_time, trade.entry_time, trade.exit_time, trade.kind, trade.direction, round(trade.entry, 1), round(trade.sl, 1), round(trade.tp, 1), round(trade.exit_price, 1), trade.exit_reason, round(trade.points, 1), round(trade.dollars, 2), trade.bars_held])

    with (period_dir / "skipped.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "reason", "direction", "entry"])
        for row in skipped:
            writer.writerow([row.get("time"), row.get("reason"), row.get("direction"), row.get("entry")])

    daily: dict[str, dict] = {}
    for trade in trades:
        key = trade.exit_time.date().isoformat()
        row = daily.setdefault(key, {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0})
        row["trades"] += 1
        row["wins"] += 1 if trade.dollars > 0 else 0
        row["losses"] += 1 if trade.dollars < 0 else 0
        row["pnl"] += trade.dollars

    with (period_dir / "daily_summary.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "trades", "wins", "losses", "pnl"])
        for day in sorted(daily):
            row = daily[day]
            writer.writerow([day, row["trades"], row["wins"], row["losses"], round(row["pnl"], 2)])

    report = [
        f"# MGC 5m MSS/BOS 61.8 Backtest - {period_dir.name}",
        "",
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
        f"- Signals: {summary['signals']}",
        f"- Filled trades: {summary['trades']}",
        f"- Skipped/expired records: {summary['skipped']}",
        f"- Wins: {summary['wins']}",
        f"- Losses: {summary['losses']}",
        f"- Win rate: {summary['win_rate']:.2f}%",
        f"- Net PnL: ${summary['net_pnl']:.2f}",
        f"- Gross profit: ${summary['gross_profit']:.2f}",
        f"- Gross loss: ${summary['gross_loss']:.2f}",
        f"- Profit factor: {summary['profit_factor']:.2f}" if summary["profit_factor"] is not None else "- Profit factor: n/a",
        f"- Average win: ${summary['avg_win']:.2f}",
        f"- Average loss: ${summary['avg_loss']:.2f}",
        f"- Max drawdown: ${summary['max_drawdown']:.2f}",
        f"- Winning days: {summary['winning_days']}",
        f"- Losing days: {summary['losing_days']}",
    ]
    (period_dir / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")


def main() -> int:
    if not DATA_PATH.exists():
        print(f"Missing data file: {DATA_PATH}")
        print("Run Strategy_Lab/fetch_mgc_history.py first.")
        return 2

    all_bars = load_bars(DATA_PATH)
    if not all_bars:
        print("No bars.")
        return 2

    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    rows = []
    latest = all_bars[-1].dt
    for days in PERIODS:
        cutoff = latest - timedelta(days=days)
        window = renumber_bars([bar for bar in all_bars if bar.dt >= cutoff])
        if len(window) < 10:
            continue
        signals, trades, skipped = run_backtest(window)
        summary = summarize(trades, signals, skipped)
        period_dir = REPORT_ROOT / f"{days:03d}d"
        write_period_outputs(period_dir, window, signals, trades, skipped, summary)
        rows.append(
            {
                "days": days,
                "actual_days": (window[-1].dt - window[0].dt).total_seconds() / 86400,
                "start": window[0].dt,
                "end": window[-1].dt,
                "bars": len(window),
                **summary,
            }
        )

    with SUMMARY_CSV.open("w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "days",
            "actual_days",
            "start",
            "end",
            "bars",
            "signals",
            "trades",
            "skipped",
            "wins",
            "losses",
            "win_rate",
            "net_pnl",
            "gross_profit",
            "gross_loss",
            "profit_factor",
            "avg_win",
            "avg_loss",
            "max_drawdown",
            "winning_days",
            "losing_days",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out = row.copy()
            for key, value in list(out.items()):
                if isinstance(value, float):
                    out[key] = round(value, 2)
            writer.writerow(out)

    md = [
        "# MGC 5m MSS/BOS 61.8 Period Scan",
        "",
        f"- Full data range: {all_bars[0].dt} to {all_bars[-1].dt} Beijing time",
        f"- Full actual span: {(all_bars[-1].dt - all_bars[0].dt).total_seconds() / 86400:.1f} days",
        f"- Full bars: {len(all_bars)}",
        f"- Data source: {DATA_SOURCE_NOTE}",
        f"- Break mode: {BREAK_MODE}",
        f"- Contract assumption: MGC ${MGC_DOLLARS_PER_POINT:.0f}/point, qty {QTY}",
        "",
    ]
    if (all_bars[-1].dt - all_bars[0].dt).total_seconds() / 86400 < max(PERIODS) - 10:
        md.extend(
            [
                "Warning: available data is shorter than the largest requested window.",
                "Longer requested windows use the full available range.",
                "",
            ]
        )
    md.extend(
        [
            "| Requested Days | Actual Days | Trades | Win Rate | Net PnL | Profit Factor | Max DD | Winning Days | Losing Days |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in rows:
        pf = f"{row['profit_factor']:.2f}" if row["profit_factor"] is not None else "n/a"
        md.append(
            f"| {row['days']} | {row['actual_days']:.1f} | {row['trades']} | {row['win_rate']:.2f}% | "
            f"${row['net_pnl']:.2f} | {pf} | ${row['max_drawdown']:.2f} | "
            f"{row['winning_days']} | {row['losing_days']} |"
        )
    md.extend(
        [
            "",
            "Each period has its own `report.md`, `trades.csv`, `signals.csv`, `skipped.csv`, and `daily_summary.csv` folder.",
        ]
    )
    SUMMARY_MD.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(SUMMARY_MD.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
