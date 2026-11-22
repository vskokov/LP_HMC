#!/usr/bin/env python3
"""Paper figure: lamellar condensate profile phi(x) at (Z, m2) = (-2, -3), where every
treatment orders into lamellae of period p = 6 (k = pi/3, khat^2 = 1).

* single mode:  A cos(kx), A^2 = 4|r0|/(3 lam), r0 = m2 - Z^2/4
* lattice mean field: unconstrained minimum of H on a 12-site ring (scripts/mf_lattice.py)
* Hartree: single-harmonic condensate A_H cos(kx) with Gaussian fluctuations
  (scripts/hartree_lattice.py, infinite volume)
* simulation: plane-averaged profiles of the final fields of the unbiased lamellar runs
  (lro L <= 18, lro2 L >= 24; reports/profiles/lro_profiles.csv from scripts/lro_profiles.jl),
  maximum shifted to x = 0, averaged over replicas, both periods and L = 24, 30, 36.

Panel (b): harmonic content.  On a period-6 lattice only k = pi/3 (fundamental) and
k = pi (third harmonic, staggered) are independent; A1 = (2/p) sum phi cos(kx),
A3 = (1/p) sum phi (-1)^x.

Output: paper/figures/lamellar_profiles.{pdf,png}
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hartree_lattice as hl  # noqa: E402
import mf_lattice as mf  # noqa: E402
from paper_style import OKABE_ITO, figsize, save, use_prd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
Z, M2, LAM, P = -2.0, -3.0, 4.0, 6
K = 2 * math.pi / P


def harmonics(phi6: np.ndarray) -> tuple[float, float]:
    x = np.arange(P)
    return float(2 / P * np.sum(phi6 * np.cos(K * x))), float(np.sum(phi6 * (-1.0) ** x) / P)


def main() -> int:
    import matplotlib.pyplot as plt

    x = np.arange(2 * P)
    xs = np.linspace(-0.3, 2 * P - 0.7, 400)
    r0 = M2 - Z * Z / 4
    A_sm = math.sqrt(-4 * r0 / (3 * LAM))
    f_mf, phi_mf = mf.minimise(A_sm * np.cos(K * x), Z, M2)
    sp = hl.Spectrum(*hl.infinite_spectrum(), None)
    f_h, A_h, q_h = hl.f_lamellar(sp, Z, M2)
    assert abs(q_h - 1.0) < 1e-9
    t = pd.read_csv(ROOT / "reports" / "profiles" / "lro_profiles.csv")
    t = t[(t.L >= 24) & t.run.str.contains("Zm2")]
    t["xm"] = t.x % P
    g = t.groupby("xm").phi
    sim, sim_err = g.mean().values, (g.std(ddof=1) / np.sqrt(g.count())).values
    print(f"single mode A={A_sm:.4f} f={-r0**2/(6*LAM):.4f}; lattice MF f={f_mf:.5f} "
          f"profile={np.round(phi_mf[:P], 4)}; Hartree A={A_h:.4f}; "
          f"simulation {np.round(sim, 4)} +- {np.round(sim_err, 4)} (n={g.count().iloc[0]})")

    use_prd()
    fig, (ax, bx) = plt.subplots(1, 2, figsize=figsize("double", 0.36),
                                 gridspec_kw={"width_ratios": [2.3, 1]})
    c_sm, c_mf, c_h, c_sim = "0.35", OKABE_ITO[1], OKABE_ITO[0], "k"
    ax.axhline(0, lw=0.4, color="0.7")
    ax.plot(xs, A_sm * np.cos(K * xs), ":", lw=1.0, color=c_sm)
    ax.plot(x, A_sm * np.cos(K * x), "o", ms=3, mfc="white", mec=c_sm, mew=0.8, label="single mode")
    ax.plot(x, phi_mf, "s-", ms=3, lw=0.7, color=c_mf, label="lattice mean field")
    ax.plot(xs, A_h * np.cos(K * xs), "--", lw=0.9, color=c_h)
    ax.plot(x, A_h * np.cos(K * x), "^", ms=3.2, color=c_h, label="Hartree")
    ax.errorbar(x, np.tile(sim, 2), yerr=np.tile(sim_err, 2), fmt="D-", ms=3, lw=0.7,
                color=c_sim, capsize=1.5, label="simulation")
    ax.set_xlabel(r"lattice site $x$ (along the modulation)")
    ax.set_ylabel(r"$\bar\phi(x)$")
    ax.set_xticks(range(0, 2 * P, 2))
    ax.set_xlim(-0.5, 2 * P - 0.5)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=4, frameon=False, fontsize=6.5,
              handletextpad=0.4, columnspacing=1.2)
    ax.text(0.98, 0.96, r"$Z=-2,\ m^2=-3$", transform=ax.transAxes, ha="right", va="top", fontsize=7)
    ax.text(-0.09, 1.07, "(a)", transform=ax.transAxes, va="bottom", fontsize=8)

    labels = ["single\nmode", "lattice\nMF", "Hartree", "simu-\nlation"]
    vals = [(A_sm, 0.0), harmonics(phi_mf[:P]), (A_h, 0.0), harmonics(sim)]
    cols = [c_sm, c_mf, c_h, c_sim]
    xb = np.arange(4)
    bx.bar(xb - 0.18, [v[0] for v in vals], 0.34, color=cols, alpha=0.85, label=r"$A_1$")
    bx.bar(xb + 0.18, [abs(v[1]) * 5 for v in vals], 0.34, color=cols, alpha=0.35,
           hatch="////", edgecolor=cols, lw=0.5, label=r"$5\,|A_3|$")
    bx.set_xticks(xb)
    bx.set_xticklabels(labels, fontsize=6.5)
    bx.set_ylabel("harmonic amplitude")
    bx.legend(frameon=False, fontsize=6.5, loc="upper right")
    bx.set_ylim(0, 1.6)
    bx.text(-0.22, 1.07, "(b)", transform=bx.transAxes, va="bottom", fontsize=8)
    for i, v in enumerate(vals):
        print(f"{labels[i].replace(chr(10), ' '):16s} A1={v[0]:.4f} A3={v[1]:+.4f}")
    fig.tight_layout(pad=0.3, w_pad=1.0)
    save(fig, ROOT / "paper" / "figures" / "lamellar_profiles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
