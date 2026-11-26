#!/usr/bin/env python3
"""Paper figure: schematic phase diagrams near the meeting point (not to scale).

(a) mean field: Lifshitz point; the moat crossover Z_eff = 0 is the line Z = 0 and joins
    the critical lines at the LP.
(b) critical endpoint (CEP): the continuous (Ising) symmetric-uniform line ends on the
    first-order line that separates the lamellar phase from both others.
(c) tricritical point (TCP) + triple point (TP): the uniform line turns first order before
    three first-order lines meet.
Thin lines: continuous transitions; thick: first order; green dash-dot: Z_eff = 0.
Near a continuous Ising line S(k) has its maximum at k = 0, so the moat line cannot touch
it; in (b) and (c) it must end on a first-order line.

Output: paper/figures/scenarios.{pdf,png}
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paper_style import OKABE_ITO, figsize, save, use_prd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
C_UNI, C_MOD, C_UM, C_MOAT = OKABE_ITO[0], OKABE_ITO[1], "0.2", OKABE_ITO[2]
THIN, THICK = 0.9, 2.4


def bez(*P, n=200):
    """Bezier curve through control points P (endpoints are interpolated)."""
    P = np.asarray(P, float)
    t = np.linspace(0, 1, n)[:, None]
    k = len(P) - 1
    from math import comb
    B = sum(comb(k, i) * t**i * (1 - t)**(k - i) * P[i] for i in range(k + 1))
    return B[:, 0], B[:, 1]


def frame(ax, title):
    ax.set_xlim(-1, 1)
    ax.set_ylim(-1, 1)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlabel(r"$Z$")
    ax.set_ylabel(r"$m^2$")
    ax.set_title(title, fontsize=7.5, pad=3)


def labels(ax, lam=(-0.75, -0.55), uni=(0.55, -0.6), sym=(0.45, 0.65)):
    ax.text(*sym, "symmetric", ha="center", fontsize=6.5)
    ax.text(*uni, "uniform", ha="center", fontsize=6.5)
    ax.text(*lam, "lamellar", ha="center", fontsize=6.5)


def moat_tag(ax, xy):
    ax.text(*xy, "moat", ha="right", va="center", fontsize=6, color=C_MOAT)


def main() -> int:
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    use_prd()
    fig, axs = plt.subplots(1, 3, figsize=figsize("double", 0.36))

    # ---------------- (a) mean field, Lifshitz point
    ax = axs[0]
    frame(ax, "(a) mean field: Lifshitz point")
    x = np.linspace(-1, 0, 200)
    ax.plot([0, 1], [0, 0], "-", lw=THIN, color=C_UNI)
    ax.plot(x, 0.45 * x**2, "-", lw=THIN, color=C_MOD)
    ax.plot(x[x > -0.82], -1.5 * x[x > -0.82]**2, "-", lw=THICK, color=C_UM)
    ax.plot([0, 0], [0, 1], "-.", lw=1.0, color=C_MOAT)
    ax.plot([0], [0], "o", ms=4, mfc="white", mec="k", mew=0.8, zorder=6)
    ax.annotate("LP", (0, 0), (0.2, -0.3), fontsize=6.5, arrowprops=dict(arrowstyle="-", lw=0.5))
    moat_tag(ax, (-0.05, 0.75))
    labels(ax, lam=(-0.62, -0.1))

    # ---------------- (b) critical endpoint
    ax = axs[1]
    frame(ax, "(b) critical endpoint")
    C = np.array([-0.30, -0.22])
    xi, yi = bez(C, (0.3, -0.03), (1.0, 0.12))
    ax.plot(xi, yi, "-", lw=THIN, color=C_UNI)
    # first-order line through the CEP, vertical tangent there: sym-lam above, uni-lam below
    xs, ys = bez((-1.0, 0.30), (-0.45, 0.12), (C[0], 0.02), C)
    ax.plot(xs, ys, "-", lw=THICK, color=C_MOD)
    xl, yl = bez(C, (C[0], -0.5), (-0.5, -0.8), (-0.62, -1.0))
    ax.plot(xl, yl, "-", lw=THICK, color=C_UM)
    # moat line: Z -> 0^- deep in the symmetric phase, runs above the Ising line, ends on the
    # first-order symmetric-lamellar line above the CEP (finite Ising window)
    E = (xs[170], ys[170])
    xm, ym = bez((-0.03, 1.0), (-0.03, 0.15), (0.0, 0.0), (-0.25, -0.05), E)
    ax.plot(xm, ym, "-.", lw=1.0, color=C_MOAT)
    ax.plot(*E, "o", ms=2.2, color=C_MOAT, zorder=6)
    ax.plot(*C, "o", ms=4, color="k", zorder=6)
    ax.annotate("CEP", C, (-0.05, -0.45), fontsize=6.5, arrowprops=dict(arrowstyle="-", lw=0.5))
    moat_tag(ax, (-0.08, 0.75))
    labels(ax)

    # ---------------- (c) tricritical point + triple point
    ax = axs[2]
    frame(ax, "(c) tricritical point + triple point")
    T, P = np.array([-0.08, -0.15]), np.array([-0.40, -0.26])
    xi, yi = bez(T, (0.4, -0.02), (1.0, 0.12))
    ax.plot(xi, yi, "-", lw=THIN, color=C_UNI)
    xf, yf = bez(P, (-0.25, -0.19), T)
    ax.plot(xf, yf, "-", lw=THICK, color=C_UNI)
    ax.plot(*bez((-1.0, 0.30), (-0.6, 0.05), P), "-", lw=THICK, color=C_MOD)
    ax.plot(*bez(P, (-0.42, -0.6), (-0.62, -1.0)), "-", lw=THICK, color=C_UM)
    E = (xf[90], yf[90])
    xm, ym = bez((-0.03, 1.0), (-0.03, 0.2), (0.0, -0.02), E)
    ax.plot(xm, ym, "-.", lw=1.0, color=C_MOAT)
    ax.plot(*E, "o", ms=2.2, color=C_MOAT, zorder=6)
    ax.plot(*T, "D", ms=3.5, color="k", zorder=6)
    ax.plot(*P, "s", ms=4, color="k", zorder=6)
    ax.annotate("TCP", T, (0.2, -0.45), fontsize=6.5, arrowprops=dict(arrowstyle="-", lw=0.5))
    ax.annotate("TP", P, (-0.1, -0.6), fontsize=6.5, arrowprops=dict(arrowstyle="-", lw=0.5))
    moat_tag(ax, (-0.08, 0.75))
    labels(ax)

    handles = [Line2D([], [], lw=THIN, color="k", label="continuous"),
               Line2D([], [], lw=THICK, color="k", label="first order"),
               Line2D([], [], ls="-.", lw=1.0, color=C_MOAT, label=r"moat crossover $Z_{\rm eff}=0$"),
               Line2D([], [], lw=1.5, color=C_UNI, label="sym.--uniform"),
               Line2D([], [], lw=1.5, color=C_MOD, label="sym.--lamellar"),
               Line2D([], [], lw=1.5, color=C_UM, label="uniform--lamellar")]
    fig.legend(handles=handles, ncol=6, loc="lower center", bbox_to_anchor=(0.5, 0.0),
               fontsize=6.5, frameon=False, columnspacing=1.2, handlelength=2.2)
    fig.tight_layout(pad=0.3, w_pad=0.8, rect=(0, 0.08, 1, 1))
    save(fig, ROOT / "paper" / "figures" / "scenarios")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
