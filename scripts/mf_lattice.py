#!/usr/bin/env python3
"""Lattice mean-field phase diagram of
    H = sum_x [ Z/2 (grad phi)^2 + 1/2 (lap phi)^2 + m2/2 phi^2 + lam/4 phi^4 ]
with the exact lattice operators used by the HMC code (forward-difference gradient,
6-neighbour Laplacian), lam = 4.

Mean-field free-energy densities are obtained by *unconstrained* minimisation of
H/V over static periodic configurations:

* uniform:      phi^2 = -m2/lam,  f_u = -m2^2/(4 lam)
* lamellar:     1D profiles phi(z) on periodic chains of N sites with n periods
                (all harmonics kept), minimised over n — gives q* and the exact
                multi-harmonic lamellar free energy;
* square/cubic: 2D / 3D periodic boxes seeded with 2 or 3 orthogonal modes, to test
                whether any higher-rank morphology beats lamellae.

Single-mode closed forms (eps = m2 - Z^2/4 at the dispersion minimum k^2=-Z/2):
  lamellar -eps^2/(6 lam), square -eps^2/(9 lam), cubic -eps^2/(10 lam);
  uniform/lamellar boundary m2 = -(2+sqrt6) Z^2/4.

Also reports the smectic elastic constants of the lamellar state (compression B and
bending K, from the curvature of f_lam(q) and the single-mode formula) used for the
Landau–Peierls/Caillé estimate of the Bragg-peak exponent.

Usage:  python3 scripts/mf_lattice.py [--out reports/mean_field]
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

LAM = 4.0
ROOT = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------ energies
def energy_nd(phi: np.ndarray, Z: float, m2: float) -> tuple[float, np.ndarray]:
    """H/V and its gradient for a periodic field of any dimension d<=3 (lattice ops)."""
    d = phi.ndim
    lap = -2 * d * phi
    grad2 = np.zeros_like(phi)
    for ax in range(d):
        fwd = np.roll(phi, -1, axis=ax)
        lap += fwd + np.roll(phi, 1, axis=ax)
        grad2 += (fwd - phi) ** 2
    e = 0.5 * lap ** 2 + 0.5 * Z * grad2 + 0.5 * m2 * phi ** 2 + 0.25 * LAM * phi ** 4
    # dH/dphi = lap(lap) - Z lap + m2 phi + lam phi^3
    laplap = -2 * d * lap
    for ax in range(d):
        laplap += np.roll(lap, -1, axis=ax) + np.roll(lap, 1, axis=ax)
    g = laplap - Z * lap + m2 * phi + LAM * phi ** 3
    V = phi.size
    return float(e.sum() / V), g / V


def minimise(phi0: np.ndarray, Z: float, m2: float) -> tuple[float, np.ndarray]:
    shape = phi0.shape
    def fun(x):
        f, g = energy_nd(x.reshape(shape), Z, m2)
        return f, g.ravel()
    res = minimize(fun, phi0.ravel(), jac=True,
                   method="L-BFGS-B", options={"maxiter": 20000, "gtol": 1e-12, "ftol": 1e-15})
    return float(res.fun), res.x.reshape(shape)


def khat2(k: float) -> float:
    return 4.0 * math.sin(k / 2.0) ** 2


def disp(k: float, Z: float, m2: float) -> float:
    q = khat2(k)
    return m2 + Z * q + q * q


def f_uniform(m2: float) -> float:
    return -m2 * m2 / (4 * LAM) if m2 < 0 else 0.0


def f_lamellar(Z: float, m2: float, N: int = 120, nmax: int | None = None) -> dict:
    """Best 1D periodic profile over n periods on an N-site ring (k = 2 pi n / N)."""
    best = {"f": 0.0, "k": 0.0, "n": 0, "amp": 0.0}
    if Z >= 0:
        return best
    kstar = 2 * math.asin(min(1.0, math.sqrt(-Z / 2) / 2))
    n0 = max(1, round(kstar * N / (2 * math.pi)))
    cands = (range(max(1, n0 // 2), min(N // 2, 2 * n0 + 2) + 1) if nmax is None
             else range(1, nmax + 1))
    x = np.arange(N)
    for n in cands:
        k = 2 * math.pi * n / N
        e = disp(k, Z, m2)
        if e >= 0:
            continue
        A = math.sqrt(-4 * e / (3 * LAM))
        f, phi = minimise(A * np.cos(k * x), Z, m2)
        if f < best["f"] - 1e-14:
            # reject solutions that relaxed to a uniform state
            if np.std(phi) > 1e-6:
                best = {"f": f, "k": k, "n": n, "amp": float(np.max(np.abs(phi - phi.mean())))}
    return best


def f_rank(Z: float, m2: float, rank: int, p: int) -> float:
    """Square (rank 2) or cubic (rank 3) pattern on a p^rank periodic box."""
    if Z >= 0:
        return 0.0
    k = 2 * math.pi / p
    e = disp(k, Z, m2)
    if e >= 0:
        return 0.0
    grids = np.meshgrid(*([np.arange(p)] * rank), indexing="ij")
    seed = sum(np.cos(k * g) for g in grids)
    A = math.sqrt(-4 * e / (3 * LAM * rank))
    f, phi = minimise(A * seed, Z, m2)
    return f


# ------------------------------------------------------------------ phase diagram
def phase_at(Z: float, m2: float) -> tuple[str, dict]:
    fu = f_uniform(m2)
    lam = f_lamellar(Z, m2)
    fl = lam["f"]
    if min(fu, fl) > -1e-12:
        return "symmetric", lam
    return ("uniform" if fu <= fl else "lamellar"), lam


def boundary_uniform_lamellar(Z: float) -> float:
    """Bisection in m2 for f_u = f_lam at fixed Z<0."""
    hi = -1e-6
    fhi = f_uniform(hi) - f_lamellar(Z, hi)["f"]
    lo = -(2 + math.sqrt(6)) * Z * Z / 4 * 0.5
    flo = f_uniform(lo) - f_lamellar(Z, lo)["f"]
    # Expand downward until the uniform state wins (it may never: walls with Z<-2 are
    # energetically favourable on this lattice, so lamellae win at all m2).
    while flo * fhi > 0 and lo > -400.0:
        hi, fhi = lo, flo
        lo *= 1.6
        flo = f_uniform(lo) - f_lamellar(Z, lo)["f"]
    if flo * fhi > 0:
        return float("nan")
    for _ in range(45):
        mid = 0.5 * (lo + hi)
        fm = f_uniform(mid) - f_lamellar(Z, mid)["f"]
        if fm * flo > 0:
            lo, flo = mid, fm
        else:
            hi = mid
    return 0.5 * (lo + hi)


def symmetric_modulated_line(Z: float) -> float:
    """Exact lattice MF instability m2 = -min_k (Z k^2 + k^4) = Z^2/4 (if -Z/2 <= 12)."""
    q = min(-Z / 2, 12.0)
    return -(Z * q + q * q)


def elastic_constants(Z: float, m2: float) -> dict:
    """Single-mode smectic constants for phi = A cos(q(z-u)), continuum dispersion.

    f(k) = (A^2/4) eps(k) + 3 lam A^4/32 with eps = m2 + Z k^2 + k^4.  A layer
    displacement u gives k^2 = q^2[(1-u_z)^2 + (grad_perp u)^2]; at the optimal
    q (Z + 2 q^2 = 0) this yields
        B = 2 A^2 q^4           (compression, coefficient of (1/2)(d_z u)^2)
        K = A^2 q^2 / 2         (bending,     coefficient of (1/2)(lap_perp u)^2)
    so lambda_pen = sqrt(K/B) = 1/(2q), and the Caille exponent of the first Bragg
    peak is eta = q^2 T / (8 pi sqrt(B K)).
    """
    if Z >= 0:
        return {}
    q2 = -Z / 2
    eps = m2 - Z * Z / 4
    if eps >= 0:
        return {}
    A2 = -4 * eps / (3 * LAM)
    B = 2 * A2 * q2 * q2
    K = A2 * q2 / 2
    eta = q2 / (8 * math.pi * math.sqrt(B * K))
    return {"q": math.sqrt(q2), "A2": A2, "B": B, "K": K, "eta_caille": eta}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "reports" / "mean_field")
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    # 1. Closed forms vs unconstrained lattice minimisation at representative points.
    checks = []
    for Z, m2 in ((-1.0, -0.5), (-2.0, -1.0), (-2.0, -3.0), (-4.0, 0.0), (-4.0, -8.0)):
        lam = f_lamellar(Z, m2)
        eps = disp(lam["k"], Z, m2) if lam["k"] else float("nan")
        p = 6 if Z == -2.0 else 4 if Z == -4.0 else 8
        row = {"Z": Z, "m2": m2, "f_uniform": f_uniform(m2), "f_lamellar": lam["f"],
               "f_lamellar_single_mode": -eps * eps / (6 * LAM) if lam["k"] else 0.0,
               "k_star": lam["k"], "khat2_star": khat2(lam["k"]) if lam["k"] else 0.0,
               "f_square_p": f_rank(Z, m2, 2, p), "f_cubic_p": f_rank(Z, m2, 3, p),
               "f_lamellar_p": minimise(math.sqrt(max(-4 * disp(2 * math.pi / p, Z, m2) / (3 * LAM), 0))
                                        * np.cos(2 * math.pi * np.arange(p) / p), Z, m2)[0], "p": p}
        checks.append(row)
    # 2. Phase boundaries on a Z grid.
    Zs = np.round(np.arange(-3.0, 1.01, 0.25 if args.quick else 0.05), 6)
    lines = []
    for Z in Zs:
        row = {"Z": float(Z), "m2_sym_uniform": 0.0 if Z >= 0 else float("nan"),
               "m2_sym_modulated": symmetric_modulated_line(Z) if Z < 0 else float("nan"),
               "m2_uniform_modulated": boundary_uniform_lamellar(Z) if Z < 0 else float("nan"),
               "m2_uniform_modulated_single_mode": -(2 + math.sqrt(6)) * Z * Z / 4 if Z < 0 else float("nan")}
        lines.append(row)
    # 3. Elastic constants along a cut inside the lamellar phase.
    elastic = []
    for Z in (-1.172, -2.0, -2.5, -3.0, -4.0):
        for frac in (0.5, 1.0):
            m2 = Z * Z / 4 - frac * Z * Z / 2
            elastic.append({"Z": Z, "m2": m2, **elastic_constants(Z, m2)})
    payload = {"lambda": LAM, "checks": checks, "lines": lines, "elastic": elastic,
               "lifshitz_point": {"Z": 0.0, "m2": 0.0}}
    (args.out / "mean_field.json").write_text(json.dumps(payload, indent=2))
    import csv
    with (args.out / "mean_field_lines.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(lines[0]))
        w.writeheader(); w.writerows(lines)
    for c in checks:
        print({k: (round(v, 6) if isinstance(v, float) else v) for k, v in c.items()})
    print("uniform/modulated boundary check (exact vs single mode):")
    for r in lines[:: max(1, len(lines) // 8)]:
        print(f"  Z={r['Z']:+.2f}  exact={r['m2_uniform_modulated']:.5f}  single={r['m2_uniform_modulated_single_mode']:.5f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
