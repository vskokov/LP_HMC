#!/usr/bin/env python3
"""Prepare, submit, and inspect the first CUDA modulation-rank campaign."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shlex
import subprocess
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-lp-hmc")

ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = ROOT / "runs/modulation_rank_gpu"
REPORT = ROOT / "reports/structure_factor_cpu/modulation_rank_gpu"
MANIFEST = REPORT / "manifest.csv"
JULIA = "/home/vskokov/.julia/juliaup/julia-1.12.6+0.x64.linux.gnu/bin/julia"
DEPOT = "/tmp/lp_hmc_julia_depot:/home/vskokov/.julia"

# Three points from the measured finite-q envelope where available.  The Z=-3
# and -4 anchors use the mean-field stability interval only as a broad guide.
ANCHORS = {
    -1.0: ((-1.9431541794, -1.3431541794, -0.9431541794), 0.38196601125),
    -1.5: ((-3.2230651515, -2.4230651515, -1.6230651515), 0.824429495415),
    -2.0: ((-5.7866118766, -3.1866118766, -0.5866118766), 0.824429495415),
    -2.375: ((-10.1954078833, -5.3954078833, -0.5954078833), 1.38196601125),
    -2.5: ((-10.6337943546, -5.4337943546, -0.4337943546), 1.38196601125),
    -3.0: ((-8.0, -4.5, -1.0), 1.5),
    -4.0: ((-14.0, -8.0, -2.0), 2.0),
}
SIZES = (16, 20)
REPLICAS = (1, 2)


def tag(value: float) -> str:
    return f"{value:g}".replace("-", "m").replace(".", "p")


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def prepare(_: argparse.Namespace) -> int:
    rows: list[dict[str, object]] = []
    task_id = 0
    for L in SIZES:
        for Z, (masses, target_q) in ANCHORS.items():
            for replica in REPLICAS:
                output = (RUN_ROOT / f"L{L}" / f"Z{tag(Z)}" /
                          f"replica_{replica}" / "statistics.csv")
                rows.append({
                    "task_id": task_id, "L": L, "Z": Z,
                    "masses": ";".join(repr(value) for value in masses),
                    "target_q": target_q, "replica": replica,
                    "seed": 2718281 + 100003 * replica + 7919 * task_id,
                    "eps": 0.010 if L == 16 else 0.0085, "n_lf": 15,
                    "settle": 100, "initial_settle": 300,
                    "samples": 100, "skip": 2, "shell_count": 1,
                    "rank_starts": "true", "gpu": "true",
                    "output": str(output),
                })
                task_id += 1
    write_rows(MANIFEST, rows)
    print(f"manifest={MANIFEST} tasks={len(rows)} mass_points={len(rows) * 3}")
    return 0


def load_manifest() -> list[dict[str, str]]:
    if not MANIFEST.is_file():
        raise SystemExit(f"missing {MANIFEST}; run prepare first")
    with MANIFEST.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def command(row: dict[str, str]) -> list[str]:
    environment = {
        "CUDA_VISIBLE_DEVICES": "0", "TI_GPU": row["gpu"], "TI_L": row["L"],
        "TI_Z": row["Z"], "TI_MASSES": row["masses"], "TI_TARGET_Q": row["target_q"],
        "TI_SEED": row["seed"], "TI_OUTPUT": row["output"], "TI_EPS": row["eps"],
        "TI_N_LF": row["n_lf"], "TI_SETTLE": row["settle"],
        "TI_INITIAL_SETTLE": row["initial_settle"], "TI_SAMPLES": row["samples"],
        "TI_SKIP": row["skip"], "TI_SHELL_COUNT": row["shell_count"],
        "TI_RANK_STARTS": row["rank_starts"], "JULIA_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1", "FFTW_NUM_THREADS": "1",
        "JULIA_DEPOT_PATH": DEPOT,
    }
    flattened = [item for pair in environment.items() for item in (f"{pair[0]}={pair[1]}",)]
    return ["env", *flattened, JULIA, "--startup-file=no", f"--project={ROOT}",
            str(ROOT / "scripts/thermodynamic_integration_multishell.jl")]


def submit(args: argparse.Namespace) -> int:
    rows = load_manifest()
    pending = [row for row in rows if not Path(row["output"]).is_file()]
    print(f"pending={len(pending)} completed={len(rows) - len(pending)} tsp_slots=1")
    for row in pending:
        label = f"rank_L{row['L']}_Z{tag(float(row['Z']))}_r{row['replica']}"
        launch = [args.tsp, "-L", label, *command(row)]
        if args.dry_run:
            print("+", shlex.join(launch))
        else:
            Path(row["output"]).parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(launch, cwd=ROOT, check=True)
    if not args.dry_run:
        subprocess.run([args.tsp, "-S", "1"], check=True)
        print(f"enqueued={len(pending)}; inspect with `{args.tsp}`")
    return 0


def status(_: argparse.Namespace) -> int:
    rows = load_manifest()
    complete = [row for row in rows if Path(row["output"]).is_file()]
    valid = 0
    for row in complete:
        try:
            with Path(row["output"]).open(newline="", encoding="utf-8") as handle:
                fields = next(csv.DictReader(handle)).keys()
            valid += int("rank_effective_dimension" in fields)
        except (OSError, StopIteration):
            pass
    payload = {"tasks": len(rows), "completed": len(complete),
               "rank_schema_valid": valid, "pending": len(rows) - len(complete)}
    print(json.dumps(payload, indent=2))
    return 0


def observed_rank(row: dict[str, str], rank_q: float) -> str:
    peak_q = float(row["q_mean_peak"])
    peak_strength = float(row["peak_S"])
    excess = float(row["rank_raw_excess_power"])
    if peak_q <= 1e-12 or peak_strength < 10.0 or excess <= 0:
        return "unmodulated"
    if not math.isclose(peak_q, rank_q, rel_tol=0.0, abs_tol=5e-10):
        return "off_target_modulation"
    eigenvalues = [float(row[f"rank_lambda{index}"]) for index in (1, 2, 3)]
    trace = sum(eigenvalues)
    if trace <= 0:
        return "undetermined"
    eigenvalues = [value / trace for value in eigenvalues]
    rank = 1 if eigenvalues[1] < 0.15 else (2 if eigenvalues[2] < 0.15 else 3)
    return f"rank{rank}"


def branch_family(branch: str) -> str:
    if branch == "uniform": return "uniform_start"
    if branch == "high_mass": return "disordered_start"
    if branch.startswith("rank2_"): return "rank2_start"
    if branch.startswith("rank3_"): return "rank3_start"
    return "rank1_start"


def analyze(_: argparse.Namespace) -> int:
    rows = load_manifest()
    measurements: list[dict[str, object]] = []
    for source in rows:
        output = Path(source["output"])
        if not output.is_file():
            raise SystemExit(f"incomplete campaign: missing {output}")
        raw = list(csv.DictReader(output.open(encoding="utf-8")))
        rank_q = float(next(row["q_initialized"] for row in raw
                            if row["branch"].startswith("shell_")))
        for row in raw:
            record: dict[str, object] = {
                "task_id": int(source["task_id"]), "replica": int(source["replica"]),
                "L": int(source["L"]), "Z": float(row["Z"]), "m2": float(row["m2"]),
                "branch": row["branch"], "branch_family": branch_family(row["branch"]),
                "rank_q": rank_q, "q_mean_peak": float(row["q_mean_peak"]),
                "peak_S": float(row["peak_S"]),
                "rank_label": observed_rank(row, rank_q),
                "settle_acceptance": float(row["settle_acceptance"]),
                "sample_acceptance": float(row["sample_acceptance"]),
            }
            for field in ("rank_lambda1", "rank_lambda2", "rank_lambda3",
                          "rank_effective_dimension", "rank_background_per_mode",
                          "rank_raw_excess_power", "rank_excess_power"):
                record[field] = float(row[field])
            measurements.append(record)

    grouped: dict[tuple[int, float, float], list[dict[str, object]]] = {}
    for row in measurements:
        grouped.setdefault((int(row["L"]), float(row["Z"]), float(row["m2"])), []).append(row)
    classification: list[dict[str, object]] = []
    for (L, Z, mass), group in sorted(grouped.items()):
        labels = [str(row["rank_label"]) for row in group]
        rank_labels = [label for label in labels if label in ("rank1", "rank2", "rank3")]
        distinct_ranks = sorted(set(rank_labels))
        if len(rank_labels) == len(group) and len(distinct_ranks) == 1:
            evidence = "branch_independent"
            final_label = distinct_ranks[0]
        elif not rank_labels and set(labels) == {"unmodulated"}:
            evidence = "branch_independent"
            final_label = "unmodulated"
        elif len(distinct_ranks) == 1:
            evidence = "metastable_phase_disagreement"
            final_label = distinct_ranks[0] + "_metastable"
        elif len(distinct_ranks) > 1:
            evidence = "mixed_rank_start_dependence"
            final_label = "mixed/undetermined"
        else:
            evidence = "off_target_or_unresolved"
            final_label = "mixed/undetermined"
        valid = [row for row in group if str(row["rank_label"]) in ("rank1", "rank2", "rank3")]
        dimensions = [float(row["rank_effective_dimension"]) for row in valid]
        replica_checks = []
        for family in sorted({str(row["branch_family"]) for row in group}):
            family_labels = {str(row["rank_label"]) for row in group
                             if row["branch_family"] == family}
            replica_checks.append(len(family_labels) == 1)
        counts = {label: labels.count(label) for label in sorted(set(labels))}
        classification.append({
            "L": L, "Z": Z, "m2": mass, "rank_q": float(group[0]["rank_q"]),
            "rank_label": final_label, "evidence": evidence,
            "rank_effective_dimension": float(sum(dimensions) / len(dimensions)) if dimensions else math.nan,
            "rank_effective_dimension_spread": max(dimensions) - min(dimensions) if dimensions else math.nan,
            "replica_agreement_fraction": sum(replica_checks) / len(replica_checks),
            "rank1_votes": counts.get("rank1", 0), "rank2_votes": counts.get("rank2", 0),
            "rank3_votes": counts.get("rank3", 0),
            "unmodulated_votes": counts.get("unmodulated", 0),
            "off_target_votes": counts.get("off_target_modulation", 0),
            "minimum_sample_acceptance": min(float(row["sample_acceptance"]) for row in group),
        })

    write_rows(REPORT / "branch_rank_measurements.csv", measurements)
    write_rows(REPORT / "classification_map.csv", classification)
    plot_classification(classification, measurements)
    summary = {
        "points": len(classification),
        "classifications": {label: sum(row["rank_label"] == label for row in classification)
                            for label in sorted({str(row["rank_label"]) for row in classification})},
        "evidence": {label: sum(row["evidence"] == label for row in classification)
                     for label in sorted({str(row["evidence"]) for row in classification})},
        "minimum_sample_acceptance": min(float(row["minimum_sample_acceptance"])
                                           for row in classification),
    }
    (REPORT / "classification_summary.json").write_text(json.dumps(summary, indent=2) + "\n",
                                                          encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


def plot_classification(classification: list[dict[str, object]],
                        measurements: list[dict[str, object]]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    figures = REPORT / "figures"; figures.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.8), sharey=True, layout="constrained")
    for axis, L in zip(axes, SIZES):
        subset = [row for row in classification if int(row["L"]) == L]
        finite = [row for row in subset if math.isfinite(float(row["rank_effective_dimension"]))]
        if finite:
            points = axis.scatter([float(row["m2"]) for row in finite],
                                  [float(row["Z"]) for row in finite],
                                  c=[float(row["rank_effective_dimension"]) for row in finite],
                                  vmin=1.0, vmax=3.0, cmap="viridis", s=70,
                                  edgecolors="black", linewidths=0.4)
        unresolved = [row for row in subset if row["rank_label"] == "mixed/undetermined"]
        axis.scatter([float(row["m2"]) for row in unresolved],
                     [float(row["Z"]) for row in unresolved], marker="x", s=75,
                     color="red", linewidths=1.5, label="mixed rank")
        axis.set(title=f"L={L}", xlabel=r"$m^2$"); axis.grid(alpha=0.2)
        if unresolved: axis.legend(frameon=False, fontsize=8)
    axes[0].set_ylabel(r"$Z$")
    fig.colorbar(points, ax=axes, label=r"$d_{\rm eff}$ over modulated branches")
    fig.savefig(figures / "classification_map.png", dpi=190); plt.close(fig)

    zvalues = sorted(ANCHORS)
    fig, axes = plt.subplots(2, len(zvalues), figsize=(3.1 * len(zvalues), 7.0),
                             sharey=True, layout="constrained")
    colors = {"uniform_start": "black", "disordered_start": "0.55",
              "rank1_start": "C0", "rank2_start": "C1", "rank3_start": "C2"}
    for row_index, L in enumerate(SIZES):
        for column, Z in enumerate(zvalues):
            axis = axes[row_index, column]
            subset = [row for row in measurements
                      if int(row["L"]) == L and math.isclose(float(row["Z"]), Z)]
            for family in colors:
                series = sorted((row for row in subset if row["branch_family"] == family),
                                key=lambda row: (float(row["m2"]), int(row["replica"])))
                if series:
                    axis.scatter([float(row["m2"]) for row in series],
                                 [float(row["rank_effective_dimension"]) for row in series],
                                 color=colors[family], s=18, alpha=0.8,
                                 label=family.replace("_start", ""))
            axis.set_title(f"L={L}, Z={Z:g}", fontsize=9); axis.grid(alpha=0.18)
            if row_index == 1: axis.set_xlabel(r"$m^2$")
            if column == 0: axis.set_ylabel(r"$d_{\rm eff}$")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 1.02),
               ncol=5, frameon=False)
    fig.savefig(figures / "branch_convergence.png", dpi=190); plt.close(fig)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="action", required=True)
    prepare_parser = sub.add_parser("prepare"); prepare_parser.set_defaults(function=prepare)
    submit_parser = sub.add_parser("submit")
    submit_parser.add_argument("--tsp", default="tsp")
    submit_parser.add_argument("--dry-run", action="store_true")
    submit_parser.set_defaults(function=submit)
    status_parser = sub.add_parser("status"); status_parser.set_defaults(function=status)
    analyze_parser = sub.add_parser("analyze"); analyze_parser.set_defaults(function=analyze)
    return root


def main() -> int:
    args = parser().parse_args()
    return args.function(args)


if __name__ == "__main__":
    raise SystemExit(main())
