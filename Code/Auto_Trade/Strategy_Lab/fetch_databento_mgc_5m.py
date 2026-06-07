#!/usr/bin/env python3
"""
Fetch MGC continuous futures data from Databento, one month at a time.

Usage:
  DATABENTO_API_KEY=... /opt/anaconda3/envs/py3.10/bin/python Strategy_Lab/fetch_databento_mgc_5m.py --days 360

This script downloads Databento `ohlcv-1m` for `MGC.c.0`, aggregates it to
5-minute bars in Beijing time, and writes:
  Strategy_Lab/data/mgc_5m_history.csv

It estimates cost before each monthly request and prints the estimate.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import databento as db
import pandas as pd


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "data" / "mgc_5m_history.csv"
DATASET = "GLBX.MDP3"
SYMBOL = "MGC.c.0"
STYPE_IN = "continuous"
SCHEMA = "ohlcv-1m"


def month_chunks(start: datetime, end: datetime):
    cur = start
    while cur < end:
        if cur.month == 12:
            nxt = datetime(cur.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            nxt = datetime(cur.year, cur.month + 1, 1, tzinfo=timezone.utc)
        yield cur, min(nxt, end)
        cur = min(nxt, end)


def normalize_prices(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ["open", "high", "low", "close"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
        if out[col].dropna().abs().median() > 100000:
            out[col] = out[col] / 1_000_000_000
    out["volume"] = pd.to_numeric(out["volume"], errors="coerce").fillna(0)
    return out


def aggregate_to_5m(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    if df.index.tz is None:
        df = df.tz_localize("UTC")
    beijing = df.tz_convert("Asia/Shanghai")
    bars = beijing.resample("5min", label="left", closed="left").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    bars = bars.dropna(subset=["open", "high", "low", "close"])
    return bars


def write_csv(bars: pd.DataFrame, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "timestamp", "open", "high", "low", "close", "volume"])
        for ts, row in bars.iterrows():
            writer.writerow(
                [
                    ts.strftime("%Y-%m-%d %H:%M:%S"),
                    int(ts.timestamp()),
                    float(row["open"]),
                    float(row["high"]),
                    float(row["low"]),
                    float(row["close"]),
                    int(row["volume"]),
                ]
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=360)
    parser.add_argument("--max-months", type=int, default=0, help="0 means no limit")
    parser.add_argument("--dry-run", action="store_true", help="Only estimate costs")
    parser.add_argument("--output", default=str(OUTPUT))
    args = parser.parse_args()

    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        print("Missing DATABENTO_API_KEY environment variable.", file=sys.stderr)
        return 2

    client = db.Historical(key)
    dataset_range = client.metadata.get_dataset_range(DATASET)
    available_end = pd.Timestamp(dataset_range["end"]).to_pydatetime()
    if available_end.tzinfo is None:
        available_end = available_end.replace(tzinfo=timezone.utc)
    end = min(datetime.now(timezone.utc), available_end)
    start = end - timedelta(days=args.days)
    frames = []
    total_estimated_cost = 0.0
    for i, (chunk_start, chunk_end) in enumerate(month_chunks(start, end), start=1):
        if args.max_months and i > args.max_months:
            break
        cost = client.metadata.get_cost(
            dataset=DATASET,
            symbols=SYMBOL,
            stype_in=STYPE_IN,
            schema=SCHEMA,
            start=chunk_start.isoformat(),
            end=chunk_end.isoformat(),
        )
        total_estimated_cost += cost
        print(f"Cost estimate {chunk_start.date()} -> {chunk_end.date()}: ${cost:.6f}", flush=True)
        if args.dry_run:
            continue
        store = client.timeseries.get_range(
            dataset=DATASET,
            symbols=SYMBOL,
            stype_in=STYPE_IN,
            schema=SCHEMA,
            start=chunk_start.isoformat(),
            end=chunk_end.isoformat(),
        )
        df = store.to_df()
        if not df.empty:
            df = normalize_prices(df)
            df = df[["open", "high", "low", "close", "volume"]]
        if not df.empty:
            frames.append(df)
            print(f"Downloaded rows: {len(df)}", flush=True)

    if args.dry_run:
        print(f"Dry run complete. Estimated total cost: ${total_estimated_cost:.6f}. No data downloaded.")
        return 0
    if not frames:
        print("No data downloaded.", file=sys.stderr)
        return 2

    raw = pd.concat(frames).sort_index()
    raw = raw[~raw.index.duplicated(keep="last")]
    bars = aggregate_to_5m(raw)
    output = Path(args.output)
    write_csv(bars, output)
    print(f"Saved {len(bars)} 5m bars: {output}")
    print(f"Range: {bars.index[0].strftime('%Y-%m-%d %H:%M')} to {bars.index[-1].strftime('%Y-%m-%d %H:%M')} Asia/Shanghai")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
