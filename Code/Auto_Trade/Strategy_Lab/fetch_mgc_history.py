#!/usr/bin/env python3
"""
Fetch MGC 5m history for multi-window strategy scans.

The output is a CSV with Beijing time:
  Strategy_Lab/data/mgc_5m_history.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from fetch_tv_mgc_5m import fetch_bars  # noqa: E402


SYMBOL = "COMEX_MINI:MGC1!"
INTERVAL = "5"
DEFAULT_DAYS = 360
DEFAULT_BARS = 120000
DEFAULT_TIMEOUT_SECONDS = 90
OUTPUT = Path(__file__).resolve().parent / "data" / "mgc_5m_history.csv"


def write_rows(rows, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "timestamp", "open", "high", "low", "close", "volume"])
        for bar in rows:
            writer.writerow(
                [
                    bar.dt.strftime("%Y-%m-%d %H:%M:%S"),
                    bar.ts,
                    bar.open,
                    bar.high,
                    bar.low,
                    bar.close,
                    "" if bar.volume is None else bar.volume,
                ]
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--bars", type=int, default=DEFAULT_BARS)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--output", default=str(OUTPUT))
    args = parser.parse_args()

    tz = ZoneInfo("Asia/Shanghai")
    cutoff = datetime.now(tz) - timedelta(days=args.days)
    bars = fetch_bars(SYMBOL, INTERVAL, args.bars, tz, args.timeout)
    rows = [bar for bar in bars if bar.dt >= cutoff]
    if not rows:
        print(f"No rows fetched for the last {args.days} days.", file=sys.stderr)
        return 2

    output = Path(args.output)
    write_rows(rows, output)
    print(f"Saved {len(rows)} rows: {output}")
    print(f"Range: {rows[0].dt.strftime('%Y-%m-%d %H:%M')} to {rows[-1].dt.strftime('%Y-%m-%d %H:%M')} Asia/Shanghai")
    if rows[0].dt > cutoff + timedelta(days=1):
        print(
            "Warning: fetched history starts later than requested cutoff. "
            "TradingView may have returned fewer historical bars than requested.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
