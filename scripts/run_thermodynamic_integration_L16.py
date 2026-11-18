#!/usr/bin/env python3
"""CPU continuation and thermodynamic-integration campaign at L=16."""

from __future__ import annotations

import argparse
import csv
import math
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
RUN_ROOT = ROOT / "runs/thermodynamic_integration_L16"
REPORT = ROOT / "reports/structure_factor_cpu/thermodynamic_integration_L16"
JULIA = "/home/vskokov/.julia/juliaup/julia-1.12.6+0.x64.linux.gnu/bin/julia"
Z_VALUES = (-0.75, -0.85, -0.95, -1.05, -1.15, -1.30, -1.50)


def crossing_fit() -> np.ndarray:
    rows = list(csv.DictReader((ROOT / "plots/binder_crossings_vs_Z.csv").open()))
    grouped = {}
    for row in rows:
        grouped.setdefault(float(row["Z"]), []).append(float(row["m2_c"]))
    z = np.asarray([-0.5, -0.25, 0.0])
    return np.polyfit(z, [np.mean(grouped[value]) for value in z], 2)


def mass_grid(center: float, high: float = 1.2, step: float = 0.2) -> list[float]:
    low = center - 0.8
    values = list(np.arange(low, high + 0.5 * step, step))
    values.extend((center, high))
    return sorted({round(float(value), 10) for value in values})


