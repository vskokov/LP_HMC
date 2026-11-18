"""Matplotlib style for Phys. Rev. D figures.

Usage::

    from paper_style import use_prd, figsize, L_STYLE, save
    use_prd()
    fig, ax = plt.subplots(figsize=figsize("single", 0.75))
    ...
    save(fig, "paper/figures/binder_curves")

* single column = 3.375 in, double column = 7.0 in (APS REVTeX 4.2).
* Fonts: Computer Modern via LaTeX when available, otherwise STIX/cm mathtext.
* Colours: Okabe–Ito colour-blind-safe palette; lattice size L keeps the same
  colour and marker in every figure.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SINGLE = 3.375
DOUBLE = 7.0
OKABE_ITO = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00",
             "#56B4E9", "#F0E442", "#000000"]
PHASE_COLORS = {
    "symmetric": "#FFFFFF",
    "uniform": "#9ecae1",
    "modulated": "#fdd0a2",
}
_MARKERS = ["o", "s", "^", "D", "v", "p", "h", "<", ">", "*", "P", "X", "d", "8"]
L_STYLE = {L: {"color": OKABE_ITO[i % len(OKABE_ITO)], "marker": _MARKERS[i]}
           for i, L in enumerate([8, 12, 16, 20, 24, 32, 18, 6, 27, 28, 30, 36, 40, 48])}


def use_prd(usetex: bool | None = None) -> None:
    if usetex is None:
        usetex = shutil.which("latex") is not None
    rc = {
        "font.size": 9,
        "axes.labelsize": 9,
        "axes.titlesize": 9,
        "legend.fontsize": 7.5,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "axes.linewidth": 0.6,
        "lines.linewidth": 1.0,
        "lines.markersize": 3.5,
        "errorbar.capsize": 1.5,
        "xtick.direction": "in",
        "ytick.direction": "in",
        "xtick.top": True,
        "ytick.right": True,
        "xtick.major.size": 3,
        "ytick.major.size": 3,
        "xtick.minor.size": 1.5,
        "ytick.minor.size": 1.5,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "legend.frameon": False,
        "legend.handlelength": 1.6,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.02,
        "savefig.dpi": 600,
        "pdf.fonttype": 42,
        "axes.prop_cycle": matplotlib.cycler(color=OKABE_ITO),
    }
    if usetex:
        rc.update({"text.usetex": True, "font.family": "serif",
                   "font.serif": ["Computer Modern Roman"],
                   "text.latex.preamble": r"\usepackage{amsmath}\usepackage{amssymb}"})
    else:
        rc.update({"text.usetex": False, "font.family": "serif",
                   "font.serif": ["STIXGeneral", "DejaVu Serif"],
                   "mathtext.fontset": "cm"})
    plt.rcParams.update(rc)


def figsize(width: str = "single", aspect: float = 0.75) -> tuple[float, float]:
    w = SINGLE if width == "single" else DOUBLE
    return (w, w * aspect)


def lstyle(L: int) -> dict:
    return dict(L_STYLE.get(int(L), {"color": "0.3", "marker": "o"}))


def save(fig, stem: str | Path, png: bool = True) -> None:
    stem = Path(stem)
    stem.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(stem.with_suffix(".pdf"))
    if png:
        fig.savefig(stem.with_suffix(".png"), dpi=300)
    plt.close(fig)
