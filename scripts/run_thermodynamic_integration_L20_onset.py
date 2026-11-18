#!/usr/bin/env python3
"""Replicated L=20 continuation scan across the L=16 modulation onset."""

from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np

import run_thermodynamic_integration_L16 as campaign


BASE_ANALYZE = campaign.analyze
campaign.RUN_ROOT = campaign.ROOT / "runs/thermodynamic_integration_L20_onset"
campaign.REPORT = campaign.ROOT / "reports/structure_factor_cpu/thermodynamic_integration_L20_onset"
campaign.Z_VALUES = (-2.25, -2.2625, -2.275, -2.2875, -2.3, -2.3125, -2.325)
REPLICAS = (0, 1)


def mass_grid(center: float, Z: float, step: float = 0.25) -> list[float]:
    low = center - 4.0
    high = max(1.5, Z * Z / 4 + 1.0)
    values = list(np.arange(low, high + 0.5 * step, step))
    values.extend((low, center, high))
    return sorted({round(float(value), 10) for value in values})


def prepare(_: object) -> int:
    campaign.REPORT.mkdir(parents=True, exist_ok=True)
    campaign.RUN_ROOT.mkdir(parents=True, exist_ok=True)
    coefficients = campaign.crossing_fit()
    rows = []
    for replica in REPLICAS:
        replica_report = campaign.REPORT / f"r{replica}"
        replica_report.mkdir(parents=True, exist_ok=True)
        replica_rows = []
        for index, Z in enumerate(campaign.Z_VALUES):
            center = float(np.polyval(coefficients, Z))
            masses = mass_grid(center, Z)
            tag = f"{Z:.4f}".replace("-", "m").replace(".", "p")
            output = campaign.RUN_ROOT / f"r{replica}" / f"Z{tag}" / "statistics.csv"
            row = {
                "task_id": replica * len(campaign.Z_VALUES) + index,
                "replicate": replica,
                "L": 20,
                "Z": Z,
                "binder_line_m2": center,
                "masses": ";".join(map(repr, masses)),
                "seed": 720011 + 104729 * replica + 7919 * index,
                "eps": 0.0085,
                "n_lf": 15,
                "settle": 100,
                "initial_settle": 300,
                "samples": 100,
                "skip": 2,
                "output": str(output),
            }
            rows.append(row)
            replica_rows.append(row)
        write_manifest(replica_report / "manifest.csv", replica_rows)
    write_manifest(campaign.REPORT / "manifest.csv", rows)
    total = sum(len(row["masses"].split(";")) for row in rows)
    print(f"prepared={len(rows)} mass_points={total} branch_points={3 * total}")
    return 0


def write_manifest(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def analyze(args: object) -> int:
    root_report = campaign.REPORT
    summaries = []
    try:
        for replica in REPLICAS:
            campaign.REPORT = root_report / f"r{replica}"
            status = BASE_ANALYZE(args)
            if status:
                return status
            for row in csv.DictReader((campaign.REPORT / "crossing_summary.csv").open()):
                row = dict(row)
                row["replicate"] = replica
                summaries.append(row)
    finally:
        campaign.REPORT = root_report
    write_manifest(root_report / "replica_crossing_summary.csv", summaries)
    build_comparison(root_report, summaries)
    return 0


def build_comparison(report: Path, summaries: list[dict]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    l16_path = (campaign.ROOT /
                "reports/structure_factor_cpu/thermodynamic_integration_L16_wide/crossing_summary.csv")
    l16 = [row for row in csv.DictReader(l16_path.open())
           if -2.34 <= float(row["Z"]) <= -2.24]

    fig, axes = plt.subplots(3, 1, figsize=(8.2, 10.8), sharex=True)
    colors = ("tab:blue", "tab:orange")
    onset_rows = []
    for replica, color in zip(REPLICAS, colors):
        selected = sorted((row for row in summaries if int(row["replicate"]) == replica),
                          key=lambda row: float(row["Z"]))
        z = np.asarray([float(row["Z"]) for row in selected])
        delta = np.asarray([float(row["delta_f_finite_q_uniform_at_binder"]) for row in selected])
        shell = np.asarray([float(row["finite_q_shell_at_binder"]) for row in selected])
        boundary = np.asarray([float(row["q0_to_any_finite_q_m2"])
                               if row["q0_to_any_finite_q_m2"] else math.nan
                               for row in selected])
        axes[0].plot(z, delta, marker="o", color=color, label=f"L=20 replica {replica}")
        axes[1].plot(z, shell, marker="o", color=color, label=f"L=20 replica {replica}")
        axes[2].plot(z, boundary, marker="o", color=color, label=f"L=20 replica {replica}")
        roots = sign_change_roots(z, delta)
        brackets = sign_change_brackets(z, delta)
        onset_rows.append({
            "L": 20,
            "replicate": replica,
            "sign_change_brackets_Z": ";".join(f"[{a:.6g},{b:.6g}]" for a, b in brackets),
            "linear_roots_Z": ";".join(f"{root:.10g}" for root in roots),
            "minimum_delta_f_at_binder": float(np.min(delta)),
            "maximum_delta_f_at_binder": float(np.max(delta)),
        })

    if l16:
        l16.sort(key=lambda row: float(row["Z"]))
        z16 = np.asarray([float(row["Z"]) for row in l16])
        d16 = np.asarray([float(row["delta_f_finite_q_uniform_at_binder"]) for row in l16])
        q16 = np.asarray([float(row["finite_q_shell_at_binder"]) for row in l16])
        b16 = np.asarray([float(row["q0_to_any_finite_q_m2"])
                          if row["q0_to_any_finite_q_m2"] else math.nan for row in l16])
        axes[0].plot(z16, d16, "k--o", label="L=16")
        axes[1].plot(z16, q16, "k--o", label="L=16")
        axes[2].plot(z16, b16, "k--o", label="L=16")

    zguide = np.asarray(sorted(campaign.Z_VALUES))
    binder = np.polyval(campaign.crossing_fit(), zguide)
    axes[0].axhline(0, color="0.25", lw=0.9)
    axes[0].set(ylabel=r"$f_{q>0}-f_{q=0}$ at extrapolated Binder line",
                title="Finite-size modulation-onset comparison")
    axes[1].plot(zguide, -zguide / 2, color="0.5", ls=":", label=r"bare $-Z/2$")
    axes[1].set(ylabel="selected coherent shell q")
    axes[2].plot(zguide, binder, color="0.4", ls=":", label="extrapolated Binder line")
    axes[2].set(xlabel="Z", ylabel=r"crossing $m^2$")
    for axis in axes:
        axis.grid(alpha=0.22)
        axis.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(report / "L16_L20_onset_comparison.png", dpi=190)
    plt.close(fig)
    write_manifest(report / "finite_size_onset_summary.csv", onset_rows)


def sign_change_brackets(z: np.ndarray, values: np.ndarray) -> list[tuple[float, float]]:
    brackets = []
    for left, right in zip(range(len(z) - 1), range(1, len(z))):
        if values[left] * values[right] < 0:
            brackets.append((float(z[left]), float(z[right])))
    return brackets


def sign_change_roots(z: np.ndarray, values: np.ndarray) -> list[float]:
    roots = []
    for left, right in zip(range(len(z) - 1), range(1, len(z))):
        if values[left] * values[right] < 0:
            fraction = -values[left] / (values[right] - values[left])
            roots.append(float(z[left] + fraction * (z[right] - z[left])))
    return roots


campaign.prepare = prepare
campaign.analyze = analyze


if __name__ == "__main__":
    raise SystemExit(campaign.main())
