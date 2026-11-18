#!/usr/bin/env python3
"""Replicate the shell-change interval found by the wide L=20 scan."""

from __future__ import annotations

import csv
import math

import numpy as np

import run_thermodynamic_integration_L16 as campaign


BASE_ANALYZE = campaign.analyze
campaign.RUN_ROOT = campaign.ROOT / "runs/thermodynamic_integration_L20_refine"
campaign.REPORT = campaign.ROOT / "reports/structure_factor_cpu/thermodynamic_integration_L20_refine"
campaign.Z_VALUES = (-2.35, -2.355, -2.36, -2.365, -2.37, -2.375)
REPLICAS = (1, 2)


def mass_grid(center: float, Z: float) -> list[float]:
    low = center - 4.0
    high = max(1.5, Z * Z / 4 + 1.0)
    values = list(np.arange(low, high + 0.125, 0.25))
    values.extend((low, center, high))
    return sorted({round(float(value), 10) for value in values})


def write_csv(path, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def prepare(_: object) -> int:
    campaign.REPORT.mkdir(parents=True, exist_ok=True)
    campaign.RUN_ROOT.mkdir(parents=True, exist_ok=True)
    coefficients = campaign.crossing_fit(); all_rows = []
    for replica in REPLICAS:
        replica_rows = []
        report = campaign.REPORT / f"r{replica}"; report.mkdir(parents=True, exist_ok=True)
        for index, Z in enumerate(campaign.Z_VALUES):
            center = float(np.polyval(coefficients, Z)); masses = mass_grid(center, Z)
            tag = f"{Z:.3f}".replace("-", "m").replace(".", "p")
            row = {"task_id": replica * len(campaign.Z_VALUES) + index,
                   "replicate": replica, "L": 20, "Z": Z,
                   "binder_line_m2": center, "masses": ";".join(map(repr, masses)),
                   "seed": 1230011 + 104729 * replica + 7919 * index,
                   "eps": 0.0085, "n_lf": 15, "settle": 100,
                   "initial_settle": 300, "samples": 100, "skip": 2,
                   "output": str(campaign.RUN_ROOT / f"r{replica}" / f"Z{tag}" / "statistics.csv")}
            replica_rows.append(row); all_rows.append(row)
        write_csv(report / "manifest.csv", replica_rows)
    write_csv(campaign.REPORT / "manifest.csv", all_rows)
    total = sum(len(row["masses"].split(";")) for row in all_rows)
    print(f"prepared={len(all_rows)} mass_points={total} branch_points={3 * total}")
    return 0


def analyze(args: object) -> int:
    root = campaign.REPORT; rows = []
    try:
        for replica in REPLICAS:
            campaign.REPORT = root / f"r{replica}"
            if BASE_ANALYZE(args): return 1
            for row in csv.DictReader((campaign.REPORT / "crossing_summary.csv").open()):
                item = dict(row); item["replicate"] = replica; rows.append(item)
    finally:
        campaign.REPORT = root
    write_csv(root / "replica_crossing_summary.csv", rows)
    plot_summary(root, rows)
    return 0


def plot_summary(report, rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    broad_path = campaign.ROOT / "reports/structure_factor_cpu/thermodynamic_integration_L20_wide/crossing_summary.csv"
    broad = [row for row in csv.DictReader(broad_path.open()) if -2.38 <= float(row["Z"]) <= -2.34]
    fig, axes = plt.subplots(2, 1, figsize=(8.0, 7.4), sharex=True)
    onset = []
    for replica, color in zip(REPLICAS, ("tab:orange", "tab:green")):
        selected = sorted((row for row in rows if int(row["replicate"]) == replica),
                          key=lambda row: float(row["Z"]))
        z = np.asarray([float(row["Z"]) for row in selected])
        delta = np.asarray([float(row["delta_f_finite_q_uniform_at_binder"]) for row in selected])
        q = np.asarray([float(row["finite_q_shell_at_binder"]) for row in selected])
        axes[0].plot(z, delta, marker="o", color=color, label=f"new replica {replica}")
        axes[1].plot(z, q, marker="o", color=color, label=f"new replica {replica}")
        roots = []
        for left in range(len(z) - 1):
            if delta[left] * delta[left + 1] < 0:
                fraction = -delta[left] / (delta[left + 1] - delta[left])
                roots.append(float(z[left] + fraction * (z[left + 1] - z[left])))
        onset.append({"replicate": replica, "linear_roots_Z": ";".join(map(str, roots)),
                      "minimum_delta_f": float(delta.min()), "maximum_delta_f": float(delta.max())})
    if broad:
        broad.sort(key=lambda row: float(row["Z"]))
        z = [float(row["Z"]) for row in broad]
        axes[0].plot(z, [float(row["delta_f_finite_q_uniform_at_binder"]) for row in broad],
                     "k--o", label="wide-scan replica")
        axes[1].plot(z, [float(row["finite_q_shell_at_binder"]) for row in broad],
                     "k--o", label="wide-scan replica")
    axes[0].axhline(0, color="0.3", lw=0.9)
    axes[0].set(ylabel=r"$f_{q>0}-f_{q=0}$ at Binder line",
                title="Replicated L=20 shell-change interval")
    axes[1].set(xlabel="Z", ylabel="selected coherent shell q")
    for axis in axes: axis.grid(alpha=0.22); axis.legend(frameon=False)
    fig.tight_layout(); fig.savefig(report / "replicated_onset.png", dpi=190); plt.close(fig)
    write_csv(report / "onset_summary.csv", onset)


campaign.prepare = prepare
campaign.analyze = analyze

if __name__ == "__main__": raise SystemExit(campaign.main())
