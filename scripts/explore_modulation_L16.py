#!/usr/bin/env python3
"""Prepare, run, and summarize the L=16 CPU modulation-onset scan."""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-lp-hmc")
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "runs/modulation_onset_L16"
REPORT = ROOT / "reports/structure_factor_cpu/modulation_onset_L16"
JULIA = "/home/vskokov/.julia/juliaup/julia-1.12.6+0.x64.linux.gnu/bin/julia"
Z_VALUES = (-0.75, -0.80, -0.85, -0.90, -0.95, -1.00, -1.05, -1.10,
            -1.20, -1.30, -1.40, -1.50)
INITS = ("uniform", "modulated", "disordered")


def crossing_fit() -> np.ndarray:
    rows = list(csv.DictReader((ROOT / "plots/binder_crossings_vs_Z.csv").open()))
    values = {}
    for row in rows:
        values.setdefault(float(row["Z"]), []).append(float(row["m2_c"]))
    z = np.asarray([-0.5, -0.25, 0.0])
    m2 = np.asarray([np.mean(values[value]) for value in z])
    return np.polyfit(z, m2, 2)


def prepare(_: argparse.Namespace) -> int:
    REPORT.mkdir(parents=True, exist_ok=True); CAMPAIGN.mkdir(parents=True, exist_ok=True)
    coefficients = crossing_fit()
    rows = []
    for Z in Z_VALUES:
        mass = float(np.polyval(coefficients, Z))
        for init_index, init in enumerate(INITS):
            task_id = len(rows); task_dir = CAMPAIGN / f"task_{task_id:03d}"
            rows.append({"task_id": task_id, "Z": Z, "m2": mass, "init": init,
                         "seed": 73001 + 1009 * task_id + init_index,
                         "task_dir": str(task_dir),
                         "summary": str(task_dir / "summary.csv"),
                         "spectrum": str(task_dir / "spectrum.csv")})
    with (REPORT / "manifest.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    with (REPORT / "crossing_fit.csv").open("w", newline="") as handle:
        writer = csv.writer(handle); writer.writerow(("quadratic", "linear", "constant")); writer.writerow(coefficients)
    print(f"prepared={len(rows)} fit={coefficients.tolist()}")
    return 0


def run_one(row: dict[str, str]) -> tuple[int, str]:
    output = Path(row["task_dir"]); output.mkdir(parents=True, exist_ok=True)
    if Path(row["summary"]).is_file(): return 0, "resume"
    environment = dict(os.environ)
    environment.update({"MODSCAN_Z": row["Z"], "MODSCAN_M2": row["m2"],
                        "MODSCAN_INIT": row["init"], "MODSCAN_SEED": row["seed"],
                        "MODSCAN_OUTPUT": row["task_dir"], "JULIA_NUM_THREADS": "1",
                        "JULIA_DEPOT_PATH": environment.get("JULIA_DEPOT_PATH",
                            "/tmp/lp_hmc_julia_depot:/home/vskokov/.julia")})
    command = [JULIA, "--startup-file=no", f"--project={ROOT}",
               str(ROOT / "scripts/scan_modulation_L16.jl")]
    result = subprocess.run(command, cwd=ROOT, env=environment, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return result.returncode, result.stdout


def run(args: argparse.Namespace) -> int:
    rows = list(csv.DictReader((REPORT / "manifest.csv").open()))
    failures = 0
    with ProcessPoolExecutor(max_workers=min(args.workers, len(rows))) as pool:
        futures = {pool.submit(run_one, row): row for row in rows}
        for number, future in enumerate(as_completed(futures), 1):
            code, log = future.result()
            if code:
                failures += 1; print(f"failed {futures[future]['task_id']}\n{log}")
            elif number == 1 or number % 6 == 0 or number == len(rows):
                print(f"completed {number}/{len(rows)}", flush=True)
    return int(bool(failures))


def analyze(_: argparse.Namespace) -> int:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    manifest = list(csv.DictReader((REPORT / "manifest.csv").open()))
    rows = []
    for source in manifest:
        if Path(source["summary"]).is_file():
            rows.extend(csv.DictReader(Path(source["summary"]).open()))
    rows.sort(key=lambda row: (float(row["Z"]), row["init"]))
    with (REPORT / "summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    fig, axes = plt.subplots(2, 1, figsize=(7.5, 7.0), sharex=True)
    for init in INITS:
        group = [row for row in rows if row["init"] == init]
        axes[0].plot([float(row["Z"]) for row in group], [float(row["q_mean_peak"]) for row in group],
                     marker="o", label=init)
        axes[1].plot([float(row["Z"]) for row in group], [float(row["mean_peak_S"]) for row in group],
                     marker="o", label=init)
    z_grid = np.linspace(min(Z_VALUES), max(Z_VALUES), 200)
    axes[0].plot(z_grid, -z_grid / 2, "k--", lw=1, label=r"bare $-Z/2$")
    axes[0].set_ylabel(r"measured peak shell $q$"); axes[0].legend(frameon=False)
    axes[1].set(xlabel=r"$Z$", ylabel=r"peak $S(q)$ per mode", yscale="log")
    for axis in axes: axis.grid(alpha=0.25)
    fig.tight_layout(); fig.savefig(REPORT / "onset_scan.png", dpi=180); plt.close(fig)
    print(f"analysis={REPORT} rows={len(rows)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare"); p.set_defaults(function=prepare)
    p = sub.add_parser("run"); p.add_argument("--workers", type=int, default=32); p.set_defaults(function=run)
    p = sub.add_parser("analyze"); p.set_defaults(function=analyze)
    args = parser.parse_args(); return args.function(args)


if __name__ == "__main__": raise SystemExit(main())
