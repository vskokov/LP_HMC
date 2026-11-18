#!/usr/bin/env python3
"""Replicated multi-shell refinement where the modulated wedge meets the Binder line."""

from __future__ import annotations

import csv
import math

import numpy as np

import run_multishell_phase_map_L20 as multi


campaign = multi.campaign
BASE_ANALYZE = multi.analyze
campaign.RUN_ROOT = campaign.ROOT / "runs/thermodynamic_integration_multishell_join_L20"
campaign.REPORT = campaign.ROOT / "reports/structure_factor_cpu/thermodynamic_integration_multishell_join_L20"
campaign.Z_VALUES = (-1.45, -1.475, -1.5, -1.525, -1.55, -1.575, -1.6, -1.625, -1.65)
REPLICAS = (1, 2)


def mass_grid(center: float, Z: float) -> list[float]:
    low = center - 0.8
    high = max(1.5, Z * Z / 4 + 1.0)
    values = list(np.arange(low, high + 0.1, 0.2))
    values.extend((low, center, high))
    return sorted({round(float(value), 10) for value in values})


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
            row = {
                "task_id": replica * len(campaign.Z_VALUES) + index,
                "replicate": replica, "L": 20, "Z": Z,
                "binder_line_m2": center, "masses": ";".join(map(repr, masses)),
                "seed": 1900013 + 104729 * replica + 7919 * index,
                "eps": 0.0085, "n_lf": 15, "settle": 100, "initial_settle": 300,
                "samples": 100, "skip": 2, "shell_count": 5,
                "script": "scripts/thermodynamic_integration_multishell.jl",
                "output": str(campaign.RUN_ROOT / f"r{replica}" / f"Z{tag}" / "statistics.csv"),
            }
            replica_rows.append(row); all_rows.append(row)
        multi.write_csv(report / "manifest.csv", replica_rows)
    multi.write_csv(campaign.REPORT / "manifest.csv", all_rows)
    masses = sum(len(row["masses"].split(";")) for row in all_rows)
    print(f"prepared={len(all_rows)} mass_points={masses} branch_points={7 * masses}")
    return 0


def analyze(args: object) -> int:
    root = campaign.REPORT; combined = []
    try:
        for replica in REPLICAS:
            campaign.REPORT = root / f"r{replica}"
            if BASE_ANALYZE(args): return 1
            for row in csv.DictReader((campaign.REPORT / "multishell_summary.csv").open()):
                item = dict(row); item["replicate"] = replica; combined.append(item)
    finally:
        campaign.REPORT = root
    multi.write_csv(root / "replica_summary.csv", combined)
    plot_join(root, combined)
    return 0


def plot_join(report, rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    production_path = (campaign.ROOT /
        "reports/structure_factor_cpu/thermodynamic_integration_multishell_L20/multishell_summary.csv")
    production = [row for row in csv.DictReader(production_path.open())
                  if -1.66 <= float(row["Z"]) <= -1.44]
    fig, axes = plt.subplots(3, 1, figsize=(8.2, 10.0), sharex=True)
    root_rows = []
    for replica, color in zip(REPLICAS, ("tab:orange", "tab:green")):
        selected = sorted((row for row in rows if int(row["replicate"]) == replica),
                          key=lambda row: float(row["Z"]))
        z = np.asarray([float(row["Z"]) for row in selected])
        delta = np.asarray([float(row["delta_f_at_binder_line"]) for row in selected])
        error = np.asarray([float(row["delta_f_mcse_at_binder_line"]) for row in selected])
        q = np.asarray([float(row["selected_q_at_binder_line"]) for row in selected])
        boundary = np.asarray([float(row["ordered_boundary_m2"]) for row in selected])
        binder = np.asarray([float(row["binder_line_m2"]) for row in selected])
        axes[0].errorbar(z, delta, yerr=error, marker="o", capsize=2,
                         color=color, label=f"replica {replica}")
        axes[1].plot(z, boundary - binder, marker="o", color=color, label=f"replica {replica}")
        axes[2].plot(z, q, marker="o", color=color, label=f"replica {replica}")
        for left in range(len(z) - 1):
            if delta[left] * delta[left + 1] < 0:
                fraction = -delta[left] / (delta[left + 1] - delta[left])
                root_rows.append({"replicate": replica,
                                  "bracket_low_Z": z[left], "bracket_high_Z": z[left + 1],
                                  "linear_root_Z": z[left] + fraction * (z[left + 1] - z[left])})
    if production:
        production.sort(key=lambda row: float(row["Z"]))
        z = np.asarray([float(row["Z"]) for row in production])
        axes[0].plot(z, [float(row["delta_f_at_binder_line"]) for row in production],
                     "k--o", label="coarse scan")
        axes[1].plot(z, [float(row["ordered_boundary_m2"]) - float(row["binder_line_m2"])
                         for row in production], "k--o", label="coarse scan")
        axes[2].plot(z, [float(row["selected_q_at_binder_line"]) for row in production],
                     "k--o", label="coarse scan")
    axes[0].axhline(0, color="0.3", lw=0.9)
    axes[1].axhline(0, color="0.3", lw=0.9)
    axes[0].set(ylabel=r"$f_{q>0}-f_{q=0}$ at Binder line",
                title="Replicated multi-shell junction with Binder line")
    axes[1].set(ylabel=r"$m^2_{q=0/q>0}-m^2_{Binder}$")
    axes[2].set(xlabel="Z", ylabel="selected shell q")
    for axis in axes: axis.grid(alpha=0.22); axis.legend(frameon=False)
    fig.tight_layout(); fig.savefig(report / "binder_line_junction.png", dpi=190); plt.close(fig)
    if root_rows: multi.write_csv(report / "junction_roots.csv", root_rows)


campaign.prepare = prepare
campaign.analyze = analyze

if __name__ == "__main__": raise SystemExit(campaign.main())
