#!/usr/bin/env python3
"""Apply production gates to ladder pilots and emit validated critical profiles."""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path

import numpy as np


CONFIG = ("L", "tempering_replicas", "mass_span", "swap_every", "epsilon", "n_lf")


def standard_error(values: list[float]) -> float:
    return float(np.std(values, ddof=1) / math.sqrt(len(values))) if len(values) > 1 else math.inf


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pilot_csv", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-points", type=int, default=3)
    parser.add_argument("--min-hmc-acceptance", type=float, default=0.65)
    parser.add_argument("--min-edge-acceptance", type=float, default=0.20)
    parser.add_argument("--min-median-edge-acceptance", type=float, default=0.30)
    parser.add_argument("--min-round-trip-walker-fraction", type=float, default=0.50)
    parser.add_argument(
        "--phase-tail-fraction", type=float, default=0.5,
        help="fraction of final measurement blocks used for phase agreement",
    )
    args = parser.parse_args()

    rows: list[dict[str, str]] = []
    for path in args.pilot_csv:
        with path.open(newline="", encoding="utf-8") as handle:
            rows.extend(csv.DictReader(handle))
    if not rows:
        parser.error("pilot inputs contain no rows")
    if not 0 < args.phase_tail_fraction <= 1:
        parser.error("--phase-tail-fraction must be in (0,1]")

    # Retain the cumulative final block for each phase/configuration/point.
    final: dict[tuple[object, ...], dict[str, str]] = {}
    histories: dict[tuple[object, ...], list[tuple[int, float]]] = defaultdict(list)
    legacy_phase_metric = "block_abs_M_mean" not in rows[0]
    for row in rows:
        config = tuple(row[name] for name in CONFIG)
        point_phase = config + (row["Z"], row["m2"], row["phase"])
        if point_phase not in final or int(row["sweeps"]) > int(final[point_phase]["sweeps"]):
            final[point_phase] = row
        phase_value = abs(float(row["M_target"])) if legacy_phase_metric else float(
            row["block_abs_M_mean"]
        )
        histories[point_phase].append((int(row["sweeps"]), phase_value))

    configurations: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for key, row in final.items():
        configurations[key[:len(CONFIG)]].append(row)

    accepted: list[tuple[tuple[str, ...], dict[str, object]]] = []
    rejected: list[tuple[tuple[str, ...], str]] = []
    for config, candidate_rows in configurations.items():
        points = {(row["Z"], row["m2"]) for row in candidate_rows}
        reasons: list[str] = []
        if legacy_phase_metric:
            rejected.append((config, "legacy_cold_start_pilot_not_equilibrium_measurement"))
            continue
        if len(points) < args.expected_points:
            reasons.append(f"points={len(points)}<{args.expected_points}")
        if any(float(row["acceptance_min"]) < args.min_hmc_acceptance for row in candidate_rows):
            reasons.append("hmc_acceptance")
        if any(float(row["swap_acceptance_min"]) < args.min_edge_acceptance for row in candidate_rows):
            reasons.append("edge_acceptance")
        if any(float(row["swap_acceptance_median"]) < args.min_median_edge_acceptance for row in candidate_rows):
            reasons.append("median_edge_acceptance")
        if any(int(float(row["unused_edges"])) != 0 for row in candidate_rows):
            reasons.append("unused_edge")
        if any(float(row["round_trip_walker_fraction"]) < args.min_round_trip_walker_fraction
               for row in candidate_rows):
            reasons.append("round_trip_coverage")
        for point in points:
            phase_keys = [
                config + point + (phase,) for phase in ("disordered", "ordered")
            ]
            if any(key not in histories for key in phase_keys):
                reasons.append("missing_phase")
                continue
            phase_values = []
            for key in phase_keys:
                ordered_history = [value for _, value in sorted(histories[key])]
                keep = max(2, math.ceil(len(ordered_history) * args.phase_tail_fraction))
                phase_values.append(ordered_history[-keep:])
            difference = abs(float(np.mean(phase_values[0])) - float(np.mean(phase_values[1])))
            combined_se = math.hypot(*(standard_error(values) for values in phase_values))
            if difference > 2.0 * combined_se:
                reasons.append("phase_disagreement")
        if reasons:
            rejected.append((config, ";".join(sorted(set(reasons)))))
        else:
            accepted.append((config, {"points": len(points)}))

    selected: dict[int, tuple[str, ...]] = {}
    for config, _ in accepted:
        lattice = int(config[0])
        rank = (int(config[1]), float(config[2]), int(config[3]))
        if lattice not in selected or rank < (
            int(selected[lattice][1]), float(selected[lattice][2]), int(selected[lattice][3])
        ):
            selected[lattice] = config

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(args.output.name + ".tmp")
    fields = ["profile", "L", "tempering_replicas", "mass_span", "swap_every",
              "epsilon", "n_lf", "validated"]
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for lattice, config in sorted(selected.items()):
            writer.writerow({
                "profile": "critical", "L": lattice,
                "tempering_replicas": config[1], "mass_span": config[2],
                "swap_every": config[3], "epsilon": config[4], "n_lf": config[5],
                "validated": "true",
            })
    temporary.replace(args.output)
    print(f"accepted_configurations={len(accepted)} rejected_configurations={len(rejected)}")
    for config, reason in rejected:
        print("REJECT", ",".join(config), reason)
    print(f"wrote {args.output}")
    return 0 if selected else 2


if __name__ == "__main__":
    raise SystemExit(main())
