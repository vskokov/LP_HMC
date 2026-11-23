#!/usr/bin/env python3
"""Lattice anisotropy of the symmetric-phase propagator: regress 1/S(k) near its minimum on
[1, k2, k2^2, k2^3, a4 - 1/2], a4 = sum_mu khat_mu^4 / khat^4 (shells of a single orientation
class only).  Usage: python3 scripts/sk_anisotropy.py "runs/cv_umbrella/zeff/Zm2/L48/*/sk.csv" """
import sys, glob, itertools, numpy as np, pandas as pd
def shells(L, kmax):
    d = {}
    for n in itertools.product(range(L), repeat=3):
        c = 4*np.sin(np.pi*np.array(n)/L)**2; q = c.sum()
        if 0 < q <= kmax + 1e-9:
            d.setdefault(round(q, 5), []).append((c**2).sum()/q**2)
    return d
for pat in sys.argv[1:]:
    for f in sorted(glob.glob(pat)):
        L = int(open(f).readline().split()[1].split("=")[1])
        t = pd.read_csv(f, comment="#")
        g = t.groupby("q").S.agg(["mean", "std", "count"]); g = g[g.index > 0]
        sh = shells(L, g.index.max())
        a4 = np.array([np.mean(sh[round(q, 5)]) for q in g.index])
        # mixed-orientation shells average; keep only shells whose members share A4
        pure = np.array([np.ptp(sh[round(q, 5)]) < 1e-9 for q in g.index])
        q = g.index.values; y = 1/g["mean"].values; e = g["std"].values/np.sqrt(g["count"].values)/g["mean"].values**2
        qmin = q[np.argmin(y)]
        w = pure & (np.abs(q - qmin) < 0.35)
        X = np.c_[np.ones(w.sum()), q[w], q[w]**2, q[w]**3, a4[w] - 0.5]
        W = 1/e[w]**2
        cov = np.linalg.inv(X.T @ (X*W[:, None])); b = cov @ (X.T @ (W*y[w]))
        r = (y[w] - X@b)/e[w]
        X0 = X[:, :4]; cov0 = np.linalg.inv(X0.T@(X0*W[:,None])); b0 = cov0@(X0.T@(W*y[w])); r0=(y[w]-X0@b0)/e[w]
        print(f"{f.split('zeff/')[-1][:32]:32s} n={w.sum():4d} c_A4={b[4]:+.5f}±{np.sqrt(cov[4,4]):.5f}  chi2/dof {np.sum(r0**2)/(w.sum()-4):.2f} -> {np.sum(r**2)/(w.sum()-5):.2f}  y_min={y.min():.3f}")
