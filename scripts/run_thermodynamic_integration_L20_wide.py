#!/usr/bin/env python3
"""Wide L=20 CPU continuation map in Z and m2."""

from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np

import run_thermodynamic_integration_L16 as campaign


BASE_ANALYZE = campaign.analyze
campaign.RUN_ROOT = campaign.ROOT / "runs/thermodynamic_integration_L20_wide"
campaign.REPORT = campaign.ROOT / "reports/structure_factor_cpu/thermodynamic_integration_L20_wide"
campaign.Z_VALUES = tuple(sorted(
    {round(float(value), 3) for value in np.arange(-0.5, -2.2501, -0.125)} |
    {round(float(value), 3) for value in np.arange(-2.25, -2.6001, -0.025)} |
    {round(float(value), 3) for value in np.arange(-2.65, -3.0001, -0.05)},
    reverse=True,
))


def mass_grid(center: float, Z: float, step: float = 0.25) -> list[float]:
    low = center - (4.0 if Z <= -2.25 else 0.75)
    high = max(1.5, Z * Z / 4 + 1.0)
    values = list(np.arange(low, high + 0.5 * step, step))
    values.extend((low, center, high))
    return sorted({round(float(value), 10) for value in values})


def existing_output(Z: float) -> Path | None:
    previous = campaign.ROOT / "runs/thermodynamic_integration_L20_onset/r0"
    tag = f"{Z:.4f}".replace("-", "m").replace(".", "p")
    candidate = previous / f"Z{tag}" / "statistics.csv"
    return candidate if candidate.is_file() else None


def prepare(_: object) -> int:
    campaign.REPORT.mkdir(parents=True, exist_ok=True)
    campaign.RUN_ROOT.mkdir(parents=True, exist_ok=True)
    coefficients = campaign.crossing_fit()
    rows = []
    reused = 0
    for index, Z in enumerate(campaign.Z_VALUES):
        center = float(np.polyval(coefficients, Z))
        masses = mass_grid(center, Z)
        tag = f"{Z:.3f}".replace("-", "m").replace(".", "p")
        prior = existing_output(Z)
        if prior is not None:
            output = prior
            reused += 1
        else:
            output = campaign.RUN_ROOT / f"Z{tag}" / "statistics.csv"
        rows.append({
            "task_id": index,
            "L": 20,
            "Z": Z,
            "binder_line_m2": center,
            "masses": ";".join(map(repr, masses)),
            "seed": 930007 + 7919 * index,
            "eps": 0.0085,
            "n_lf": 15,
            "settle": 100,
            "initial_settle": 300,
            "samples": 100,
            "skip": 2,
            "output": str(output),
        })
    with (campaign.REPORT / "manifest.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    total = sum(len(row["masses"].split(";")) for row in rows)
    print(f"prepared={len(rows)} reused={reused} mass_points={total} branch_points={3 * total}")
    return 0


def analyze(args: object) -> int:
    status = BASE_ANALYZE(args)
    if status:
        return status
    build_phase_map()
    return 0


def build_phase_map() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from matplotlib.lines import Line2D

    rows = list(csv.DictReader((campaign.REPORT / "integrated_branches.csv").open()))
    labels = ("ambiguous", "disordered", "q=0 ordered", "finite-q ordered")
    label_number = {label: index for index, label in enumerate(labels)}
    colors = ("#bdbdbd", "#f4a261", "#4575b4", "#7b3294")
    physical_labels = []
    selected_q = []
    selected_strength = []
    for row in rows:
        branch = row["preferred_branch_2mcse"]
        if branch == "uniform":
            physical_labels.append("q=0 ordered")
            selected_q.append(0.0)
            selected_strength.append(float(row["peak_S_uniform"]))
        elif branch in ("modulated", "disordered"):
            suffix = "modulated" if branch == "modulated" else "disordered"
            strength = float(row[f"peak_S_{suffix}"])
            qvalue = float(row[f"qpeak_{suffix}"])
            if strength >= 10 and qvalue > 0:
                physical_labels.append("finite-q ordered")
                selected_q.append(qvalue)
            else:
                physical_labels.append("disordered")
                selected_q.append(math.nan)
            selected_strength.append(strength)
        else:
            physical_labels.append("ambiguous")
            selected_q.append(math.nan)
            selected_strength.append(float(row["peak_S_modulated"]))

    z = np.asarray([float(row["Z"]) for row in rows])
    mass = np.asarray([float(row["m2"]) for row in rows])
    phase = np.asarray([label_number[label] for label in physical_labels])
    selected_q = np.asarray(selected_q)
    selected_strength = np.asarray(selected_strength)
    cmap = ListedColormap(colors)
    norm = BoundaryNorm(np.arange(-0.5, len(labels) + 0.5), cmap.N)

    summary = sorted(csv.DictReader((campaign.REPORT / "crossing_summary.csv").open()),
                     key=lambda row: float(row["Z"]))
    zs = np.asarray([float(row["Z"]) for row in summary])
    binder = np.asarray([float(row["binder_line_m2"]) for row in summary])
    boundary = np.asarray([float(row["q0_to_any_finite_q_m2"])
                           if row["q0_to_any_finite_q_m2"] else math.nan
                           for row in summary])

    fig, axes = plt.subplots(1, 2, figsize=(13.0, 6.3), sharex=True, sharey=True)
    axes[0].scatter(z, mass, c=phase, cmap=cmap, norm=norm, marker="s", s=25, linewidths=0)
    handles = [Line2D([], [], marker="s", ls="", color=color, label=label)
               for label, color in zip(labels, colors)]
    axes[0].legend(handles=handles, frameon=False, fontsize=8, loc="lower left")
    axes[0].set_title("Two-MCSE preferred phase")
    coherent = np.isfinite(selected_q)
    scatter = axes[1].scatter(
        z[coherent], mass[coherent], c=selected_q[coherent], cmap="magma",
        vmin=0, vmax=max(1.6, np.nanmax(selected_q)),
        s=np.clip(12 + 4 * np.sqrt(selected_strength[coherent]), 14, 70), linewidths=0)
    fig.colorbar(scatter, ax=axes[1], label="selected peak shell q")
    axes[1].set_title("Selected ordered momentum")
    for axis in axes:
        axis.plot(zs, binder, "k-", lw=1.5, label="extrapolated Binder line")
        axis.plot(zs, boundary, color="cyan", lw=1.8, label=r"$q=0$ / finite-$q$")
        axis.set(xlabel="Z", ylabel=r"$m^2$")
        axis.grid(alpha=0.18)
    axes[1].legend(frameon=False, fontsize=8, loc="lower left")
    fig.suptitle("Wide L=20 continuation map (exploratory)")
    fig.tight_layout()
    fig.savefig(campaign.REPORT / "wide_phase_map.png", dpi=190)
    plt.close(fig)


campaign.prepare = prepare
campaign.analyze = analyze


if __name__ == "__main__":
    raise SystemExit(campaign.main())
