#!/usr/bin/env python3
"""Wide L=16 CPU map of uniform, modulated, and disordered continuations."""

from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np

import run_thermodynamic_integration_L16 as campaign


BASE_ANALYZE = campaign.analyze
campaign.RUN_ROOT = campaign.ROOT / "runs/thermodynamic_integration_L16_wide"
campaign.REPORT = campaign.ROOT / "reports/structure_factor_cpu/thermodynamic_integration_L16_wide"
campaign.Z_VALUES = tuple(sorted(
    {round(float(value), 3) for value in np.arange(-0.5, -3.0001, -0.125)} |
    {round(float(value), 3) for value in np.arange(-2.25, -2.5001, -0.025)},
    reverse=True,
))


def wide_mass_grid(center: float, Z: float, step: float = 0.25) -> list[float]:
    # Once the modulated boundary crosses the extrapolated Binder line, a much
    # deeper low-mass endpoint is required to recover the uniform branch.
    low = center - (4.0 if Z <= -2.3 else 0.75)
    high = max(1.5, Z * Z / 4 + 1.0)
    values = list(np.arange(low, high + 0.5 * step, step))
    values.extend((low, center, high))
    return sorted({round(float(value), 10) for value in values})


def prepare(_: object) -> int:
    campaign.REPORT.mkdir(parents=True, exist_ok=True)
    campaign.RUN_ROOT.mkdir(parents=True, exist_ok=True)
    coefficients = campaign.crossing_fit()
    rows = []
    for task_id, Z in enumerate(campaign.Z_VALUES):
        center = float(np.polyval(coefficients, Z))
        masses = wide_mass_grid(center, Z)
        tag = f"{Z:.3f}".replace("-", "m").replace(".", "p")
        suffix = "_deep" if Z <= -2.3 else ""
        output = campaign.RUN_ROOT / f"Z{tag}{suffix}" / "statistics.csv"
        rows.append({
            "task_id": task_id,
            "Z": Z,
            "binder_line_m2": center,
            "masses": ";".join(map(repr, masses)),
            "seed": 410003 + 7919 * task_id,
            "output": str(output),
        })
    with (campaign.REPORT / "manifest.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    total = sum(len(row["masses"].split(";")) for row in rows)
    print(f"prepared={len(rows)} mass_points={total} branch_points={3 * total}")
    return 0


def analyze(args: object) -> int:
    status = BASE_ANALYZE(args)
    if status:
        return status
    plot_phase_map()
    return 0


def plot_phase_map() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from matplotlib.lines import Line2D

    path = campaign.REPORT / "integrated_branches.csv"
    rows = list(csv.DictReader(path.open()))
    labels = ("ambiguous", "disordered", "q=0 ordered", "finite-q ordered")
    label_number = {label: index for index, label in enumerate(labels)}
    colors = ("#bdbdbd", "#f4a261", "#4575b4", "#7b3294")
    cmap = ListedColormap(colors)
    norm = BoundaryNorm(np.arange(-0.5, len(labels) + 0.5), cmap.N)

    z = np.asarray([float(row["Z"]) for row in rows])
    mass = np.asarray([float(row["m2"]) for row in rows])
    physical_labels = []
    q_selected = []
    strength = []
    for row in rows:
        branch = row["preferred_branch_2mcse"]
        if branch == "uniform":
            physical_labels.append("q=0 ordered")
            q_selected.append(0.0)
            strength.append(float(row["peak_S_uniform"]))
        elif branch in ("modulated", "disordered"):
            suffix = "modulated" if branch == "modulated" else "disordered"
            branch_strength = float(row[f"peak_S_{suffix}"])
            branch_q = float(row[f"qpeak_{suffix}"])
            if branch_strength >= 10 and branch_q > 0:
                physical_labels.append("finite-q ordered")
                q_selected.append(branch_q)
            else:
                physical_labels.append("disordered")
                q_selected.append(math.nan)
            strength.append(branch_strength)
        else:
            physical_labels.append("ambiguous")
            q_selected.append(math.nan)
            strength.append(float(row["peak_S_modulated"]))
    phase = np.asarray([label_number[label] for label in physical_labels])
    q_selected = np.asarray(q_selected)
    strength = np.asarray(strength)

    fig, axes = plt.subplots(1, 2, figsize=(13.0, 6.2), sharex=True, sharey=True)
    axes[0].scatter(z, mass, c=phase, cmap=cmap, norm=norm, marker="s", s=22, linewidths=0)
    handles = [Line2D([], [], marker="s", ls="", color=color, label=label)
               for label, color in zip(labels, colors)]
    axes[0].legend(handles=handles, frameon=False, fontsize=8, loc="lower left")
    axes[0].set_title("Two-MCSE preferred restricted branch")

    coherent = np.isfinite(q_selected)
    scatter = axes[1].scatter(z[coherent], mass[coherent], c=q_selected[coherent],
                              cmap="magma", vmin=0, vmax=max(1.5, np.nanmax(q_selected)),
                              s=np.clip(12 + 4 * np.sqrt(strength[coherent]), 14, 70),
                              linewidths=0)
    fig.colorbar(scatter, ax=axes[1], label="selected peak shell q")
    axes[1].set_title("Selected ordered momentum; size scales with peak strength")

    summary = list(csv.DictReader((campaign.REPORT / "crossing_summary.csv").open()))
    summary.sort(key=lambda row: float(row["Z"]))
    zs = np.asarray([float(row["Z"]) for row in summary])
    binder = np.asarray([float(row["binder_line_m2"]) for row in summary])
    boundary = np.asarray([
        float(row["q0_to_any_finite_q_m2"])
        if row["q0_to_any_finite_q_m2"] else math.nan for row in summary
    ])
    for axis in axes:
        axis.plot(zs, binder, "k-", lw=1.5, label="extrapolated Binder line")
        axis.plot(zs, boundary, color="cyan", lw=1.8, label=r"$q=0$ / finite-$q$")
        axis.set(xlabel="Z", ylabel=r"$m^2$")
        axis.grid(alpha=0.18)
    axes[1].legend(frameon=False, fontsize=8, loc="lower left")
    fig.suptitle("Wide L=16 continuation map (exploratory)")
    fig.tight_layout()
    fig.savefig(campaign.REPORT / "wide_phase_map.png", dpi=190)
    plt.close(fig)


campaign.prepare = prepare
campaign.analyze = analyze


if __name__ == "__main__":
    raise SystemExit(campaign.main())
