#!/usr/bin/env python3
"""Find linearly interpolated U4 level crossings in reweight_binder.py output."""

from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_LEVELS = (1.0 / 3.0, 0.465)
COORDINATES = ("t", "Z", "m2")


@dataclass(frozen=True)
class Point:
    row: int
    L: int
    t: float
    Z: float
    m2: float
    U4: float


def finite_float(raw: str | None, *, column: str, row: int, path: Path) -> float:
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path}:{row}: invalid {column} value {raw!r}") from exc
    if not math.isfinite(value):
        raise ValueError(f"{path}:{row}: non-finite {column} value")
    return value


def read_points(path: Path) -> dict[int, list[Point]]:
    grouped: dict[int, list[Point]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"L", "U4", *COORDINATES}
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path}: missing columns: {', '.join(sorted(missing))}")
        for row_number, record in enumerate(reader, start=2):
            lattice_value = finite_float(
                record.get("L"), column="L", row=row_number, path=path
            )
            lattice = int(lattice_value)
            if lattice != lattice_value:
                raise ValueError(f"{path}:{row_number}: L must be an integer")
            point = Point(
                row=row_number,
                L=lattice,
                t=finite_float(record.get("t"), column="t", row=row_number, path=path),
                Z=finite_float(record.get("Z"), column="Z", row=row_number, path=path),
                m2=finite_float(record.get("m2"), column="m2", row=row_number, path=path),
                U4=finite_float(record.get("U4"), column="U4", row=row_number, path=path),
            )
            grouped.setdefault(lattice, []).append(point)
    if not grouped:
        raise ValueError(f"{path}: contains no data rows")
    for lattice, points in grouped.items():
        points.sort(key=lambda point: point.t)
        if any(right.t <= left.t for left, right in zip(points, points[1:])):
            raise ValueError(f"{path}: t must be strictly increasing for L={lattice}")
    return grouped


def interpolate(left: Point, right: Point, fraction: float) -> tuple[float, float, float]:
    return tuple(
        getattr(left, name) + fraction * (getattr(right, name) - getattr(left, name))
        for name in COORDINATES
    )  # type: ignore[return-value]


def find_crossings(
    points: Iterable[Point], level: float, *, tolerance: float = 1e-12
) -> list[dict[str, object]]:
    ordered = list(points)
    results: list[dict[str, object]] = []
    seen_exact: set[int] = set()
    for left, right in zip(ordered, ordered[1:]):
        left_delta = left.U4 - level
        right_delta = right.U4 - level
        left_exact = math.isclose(left.U4, level, rel_tol=0.0, abs_tol=tolerance)
        right_exact = math.isclose(right.U4, level, rel_tol=0.0, abs_tol=tolerance)
        if left_exact and right_exact:
            results.append({
                "L": left.L, "level": level, "kind": "plateau",
                "direction": "flat", "t": "", "Z": "", "m2": "",
                "t_left": left.t, "t_right": right.t,
                "U4_left": left.U4, "U4_right": right.U4,
            })
            seen_exact.update((left.row, right.row))
            continue
        exact = left if left_exact else right if right_exact else None
        if exact is not None:
            if exact.row not in seen_exact:
                results.append({
                    "L": exact.L, "level": level, "kind": "exact",
                    "direction": "up" if right.U4 > left.U4 else "down",
                    "t": exact.t, "Z": exact.Z, "m2": exact.m2,
                    "t_left": left.t, "t_right": right.t,
                    "U4_left": left.U4, "U4_right": right.U4,
                })
                seen_exact.add(exact.row)
            continue
        if left_delta * right_delta < 0.0:
            fraction = (level - left.U4) / (right.U4 - left.U4)
            t, Z, m2 = interpolate(left, right, fraction)
            results.append({
                "L": left.L, "level": level, "kind": "interpolated",
                "direction": "up" if right.U4 > left.U4 else "down",
                "t": t, "Z": Z, "m2": m2,
                "t_left": left.t, "t_right": right.t,
                "U4_left": left.U4, "U4_right": right.U4,
            })
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path, help="CSV written by reweight_binder.py")
    parser.add_argument(
        "--level", dest="levels", type=float, action="append",
        help="U4 level to find; repeat for several levels (default: 1/3 and 0.465)",
    )
    parser.add_argument(
        "--output", type=Path,
        help="optional output CSV; results are always printed to stdout",
    )
    parser.add_argument(
        "--tolerance", type=float, default=1e-12,
        help="absolute tolerance for recognizing an exact crossing",
    )
    args = parser.parse_args()
    args.levels = args.levels or list(DEFAULT_LEVELS)
    if any(not math.isfinite(level) for level in args.levels):
        parser.error("--level values must be finite")
    if not math.isfinite(args.tolerance) or args.tolerance < 0:
        parser.error("--tolerance must be finite and non-negative")
    return args


def write_results(rows: list[dict[str, object]], handle) -> None:
    fields = [
        "L", "level", "kind", "direction", "t", "Z", "m2",
        "t_left", "t_right", "U4_left", "U4_right",
    ]
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)


def main() -> int:
    args = parse_args()
    grouped = read_points(args.csv_file)
    rows = [
        crossing
        for lattice in sorted(grouped)
        for level in args.levels
        for crossing in find_crossings(grouped[lattice], level, tolerance=args.tolerance)
    ]
    write_results(rows, sys.stdout)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_name(args.output.name + ".tmp")
        with temporary.open("w", newline="", encoding="utf-8") as handle:
            write_results(rows, handle)
        temporary.replace(args.output)
    if not rows:
        print("no crossings found", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
