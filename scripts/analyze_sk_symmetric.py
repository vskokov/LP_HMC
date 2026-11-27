#!/usr/bin/env python3
"""Renormalized dispersion from the unbiased symmetric-phase runs (scripts/sk_symmetric.jl).

For every run directory (runs/sk_symmetric/<Z>/<L>/<m2>/) with complete.json:

* replicas that ordered (largest non-zero shell power P_max above ``--order-threshold``
  (default 5) times the median P_max of the least-ordered replica, anywhere in the last
  half of the samples) are dropped and reported.  Disordered replicas stay below 4x
  across all 199 runs; nucleated lamellae reach 6-15x.  A replica whose late-time mean
  P_max exceeds 0.1 is also dropped (catches runs in which every replica ordered);
* S(k̂²) per shell is averaged over the remaining replicas and blocks;
* G⁻¹ = 1/S is fitted with a + b k̂² + c k̂⁴ for 0 ≤ k̂² ≤ --kfit (weighted by the
  block-bootstrap errors), giving

      Z_eff = b/c,  k̂²* = −b/(2c),  m²_eff = a/c   (k̂⁴ coefficient normalised to 1),

  errors from a bootstrap over (replica, block) units.

Output: reports/sk_symmetric/summary.csv and per-run spectrum.csv.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ORDER_ABS = 0.1   # late-time mean P_max of a lamella is 0.2-0.3; disordered <= 0.05 for L >= 32


def fit(q, S, err):
    y = 1.0 / S
    w = S**2 / np.maximum(err, 1e-12)       # 1/σ(1/S) = S²/σ(S)
    A = np.vstack([np.ones_like(q), q, q**2]).T
    coef = np.linalg.lstsq(A * w[:, None], y * w, rcond=None)[0]
    chi2 = float((((A @ coef) - y) * w) ** 2 @ np.ones_like(q))
    return coef, chi2 / max(len(q) - 3, 1)


def analyze(run: Path, root: Path, kfit: float, thr: float, nboot: int, rng) -> dict | None:
    if not (run / "complete.json").is_file():
        return None
    sk = pd.read_csv(run / "sk.csv", comment="#")
    obs = pd.read_csv(run / "obs.csv", comment="#")
    late = obs[obs["sample"] > obs["sample"].max() / 2]
    # reference: the least-ordered replica (the run median fails when most replicas nucleated)
    ref = obs.groupby("replica")["P_max"].median().min()
    g = late.groupby("replica")["P_max"]
    ordered = sorted(set(g.max().loc[lambda x: x > thr * ref].index)
                     | set(g.mean().loc[lambda x: x > ORDER_ABS].index))
    sk = sk[~sk.replica.isin(ordered)]
    meta = json.loads((run / "diagnostics.json").read_text())
    if sk.empty:
        (out_dir(run, root) / "spectrum.csv").unlink(missing_ok=True)
        return dict(Z=meta["Z"], L=meta["L"], m2=meta["m2"], replicas_used=0, ordered=len(ordered))
    sk = sk[sk.q <= kfit + 1e-9]
    table = sk.pivot_table(index=["replica", "block"], columns="q", values="S")
    q = table.columns.values.astype(float)
    X = table.values
    S = X.mean(0)
    boot = np.empty((nboot, len(q)))
    n = len(X)
    for i in range(nboot):
        boot[i] = X[rng.integers(0, n, n)].mean(0)
    err = boot.std(0, ddof=1)
    coef, chi2 = fit(q, S, err)
    bc = np.array([fit(q, b, err)[0] for b in boot])
    zeff = bc[:, 1] / bc[:, 2]
    k2s = -bc[:, 1] / (2 * bc[:, 2])
    pd.DataFrame({"q": q, "S": S, "S_err": err, "invS_fit": coef[0] + coef[1] * q + coef[2] * q**2}) \
        .to_csv(out_dir(run, root) / "spectrum.csv", index=False)
    return dict(Z=meta["Z"], L=meta["L"], m2=meta["m2"], replicas_used=meta["replicas"] - len(ordered),
                ordered=len(ordered), units=n, Zeff=coef[1] / coef[2], Zeff_err=zeff.std(ddof=1),
                k2_star=-coef[1] / (2 * coef[2]), k2_star_err=k2s.std(ddof=1), c=coef[2],
                m2_eff=coef[0] / coef[2], q_Smax=q[np.argmax(S)], Smax=S.max(), chi2_dof=chi2,
                acc=meta["hmc_acceptance_mean"])


def out_dir(run: Path, root: Path) -> Path:
    d = ROOT / "reports" / "sk_symmetric" / root.name / run.relative_to(root)
    d.mkdir(parents=True, exist_ok=True)
    return d


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", type=Path, nargs="+",
                    default=[ROOT / "runs" / "sk_symmetric", ROOT / "runs" / "cv_umbrella" / "zeff",
                             ROOT / "runs" / "cv_umbrella" / "zeff2",
                             ROOT / "runs" / "cv_umbrella" / "zeff3",
                             ROOT / "runs" / "cv_umbrella" / "zeff4",
                             ROOT / "runs" / "cv_umbrella" / "zeff5",
                             ROOT / "runs" / "cv_umbrella" / "zeff6",
                             ROOT / "runs" / "cv_umbrella" / "zeff7",
                             ROOT / "runs" / "cv_umbrella" / "zeff8",
                             ROOT / "runs" / "cv_umbrella" / "zeffL"],
                    help="local scan and the Hazel zeff/zeff2 stages (pulled by hpc_sync.py)")
    ap.add_argument("--kfit", type=float, default=3.0)
    ap.add_argument("--order-threshold", type=float, default=5.0)
    ap.add_argument("--bootstrap", type=int, default=200)
    args = ap.parse_args()
    rng = np.random.default_rng(1)
    rows = []
    for root in args.root:
        for run in sorted(p.parent for p in root.glob("*/L*/*/complete.json")):
            r = analyze(run, root, args.kfit, args.order_threshold, args.bootstrap, rng)
            if r:
                r["run"] = f"{root.name}/{run.relative_to(root)}"
                rows.append(r)
    t = pd.DataFrame(rows)
    if t.empty:
        print("no complete runs")
        return 0
    out = ROOT / "reports" / "sk_symmetric" / "summary.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    t.to_csv(out, index=False)
    pd.set_option("display.width", 220)
    print(t.drop(columns=["run"]).round(4).to_string(index=False))
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
