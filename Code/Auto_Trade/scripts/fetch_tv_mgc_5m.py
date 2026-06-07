#!/usr/bin/env python3
"""
Fetch TradingView 5-minute OHLC bars for MGC and filter a local time window.

Default:
  symbol: COMEX_MINI:MGC1!
  date: latest completed window date in Asia/Shanghai
  window: 17:00-22:00 Asia/Shanghai

Edit the QUERY_* values below to change the default query without typing CLI args.
Date format: YYYY-MM-DD, e.g. 2026-06-01. Empty QUERY_DATE means auto date.
Time format: HH:MM in 24-hour Beijing time, e.g. 17:00 or 22:00.

Install dependency:
  python3 -m pip install websocket-client

Run:
  python3 scripts/fetch_tv_mgc_5m.py

Examples:
  python3 scripts/fetch_tv_mgc_5m.py --date 2026-06-01
  python3 scripts/fetch_tv_mgc_5m.py --symbol COMEX_MINI:MGCM2026 --output mgc.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import string
import sys
import time as time_module
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    import websocket
    from websocket import WebSocketConnectionClosedException, WebSocketTimeoutException
except ImportError:
    print(
        "Missing dependency: websocket-client\n"
        "Install it with:\n"
        "  python3 -m pip install websocket-client",
        file=sys.stderr,
    )
    raise SystemExit(1)


TV_WS_URL = "wss://data.tradingview.com/socket.io/websocket"

# Default query settings. Change these values, then run this file directly.
# QUERY_DATE format: "YYYY-MM-DD", e.g. "2026-06-01"; "" means auto date.
# QUERY_START/QUERY_END format: "HH:MM" in 24-hour Beijing time, e.g. "17:00".
# QUERY_OUTPUT: "" means save to this script's folder with the current timestamp.
QUERY_SYMBOL = "COMEX_MINI:MGC1!"
QUERY_DATE = "2026-06-01"
QUERY_START = "6:00"
QUERY_END = "7:00"
QUERY_INTERVAL = "5"
QUERY_BARS = 1500
QUERY_TIMEOUT = 30
QUERY_OUTPUT = ""


@dataclass
class Bar:
    ts: int
    dt: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


def session_id(prefix: str) -> str:
    suffix = "".join(random.choice(string.ascii_lowercase) for _ in range(12))
    return f"{prefix}_{suffix}"


def wrap_message(method: str, params: list) -> str:
    payload = json.dumps({"m": method, "p": params}, separators=(",", ":"))
    return f"~m~{len(payload)}~m~{payload}"


def iter_tv_messages(raw: str):
    for match in re.finditer(r"~m~(\d+)~m~", raw):
        start = match.end()
        size = int(match.group(1))
        chunk = raw[start : start + size]
        if len(chunk) != size:
            continue
        try:
            yield json.loads(chunk)
        except json.JSONDecodeError:
            continue


def parse_series_payload(msg: dict, tz: ZoneInfo) -> list[Bar]:
    bars: list[Bar] = []
    if msg.get("m") not in {"timescale_update", "du"}:
        return bars

    payload = msg.get("p", [])
    if len(payload) < 2 or not isinstance(payload[1], dict):
        return bars

    for series in payload[1].values():
        raw_bars = series.get("s") if isinstance(series, dict) else None
        if not isinstance(raw_bars, list):
            continue
        for item in raw_bars:
            values = item.get("v") if isinstance(item, dict) else None
            if not values or len(values) < 5:
                continue
            ts = int(values[0])
            bars.append(
                Bar(
                    ts=ts,
                    dt=datetime.fromtimestamp(ts, tz),
                    open=float(values[1]),
                    high=float(values[2]),
                    low=float(values[3]),
                    close=float(values[4]),
                    volume=float(values[5]) if len(values) > 5 and values[5] is not None else None,
                )
            )
    return bars


class TradingViewError(RuntimeError):
    pass


def describe_tv_error(msg: dict) -> str | None:
    method = msg.get("m")
    params = msg.get("p", [])
    if method == "symbol_error" and len(params) >= 3:
        return f"{params[2]}: {params[1]}"
    if method == "series_error" and len(params) >= 4:
        return f"{params[3]}: {params[1]}"
    if method == "critical_error" and len(params) >= 3:
        return f"{params[2]}: {params[1]}"
    return None


def fetch_bars(symbol: str, interval: str, bars_count: int, tz: ZoneInfo, timeout: int) -> list[Bar]:
    chart_session = session_id("cs")
    ws = websocket.create_connection(
        TV_WS_URL,
        timeout=20,
        origin="https://www.tradingview.com",
        header=[
            "User-Agent: Mozilla/5.0",
            "Accept-Encoding: gzip, deflate, br",
        ],
    )

    symbol_payload = json.dumps(
        {
            "symbol": symbol,
            "adjustment": "splits",
            "session": "regular",
        },
        separators=(",", ":"),
    )
    bars: dict[int, Bar] = {}
    errors: list[str] = []
    deadline = time_module.monotonic() + timeout

    try:
        messages = [
            ("set_auth_token", ["unauthorized_user_token"]),
            ("chart_create_session", [chart_session, ""]),
            ("resolve_symbol", [chart_session, "symbol_1", f"={symbol_payload}"]),
            ("create_series", [chart_session, "s1", "s1", "symbol_1", interval, bars_count]),
        ]
        for method, params in messages:
            ws.send(wrap_message(method, params))

        while time_module.monotonic() < deadline:
            try:
                raw = ws.recv()
            except WebSocketTimeoutException:
                continue
            except WebSocketConnectionClosedException:
                if bars:
                    return [bars[k] for k in sorted(bars)]
                raise
            if isinstance(raw, str) and raw.startswith("~h~"):
                # TradingView heartbeat. Echo it back to keep the socket alive.
                try:
                    ws.send(raw)
                except Exception:
                    pass
                continue
            for msg in iter_tv_messages(raw):
                error = describe_tv_error(msg)
                if error:
                    errors.append(error)
                for bar in parse_series_payload(msg, tz):
                    bars[bar.ts] = bar
                if msg.get("m") == "series_completed":
                    return [bars[k] for k in sorted(bars)]
        if bars:
            return [bars[k] for k in sorted(bars)]
        detail = "; ".join(dict.fromkeys(errors)) if errors else "no data received before timeout"
        raise TradingViewError(f"TradingView request failed for {symbol}: {detail}")
    finally:
        ws.close()


def parse_clock(value: str) -> time:
    return datetime.strptime(value, "%H:%M").time()


def default_query_date(tz: ZoneInfo, end: time) -> str:
    now = datetime.now(tz)
    if now.time().replace(second=0, microsecond=0) < end:
        return (now.date() - timedelta(days=1)).isoformat()
    return now.date().isoformat()


def filter_window(bars: list[Bar], day: str, start: time, end: time) -> list[Bar]:
    return [
        bar
        for bar in bars
        if bar.dt.date().isoformat() == day and start <= bar.dt.time().replace(second=0, microsecond=0) <= end
    ]


def timestamp_output_path(tz: ZoneInfo) -> str:
    timestamp = datetime.now(tz).strftime("%Y%m%d_%H%M%S")
    return str(Path(__file__).resolve().parent / f"{timestamp}.csv")


def write_csv(rows: list[Bar], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "open", "high", "low", "close", "volume"])
        for bar in rows:
            writer.writerow(
                [
                    bar.dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
                    bar.open,
                    bar.high,
                    bar.low,
                    bar.close,
                    "" if bar.volume is None else bar.volume,
                ]
            )


def print_table(rows: list[Bar]) -> None:
    print("time,open,high,low,close,volume")
    for bar in rows:
        vol = "" if bar.volume is None else str(bar.volume)
        print(f"{bar.dt.strftime('%Y-%m-%d %H:%M:%S %Z')},{bar.open},{bar.high},{bar.low},{bar.close},{vol}")


def main() -> int:
    tz = ZoneInfo("Asia/Shanghai")
    default_date = QUERY_DATE or default_query_date(tz, parse_clock(QUERY_END))
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--symbol",
        default=QUERY_SYMBOL,
        help="TradingView symbol, e.g. COMEX_MINI:MGC1! or COMEX_MINI:MGCM2026",
    )
    parser.add_argument("--date", default=default_date, help="Date in Asia/Shanghai, YYYY-MM-DD")
    parser.add_argument("--start", default=QUERY_START, help="Start time in Asia/Shanghai, HH:MM")
    parser.add_argument("--end", default=QUERY_END, help="End time in Asia/Shanghai, HH:MM")
    parser.add_argument("--interval", default=QUERY_INTERVAL, help="TradingView interval. 5 means 5 minutes.")
    parser.add_argument("--bars", type=int, default=QUERY_BARS, help="Number of recent bars to request")
    parser.add_argument("--timeout", type=int, default=QUERY_TIMEOUT, help="TradingView websocket timeout in seconds")
    parser.add_argument("--output", default=QUERY_OUTPUT, help="CSV output path. Empty means timestamp CSV next to script.")
    args = parser.parse_args()

    try:
        bars = fetch_bars(args.symbol, args.interval, args.bars, tz, args.timeout)
    except TradingViewError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    start = parse_clock(args.start)
    end = parse_clock(args.end)
    rows = filter_window(bars, args.date, start, end)
    if not rows:
        if bars:
            print(
                "No rows found for "
                f"{args.date} {args.start}-{args.end} Asia/Shanghai. "
                f"Fetched range: {bars[0].dt.strftime('%Y-%m-%d %H:%M')} to "
                f"{bars[-1].dt.strftime('%Y-%m-%d %H:%M')} Asia/Shanghai. "
                "Try --date/--start/--end or increase --bars.",
                file=sys.stderr,
            )
        else:
            print("No rows found. Try increasing --bars or checking --symbol/--date.", file=sys.stderr)
        return 2

    print_table(rows)
    output_path = args.output or timestamp_output_path(tz)
    write_csv(rows, output_path)
    print(f"\nSaved CSV: {output_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
