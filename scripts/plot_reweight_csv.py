#!/usr/bin/env python3
"""Plot one or more CSV files produced by reweight_binder.py."""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np


REQUIRED_COLUMNS = {"t", "Z", "m2", "L", "U4"}
DEFAULT_LEVELS = (1.0 / 3.0, 0.465)


@dataclass(frozen=True)
class Series:
    path: Path
    L: int
    t: np.ndarray
    Z: np.ndarray
    m2: np.ndarray
    U4: np.ndarray
    uncertainty: np.ndarray | None
    warning: np.ndarray


def finite_float(raw: str | None, *, column: str, row: int, path: Path) -> float:
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path}:{row}: invalid {column} value {raw!r}") from exc
    if not math.isfinite(value):
        raise ValueError(f"{path}:{row}: non-finite {column} value")
    return value


def read_series(path: Path) -> list[Series]:
    grouped: dict[int, list[dict[str, object]]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or ())
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise ValueError(f"{path}: missing columns: {', '.join(sorted(missing))}")
        has_uncertainty = "uncertainty" in columns
        has_warning = "warning_status" in columns
        for row_number, record in enumerate(reader, start=2):
            lattice_value = finite_float(
                record.get("L"), column="L", row=row_number, path=path
            )
            lattice = int(lattice_value)
            if lattice != lattice_value:
                raise ValueError(f"{path}:{row_number}: L must be an integer")
            parsed = {
                name: finite_float(record.get(name), column=name, row=row_number, path=path)
                for name in ("t", "Z", "m2", "U4")
            }
            if has_uncertainty:
                uncertainty = finite_float(
                    record.get("uncertainty"), column="uncertainty",
                    row=row_number, path=path,
                )
                if uncertainty < 0:
                    raise ValueError(f"{path}:{row_number}: uncertainty must be non-negative")
                parsed["uncertainty"] = uncertainty
            parsed["warning"] = bool(
                has_warning and record.get("warning_status", "").strip().lower() != "ok"
            )
            grouped.setdefault(lattice, []).append(parsed)

    if not grouped:
        raise ValueError(f"{path}: contains no data rows")

    result: list[Series] = []
    for lattice, rows in sorted(grouped.items()):
        rows.sort(key=lambda row: float(row["t"]))
        result.append(Series(
            path=path,
            L=lattice,
            t=np.asarray([row["t"] for row in rows], dtype=float),
            Z=np.asarray([row["Z"] for row in rows], dtype=float),
            m2=np.asarray([row["m2"] for row in rows], dtype=float),
            U4=np.asarray([row["U4"] for row in rows], dtype=float),
            uncertainty=(
                np.asarray([row["uncertainty"] for row in rows], dtype=float)
                if "uncertainty" in rows[0] else None
            ),
            warning=np.asarray([row["warning"] for row in rows], dtype=bool),
        ))
    return result


def constant(values: np.ndarray) -> bool:
    return bool(np.allclose(values, values[0], rtol=0.0, atol=1e-13))


def choose_x_field(series: Sequence[Series], requested: str) -> str:
    if requested != "auto":
        return requested
    all_z_constant = all(constant(item.Z) for item in series)
    all_m2_constant = all(constant(item.m2) for item in series)
    if all_z_constant and not all_m2_constant:
        return "m2"
    if all_m2_constant and not all_z_constant:
        return "Z"
    if all_z_constant and all_m2_constant:
        raise ValueError("all Z and m2 values are constant; choose --x t explicitly")
    return "t"


