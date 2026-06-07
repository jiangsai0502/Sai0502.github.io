#!/usr/bin/env python3
"""
Create clean MGC data files by excluding Databento degraded dates.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DEGRADED_DATES = {
    "2025-09-17",
    "2025-09-24",
    "2025-11-28",
    "2026-03-15",
    "2026-03-16",
    "2026-04-10",
    "2026-05-24",
    "2026-05-31",
}


def row_date(row: dict[str, str]) -> str:
    return datetime.strptime(row["time"], "%Y-%m-%d %H:%M:%S").date().isoformat()


def filter_file(input_path: Path, output_path: Path) -> tuple[int, int]:
    kept = 0
    removed = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with input_path.open("r", encoding="utf-8") as src, output_path.open("w", newline="", encoding="utf-8") as dst:
        reader = csv.DictReader(src)
        writer = csv.DictWriter(dst, fieldnames=reader.fieldnames)
        writer.writeheader()
        for row in reader:
            if row_date(row) in DEGRADED_DATES:
                removed += 1
                continue
            writer.writerow(row)
            kept += 1
    return kept, removed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-1m", default=str(DATA_DIR / "mgc_1m_history.csv"))
    parser.add_argument("--input-5m", default=str(DATA_DIR / "mgc_5m_history.csv"))
    parser.add_argument("--output-1m", default=str(DATA_DIR / "mgc_1m_history_clean.csv"))
    parser.add_argument("--output-5m", default=str(DATA_DIR / "mgc_5m_history_clean.csv"))
    args = parser.parse_args()

    for input_path, output_path in [
        (Path(args.input_1m), Path(args.output_1m)),
        (Path(args.input_5m), Path(args.output_5m)),
    ]:
        kept, removed = filter_file(input_path, output_path)
        print(f"{input_path.name} -> {output_path.name}: kept={kept} removed={removed}")
    print("Excluded dates:", ", ".join(sorted(DEGRADED_DATES)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
