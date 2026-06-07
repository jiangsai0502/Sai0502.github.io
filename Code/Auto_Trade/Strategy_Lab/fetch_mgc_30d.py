#!/usr/bin/env python3
"""
Fetch recent MGC 5m data for Strategy_Lab.

The output is a CSV with Beijing time:
  Strategy_Lab/data/mgc_5m_last30d.csv
"""

from __future__ import annotations

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
DAYS = 30
BARS = 12000
TIMEOUT_SECONDS = 45
OUTPUT = Path(__file__).resolve().parent / "data" / "mgc_5m_last30d.csv"


def main() -> int:
    tz = ZoneInfo("Asia/Shanghai")
    cutoff = datetime.now(tz) - timedelta(days=DAYS)
    bars = fetch_bars(SYMBOL, INTERVAL, BARS, tz, TIMEOUT_SECONDS)
    rows = [bar for bar in bars if bar.dt >= cutoff]
    if not rows:
        print("No rows fetched for the last 30 days.", file=sys.stderr)
        return 2

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
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

    print(f"Saved {len(rows)} rows: {OUTPUT}")
    print(f"Range: {rows[0].dt.strftime('%Y-%m-%d %H:%M')} to {rows[-1].dt.strftime('%Y-%m-%d %H:%M')} Asia/Shanghai")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
