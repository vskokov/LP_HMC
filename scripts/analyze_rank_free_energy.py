#!/usr/bin/env python3
"""Analyze rank-resolved mass continuations and compare restricted free energies."""

from __future__ import annotations

import csv
import json
import math
import os
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-lp-hmc")

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/structure_factor_cpu/modulation_rank_free_energy_gpu"
MANIFEST = REPORT / "manifest.csv"
RANKS = (1, 2, 3)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def branch_rank(branch: str) -> int | None:
    if branch.startswith("shell_"):
        return 1
    if branch.startswith("rank2_"):
        return 2
    if branch.startswith("rank3_"):
        return 3
    return None


def observed_rank(row: dict[str, str]) -> str:
    peak = float(row["peak_S"])
    excess = float(row["rank_raw_excess_power"])
    if peak < 10.0 or excess <= 0:
        return "unmodulated"
    initialized = float(row["q_initialized"])
    q_peak = float(row["q_mean_peak"])
    if not math.isclose(q_peak, initialized, abs_tol=5e-10, rel_tol=0.0):
        return "off_target"
    values = [float(row[f"rank_lambda{i}"]) for i in RANKS]
    total = sum(values)
    if total <= 0:
        return "undetermined"
    values = [value / total for value in values]
    return "rank1" if values[1] < 0.15 else ("rank2" if values[2] < 0.15 else "rank3")


def integrate_difference(rows_a: list[dict[str, str]],
                         rows_b: list[dict[str, str]]) -> dict[float, tuple[float, float]]:
    """Return F_a-F_b, normalized to zero at the common largest mass."""
    a = {float(row["m2"]): row for row in rows_a}
    b = {float(row["m2"]): row for row in rows_b}
    masses = sorted(set(a) & set(b), reverse=True)
    if len(masses) != len(a) or len(masses) != len(b):
        raise ValueError("branch mass grids differ")
    result = {masses[0]: (0.0, 0.0)}
    value = variance = 0.0
    for high, low in zip(masses, masses[1:]):
        # d(F_a-F_b)/dm2 = (Q_a-Q_b)/2.
        derivatives = []
        derivative_variances = []
        for mass in (high, low):
            qa, qb = float(a[mass]["Q_density"]), float(b[mass]["Q_density"])
            ea, eb = float(a[mass]["Q_density_mcse"]), float(b[mass]["Q_density_mcse"])
            derivatives.append(0.5 * (qa - qb))
            derivative_variances.append(0.25 * (ea * ea + eb * eb))
        width = low - high
        value += 0.5 * width * sum(derivatives)
        variance += (0.5 * width) ** 2 * sum(derivative_variances)
        result[low] = (value, variance)
    return result


def aggregate(values: list[tuple[float, float]]) -> tuple[float, float, float]:
    """Mean and conservative SE combining propagated MCSE and replica spread."""
    estimates = [value for value, _ in values]
    mean = sum(estimates) / len(estimates)
    within = math.sqrt(sum(variance for _, variance in values)) / len(values)
    between = (abs(estimates[0] - estimates[1]) / 2.0
               if len(estimates) == 2 else 0.0)
    return mean, max(within, between), between


def crossings(masses: list[float], values: list[float]) -> list[float]:
    found: list[float] = []
    for x0, x1, y0, y1 in zip(masses, masses[1:], values, values[1:]):
        if y0 == 0:
            found.append(x0)
        elif y0 * y1 < 0:
            found.append(x0 - y0 * (x1 - x0) / (y1 - y0))
    return found


