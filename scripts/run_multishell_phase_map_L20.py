#!/usr/bin/env python3
"""Multi-shell L=20 continuation map and connection to the Binder line."""

from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np

import run_thermodynamic_integration_L16 as campaign


campaign.RUN_ROOT = campaign.ROOT / "runs/thermodynamic_integration_multishell_L20"
campaign.REPORT = campaign.ROOT / "reports/structure_factor_cpu/thermodynamic_integration_multishell_L20"
campaign.Z_VALUES = tuple(round(float(value), 3) for value in np.arange(-0.5, -2.5001, -0.125))


def mass_grid(center: float, Z: float, step: float = 0.2) -> list[float]:
    low = center - (4.0 if Z <= -2.25 else 0.8)
    high = max(1.5, Z * Z / 4 + 1.0)
    values = list(np.arange(low, high + 0.5 * step, step))
    values.extend((low, center, high))
    return sorted({round(float(value), 10) for value in values})


def prepare(_: object) -> int:
    campaign.REPORT.mkdir(parents=True, exist_ok=True)
    campaign.RUN_ROOT.mkdir(parents=True, exist_ok=True)
    coefficients = campaign.crossing_fit(); rows = []
    for index, Z in enumerate(campaign.Z_VALUES):
        center = float(np.polyval(coefficients, Z)); masses = mass_grid(center, Z)
        tag = f"{Z:.3f}".replace("-", "m").replace(".", "p")
        rows.append({
            "task_id": index, "L": 20, "Z": Z, "binder_line_m2": center,
            "masses": ";".join(map(repr, masses)), "seed": 1500011 + 7919 * index,
            "eps": 0.0085, "n_lf": 15, "settle": 100, "initial_settle": 300,
            "samples": 100, "skip": 2, "shell_count": 5,
            "script": "scripts/thermodynamic_integration_multishell.jl",
            "output": str(campaign.RUN_ROOT / f"Z{tag}" / "statistics.csv"),
        })
    write_csv(campaign.REPORT / "manifest.csv", rows)
    masses = sum(len(row["masses"].split(";")) for row in rows)
    print(f"prepared={len(rows)} mass_points={masses} branch_points={7 * masses}")
    return 0


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def analyze(_: object) -> int:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    manifest = list(csv.DictReader((campaign.REPORT / "manifest.csv").open()))
    integrated = []; summary = []
    for source in manifest:
        raw = list(csv.DictReader(Path(source["output"]).open()))
        branches = sorted({row["branch"] for row in raw})
        by_branch = {name: sorted((row for row in raw if row["branch"] == name),
                                  key=lambda row: float(row["m2"])) for name in branches}
        uniform = by_branch["uniform"]
        masses = np.asarray([float(row["m2"]) for row in uniform])
        q_uniform = np.asarray([float(row["Q_density"]) for row in uniform])
        e_uniform = np.asarray([float(row["Q_density_mcse"]) for row in uniform])
        anchor = len(masses) - 1
        branch_data = {}
        for name in branches:
            if name == "uniform": continue
            rows = by_branch[name]
            branch_masses = np.asarray([float(row["m2"]) for row in rows])
            if not np.allclose(masses, branch_masses, rtol=0, atol=1e-10):
                raise ValueError(f"mass grid mismatch for Z={source['Z']} branch={name}")
            q = np.asarray([float(row["Q_density"]) for row in rows])
            error = np.asarray([float(row["Q_density_mcse"]) for row in rows])
            derivative = 0.5 * (q - q_uniform)
            derivative_error = 0.5 * np.sqrt(error**2 + e_uniform**2)
            delta, delta_error = campaign.cumulative_delta_f(
                masses, derivative, derivative_error, anchor)
            branch_data[name] = {
                "delta": delta, "error": delta_error,
                "peak": np.asarray([float(row["q_mean_peak"]) for row in rows]),
                "strength": np.asarray([float(row["peak_S"]) for row in rows]),
                "q_initialized": float(rows[0]["q_initialized"]),
            }

        envelope = np.full(len(masses), np.nan)
        envelope_error = np.full(len(masses), np.nan)
        envelope_q = np.full(len(masses), np.nan)
        envelope_branch = [""] * len(masses)
        envelope_strength = np.full(len(masses), np.nan)
        for index in range(len(masses)):
            candidates = []
            for name, data in branch_data.items():
                if data["strength"][index] >= 10 and data["peak"][index] > 0:
                    candidates.append((data["delta"][index], name, data))
            if candidates:
                value, name, data = min(candidates, key=lambda item: item[0])
                envelope[index] = value
                envelope_error[index] = data["error"][index]
                envelope_q[index] = data["peak"][index]
                envelope_branch[index] = name
                envelope_strength[index] = data["strength"][index]

        roots = campaign.entry_crossings(masses, envelope)
        coherence_limits = [campaign.falling_threshold(masses, data["strength"], 10.0)
                            for data in branch_data.values()]
        finite_limits = [value for value in coherence_limits if math.isfinite(value)]
        coherence_limit = max(finite_limits) if finite_limits else math.nan
        center = float(source["binder_line_m2"])
        center_index = int(np.argmin(np.abs(masses - center)))
        Z = float(source["Z"])
        for index, mass in enumerate(masses):
            integrated.append({
                "Z": Z, "m2": mass, "binder_line_m2": center,
                "delta_f_finite_q_envelope_minus_uniform": envelope[index],
                "delta_f_envelope_mcse": envelope_error[index],
                "selected_finite_q": envelope_q[index],
                "selected_branch": envelope_branch[index],
                "selected_peak_S": envelope_strength[index],
            })
        summary.append({
            "Z": Z, "binder_line_m2": center,
            "q0_to_finite_q_crossings_m2": ";".join(f"{root:.10g}" for root in roots),
            "ordered_boundary_m2": roots[0] if roots else math.nan,
            "finite_q_coherence_limit_m2": coherence_limit,
            "modulated_wedge_width": (coherence_limit - roots[0]
                                       if roots and math.isfinite(coherence_limit) else math.nan),
            "delta_f_at_binder_line": envelope[center_index],
            "delta_f_mcse_at_binder_line": envelope_error[center_index],
            "selected_q_at_binder_line": envelope_q[center_index],
            "selected_branch_at_binder_line": envelope_branch[center_index],
            "initialized_shells": ";".join(
                f"{data['q_initialized']:.12g}" for name, data in branch_data.items()
                if name.startswith("shell_")),
        })

    write_csv(campaign.REPORT / "integrated_multishell.csv", integrated)
    write_csv(campaign.REPORT / "multishell_summary.csv", summary)
    plot_results(summary, integrated, plt)
    print(f"analysis={campaign.REPORT} Z_points={len(summary)}")
    return 0


