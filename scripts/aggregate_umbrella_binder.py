#!/usr/bin/env python3
"""Aggregate per-L umbrella MBAR Binder results into one CSV table."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def load_report(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["source"] = str(path.resolve())
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path,
                        help="analyze_umbrella.py JSON outputs")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows: list[dict[str, object]] = []
    for path in args.reports:
        report = load_report(path)
        rows.append({
            "L": report.get("L"),
            "Z": report.get("Z"),
            "m2": report.get("m2"),
            "binder": report.get("binder"),
            "binder_error": report.get("binder_error"),
            "mean_M2": report.get("mean_M2"),
            "mean_M2_error": report.get("mean_M2_error"),
            "effective_sample_size": report.get("effective_sample_size"),
            "minimum_neighbor_overlap": min(report.get("neighbor_overlap", [0.0])),
            "source": report["source"],
        })
    rows.sort(key=lambda row: int(row["L"]))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {args.output} ({len(rows)} lattice sizes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