def main() -> None:
    manifest = read_csv(MANIFEST)
    replica_data: dict[tuple[int, float, int], dict[int, list[dict[str, str]]]] = {}
    anchor_rows: list[dict[str, object]] = []
    pair_integrals: dict[tuple[int, float, int, int, int], dict[float, tuple[float, float]]] = {}
    observed: dict[tuple[int, float, int, int, float], str] = {}

    for task in manifest:
        L, Z, replica = int(task["L"]), float(task["Z"]), int(task["replica"])
        records = read_csv(Path(task["output"]))
        branches: dict[int, list[dict[str, str]]] = {}
        for rank in RANKS:
            selected = [row for row in records if branch_rank(row["branch"]) == rank]
            branches[rank] = sorted(selected, key=lambda row: float(row["m2"]))
            for row in selected:
                observed[(L, Z, replica, rank, float(row["m2"]))] = observed_rank(row)
        replica_data[(L, Z, replica)] = branches

        anchor = float(task["anchor_m2"])
        endpoint = [row for row in records if math.isclose(float(row["m2"]), anchor)]
        q_values = [float(row["Q_density"]) for row in endpoint]
        peak_values = [float(row["peak_S"]) for row in endpoint]
        anchor_rows.append({
            "L": L, "Z": Z, "replica": replica, "anchor_m2": anchor,
            "branches": len(endpoint), "Q_min": min(q_values), "Q_max": max(q_values),
            "Q_spread": max(q_values) - min(q_values),
            "maximum_peak_S": max(peak_values),
            "all_peak_S_below_10": max(peak_values) < 10.0,
            "minimum_sample_acceptance": min(float(row["sample_acceptance"]) for row in records),
        })
        for a, b in ((2, 1), (3, 1), (3, 2)):
            pair_integrals[(L, Z, replica, a, b)] = integrate_difference(branches[a], branches[b])

    integrated: list[dict[str, object]] = []
    crossing_rows: list[dict[str, object]] = []
    groups = sorted({(int(row["L"]), float(row["Z"])) for row in manifest})
    for L, Z in groups:
        replicas = sorted(int(row["replica"]) for row in manifest
                          if int(row["L"]) == L and float(row["Z"]) == Z)
        masses = sorted(pair_integrals[(L, Z, replicas[0], 2, 1)])
        aggregate_pairs: dict[tuple[int, int], dict[float, tuple[float, float, float]]] = {}
        for a, b in ((2, 1), (3, 1), (3, 2)):
            aggregate_pairs[(a, b)] = {
                mass: aggregate([pair_integrals[(L, Z, replica, a, b)][mass]
                                 for replica in replicas]) for mass in masses
            }
            means = [aggregate_pairs[(a, b)][mass][0] for mass in masses]
            found = crossings(masses, means)
            # Ignore the forced common-anchor zero when reporting physical crossings.
            anchor = masses[-1]
            found = [value for value in found if abs(value - anchor) > 1e-9]
            crossing_rows.append({
                "L": L, "Z": Z, "pair": f"rank{a}_minus_rank{b}",
                "crossing_count": len(found),
                "crossings_m2": ";".join(f"{value:.8g}" for value in found),
            })

        for mass in masses:
            d21, e21, s21 = aggregate_pairs[(2, 1)][mass]
            d31, e31, s31 = aggregate_pairs[(3, 1)][mass]
            d32, e32, s32 = aggregate_pairs[(3, 2)][mass]
            free = {1: 0.0, 2: d21, 3: d31}
            order = sorted(RANKS, key=lambda rank: free[rank])
            winner, runner = order[0], order[1]
            if (winner, runner) == (1, 2): gap, gap_error = -d21, e21
            elif (winner, runner) == (1, 3): gap, gap_error = -d31, e31
            elif (winner, runner) == (2, 1): gap, gap_error = d21, e21
            elif (winner, runner) == (2, 3): gap, gap_error = -d32, e32
            elif (winner, runner) == (3, 1): gap, gap_error = d31, e31
            else: gap, gap_error = d32, e32
            # gap is F_winner-F_runner and should be negative.
            separation = (0.0 if abs(gap) < 1e-15 else
                          (abs(gap) / gap_error if gap_error > 0 else math.inf))
            winner_label = f"rank{winner}" if separation >= 2.0 else "unresolved"
            observed_votes = [observed[(L, Z, replica, winner, mass)] for replica in replicas]
            observed_label = observed_votes[0] if len(set(observed_votes)) == 1 else "replica_disagreement"
            if winner_label == "unresolved":
                physical_preference = "unresolved"
            elif observed_label in ("rank1", "rank2", "rank3"):
                physical_preference = observed_label
            else:
                physical_preference = "not_modulated_or_not_reproducible"
            integrated.append({
                "L": L, "Z": Z, "m2": mass,
                "delta_f_rank2_minus_rank1": d21, "delta_f_rank2_minus_rank1_se": e21,
                "delta_f_rank3_minus_rank1": d31, "delta_f_rank3_minus_rank1_se": e31,
                "delta_f_rank3_minus_rank2": d32, "delta_f_rank3_minus_rank2_se": e32,
                "replica_spread_rank2_minus_rank1": s21,
                "replica_spread_rank3_minus_rank1": s31,
                "replica_spread_rank3_minus_rank2": s32,
                "preferred_seed_rank": winner_label,
                "winner_separation_sigma": separation,
                "winner_observed_rank": observed_label,
                "physical_morphology_preference": physical_preference,
            })

    write_csv(REPORT / "anchor_convergence.csv", anchor_rows)
    write_csv(REPORT / "integrated_rank_free_energy.csv", integrated)
    write_csv(REPORT / "rank_crossings.csv", crossing_rows)

    summary = {
        "tasks": len(manifest), "raw_rows": sum(int(row["expected_rows"]) for row in manifest),
        "anchor_groups": len(anchor_rows),
        "anchors_all_unmodulated_by_peak_threshold": sum(bool(row["all_peak_S_below_10"])
                                                           for row in anchor_rows),
        "minimum_sample_acceptance": min(float(row["minimum_sample_acceptance"])
                                           for row in anchor_rows),
        "preferred_counts": {label: sum(row["preferred_seed_rank"] == label for row in integrated)
                             for label in ("rank1", "rank2", "rank3", "unresolved")},
        "physical_morphology_counts": {
            label: sum(row["physical_morphology_preference"] == label for row in integrated)
            for label in ("rank1", "rank2", "rank3", "unresolved",
                          "not_modulated_or_not_reproducible")
        },
    }
    (REPORT / "analysis_summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    figure, axes = plt.subplots(len(groups) // 2, 2, figsize=(12, 14), sharex=False)
    for axis, (L, Z) in zip(axes.flat, groups):
        rows = [row for row in integrated if row["L"] == L and row["Z"] == Z]
        masses = [float(row["m2"]) for row in rows]
        for field, error, label, color in (
            ("delta_f_rank2_minus_rank1", "delta_f_rank2_minus_rank1_se", r"$F_2-F_1$", "C1"),
            ("delta_f_rank3_minus_rank1", "delta_f_rank3_minus_rank1_se", r"$F_3-F_1$", "C2"),
        ):
            axis.plot(masses, [float(row[field]) for row in rows], color=color, label=label)
            low = [float(row[field]) - 2 * float(row[error]) for row in rows]
            high = [float(row[field]) + 2 * float(row[error]) for row in rows]
            axis.fill_between(masses, low, high, color=color, alpha=0.18)
        axis.axhline(0, color="black", lw=0.8)
        axis.set(title=f"L={L}, Z={Z:g}", xlabel=r"$m^2$", ylabel=r"$\Delta f$")
        axis.grid(alpha=0.2)
    axes.flat[0].legend()
    figure.tight_layout()
    figure.savefig(REPORT / "rank_free_energy_comparison.png", dpi=180)
    plt.close(figure)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