def plot_results(summary, integrated, plt) -> None:
    summary = sorted(summary, key=lambda row: row["Z"])
    z = np.asarray([row["Z"] for row in summary])
    binder = np.asarray([row["binder_line_m2"] for row in summary])
    ordered = np.asarray([row["ordered_boundary_m2"] for row in summary])
    coherence = np.asarray([row["finite_q_coherence_limit_m2"] for row in summary])
    delta = np.asarray([row["delta_f_at_binder_line"] for row in summary])
    delta_error = np.asarray([row["delta_f_mcse_at_binder_line"] for row in summary])
    selected_q = np.asarray([row["selected_q_at_binder_line"] for row in summary])

    binder_rows = list(csv.DictReader((campaign.ROOT / "plots/binder_crossings_vs_Z.csv").open()))
    binder_means = {}
    for row in binder_rows:
        binder_means.setdefault(float(row["Z"]), []).append(float(row["m2_c"]))
    measured_z = np.asarray(sorted(binder_means))
    measured_m = np.asarray([np.mean(binder_means[value]) for value in measured_z])

    fig, axes = plt.subplots(3, 1, figsize=(8.5, 11.0), sharex=False)
    axes[0].plot(measured_z, measured_m, "ko", label="measured Binder crossings")
    positive = np.linspace(-0.5, 2.0, 150)
    axes[0].plot(positive, np.polyval(campaign.crossing_fit(), positive), "k-", alpha=0.65)
    axes[0].plot(z, binder, "k--", label="negative-Z Binder extrapolation")
    axes[0].plot(z, ordered, "o-", color="tab:blue", label=r"$q=0$/finite-$q$ equality")
    axes[0].plot(z, coherence, "s--", color="tab:orange",
                 label=r"finite-$q$ coherence proxy ($S_{peak}=10$)")
    valid = np.isfinite(ordered) & np.isfinite(coherence) & (coherence >= ordered)
    axes[0].fill_between(z, ordered, coherence, where=valid, color="tab:purple", alpha=0.16,
                         label="candidate modulated wedge")
    axes[0].set(xlabel="Z", ylabel=r"$m^2$", title="Multi-shell phase-line connection")
    axes[0].legend(frameon=False, fontsize=8, ncol=2); axes[0].grid(alpha=0.22)

    axes[1].errorbar(z, delta, yerr=delta_error, marker="o", capsize=2)
    axes[1].axhline(0, color="0.3", lw=0.9)
    axes[1].set(xlabel="Z", ylabel=r"$f_{q>0}-f_{q=0}$ at Binder line")
    axes[1].grid(alpha=0.22)
    axes[2].plot(z, selected_q, "o-", label="lowest coherent shell")
    axes[2].plot(z, -z / 2, ":", color="0.4", label=r"bare $-Z/2$")
    axes[2].set(xlabel="Z", ylabel="q at Binder line")
    axes[2].legend(frameon=False); axes[2].grid(alpha=0.22)
    fig.tight_layout(); fig.savefig(campaign.REPORT / "phase_line_connection.png", dpi=190)
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(9.0, 6.5))
    for Z in sorted({float(row["Z"]) for row in integrated}):
        rows = sorted((row for row in integrated if float(row["Z"]) == Z),
                      key=lambda row: float(row["m2"]))
        axis.plot([float(row["m2"]) for row in rows],
                  [float(row["delta_f_finite_q_envelope_minus_uniform"]) for row in rows],
                  marker="o", ms=2, label=f"Z={Z:g}")
    axis.axhline(0, color="k", lw=0.8); axis.grid(alpha=0.2)
    axis.set(xlabel=r"$m^2$", ylabel=r"$f_{q>0}^{envelope}-f_{q=0}$",
             title="Five-shell restricted free-energy envelope")
    axis.legend(frameon=False, fontsize=7, ncol=3)
    fig.tight_layout(); fig.savefig(campaign.REPORT / "multishell_envelopes.png", dpi=190)
    plt.close(fig)


campaign.prepare = prepare
campaign.analyze = analyze

if __name__ == "__main__": raise SystemExit(campaign.main())
