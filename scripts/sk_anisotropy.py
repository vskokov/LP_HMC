#!/usr/bin/env python3
"""Cubic-anisotropy check of the moat line.  Z_eff from the small-k fit (khat^2<=0.8) using shell subsets: all, axis (deg 6 + k=0),
non-axis (deg != 6).  Same replica exclusion and fit as analyze_sk_symmetric.py.

Output: reports/sk_symmetric/anisotropy_zeff.csv; crossings per subset to stdout.
"""
import sys, json, glob
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
from analyze_sk_symmetric import fit, ORDER_ABS
rng = np.random.default_rng(1)
summ = pd.read_csv(ROOT / "reports/sk_symmetric/summary_kfit0p8.csv"); summ = summ[summ.replicas_used > 0]
summ["Z"] = summ.Z.round(4)
summ = summ.loc[summ.groupby(["Z", "m2"]).L.idxmax()]
rows = []
for _, r in summ.iterrows():
    run = ROOT / "runs/cv_umbrella" / r.run if (ROOT / "runs/cv_umbrella" / r.run).is_dir() else ROOT / "runs/sk_symmetric" / r.run
    if not run.is_dir():
        continue
    sk = pd.read_csv(run / "sk.csv", comment="#"); obs = pd.read_csv(run / "obs.csv", comment="#")
    late = obs[obs["sample"] > obs["sample"].max() / 2]
    ref = obs.groupby("replica")["P_max"].median().min(); g = late.groupby("replica")["P_max"]
    ordered = set(g.max().loc[lambda x: x > 5 * ref].index) | set(g.mean().loc[lambda x: x > ORDER_ABS].index)
    sk = sk[~sk.replica.isin(ordered) & (sk.q <= 0.8 + 1e-9)]
    deg = sk.groupby("q").deg.first()
    table = sk.pivot_table(index=["replica", "block"], columns="q", values="S")
    q = table.columns.values.astype(float); X = table.values; n = len(X)
    boot = np.array([X[rng.integers(0, n, n)].mean(0) for _ in range(200)])
    S, err = X.mean(0), boot.std(0, ddof=1)
    d = deg.loc[q].values
    out = dict(Z=r.Z, m2=r.m2, L=r.L)
    for name, m in [("all", np.ones_like(q, bool)), ("axis", (d == 6) | (q == 0)), ("off", d != 6)]:
        c, chi = fit(q[m], S[m], err[m])
        bz = np.array([(lambda cc: cc[1] / cc[2])(fit(q[m], b[m], err[m])[0]) for b in boot])
        out[f"Zeff_{name}"] = c[1] / c[2]; out[f"err_{name}"] = bz.std(ddof=1); out[f"chi2_{name}"] = chi; out[f"n_{name}"] = int(m.sum())
    rows.append(out)
t = pd.DataFrame(rows).sort_values(["Z", "m2"])
t.to_csv(ROOT / "reports/sk_symmetric/anisotropy_zeff.csv", index=False)
def zero(g, col):
    g = g.sort_values("m2", ascending=False); m, z = g.m2.values, g[col].values
    for i in range(len(m) - 1):
        if np.sign(z[i]) != np.sign(z[i + 1]):
            return m[i] + (m[i + 1] - m[i]) * z[i] / (z[i] - z[i + 1])
    return np.nan
print("crossings (m2) by subset")
for Z, g in t.groupby("Z"):
    if -1.0 <= Z <= 0:
        print(f"Z={Z:+.3f}  all {zero(g,'Zeff_all'):+.4f}  axis {zero(g,'Zeff_axis'):+.4f}  off-axis {zero(g,'Zeff_off'):+.4f}   L={int(g.L.max())}")
print("\nclosest-to-transition masses:")
for Z, g in t.groupby("Z"):
    if Z in (-0.95, -0.9, -0.8, -0.6, -0.4, -0.2):
        r = g.sort_values("m2").iloc[0]
        print(f"Z={Z:+.2f} m2={r.m2:.3f}: all {r.Zeff_all:+.4f}({r.err_all:.4f}) chi2 {r.chi2_all:.1f} | axis {r.Zeff_axis:+.4f}({r.err_axis:.4f}) chi2 {r.chi2_axis:.1f} n={r.n_axis} | off {r.Zeff_off:+.4f}({r.err_off:.4f}) chi2 {r.chi2_off:.1f}")
