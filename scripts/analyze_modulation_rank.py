#!/usr/bin/env python3
"""Build separate metastable and envelope-supported modulation-rank maps."""

from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from structure_factor_analysis import rank_from_eigenvalues, write_rows  # noqa: E402
from structure_factor_campaign import adaptive_rank_refinements  # noqa: E402


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=5e-10)


def provisional_label(row: dict[str, str]) -> str:
    excess = float(row["rank_raw_excess_power"])
    if excess <= 0:
        return "unmodulated"
    rank = rank_from_eigenvalues(float(row["rank_lambda2"]), float(row["rank_lambda3"]),
                                 lambda1=float(row["rank_lambda1"]))
    return f"rank{rank}"


def load_measurements(manifests: list[Path]) -> list[dict[str, object]]:
    measurements: list[dict[str, object]] = []
    required = {"rank_lambda1", "rank_lambda2", "rank_lambda3",
                "rank_effective_dimension", "rank_raw_excess_power"}
    for source_id, manifest in enumerate(manifests):
        for task in read_rows(manifest):
            output = Path(task["output"])
            if not output.is_file():
                continue
            for row in read_rows(output):
                if not required.issubset(row):
                    continue
                record: dict[str, object] = {
                    "source_id": source_id, "source_manifest": str(manifest),
                    "source_file": str(output), "L": int(task["L"]),
                    "Z": float(row["Z"]), "m2": float(row["m2"]),
                    "branch": row["branch"], "q_initialized": float(row["q_initialized"]),
                    "q_mean_peak": float(row["q_mean_peak"]),
                    "peak_S": float(row["peak_S"]),
                }
                for field in ("rank_lambda1", "rank_lambda2", "rank_lambda3",
                              "rank_effective_dimension", "rank_background_per_mode",
                              "rank_raw_excess_power", "rank_excess_power"):
                    record[field] = float(row[field])
                record["rank_label"] = provisional_label(row)
                record["evidence"] = "metastable_branch"
                measurements.append(record)
    return measurements


def envelope_selection(paths: list[Path], source_count: int) -> dict[int, list[dict[str, str]]]:
    if len(paths) == 1:
        shared = read_rows(paths[0])
        return {source_id: shared for source_id in range(source_count)}
    if len(paths) != source_count:
        raise ValueError("provide one shared envelope or one envelope per manifest, in matching order")
    return {source_id: read_rows(path) for source_id, path in enumerate(paths)}


def selected_measurements(measurements: list[dict[str, object]],
                          envelopes: dict[int, list[dict[str, str]]]) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    for row in measurements:
        match = next((item for item in envelopes[int(row["source_id"])]
                      if close(float(item["Z"]), float(row["Z"]))
                      and close(float(item["m2"]), float(row["m2"]))
                      and item["selected_branch"] == row["branch"]), None)
        if match is not None:
            selected.append({**row, "evidence": "free_energy_envelope_candidate"})
    return selected


def aggregate_selected(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    groups: dict[tuple[int, float, float], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        groups[(int(row["L"]), float(row["Z"]), float(row["m2"]))].append(row)
    result: list[dict[str, object]] = []
    for (L, Z, m2), group in sorted(groups.items()):
        labels = {str(row["rank_label"]) for row in group}
        dimensions = np.asarray([float(row["rank_effective_dimension"]) for row in group])
        independent_sources = len({int(row["source_id"]) for row in group})
        agrees = len(labels) == 1 and float(np.ptp(dimensions)) <= 0.25
        evidence = ("equilibrium_supported" if independent_sources >= 2 and agrees
                    else "free_energy_envelope_candidate")
        record: dict[str, object] = {
            "L": L, "Z": Z, "m2": m2, "sources": independent_sources,
            "rank_label": next(iter(labels)) if agrees else "mixed/undetermined",
            "rank_effective_dimension": float(np.mean(dimensions)),
            "rank_effective_dimension_source_spread": float(np.ptp(dimensions)),
            "evidence": evidence,
            "selected_branches": ";".join(sorted({str(row["branch"]) for row in group})),
        }
        for field in ("rank_lambda1", "rank_lambda2", "rank_lambda3",
                      "rank_raw_excess_power", "rank_excess_power"):
            record[field] = float(np.mean([float(row[field]) for row in group]))
        result.append(record)
    return result


def plot_maps(output: Path, metastable: list[dict[str, object]],
              selected: list[dict[str, object]]) -> None:
    if not metastable:
        return
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure_dir = output / "figures"
    figure_dir.mkdir(exist_ok=True)
    for name, rows in (("metastable", metastable), ("envelope_supported", selected)):
        if not rows:
            continue
        fig, axis = plt.subplots(figsize=(7.0, 5.0))
        points = axis.scatter(
            [float(row["m2"]) for row in rows], [float(row["Z"]) for row in rows],
            c=[float(row["rank_effective_dimension"]) for row in rows],
            vmin=1.0, vmax=3.0, cmap="viridis", s=45, edgecolors="black", linewidths=0.3,
        )
        axis.set(xlabel=r"$m^2$", ylabel=r"$Z$",
                 title=name.replace("_", " ").title() + " modulation dimension")
        axis.grid(alpha=0.2)
        fig.colorbar(points, ax=axis, label=r"$d_{\rm eff}$")
        fig.tight_layout(); fig.savefig(figure_dir / f"{name}_rank_map.png", dpi=190)
        plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, action="append", required=True,
                        help="repeat for independent TI replicas")
    parser.add_argument("--envelope", type=Path, action="append", required=True,
                        help="integrated_multishell.csv; repeat with independent analyses")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "reports/structure_factor_cpu/modulation_rank")
    args = parser.parse_args()

    measurements = load_measurements(args.manifest)
    if not measurements:
        raise SystemExit("no rank-aware TI outputs found; rerun with the updated collector")
    selected = aggregate_selected(selected_measurements(
        measurements, envelope_selection(args.envelope, len(args.manifest))))
    args.output.mkdir(parents=True, exist_ok=True)
    write_rows(args.output / "metastable_branch_rank_map.csv", measurements)
    write_rows(args.output / "envelope_supported_rank_map.csv", selected)
    write_rows(args.output / "adaptive_rank_anchors.csv", adaptive_rank_refinements(selected))
    plot_maps(args.output, measurements, selected)
    print(f"modulation_rank={args.output} metastable={len(measurements)} selected={len(selected)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
