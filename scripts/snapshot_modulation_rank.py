#!/usr/bin/env python3
"""Reprocess final structure-factor checkpoints into an exploratory rank map."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from structure_factor_analysis import (RANK_METRICS, census_weights, rank_from_eigenvalues,
                                       read_shell_table, write_rows)  # noqa: E402
from structure_factor_campaign import (DEFAULT_DEPOT, DEFAULT_JULIA,
                                       adaptive_rank_refinements,
                                       read_umbrella_bias_columns)  # noqa: E402


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def latest_collection_checkpoint(row: dict[str, str]) -> Path | None:
    progress = Path(row["progress_path"])
    if not progress.is_file():
        return None
    payload = json.loads(progress.read_text(encoding="utf-8"))
    path = Path(payload["checkpoint"])
    return path if path.is_file() else None


def run_census(payload: tuple[dict[str, str], str, Path]) -> tuple[dict[str, str], str]:
    row, julia, destination = payload
    checkpoint = latest_collection_checkpoint(row)
    if checkpoint is None:
        raise FileNotFoundError(f"no collection checkpoint for task {row['structure_task_id']}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment.update({"JULIA_NUM_THREADS": "1", "FFTW_NUM_THREADS": "1",
                        "JULIA_DEPOT_PATH": environment.get("JULIA_DEPOT_PATH", DEFAULT_DEPOT)})
    command = [julia, f"--project={ROOT}", str(ROOT / "scripts/census_structure_factor.jl"),
               str(checkpoint), str(destination)]
    result = subprocess.run(command, cwd=ROOT, env=environment, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    if result.returncode:
        raise RuntimeError(result.stdout)
    return row, str(destination)


def summarize(row: dict[str, str], snapshot: Path) -> dict[str, object]:
    table = read_shell_table(snapshot)
    if not all(metric in table.arrays for metric in RANK_METRICS):
        raise ValueError(f"{snapshot}: rank fields are absent")
    production = read_umbrella_bias_columns(Path(row["merged_path"]))
    weights = census_weights(table, production)
    result: dict[str, object] = {
        "structure_task_id": int(row["structure_task_id"]), "L": int(row["L"]),
        "Z": float(row["Z"]), "m2": float(row["m2"]), "phase": row["init_phase"],
        "selected_q": float(row["selected_q"]), "evidence": "final_checkpoint_snapshot",
        "snapshot_ess": 1.0 / float(np.dot(weights, weights)),
    }
    result.update({metric: float(np.dot(weights, table.arrays[metric])) for metric in RANK_METRICS})
    if result["rank_raw_excess_power"] <= 0:
        result["rank_label"] = "unmodulated"
    else:
        rank = rank_from_eigenvalues(float(result["rank_lambda2"]),
                                     float(result["rank_lambda3"]),
                                     lambda1=float(result["rank_lambda1"]))
        result["rank_label"] = f"rank{rank}_provisional"
    return result


def combine(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[float, int, float], list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault((float(row["Z"]), int(row["L"]), float(row["m2"])), []).append(row)
    combined: list[dict[str, object]] = []
    for (Z, L, mass), group in sorted(grouped.items()):
        labels = {str(row["rank_label"]) for row in group}
        dimensions = [float(row["rank_effective_dimension"]) for row in group]
        record: dict[str, object] = {
            "Z": Z, "L": L, "m2": mass, "phase_sources": len(group),
            "selected_q": float(group[0]["selected_q"]),
            "rank_label": next(iter(labels)) if len(labels) == 1 else "mixed/undetermined",
            "rank_effective_dimension": float(np.mean(dimensions)),
            "rank_effective_dimension_source_spread": float(np.ptp(dimensions)),
            "evidence": "snapshot_source_agreement" if len(labels) == 1 and len(group) >= 2
                        else "final_checkpoint_snapshot",
        }
        for metric in RANK_METRICS:
            record[metric] = float(np.mean([float(row[metric]) for row in group]))
        combined.append(record)
    return combined


def plot_results(output: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figures = output / "figures"
    figures.mkdir(exist_ok=True)
    volumes = sorted({int(row["L"]) for row in rows})
    fig, axes = plt.subplots(1, len(volumes), figsize=(4.2 * len(volumes), 4.2),
                             sharex=True, sharey=True, squeeze=False,
                             layout="constrained")
    points = None
    for axis, L in zip(axes[0], volumes):
        subset = [row for row in rows if int(row["L"]) == L]
        points = axis.scatter(
            [float(row["m2"]) for row in subset], [float(row["Z"]) for row in subset],
            c=[float(row["rank_effective_dimension"]) for row in subset],
            vmin=0.0, vmax=3.0, cmap="viridis", s=55, edgecolors="black", linewidths=0.3,
        )
        axis.set_title(f"L={L}"); axis.set_xlabel(r"$m^2$"); axis.grid(alpha=0.2)
    axes[0, 0].set_ylabel(r"$Z$")
    if points is not None:
        fig.colorbar(points, ax=axes.ravel().tolist(), label=r"snapshot $d_{\rm eff}$")
    fig.savefig(figures / "snapshot_modulation_dimension_map.png", dpi=190)
    plt.close(fig)

    nonzero = [row for row in rows if float(row["selected_q"]) > 1e-12]
    if nonzero:
        fig, axis = plt.subplots(figsize=(6.8, 4.6))
        for L in sorted({int(row["L"]) for row in nonzero}):
            series = sorted((row for row in nonzero if int(row["L"]) == L),
                            key=lambda row: float(row["m2"]))
            axis.plot([float(row["m2"]) for row in series],
                      [float(row["rank_effective_dimension"]) for row in series],
                      marker="o", label=f"L={L}")
        axis.axhline(1.0, color="k", ls=":", lw=1)
        axis.axhline(2.0, color="k", ls=":", lw=1)
        axis.set(xlabel=r"$m^2$", ylabel=r"snapshot $d_{\rm eff}$",
                 title="Finite-volume modulation dimension")
        axis.grid(alpha=0.2); axis.legend(frameon=False)
        fig.tight_layout(); fig.savefig(figures / "snapshot_deff_finite_size.png", dpi=190)
        plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "reports/structure_factor_cpu/rank_snapshots")
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--julia", default=DEFAULT_JULIA)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    source = read_rows(args.manifest)
    snapshot_dir = args.output / "snapshots"
    payloads = []
    completed: list[tuple[dict[str, str], Path]] = []
    for row in source:
        destination = snapshot_dir / f"task_{int(row['structure_task_id']):06d}.csv"
        if args.resume and destination.is_file():
            completed.append((row, destination))
        else:
            payloads.append((row, args.julia, destination))
    with ProcessPoolExecutor(max_workers=min(args.workers, max(1, len(payloads)))) as pool:
        futures = {pool.submit(run_census, payload): payload for payload in payloads}
        for number, future in enumerate(as_completed(futures), start=1):
            row, path = future.result(); completed.append((row, Path(path)))
            if number == 1 or number % 20 == 0 or number == len(payloads):
                print(f"rank snapshots {number}/{len(payloads)}", flush=True)
    task_rows = [summarize(row, path) for row, path in completed]
    task_rows.sort(key=lambda row: int(row["structure_task_id"]))
    combined = combine(task_rows)
    args.output.mkdir(parents=True, exist_ok=True)
    write_rows(args.output / "task_rank_snapshots.csv", task_rows)
    write_rows(args.output / "combined_rank_snapshots.csv", combined)
    write_rows(args.output / "adaptive_rank_anchors.csv", adaptive_rank_refinements(combined))
    plot_results(args.output, combined)
    print(f"rank_snapshot_map={args.output} tasks={len(task_rows)} points={len(combined)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
