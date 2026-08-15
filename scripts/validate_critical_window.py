#!/usr/bin/env python3
"""Validate reweighting quality around Binder crossings and suggest new sources."""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path

from find_binder_crossings import DEFAULT_LEVELS, Point, find_crossings, read_points


def load_records(path: Path) -> dict[tuple[int, float], list[dict[str, str]]]:
    groups: dict[tuple[int, float], list[dict[str, str]]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {
            "L", "Z", "m2", "U4", "ess_fraction", "top1_m4_fraction",
            "usable_source_count", "warning_status",
        }
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path}: missing columns: {', '.join(sorted(missing))}")
        if "kish_ess" not in (reader.fieldnames or ()) and "ESS" not in (reader.fieldnames or ()):
            raise ValueError(f"{path}: missing ESS column (expected kish_ess or ESS)")
        for row in reader:
            groups[(int(float(row["L"])), float(row["Z"]))].append(row)
    for rows in groups.values():
        rows.sort(key=lambda row: float(row["m2"]))
    return groups


def row_ok(row: dict[str, str], args: argparse.Namespace) -> bool:
    return (
        row["warning_status"].strip().lower() == "ok"
        and float(row.get("kish_ess") or row.get("ESS") or "nan") >= args.min_ess
        and float(row["ess_fraction"]) >= args.min_ess_fraction
        and float(row["top1_m4_fraction"]) <= args.max_top1_m4_fraction
        and int(float(row["usable_source_count"])) >= args.min_usable_sources
    )


def write_suggestions(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    # Deliberately match submit_reweight_{tsp,array,bsub}.py --points-csv.
    fields = ["Z", "m2"]
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(({key: row[key] for key in fields} for row in rows))
    temporary.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("--level", dest="levels", type=float, action="append")
    parser.add_argument("--margin", type=float, default=0.01)
    parser.add_argument("--min-ess", type=float, default=50.0)
    parser.add_argument("--min-ess-fraction", type=float, default=0.01)
    parser.add_argument("--max-top1-m4-fraction", type=float, default=0.5)
    parser.add_argument("--min-usable-sources", type=int, default=2)
    parser.add_argument("--suggestions", type=Path)
    args = parser.parse_args()
    args.levels = args.levels or list(DEFAULT_LEVELS)
    if args.margin < 0 or not math.isfinite(args.margin):
        parser.error("--margin must be finite and non-negative")
    if args.min_ess < 0 or args.min_ess_fraction < 0:
        parser.error("ESS thresholds must be non-negative")
    if args.max_top1_m4_fraction < 0:
        parser.error("--max-top1-m4-fraction must be non-negative")
    if args.min_usable_sources < 1:
        parser.error("--min-usable-sources must be positive")
    return args


def main() -> int:
    args = parse_args()
    grouped_points = read_points(args.csv_file)
    records = load_records(args.csv_file)
    suggestions: list[dict[str, object]] = []
    failures = 0
    print("L,Z,m2_low,m2_high,rows,bad_rows,status")
    for (lattice, z_value), rows in sorted(records.items()):
        points: list[Point] = [
            point for point in grouped_points[lattice]
            if math.isclose(point.Z, z_value, rel_tol=0.0, abs_tol=1e-12)
        ]
        crossings = [
            crossing
            for level in args.levels
            for crossing in find_crossings(points, level, include_warnings=True)
            if crossing["m2"] != ""
        ]
        if not crossings:
            failures += 1
            print(f"{lattice},{z_value:g},,,,0,no_crossing")
            continue
        crossing_masses = sorted(float(item["m2"]) for item in crossings)
        low = crossing_masses[0] - args.margin
        high = crossing_masses[-1] + args.margin
        window = [row for row in rows if low <= float(row["m2"]) <= high]
        coverage_ok = bool(rows) and float(rows[0]["m2"]) <= low and float(rows[-1]["m2"]) >= high
        bad = [row for row in window if not row_ok(row, args)]
        status = "ok" if coverage_ok and window and not bad else "needs_sources"
        failures += status != "ok"
        print(f"{lattice},{z_value:g},{low:.9g},{high:.9g},{len(window)},{len(bad)},{status}")
        if status != "ok":
            candidate_masses = {low, high, *crossing_masses}
            if bad:
                bad_masses = [float(row["m2"]) for row in bad]
                candidate_masses.add(0.5 * (min(bad_masses) + max(bad_masses)))
            for mass in sorted(candidate_masses):
                suggestions.append({
                    "L": lattice, "Z": z_value, "m2": f"{mass:.12g}",
                    "reason": "window_edge" if mass in (low, high) else
                              "crossing" if mass in crossing_masses else "failing_region_midpoint",
                })
    if args.suggestions is not None:
        write_suggestions(args.suggestions, suggestions)
        print(f"wrote {args.suggestions}")
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
