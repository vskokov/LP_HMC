#!/usr/bin/env python3
"""Hartree (Gibbs–Bogoliubov) / Brazovskii phase diagram with the exact lattice spectrum.

Model: H = sum_x [Z/2 (grad phi)^2 + 1/2 (lap phi)^2 + m2/2 phi^2 + lam/4 phi^4], T = 1.
Lattice dispersion: eps(k) = Z q + q^2,  q = khat^2 = sum_mu 4 sin^2(k_mu/2) in [0, 12].

Trial ensemble: phi = Phi(x) + Gaussian fluctuation with propagator 1/(r + eps(k)).
The variational free-energy density is

  F = (1/2) Sum_k ln(r + eps_k) + (m2 - r)/2 G0 + (3 lam/4) G0^2
      + <K[Phi]> + m2/2 <Phi^2> + lam/4 <Phi^4> + (3 lam/2) G0 <Phi^2>,

  G0(r) = Sum_k 1/(r + eps_k)   (Sum_k = (1/V) sum_k, or the BZ integral),

stationary in r at r = m2 + 3 lam (G0 + <Phi^2>)  (Hartree).  Condensates:
  symmetric  Phi = 0
  uniform    Phi = phi0:                <Phi^2>=phi0^2, <Phi^4>=phi0^4, K=0
  lamellar   Phi = A cos(k.x), q=khat^2: <Phi^2>=A^2/2, <Phi^4>=3A^4/8, K=A^2 eps(q)/4
(the fluctuation propagator is taken translation invariant -- Brazovskii's
approximation).  For Z<0 G0 diverges as (r - Z^2/4)^(-1/2) (degenerate shell), so the
symmetric phase never becomes locally unstable and the ordering transition is first
order.  Hartree is known to make the Ising (uniform) transition spuriously first order;
the uniform line is therefore reported but only the modulated side is used
quantitatively.

The infinite-volume momentum integral uses the exact density of states of q (the
convolution of three arcsine densities on [0,4]); finite L uses the exact mode sums.

Usage: python3 scripts/hartree_lattice.py [--L 0 12 16 20 24] [--out reports/hartree]
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np
from scipy.optimize import brentq, minimize_scalar

LAM = 4.0
ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- spectra
def infinite_spectrum(nbins: int = 120000) -> tuple[np.ndarray, np.ndarray]:
    """Bin-integrated density of states of q = q1+q2+q3, q_i = 4 sin^2(k_i/2)."""
    edges1 = np.linspace(0.0, 4.0, nbins // 3 + 1)
    # arcsine CDF: F(q) = (2/pi) asin(sqrt(q)/2)
    cdf = (2 / math.pi) * np.arcsin(np.sqrt(edges1) / 2)
    p1 = np.diff(cdf)                      # exact bin probabilities
    p2 = np.convolve(p1, p1)
    p3 = np.convolve(p2, p1)
    h = edges1[1] - edges1[0]
    # q of the sum of three bins i,j,k lies in [(i+j+k)h, (i+j+k+3)h]; use the midpoint.
    centers = (np.arange(len(p3)) + 1.5) * h
    return centers, p3 / p3.sum()


def finite_spectrum(L: int) -> tuple[np.ndarray, np.ndarray]:
    q1 = 4 * np.sin(np.pi * np.arange(L) / L) ** 2
    q = (q1[:, None, None] + q1[None, :, None] + q1[None, None, :]).ravel()
    vals, counts = np.unique(np.round(q, 12), return_counts=True)
    return vals, counts / float(L ** 3)


class Spectrum:
    def __init__(self, q: np.ndarray, w: np.ndarray, L: int | None):
        self.q, self.w, self.L = q, w, L

    def eps(self, Z):
        return Z * self.q + self.q ** 2

    def rmin(self, Z):
        e = self.eps(Z)
        if self.L is not None:
            # exclude q=0 when it is the zero mode carried by the uniform condensate? No:
            # all modes fluctuate; positivity needs r > -min eps.
            pass
        return -float(e.min())

    def G0(self, r, Z):
        return float(np.sum(self.w / (r + self.eps(Z))))

    def logdet(self, r, Z):
        return 0.5 * float(np.sum(self.w * np.log(r + self.eps(Z))))


# ---------------------------------------------------------------- free energies
def solve_r(sp: Spectrum, Z: float, m2: float, phi2: float) -> float:
    rmin = sp.rmin(Z)
    g = lambda r: r - m2 - 3 * LAM * (sp.G0(r, Z) + phi2)
    lo = rmin + 1e-14 * max(1.0, abs(rmin))
    # In infinite volume with Z<0 G0 diverges at rmin, so g(lo) < 0.  In finite volume
    # G0 is finite-but-huge near rmin for the same reason.
    if g(lo) > 0:
        lo = rmin + 1e-300
    hi = max(abs(m2) + 3 * LAM * (phi2 + 1.0) + 10.0, rmin + 10.0)
    while g(hi) < 0:
        hi *= 2
    step = 1e-12
    while g(lo) > 0 and step < 1:
        lo = rmin + step; step *= 10
    return brentq(g, lo, hi, xtol=1e-14, rtol=1e-13, maxiter=500)


def free_energy(sp: Spectrum, Z: float, m2: float, phi2: float, phi4: float, kin: float):
    r = solve_r(sp, Z, m2, phi2)
    G0 = sp.G0(r, Z)
    F = (sp.logdet(r, Z) + 0.5 * (m2 - r) * G0 + 0.75 * LAM * G0 ** 2
         + kin + 0.5 * m2 * phi2 + 0.25 * LAM * phi4 + 1.5 * LAM * G0 * phi2)
    return F, r, G0


def f_sym(sp, Z, m2):
    return free_energy(sp, Z, m2, 0.0, 0.0, 0.0)[0]


def f_uniform(sp, Z, m2):
    def F(a):
        return free_energy(sp, Z, m2, a * a, a ** 4, 0.0)[0]
    res = minimize_scalar(F, bounds=(1e-6, 4.0), method="bounded",
                          options={"xatol": 1e-9})
    return float(res.fun), float(res.x)


def lamellar_q(sp: Spectrum, Z: float) -> float:
    """khat^2 of the condensate: continuous optimum -Z/2 (infinite volume) or the
    allowed finite-L shell minimising eps."""
    if sp.L is None:
        return min(-Z / 2, 4.0)  # lamella along an axis: khat^2 <= 4
    q1 = 4 * np.sin(np.pi * np.arange(1, sp.L // 2 + 1) / sp.L) ** 2   # axis modes
    return float(q1[np.argmin(Z * q1 + q1 ** 2)])


def f_lamellar(sp, Z, m2):
    if Z >= 0:
        return 0.0, 0.0, float("nan")
    q = lamellar_q(sp, Z)
    e = Z * q + q * q

    def F(A):
        return free_energy(sp, Z, m2, A * A / 2, 3 * A ** 4 / 8, A * A * e / 4)[0]
    res = minimize_scalar(F, bounds=(1e-6, 5.0), method="bounded", options={"xatol": 1e-9})
    return float(res.fun), float(res.x), q


def phase(sp, Z, m2):
    fs = f_sym(sp, Z, m2)
    fu, a = f_uniform(sp, Z, m2)
    fl, A, q = f_lamellar(sp, Z, m2) if Z < 0 else (fs, 0.0, float("nan"))
    vals = {"symmetric": fs, "uniform": fu if a > 1e-4 else fs, "lamellar": fl if A > 1e-4 else fs}
    best = min(vals, key=vals.get)
    if vals[best] > fs - 1e-13:
        best = "symmetric"
    return best, vals, a, A


def boundary(sp, Z, which: str, lo: float, hi: float) -> float:
    """Bisection on m2 for f_which = f_sym (ordering transition)."""
    def d(m2):
        fs = f_sym(sp, Z, m2)
        if which == "uniform":
            f, a = f_uniform(sp, Z, m2)
            return (f - fs) if a > 1e-4 else 1e-12
        f, A, _ = f_lamellar(sp, Z, m2)
        return (f - fs) if A > 1e-4 else 1e-12
    dl, dh = d(lo), d(hi)
    if dl * dh > 0:
        return float("nan")
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        dm = d(mid)
        if dm * dl > 0:
            lo, dl = mid, dm
        else:
            hi = mid
    return 0.5 * (lo + hi)


def boundary_ul(sp, Z, lo, hi) -> float:
    def d(m2):
        return f_uniform(sp, Z, m2)[0] - f_lamellar(sp, Z, m2)[0]
    dl, dh = d(lo), d(hi)
    if dl * dh > 0:
        return float("nan")
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        dm = d(mid)
        if dm * dl > 0:
            lo, dl = mid, dm
        else:
            hi = mid
    return 0.5 * (lo + hi)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--L", type=int, nargs="+", default=[0, 12, 16, 20, 24])
    ap.add_argument("--Z", type=float, nargs="+",
                    default=[round(z, 4) for z in np.arange(-3.0, 1.01, 0.1)])
    ap.add_argument("--out", type=Path, default=ROOT / "reports" / "hartree")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    for L in args.L:
        sp = Spectrum(*infinite_spectrum(), None) if L == 0 else Spectrum(*finite_spectrum(L), L)
        for Z in args.Z:
            # Ordering transitions from the symmetric phase: scan m2 downward.
            mu = boundary(sp, Z, "uniform", -12.0, 1.0)
            ml = boundary(sp, Z, "lamellar", -12.0, 3.0) if Z < 0 else float("nan")
            mul = boundary_ul(sp, Z, -40.0, -1e-3) if Z < 0 else float("nan")
            # Which ordering wins first on cooling (larger m2)?
            first = "uniform" if (math.isnan(ml) or (not math.isnan(mu) and mu > ml)) else "lamellar"
            rows.append({"L": L, "Z": Z, "m2_sym_uniform": mu, "m2_sym_lamellar": ml,
                         "m2_uniform_lamellar": mul, "first_order_parameter": first,
                         "q_lamellar": lamellar_q(sp, Z) if Z < 0 else float("nan")})
            r = rows[-1]
            print(f"L={L:>2} Z={Z:+.2f}  sym/uni={mu:+.4f}  sym/lam={ml:+.4f}  uni/lam={mul:+.4f}  first={first}",
                  flush=True)
    with (args.out / "hartree_lines.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    (args.out / "hartree.json").write_text(json.dumps({"lambda": LAM, "rows": rows}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