def prepare(_: argparse.Namespace) -> int:
    REPORT.mkdir(parents=True, exist_ok=True); RUN_ROOT.mkdir(parents=True, exist_ok=True)
    coefficients = crossing_fit(); rows = []
    for task_id, Z in enumerate(Z_VALUES):
        center = float(np.polyval(coefficients, Z)); masses = mass_grid(center)
        output = RUN_ROOT / f"Z{str(Z).replace('-', 'm').replace('.', 'p')}" / "statistics.csv"
        rows.append({"task_id": task_id, "Z": Z, "binder_line_m2": center,
                     "masses": ";".join(map(repr, masses)), "seed": 91001 + 7919 * task_id,
                     "output": str(output)})
    with (REPORT / "manifest.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    print(f"prepared={len(rows)} mass_points={[len(r['masses'].split(';')) for r in rows]}")
    return 0


def run_one(row: dict[str, str]) -> tuple[int, str]:
    output = Path(row["output"]); output.parent.mkdir(parents=True, exist_ok=True)
    if output.is_file(): return 0, "resume"
    environment = dict(os.environ)
    environment.update({"TI_Z": row["Z"], "TI_MASSES": row["masses"],
                        "TI_SEED": row["seed"], "TI_OUTPUT": row["output"],
                        "JULIA_NUM_THREADS": "1",
                        "JULIA_DEPOT_PATH": environment.get("JULIA_DEPOT_PATH",
                            "/tmp/lp_hmc_julia_depot:/home/vskokov/.julia")})
    for column, variable in (("L", "TI_L"), ("eps", "TI_EPS"),
                             ("n_lf", "TI_N_LF"), ("settle", "TI_SETTLE"),
                             ("initial_settle", "TI_INITIAL_SETTLE"),
                             ("samples", "TI_SAMPLES"), ("skip", "TI_SKIP"),
                             ("shell_count", "TI_SHELL_COUNT")):
        if row.get(column):
            environment[variable] = row[column]
    script = row.get("script") or "scripts/thermodynamic_integration_L16.jl"
    command = [JULIA, "--startup-file=no", f"--project={ROOT}", str(ROOT / script)]
    result = subprocess.run(command, cwd=ROOT, env=environment, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return result.returncode, result.stdout


def run(args: argparse.Namespace) -> int:
    rows = list(csv.DictReader((REPORT / "manifest.csv").open())); failures = 0
    with ProcessPoolExecutor(max_workers=min(args.workers, len(rows))) as pool:
        futures = {pool.submit(run_one, row): row for row in rows}
        for number, future in enumerate(as_completed(futures), 1):
            code, log = future.result()
            if code:
                failures += 1; print(f"failed Z={futures[future]['Z']}\n{log}")
            else: print(f"completed {number}/{len(rows)} Z={futures[future]['Z']}", flush=True)
    return int(bool(failures))


def cumulative_delta_f(masses: np.ndarray, delta_derivative: np.ndarray,
                       delta_error: np.ndarray, anchor: int) -> tuple[np.ndarray, np.ndarray]:
    values = np.full(len(masses), np.nan); errors = np.full(len(masses), np.nan)
    values[anchor] = 0.0; errors[anchor] = 0.0
    for index in range(anchor - 1, -1, -1):
        width = masses[index + 1] - masses[index]
        increment = -0.5 * width * (delta_derivative[index + 1] + delta_derivative[index])
        variance = (0.5 * width) ** 2 * (delta_error[index + 1] ** 2 + delta_error[index] ** 2)
        values[index] = values[index + 1] + increment
        errors[index] = math.sqrt(errors[index + 1] ** 2 + variance)
    return values, errors


def zero_crossings(masses: np.ndarray, values: np.ndarray) -> list[float]:
    """Return linearly interpolated interior roots, excluding the imposed anchor."""
    roots = []
    finite = np.flatnonzero(np.isfinite(values))
    for left, right in zip(finite[:-1], finite[1:]):
        if values[left] * values[right] < 0:
            fraction = -values[left] / (values[right] - values[left])
            roots.append(float(masses[left] + fraction * (masses[right] - masses[left])))
    return roots


def ordered_entry_crossings(masses: np.ndarray, values: np.ndarray,
                            peak_strength: np.ndarray, minimum_peak: float = 10.0) -> list[float]:
    """Roots entering a coherent modulated branch as m2 increases."""
    roots = []
    for left, right in zip(range(len(masses) - 1), range(1, len(masses))):
        if values[left] > 0 and values[right] < 0:
            fraction = -values[left] / (values[right] - values[left])
            strength = peak_strength[left] + fraction * (peak_strength[right] - peak_strength[left])
            if strength >= minimum_peak:
                roots.append(float(masses[left] + fraction * (masses[right] - masses[left])))
    return roots


def entry_crossings(masses: np.ndarray, values: np.ndarray) -> list[float]:
    """Positive-to-negative roots for an array that may contain NaNs."""
    roots = []
    for left, right in zip(range(len(masses) - 1), range(1, len(masses))):
        if (np.isfinite(values[left]) and np.isfinite(values[right]) and
                values[left] > 0 and values[right] < 0):
            fraction = -values[left] / (values[right] - values[left])
            roots.append(float(masses[left] + fraction * (masses[right] - masses[left])))
    return roots


def falling_threshold(masses: np.ndarray, values: np.ndarray, threshold: float) -> float:
    for left, right in zip(range(len(masses) - 1), range(1, len(masses))):
        if values[left] >= threshold and values[right] < threshold:
            fraction = (threshold - values[left]) / (values[right] - values[left])
            return float(masses[left] + fraction * (masses[right] - masses[left]))
    return math.nan


def root_string(roots: list[float]) -> str:
    return ";".join(f"{root:.10g}" for root in roots)


def preferred_branch(delta_mu: float, error_mu: float, delta_du: float,
                     error_du: float, delta_md: float, error_md: float) -> str:
    """Label a branch only when it wins both pairwise tests by two MCSE."""
    values = {"uniform": 0.0, "modulated": delta_mu, "disordered": delta_du}
    candidate = min(values, key=values.get)
    if candidate == "uniform":
        decisive = delta_mu > 2 * error_mu and delta_du > 2 * error_du
    elif candidate == "modulated":
        decisive = delta_mu < -2 * error_mu and delta_md < -2 * error_md
    else:
        decisive = delta_du < -2 * error_du and delta_md > 2 * error_md
    return candidate if decisive else "ambiguous"


def analyze(_: argparse.Namespace) -> int:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    manifest = list(csv.DictReader((REPORT / "manifest.csv").open()))
    combined = []; crossings = []; pairwise_crossings = []
    fig, axes = plt.subplots(3, 1, figsize=(8.4, 11.0), sharex=False)
    colors = plt.cm.viridis(np.linspace(0.05, 0.95, len(manifest)))
    for source, color in zip(manifest, colors):
        rows = list(csv.DictReader(Path(source["output"]).open()))
        by_branch = {branch: sorted((row for row in rows if row["branch"] == branch),
                                    key=lambda row: float(row["m2"]))
                     for branch in ("uniform", "modulated", "disordered")}
        uniform = by_branch["uniform"]
        modulated = by_branch["modulated"]
        disordered = by_branch["disordered"]
        masses = np.asarray([float(row["m2"]) for row in uniform])
        for branch_rows in (modulated, disordered):
            branch_masses = np.asarray([float(row["m2"]) for row in branch_rows])
            if not np.allclose(branch_masses, masses, rtol=0, atol=1e-10):
                raise ValueError(f"branch mass grids do not agree for Z={source['Z']}")
        q_uniform = np.asarray([float(row["Q_density"]) for row in uniform])
        q_modulated = np.asarray([float(row["Q_density"]) for row in modulated])
        q_disordered = np.asarray([float(row["Q_density"]) for row in disordered])
        e_uniform = np.asarray([float(row["Q_density_mcse"]) for row in uniform])
        e_modulated = np.asarray([float(row["Q_density_mcse"]) for row in modulated])
        e_disordered = np.asarray([float(row["Q_density_mcse"]) for row in disordered])
        peak_uniform = np.asarray([float(row["q_mean_peak"]) for row in uniform])
        peak_modulated = np.asarray([float(row["q_mean_peak"]) for row in modulated])
        peak_disordered = np.asarray([float(row["q_mean_peak"]) for row in disordered])
        strength_uniform = np.asarray([float(row["peak_S"]) for row in uniform])
        strength_modulated = np.asarray([float(row["peak_S"]) for row in modulated])
        strength_disordered = np.asarray([float(row["peak_S"]) for row in disordered])
        differences = {
            "mod_minus_uniform": 0.5 * (q_modulated - q_uniform),
            "dis_minus_uniform": 0.5 * (q_disordered - q_uniform),
            "mod_minus_dis": 0.5 * (q_modulated - q_disordered),
        }
        difference_errors = {
            "mod_minus_uniform": 0.5 * np.sqrt(e_modulated**2 + e_uniform**2),
            "dis_minus_uniform": 0.5 * np.sqrt(e_disordered**2 + e_uniform**2),
            "mod_minus_dis": 0.5 * np.sqrt(e_modulated**2 + e_disordered**2),
        }
        # The largest mass was deliberately chosen in the unique disordered regime.
        # Peak-shell labels are noise-dominated there and are not a merge criterion.
        anchor = len(masses) - 1
        free_energies = {}
        free_energy_errors = {}
        for name in differences:
            free_energies[name], free_energy_errors[name] = cumulative_delta_f(
                masses, differences[name], difference_errors[name], anchor)
        delta_mu = free_energies["mod_minus_uniform"]
        delta_du = free_energies["dis_minus_uniform"]
        delta_md = free_energies["mod_minus_dis"]
        error_mu = free_energy_errors["mod_minus_uniform"]
        error_du = free_energy_errors["dis_minus_uniform"]
        error_md = free_energy_errors["mod_minus_dis"]
        Z = float(source["Z"]); center = float(source["binder_line_m2"])
        coherent_mod = strength_modulated >= 10.0
        coherent_dis = strength_disordered >= 10.0
        finite_q_envelope = np.full(len(masses), np.nan)
        finite_q_envelope_error = np.full(len(masses), np.nan)
        finite_q_envelope_q = np.full(len(masses), np.nan)
        for index in range(len(masses)):
            candidates = []
            if coherent_mod[index] and peak_modulated[index] > 0:
                candidates.append((delta_mu[index], error_mu[index], peak_modulated[index]))
            if coherent_dis[index] and peak_disordered[index] > 0:
                candidates.append((delta_du[index], error_du[index], peak_disordered[index]))
            if candidates:
                value, error, qvalue = min(candidates, key=lambda item: item[0])
                finite_q_envelope[index] = value
                finite_q_envelope_error[index] = error
                finite_q_envelope_q[index] = qvalue
        for index, mass in enumerate(masses):
            combined.append({"Z": Z, "m2": mass, "binder_line_m2": center,
                             "Q_uniform": q_uniform[index], "Q_modulated": q_modulated[index],
                             "Q_disordered": q_disordered[index],
                             "qpeak_uniform": peak_uniform[index], "qpeak_modulated": peak_modulated[index],
                             "qpeak_disordered": peak_disordered[index],
                             "peak_S_uniform": strength_uniform[index],
                             "peak_S_modulated": strength_modulated[index],
                             "peak_S_disordered": strength_disordered[index],
                             "delta_f_mod_minus_uniform": delta_mu[index],
                             "delta_f_mod_minus_uniform_mcse": error_mu[index],
                             "delta_f_dis_minus_uniform": delta_du[index],
                             "delta_f_dis_minus_uniform_mcse": error_du[index],
                             "delta_f_mod_minus_dis": delta_md[index],
                             "delta_f_mod_minus_dis_mcse": error_md[index],
                             "delta_f_finite_q_envelope_minus_uniform": finite_q_envelope[index],
                             "delta_f_finite_q_envelope_mcse": finite_q_envelope_error[index],
                             "finite_q_envelope_shell": finite_q_envelope_q[index],
                             "preferred_branch_2mcse": preferred_branch(
                                 delta_mu[index], error_mu[index], delta_du[index],
                                 error_du[index], delta_md[index], error_md[index]),
                             "anchor_mass": masses[anchor]})
        roots_mu = zero_crossings(masses, delta_mu)
        roots_du = zero_crossings(masses, delta_du)
        roots_md = zero_crossings(masses, delta_md)
        ordered_entries = ordered_entry_crossings(masses, delta_mu, strength_modulated)
        envelope_entries = entry_crossings(masses, finite_q_envelope)
        coherence_limit = falling_threshold(masses, strength_modulated, 10.0)
        for pair, roots in (("modulated-uniform", roots_mu),
                            ("disordered-uniform", roots_du),
                            ("modulated-disordered", roots_md)):
            for root in roots:
                pairwise_crossings.append({"Z": Z, "pair": pair, "crossing_m2": root,
                                           "binder_line_m2": center})
        crossings.append({"Z": Z, "binder_line_m2": center, "merge_anchor_m2": masses[anchor],
                          "mod_uniform_crossings_m2": root_string(roots_mu),
                          "dis_uniform_crossings_m2": root_string(roots_du),
                          "mod_dis_crossings_m2": root_string(roots_md),
                          "q0_to_coherent_modulated_m2": root_string(ordered_entries),
                          "q0_to_any_finite_q_m2": root_string(envelope_entries),
                          "offset_from_binder_line": (ordered_entries[0] - center
                                                       if ordered_entries else math.nan),
                          "any_finite_q_offset_from_binder": (envelope_entries[0] - center
                                                               if envelope_entries else math.nan),
                          "finite_q_boundary_status": ("bracketed" if envelope_entries else
                              "finite_q_at_low_edge" if np.isfinite(finite_q_envelope[0]) and
                              finite_q_envelope[0] < 0 else "not_found"),
                          "modulated_peak_S10_limit_m2": coherence_limit,
                          "delta_f_mod_uniform_at_binder": float(np.interp(center, masses, delta_mu)),
                          "delta_f_dis_uniform_at_binder": float(np.interp(center, masses, delta_du)),
                          "delta_f_mod_dis_at_binder": float(np.interp(center, masses, delta_md)),
                          "delta_f_finite_q_uniform_at_binder": finite_q_envelope[
                              int(np.argmin(np.abs(masses - center)))],
                          "finite_q_shell_at_binder": finite_q_envelope_q[
                              int(np.argmin(np.abs(masses - center)))],
                          "minimum_delta_f_mod_uniform": float(np.nanmin(delta_mu)),
                          "minimum_delta_f_dis_uniform": float(np.nanmin(delta_du))})
        axes[0].plot(masses, delta_mu, marker="o", ms=3, color=color, label=f"Z={Z:g}")
        axes[1].plot(masses, delta_du, marker="o", ms=3, color=color, label=f"Z={Z:g}")
    for axis in axes[:2]:
        axis.axhline(0, color="k", lw=0.8)
        axis.grid(alpha=0.25)
    axes[0].set(ylabel=r"$f_{mod}-f_{q=0}$", title="Restricted-branch thermodynamic integration")
    axes[0].legend(frameon=False, ncol=2, fontsize=8)
    axes[1].set(xlabel=r"$m^2$", ylabel=r"$f_{dis}-f_{q=0}$")
    z_summary = np.asarray([row["Z"] for row in crossings])
    axes[2].plot(z_summary, [row["binder_line_m2"] for row in crossings],
                 color="k", marker="o", label="extrapolated Binder line")
    physical_y = [(float(row["q0_to_any_finite_q_m2"])
                   if row["q0_to_any_finite_q_m2"] else math.nan)
                  for row in crossings]
    axes[2].plot(z_summary, physical_y,
                 color="tab:blue", marker="o", label=r"$q=0$ to lowest coherent finite-$q$")
    axes[2].plot(z_summary, [row["modulated_peak_S10_limit_m2"] for row in crossings],
                 color="tab:orange", marker="s", ls="--", label=r"finite-$q$ branch: $S_{peak}=10$")
    axes[2].set(xlabel="Z", ylabel=r"$m^2$",
                title="Physical ordered-branch crossing and coherence range")
    axes[2].grid(alpha=0.25); axes[2].legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(REPORT / "thermodynamic_integration.png", dpi=180); plt.close(fig)
    for path, rows in ((REPORT / "integrated_branches.csv", combined),
                       (REPORT / "crossing_summary.csv", crossings),
                       (REPORT / "pairwise_crossings.csv", pairwise_crossings)):
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    print(f"analysis={REPORT} Z_points={len(crossings)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest="command", required=True)
    item = sub.add_parser("prepare"); item.set_defaults(function=prepare)
    item = sub.add_parser("run"); item.add_argument("--workers", type=int, default=7); item.set_defaults(function=run)
    item = sub.add_parser("analyze"); item.set_defaults(function=analyze)
    args = parser.parse_args(); return args.function(args)


if __name__ == "__main__": raise SystemExit(main())
