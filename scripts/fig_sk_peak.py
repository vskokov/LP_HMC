#!/usr/bin/env python3
"""Paper figure: fluctuation-renormalized dispersion in the symmetric phase.

(a) position k2* of the maximum of S(k) versus m2 for several Z, with the bare moat
    -Z/2 as dotted lines.  k2* from a local parabola in khat^2 through 1/S at the five
    momenta closest to the minimum of 1/S (model independent; the global
    a + b k^2 + c k^4 fit of analyze_sk_symmetric.py fails near the meeting region).
    Error bars: parabola refits with S resampled within S_err (200 draws).
(b) 1/S(k) at two masses for Z = -1.1716 (moat persists) and Z = -0.95 (moat closes).

Inputs:  reports/sk_symmetric/summary.csv and the per-run spectrum.csv files
         (scripts/analyze_sk_symmetric.py).
Output:  paper/figures/sk_peak.{pdf,png}; table reports/sk_symmetric/peak_local.csv
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paper_style import OKABE_ITO, figsize, save, use_prd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REP = ROOT / "reports" / "sk_symmetric"
ZSHOW = [-2.0, -1.5, -1.171573, -1.05, -0.95, -0.8]
MARK = ["o", "s", "^", "D", "v", "p"]


def local_peak(sp: pd.DataFrame, rng, ndraw: int = 200) -> tuple[float, float]:
    q, S, e = sp.q.values, sp.S.values, sp.S_err.values
    i0 = int(np.argmin(1 / S))
    lo = max(0, min(i0 - 2, len(q) - 5))
    sl = slice(lo, lo + 5)

    def vertex(Sv):
        c2, c1, _ = np.polyfit(q[sl], 1 / Sv[sl], 2)
        v = -c1 / (2 * c2) if c2 > 0 else q[i0]
        return float(np.clip(v, 0.0, q[sl].max()))

    v0 = vertex(S)
    draws = [vertex(S + rng.normal(0, 1, len(S)) * e) for _ in range(ndraw)]
    return v0, float(np.std(draws))


def load() -> pd.DataFrame:
    t = pd.read_csv(REP / "summary.csv")
    rng = np.random.default_rng(1)
    rows = []
    for _, r in t.iterrows():
        sp = pd.read_csv(REP / r.run / "spectrum.csv")
        k, ke = local_peak(sp, rng)
        rows.append({"Z": round(r.Z, 6), "L": r.L, "m2": r.m2, "k2_local": k, "k2_local_err": ke,
                     "k2_fit": r.k2_star, "chi2_dof": r.chi2_dof, "run": r.run})
    out = pd.DataFrame(rows).sort_values(["Z", "m2", "L"])
    out.to_csv(REP / "peak_local.csv", index=False)
    return out


def main() -> int:
    import matplotlib.pyplot as plt

    d = load()
    use_prd()
    fig, (ax, bx) = plt.subplots(1, 2, figsize=figsize("double", 0.34))
    for i, Z in enumerate(ZSHOW):
        s = d[np.isclose(d.Z, Z, atol=1e-4)]
        s = s.loc[s.groupby("m2").L.idxmax()]          # largest L at each mass
        c = OKABE_ITO[i]
        ax.axhline(-Z / 2, ls=":", lw=0.8, color=c)
        ax.errorbar(s.m2, s.k2_local, yerr=s.k2_local_err, fmt=MARK[i] + "-", ms=3, lw=0.8,
                    color=c, mfc="white" if Z > -1.1 else c, label=rf"$Z={Z:.4g}$")
    ax.set_xlabel(r"$m^2$")
    ax.set_ylabel(r"peak position $\hat k^2_*$")
    ax.set_ylim(-0.02, 1.05)
    from matplotlib.lines import Line2D
    h, lab = ax.get_legend_handles_labels()
    h.append(Line2D([], [], ls=":", lw=0.8, color="0.3")); lab.append(r"bare $-Z/2$")
    ax.legend(h, lab, ncol=4, fontsize=6.5, loc="lower center", bbox_to_anchor=(0.5, 1.0), columnspacing=0.8, handlelength=1.4)
    ax.text(-0.16, 1.13, "(a)", transform=ax.transAxes, va="bottom", fontsize=8)

    cases = [(-1.171573, -1.3, OKABE_ITO[2], "-"), (-1.171573, -2.03, OKABE_ITO[2], "--"),
             (-0.95, -2.035, OKABE_ITO[4], "-"), (-0.95, -2.465, OKABE_ITO[4], "--")]
    for Z, m2, c, ls in cases:
        s = d[np.isclose(d.Z, Z, atol=1e-4) & np.isclose(d.m2, m2)]
        if s.empty:
            continue
        r = s.loc[s.L.idxmax()]
        sp = pd.read_csv(REP / r.run / "spectrum.csv")
        sp = sp[sp.q <= 1.0]
        bx.errorbar(sp.q, 1 / sp.S, yerr=sp.S_err / sp.S**2, fmt=ls, lw=0.9, color=c, elinewidth=0.5, capsize=0,
                    label=rf"$Z={Z:.4g},\ m^2={m2:g}$")
    bx.set_xlabel(r"$\hat k^2$")
    bx.set_ylabel(r"$1/S(k)$")
    bx.set_ylim(0, 0.45)
    bx.set_xlim(0, 1.0)
    bx.legend(fontsize=6.5, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=2, columnspacing=1.0)
    bx.text(-0.16, 1.13, "(b)", transform=bx.transAxes, va="bottom", fontsize=8)
    fig.tight_layout(pad=0.3, w_pad=1.2)
    save(fig, ROOT / "paper" / "figures" / "sk_peak")
    for Z in ZSHOW:
        s = d[np.isclose(d.Z, Z, atol=1e-4)]
        print(f"Z={Z:+.4f}: " + "  ".join(f"{m:.3f}:{k:.3f}({e:.3f})"
                                          for m, k, e in zip(s.m2, s.k2_local, s.k2_local_err)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
