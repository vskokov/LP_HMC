#!/usr/bin/env python3
"""PRELIMINARY lattice phase diagram (Z, m^2) from the data available on 2026-11-25.

Symbols
* symmetric -> uniform: chi_max of the M^2-umbrella runs at the largest L with an interior
  maximum (reports/transition_order/summary.csv; L = 24, L = 32 at Z = -0.6).  Filled for
  Z >= -0.75 (continuous: U4_min -> 0 and barrier -> 0 with L), open where the order is
  still undecided (gate G1, `uline` L = 32 pending).
* symmetric -> lamellar: equal-weight mass m_eq of the shell / band umbrellas.  Z = -2 at
  L = 30 (barrier 1.2 -> 19.3 kT for L = 12 -> 30, first order); Z = -1.3 band CV at L = 20
  (single size); Z8 band CV at L = 20 is a chi_s peak at the edge of the reweighting range.
* Z9 = -0.936, L = 18 mixed CV: symmetric -> uniform m_eq.
* Vertical bars: unbiased L = 48 chains (reports/sk_symmetric), all symmetric at the upper
  end, ordered chains (lamellae, or slabs at Z = -1.0) at the lower end.  The symmetric
  phase can be metastable below m_c, so the bar marks where ordering sets in on the run
  time scale; it is not an error bar on m_c.
* Z8 L = 20: chi_s still rising at the upper edge of the reweighting range, so the point
  is a lower bound on m_c(L=20) (arrow).
* uniform <-> lamellar: brackets from the local direct-coexistence runs (stages ulam, ulam2;
  reports/ulam/summary.csv, scripts/analyze_ulam.py).  Half-uniform / half-lamellar L = 48
  boxes; the bar spans the lowest m2 where lamellae invade (all replicas) to the highest m2
  where the uniform phase invades.  Where no uniform win was found yet, a downward arrow from
  the lowest lamellar-win mass.
* symmetric -> moat crossover: Z_eff = 0 (curvature of 1/S at k = 0 changes sign), from
  reports/sk_symmetric/moat_line.csv (scripts/moat_line.py).  For -1.05 <= Z <= -0.6 the
  moat persists to within ~0.02 of the uniform transition (no separate line visible).
* Open circle at the origin: mean-field Lifshitz point (theory lines: fig_theory.py).  Grey band (near the transition only): Z range where the
  renormalized S(k) peak moves to k -> 0 at the transition.

Output: paper/figures/phase_diagram_prelim.{pdf,png}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paper_style import OKABE_ITO, figsize, save, use_prd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
C_UNI, C_MOD, C_UM, C_MOAT = OKABE_ITO[0], OKABE_ITO[1], "0.25", OKABE_ITO[2]
Z8 = -8 * np.sin(np.pi / 8) ** 2


def uniform_line() -> pd.DataFrame:
    t = pd.read_csv(ROOT / "reports" / "transition_order" / "summary.csv")
    t = t[~t.chi_max_at_edge.astype(bool) & (t.L >= 16)].copy()
    t["Z"] = t.Z.round(4)
    t = t.loc[t.groupby("Z").L.idxmax()].sort_values("Z")
    return t[["Z", "L", "m_chi_max", "m_chi_max_err"]]


def lamellar_points() -> list[dict]:
    out = []
    for d, Z, kind in (("combined/Zm2/L30", -2.0, "filled"), ("b13/Zm1p3/L20", -1.3, "open"),
                       ("b8/Zm1p1716/L20", Z8, "edge")):
        a = json.loads((ROOT / "reports" / "cv_umbrella" / d / "analysis.json").read_text())
        c = a["summary"].get("coexistence") or {}
        m = c.get("m_eq", a["summary"]["m_chi_s_max"])
        e = a.get("errors", {}).get("m_eq") or a.get("errors", {}).get("m_chi_s_max") or 0.0
        out.append({"Z": Z, "m2": m, "err": e, "kind": kind, "L": a["L"]})
    return out


def ulam_brackets() -> list[tuple[float, float, float | None]]:
    """(Z, lowest m2 with lamellar win, highest m2 with uniform win or None)."""
    f = ROOT / "reports" / "ulam" / "summary.csv"
    if not f.is_file():
        return []
    t = pd.read_csv(f)
    t = t[t.complete.astype(bool)]
    out = []
    for Z, g in t.groupby("Z"):
        lam = g[g.lamellar == g[["uniform", "lamellar", "slab", "symmetric"]].sum(axis=1)].m2
        uni = g[g.uniform > 0].m2
        if lam.empty:
            continue
        lo = lam.min()
        hi = uni[uni < lo].max() if not uni.empty else None
        out.append((round(Z, 4), lo, None if hi is None or np.isnan(hi) else hi))
    return out


# unbiased L=48 chains: (Z, last fully symmetric m2, first m2 with nucleated order, state)
NUCLEATION = [(-1.3, -2.30, -2.40, "lamellae"), (Z8, -2.25, -2.35, "lamellae"),
              (-1.1, -2.40, -2.50, "lamellae"), (-1.0, -2.50, -2.60, "slabs")]


def moat_points() -> pd.DataFrame:
    f = ROOT / "reports" / "sk_symmetric" / "moat_line.csv"
    if not f.is_file():
        return pd.DataFrame(columns=["Z", "m2_moat", "sys"])
    t = pd.read_csv(f)
    return t[t.kind == "crossing"].sort_values("Z")


def draw(ax, U, lam, H, inset=False, UL=(), MO=None):
    ms = 3.2 if not inset else 3.6
    if MO is not None and len(MO):
        ax.errorbar(MO.Z, MO.m2_moat, yerr=MO["sys"].fillna(0), fmt="^-.", ms=ms, lw=0.9, color=C_MOAT, zorder=4)
    mid = []
    for Z, lo, hi in UL:
        if hi is None:
            ax.annotate("", (Z, lo - 0.25), (Z, lo), arrowprops=dict(arrowstyle="->", lw=0.8, color=C_UM))
            ax.plot([Z], [lo], "_", ms=5, mew=1.0, color=C_UM)
        else:
            ax.plot([Z, Z], [hi, lo], "-", lw=1.4, color=C_UM, solid_capstyle="butt", zorder=3)
            ax.plot([Z, Z], [hi, lo], "_", ms=5, mew=1.0, color=C_UM, zorder=3)
            mid.append((Z, 0.5 * (hi + lo)))
    if mid:
        z, m = zip(*sorted(mid))
        ax.plot(z, m, ":", lw=1.0, color=C_UM, zorder=2)
    ax.fill_betweenx([-2.62, -2.30], -1.10, -1.05, color="0.88", lw=0, zorder=0)  # peak -> k=0 at the transition
    # symmetric -> uniform
    cont = U.Z >= -0.75
    ax.plot(U.Z, U.m_chi_max, "-", lw=1.0, color=C_UNI, zorder=2)
    ax.errorbar(U.Z[cont], U.m_chi_max[cont], yerr=U.m_chi_max_err[cont], fmt="o", ms=ms, color=C_UNI, zorder=3)
    ax.errorbar(U.Z[~cont], U.m_chi_max[~cont], yerr=U.m_chi_max_err[~cont], fmt="o", ms=ms, mfc="white",
                color=C_UNI, zorder=3)
    ax.plot([-0.936], [-2.449], "s", ms=ms, mfc="white", mec=C_UNI, mew=0.9, zorder=4)
    # symmetric -> lamellar
    for p in lam:
        st = {"filled": dict(mfc=C_MOD), "open": dict(mfc="white"), "edge": dict(mfc="white", alpha=0.6)}[p["kind"]]
        ax.errorbar([p["Z"]], [p["m2"]], yerr=[p["err"]], fmt="D", ms=ms, color=C_MOD, zorder=4, **st)
        if p["kind"] == "edge":
            ax.annotate("", (p["Z"], p["m2"] + (0.06 if inset else 0.12)), (p["Z"], p["m2"] + 0.01),
                        arrowprops=dict(arrowstyle="->", lw=0.7, color=C_MOD))
    for Z, hi, lo, state in NUCLEATION:
        c = C_MOD if state == "lamellae" else C_UNI
        ax.plot([Z, Z], [lo, hi], "-", lw=2.2, color=c, alpha=0.35, solid_capstyle="butt", zorder=1)
    zl = [p["Z"] for p in lam] + [-1.1]
    ml = [p["m2"] for p in lam] + [-2.45]
    o = np.argsort(zl)
    ax.plot(np.array(zl)[o], np.array(ml)[o], "--", lw=1.0, color=C_MOD, zorder=2)
    if not inset:
        ax.plot([0], [0], "o", ms=3.5, mfc="white", mec="k", mew=0.8)


def main() -> int:
    import matplotlib.pyplot as plt

    U = uniform_line()
    lam = lamellar_points()
    UL = ulam_brackets()
    MO = moat_points()
    print("uniform-lamellar brackets", UL)
    H = pd.read_csv(ROOT / "reports" / "hartree" / "hartree_lines.csv")
    H = H[H.L == 0].sort_values("Z")
    H = H[(H.Z >= -2.3) & (H.Z <= 2.1)]
    print(U.round(4).to_string(index=False))
    for p in lam:
        print(p)

    use_prd()
    fig, (ax, bx) = plt.subplots(2, 1, figsize=figsize("single", 1.6),
                                 gridspec_kw={"height_ratios": [1.15, 1]})
    draw(ax, U, lam, H, UL=UL, MO=MO)
    ax.set_xlim(-2.25, 2.1)
    ax.set_ylim(-4.0, 0.25)
    ax.set_xlabel(r"$Z$")
    ax.set_ylabel(r"$m^2$")
    ax.text(1.2, -0.4, "symmetric", ha="center", fontsize=8)
    ax.text(-1.6, -0.6, "symmetric\n(moat)", ha="center", fontsize=7, color="0.3")
    ax.text(0.9, -1.6, "uniform", ha="center", fontsize=8)
    ax.text(-0.75, -3.4, "uniform", ha="center", fontsize=8)
    ax.text(-1.75, -2.6, "lamellar", ha="center", fontsize=8)
    ax.annotate("MF LP", (0, 0), (0.2, -0.2), fontsize=6.5, arrowprops=dict(arrowstyle="-", lw=0.5))
    ax.text(0.98, 0.98, "PRELIMINARY", transform=ax.transAxes, ha="right", va="top", fontsize=6.5, color="0.5")
    ax.text(0.02, 0.98, "(a)", transform=ax.transAxes, va="top", fontsize=8)

    zx, zy = (-1.45, -0.25), (-2.72, -1.40)
    from matplotlib.patches import Rectangle
    ax.add_patch(Rectangle((zx[0], zy[0]), zx[1] - zx[0], zy[1] - zy[0], fill=False, ec="0.5", lw=0.5, ls="--"))
    draw(bx, U, lam, H, inset=True, UL=UL, MO=MO)
    bx.set_xlim(*zx)
    bx.set_ylim(*zy)
    bx.set_xlabel(r"$Z$")
    bx.set_ylabel(r"$m^2$")
    bx.text(0.02, 0.98, "(b)", transform=bx.transAxes, va="top", fontsize=8)
    bx.text(-1.3, -1.6, "symmetric (moat)", fontsize=7, color="0.3")
    bx.text(-0.55, -2.4, "uniform", fontsize=7)
    bx.text(-1.4, -2.6, "lamellar", fontsize=7)

    from matplotlib.lines import Line2D
    h = [Line2D([], [], marker="o", ls="-", color=C_UNI, ms=3, label="sym–uni, continuous"),
         Line2D([], [], marker="o", ls="-", color=C_UNI, mfc="white", ms=3, label="sym–uni, order open"),
         Line2D([], [], marker="D", ls="--", color=C_MOD, ms=3, label="sym–lam, 1st order"),
         Line2D([], [], marker="s", ls="", color=C_UNI, mfc="white", ms=3, label=r"sym–uni, mixed CV ($Z_9$)"),
         Line2D([], [], lw=2.2, color=C_MOD, alpha=0.35, label="ordering onset ($L=48$)"),
         Line2D([], [], marker="_", ls="-", lw=1.4, color=C_UM, ms=5, label="uni–lam bracket ($L=48$)"),
         Line2D([], [], marker="^", ls="-.", color=C_MOAT, ms=3, label=r"moat crossover ($Z_{\rm eff}=0$)")]
    ax.legend(handles=h, loc="lower right", fontsize=5.5, frameon=False, handlelength=1.6)
    fig.tight_layout(pad=0.3)
    save(fig, ROOT / "paper" / "figures" / "phase_diagram_prelim")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