def series_label(item: Series, x_field: str, duplicate_lattices: set[int],
                 varying_fixed_coordinate: bool) -> str:
    if item.L in duplicate_lattices:
        return f"{item.path.stem}, L={item.L}"
    label = f"L={item.L}"
    if varying_fixed_coordinate and x_field == "m2" and constant(item.Z):
        label += f", Z={item.Z[0]:g}"
    elif varying_fixed_coordinate and x_field == "Z" and constant(item.m2):
        label += rf", $m^2$={item.m2[0]:g}"
    return label


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "csv_files", type=Path, nargs="+",
        help="one or more CSV files written by reweight_binder.py",
    )
    parser.add_argument("--output", type=Path, required=True, help="output PNG or PDF")
    parser.add_argument(
        "--x", choices=("auto", "m2", "Z", "t"), default="auto",
        help="horizontal coordinate (default: infer from the scans)",
    )
    parser.add_argument("--title", help="custom plot title")
    parser.add_argument("--level", type=float, action="append",
                        help="horizontal reference level; repeat as needed")
    parser.add_argument("--no-levels", action="store_true",
                        help="omit the default U4=1/3 and U4=0.465 lines")
    parser.add_argument("--no-uncertainty", action="store_true",
                        help="omit bootstrap uncertainty bands")
    parser.add_argument("--no-warning-markers", action="store_true",
                        help="do not mark rows whose warning_status is not ok")
    parser.add_argument("--xlim", type=float, nargs=2, metavar=("MIN", "MAX"))
    parser.add_argument("--ylim", type=float, nargs=2, metavar=("MIN", "MAX"))
    parser.add_argument("--dpi", type=int, default=180)
    args = parser.parse_args()
    if args.dpi < 1:
        parser.error("--dpi must be positive")
    if args.level and any(not math.isfinite(level) for level in args.level):
        parser.error("--level values must be finite")
    return args


def main() -> int:
    args = parse_args()
    series = [item for path in args.csv_files for item in read_series(path)]
    x_field = choose_x_field(series, args.x)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    counts: dict[int, int] = {}
    for item in series:
        counts[item.L] = counts.get(item.L, 0) + 1
    duplicate_lattices = {L for L, count in counts.items() if count > 1}
    if x_field == "m2":
        fixed_values = {round(float(item.Z[0]), 13) for item in series if constant(item.Z)}
    elif x_field == "Z":
        fixed_values = {round(float(item.m2[0]), 13) for item in series if constant(item.m2)}
    else:
        fixed_values = set()

    figure, axis = plt.subplots(figsize=(7.2, 5.0))
    for item in series:
        x = getattr(item, x_field)
        order = np.argsort(x)
        x = x[order]
        u4 = item.U4[order]
        label = series_label(
            item, x_field, duplicate_lattices, len(fixed_values) > 1
        )
        line, = axis.plot(x, u4, linewidth=1.7, label=label)
        if not args.no_uncertainty and item.uncertainty is not None:
            error = item.uncertainty[order]
            axis.fill_between(
                x, u4 - error, u4 + error,
                color=line.get_color(), alpha=0.18, linewidth=0,
            )
        warning = item.warning[order]
        if not args.no_warning_markers and np.any(warning):
            axis.scatter(
                x[warning], u4[warning], marker="x", s=28,
                color=line.get_color(), linewidths=1.0,
            )

    levels = [] if args.no_levels else (args.level or list(DEFAULT_LEVELS))
    for level in levels:
        label = r"$U_4=1/3$" if math.isclose(level, 1.0 / 3.0) else f"$U_4={level:g}$"
        axis.axhline(level, color="0.35", linestyle="--", linewidth=1.0,
                    alpha=0.8, label=label)

    xlabel = {"m2": r"target $m^2$", "Z": r"target $Z$", "t": "line parameter t"}[x_field]
    axis.set_xlabel(xlabel)
    axis.set_ylabel(r"$U_4$")
    axis.set_title(args.title or "Reweighted Binder cumulant")
    if args.xlim:
        axis.set_xlim(*args.xlim)
    if args.ylim:
        axis.set_ylim(*args.ylim)
    axis.grid(alpha=0.25)
    axis.legend()
    figure.tight_layout()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(args.output, dpi=args.dpi)
    plt.close(figure)
    print(f"wrote {args.output} ({len(series)} curves from {len(args.csv_files)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
