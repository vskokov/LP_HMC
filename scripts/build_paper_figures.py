#!/usr/bin/env python3
"""Build manuscript figures and a provenance-rich phase-boundary catalog.

The catalog intentionally keeps direct finite-size measurements separate from
restricted-branch continuation estimates.  It must not be interpreted as a
single set of thermodynamic-limit phase boundaries.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "paper" / "generated"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError(f"refusing to write empty table: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def mean_field_figure() -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2))

    z = np.linspace(-3.0, 0.0, 500)
    symmetric_modulated = z**2 / 4.0
    broken_modulated = -(2.0 + np.sqrt(6.0)) * z**2 / 4.0
    axis = axes[0]
    axis.plot(z, symmetric_modulated, color="tab:orange", lw=2.2,
              label=r"symmetric--modulated: $r=Z^2/4$")
    axis.plot(z, broken_modulated, color="tab:purple", lw=2.2,
              label=r"broken--modulated: $r=-(2+\sqrt{6})Z^2/4$")
    axis.plot([0.0, 1.0], [0.0, 0.0], color="tab:blue", lw=2.2,
              label=r"symmetric--broken: $r=0$")
    axis.fill_between(z, symmetric_modulated, 3.0, color="tab:orange", alpha=0.10)
    axis.fill_between(z, broken_modulated, symmetric_modulated,
                      color="tab:purple", alpha=0.12)
    axis.fill_between(z, -11.0, broken_modulated, color="tab:blue", alpha=0.08)
    z_positive = np.linspace(0, 1, 80)
    axis.fill_between(z_positive, 0.0, 3.0, color="tab:orange", alpha=0.10)
    axis.fill_between(z_positive, -11.0, 0.0, color="tab:blue", alpha=0.08)
    axis.scatter([0], [0], s=35, color="black", zorder=5)
    axis.annotate("mean-field\nLifshitz point", (0, 0), xytext=(0.22, 0.65),
                  arrowprops={"arrowstyle": "->", "lw": 0.8}, fontsize=8)
    axis.text(-2.65, 2.2, "symmetric", fontsize=9)
    axis.text(-2.65, -2.1, "modulated", fontsize=9)
    axis.text(-2.65, -9.2, "uniform broken", fontsize=9)
    axis.set(xlabel=r"$Z$", ylabel=r"bare mass $r\equiv m^2$",
             xlim=(-3, 1), ylim=(-11, 3), title="Single-mode mean-field diagram")
    axis.grid(alpha=0.18)
    axis.legend(frameon=False, fontsize=7, loc="lower right")

    q = np.linspace(0, 2.5, 500)
    axis = axes[1]
    for z_value, color in [(0.7, "tab:blue"), (0.0, "0.35"),
                           (-0.8, "tab:orange"), (-2.0, "tab:red")]:
        kernel = z_value * q + q**2
        axis.plot(q, kernel, color=color, lw=2, label=fr"$Z={z_value:g}$")
        if z_value < 0:
            q_star = -z_value / 2.0
            axis.plot(q_star, -z_value**2 / 4.0, "o", color=color, ms=4)
    axis.axhline(0, color="black", lw=0.7)
    axis.set(xlabel=r"lattice momentum variable $q=\widehat{k}^{,2}$",
             ylabel=r"$Zq+q^2$", xlim=(0, 2.5), ylim=(-1.2, 7.2),
             title="Quadratic dispersion (mass omitted)")
    axis.grid(alpha=0.18)
    axis.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "mean_field_phase_diagram.pdf", bbox_inches="tight")
    fig.savefig(OUT / "mean_field_phase_diagram.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def phase_status_figure() -> None:
    binder_rows = read_csv(ROOT / "plots" / "binder_crossings_vs_Z.csv")
    grouped: dict[float, list[float]] = {}
    for row in binder_rows:
        grouped.setdefault(float(row["Z"]), []).append(float(row["m2_c"]))
    binder_z = np.asarray(sorted(grouped))
    binder_mean = np.asarray([np.mean(grouped[z]) for z in binder_z])
    binder_spread = np.asarray([np.ptp(grouped[z]) for z in binder_z])

    multi_path = (ROOT / "reports" / "structure_factor_cpu" /
                  "thermodynamic_integration_multishell_L20" /
                  "multishell_summary.csv")
    multi_rows = read_csv(multi_path)
    mz = np.asarray([float(row["Z"]) for row in multi_rows])
    equality = np.asarray([float(row["ordered_boundary_m2"])
                           for row in multi_rows])
    coherence = np.asarray([float(row["finite_q_coherence_limit_m2"])
                            for row in multi_rows])
    binder_extrap = np.asarray([float(row["binder_line_m2"])
                                for row in multi_rows])

    fig, axis = plt.subplots(figsize=(7.6, 5.4))
    axis.errorbar(binder_z, binder_mean, yerr=binder_spread / 2,
                  fmt="o", color="tab:blue", capsize=2,
                  label="direct uniform Binder crossings\n(pair spread, not statistical error)")
    axis.plot(mz, binder_extrap, "--", color="tab:blue", alpha=0.5,
              label="quadratic continuation of Binder line")
    valid = np.isfinite(equality)
    axis.plot(mz[valid], equality[valid], "s-", color="tab:purple",
              label=r"restricted $q=0$/finite-$q$ equal free energy ($L=20$)")
    axis.plot(mz, coherence, "^-.", color="tab:orange",
              label=r"operational finite-$q$ coherence limit ($L=20$)")
    axis.axvspan(-0.9625, -0.95, color="tab:red", alpha=0.14,
                 label="current termination bracket")
    axis.set(xlabel=r"$Z$", ylabel=r"$m^2$", xlim=(-2.6, 2.1), ylim=(-10.2, 0.1),
             title="Numerical phase-diagram status (different evidence levels)")
    axis.grid(alpha=0.18)
    axis.legend(frameon=False, fontsize=7.5, loc="lower right")
    fig.tight_layout()
    fig.savefig(OUT / "phase_diagram_status.pdf", bbox_inches="tight")
    fig.savefig(OUT / "phase_diagram_status.png", dpi=200, bbox_inches="tight")
    plt.close(fig)

    catalog: list[dict[str, object]] = []
    for z in binder_z:
        values = grouped[z]
        catalog.append({
            "boundary": "uniform_broken__symmetric",
            "evidence": "direct_pairwise_Binder_crossing",
            "L_or_pair": "12x16;16x20;20x24",
            "Z": z,
            "m2": float(np.mean(values)),
            "uncertainty_proxy": float(np.ptp(values) / 2),
            "status": "finite_size_direct",
            "source": "plots/binder_crossings_vs_Z.csv",
        })
    for row in multi_rows:
        z = float(row["Z"])
        value = float(row["ordered_boundary_m2"])
        if math.isfinite(value):
            catalog.append({
                "boundary": "uniform_broken__modulated",
                "evidence": "restricted_branch_equal_free_energy",
                "L_or_pair": "20",
                "Z": z,
                "m2": value,
                "uncertainty_proxy": "",
                "status": "exploratory_not_thermodynamic_boundary",
                "source": str(multi_path.relative_to(ROOT)),
            })
        catalog.append({
            "boundary": "modulated__symmetric",
            "evidence": "finite_q_coherence_threshold_Speak_eq_10",
            "L_or_pair": "20",
            "Z": z,
            "m2": float(row["finite_q_coherence_limit_m2"]),
            "uncertainty_proxy": "",
            "status": "operational_proxy_not_phase_boundary",
            "source": str(multi_path.relative_to(ROOT)),
        })
    write_csv(OUT / "phase_boundary_catalog.csv", catalog)


def campaign_table() -> None:
    anchors = (-0.5, -0.75, -0.9, -0.95, -0.95625, -0.9625, -1.0,
               -1.25, -1.5, -1.75, -2.0, -2.25, -2.5)
    rows = []
    for index, z in enumerate(anchors):
        priority = "endpoint" if -0.97 < z < -0.94 else ("anchor" if z in (-0.5, -1.0, -1.5, -2.0, -2.5) else "fill")
        rows.append({
            "sequence": index + 1,
            "Z": z,
            "priority": priority,
            "discovery_sizes": "12;16;20",
            "confirmation_sizes": "20;24",
            "scan": "adaptive in m2 around both candidate boundaries",
            "required_orders": "M2;Pq;H;Q;G",
            "classification": "joint histograms; FSS peaks; barrier scaling; source agreement",
        })
    write_csv(OUT / "proposed_transition_campaign.csv", rows)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    mean_field_figure()
    phase_status_figure()
    campaign_table()
    print(f"wrote manuscript artifacts to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
