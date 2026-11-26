#!/usr/bin/env python3
"""Paper figure: mean-field and Hartree (lattice spectrum, L=inf) phase diagrams.

Inputs:  reports/mean_field/mean_field_lines.csv  (scripts/mf_lattice.py)
         reports/hartree/hartree_lines.csv         (scripts/hartree_lattice.py)
Symmetric -> moat crossover: both approximations keep the self-energy momentum
independent, so Z_eff = Z and the crossover is the vertical line Z = 0 above the
symmetric boundary (m2 > 0 in mean field, m2 > m2_sym_uniform(0) in Hartree).
Output:  paper/figures/theory_phase_diagram.{pdf,png}
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np

from paper_style import OKABE_ITO, figsize, save, use_prd

C_UNI, C_MOD, C_UM, C_MOAT = OKABE_ITO[0], OKABE_ITO[1], "0.15", OKABE_ITO[2]

ROOT = Path(__file__).resolve().parents[1]


def read(path: Path) -> list[dict]:
    with path.open() as fh:
        return [{k: float(v) if v not in ("", "uniform", "lamellar") else v for k, v in r.items()}
                for r in csv.DictReader(fh)]


def hartree_meeting(rows: list[dict]) -> tuple[float, float]:
    """Interpolate the Z where the sym/uniform and sym/lamellar Hartree lines cross."""
    rows = sorted(rows, key=lambda r: r["Z"])
    for a, b in zip(rows, rows[1:]):
        da = a["m2_sym_uniform"] - a["m2_sym_lamellar"]
        db = b["m2_sym_uniform"] - b["m2_sym_lamellar"]
        if np.isfinite(da) and np.isfinite(db) and da * db < 0:
            t = da / (da - db)
            Z = a["Z"] + t * (b["Z"] - a["Z"])
            m2 = a["m2_sym_uniform"] + t * (b["m2_sym_uniform"] - a["m2_sym_uniform"])
            return Z, m2
    return math.nan, math.nan


def main() -> int:
    import matplotlib.pyplot as plt

    use_prd()
    mf = read(ROOT / "reports" / "mean_field" / "mean_field_lines.csv")
    hl = [r for r in read(ROOT / "reports" / "hartree" / "hartree_lines.csv") if r["L"] == 0]
    Zt, mt = hartree_meeting(hl)
    print(f"Hartree meeting point (L=inf): Z={Zt:.3f}, m2={mt:.3f}")

    fig, ax = plt.subplots(figsize=figsize("single", 0.82))
    # ---- mean field (thin dashed)
    Z = np.array([r["Z"] for r in mf])
    neg = Z < 0
    ax.plot(Z[neg], [r["m2_sym_modulated"] for r in np.array(mf)[neg]], "--", lw=0.9,
            color=C_MOD)
    um = np.array([r["m2_uniform_modulated"] for r in mf])
    ok = neg & np.isfinite(um)
    ax.plot(Z[ok], um[ok], "--", lw=0.9, color=C_UM)
    ax.plot([0, Z.max()], [0, 0], "--", lw=0.9, color=C_UNI)
    # ---- single-mode approximation (dotted): phi = A cos(q.x) on the moat, no harmonics.
    # Its symmetric-lamellar (m2 = Z^2/4) and symmetric-uniform (m2 = 0) lines coincide with
    # the exact lattice mean field; only the uniform-lamellar line differs.
    zsm = np.linspace(-3.0, 0.0, 301)
    ax.plot(zsm, -(2 + math.sqrt(6)) * zsm**2 / 4, ":", lw=1.1, color=C_UM)
    ax.plot([0], [0], "o", ms=3.5, mfc="white", mec="k", mew=0.8, zorder=5)

    # ---- Hartree (solid), only the thermodynamically relevant branch of each line
    H = sorted(hl, key=lambda r: r["Z"])
    zs = np.array([r["Z"] for r in H])
    mu = np.array([r["m2_sym_uniform"] for r in H])
    ml = np.array([r["m2_sym_lamellar"] for r in H])
    mul = np.array([r["m2_uniform_lamellar"] for r in H])
    uni = zs >= Zt
    lam = zs <= Zt
    zu = np.concatenate([[Zt], zs[uni]]); mu_ = np.concatenate([[mt], mu[uni]])
    zl = np.concatenate([zs[lam], [Zt]]); ml_ = np.concatenate([ml[lam], [mt]])
    ax.plot(zu, mu_, "-", lw=1.4, color=C_UNI)
    ax.plot(zl, ml_, "-", lw=1.4, color=C_MOD)
    good = lam & np.isfinite(mul) & (mul < np.fmin(mu, ml))
    zul = np.concatenate([zs[good], [Zt]]); mul_ = np.concatenate([mul[good], [mt]])
    ax.plot(zul, mul_, "-", lw=1.4, color=C_UM)
    ax.plot([Zt], [mt], "s", ms=3.5, color="k", zorder=6)

    # ---- symmetric -> moat crossover, Z_eff = Z = 0 in both approximations
    mH0 = float(np.interp(0.0, zs, mu))
    ax.plot([0, 0], [mH0, 2.5], "-", lw=1.4, color=C_MOAT, zorder=3)
    ax.text(-0.07, 1.9, "moat", ha="right", va="center", fontsize=7, color=C_MOAT)
    ax.text(0.07, 1.9, "no moat", ha="left", va="center", fontsize=7, color=C_MOAT)
    print(f"Hartree moat line: Z=0, m2 > {mH0:.3f}")

    ax.set_xlim(-3.0, 1.0)
    ax.set_ylim(-6.0, 2.5)
    ax.set_xlabel(r"$Z$")
    ax.set_ylabel(r"$m^2$")
    ax.text(-1.3, 1.6, "symmetric", ha="center", fontsize=8)
    ax.text(0.5, -3.0, "uniform", ha="center", fontsize=8)
    ax.text(-2.3, -1.9, "lamellar", ha="center", fontsize=8)
    ax.annotate("LP (MF)", (0, 0), (0.3, 0.55), fontsize=7,
                arrowprops=dict(arrowstyle="-", lw=0.5))
    from matplotlib.lines import Line2D
    handles = [Line2D([], [], ls=":", lw=1.1, color="k", label="single mode"),
               Line2D([], [], ls="--", lw=0.9, color="k", label="lattice mean field"),
               Line2D([], [], ls="-", lw=1.4, color="k", label="Hartree")]
    ax.legend(handles=handles, loc="lower right", frameon=False, fontsize=7)
    fig.tight_layout(pad=0.3)
    save(fig, ROOT / "paper" / "figures" / "theory_phase_diagram")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
