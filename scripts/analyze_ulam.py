#!/usr/bin/env python3
"""Direct-coexistence (slab) runs of the `ulam` stage: which phase invades the box.

Each replica starts half uniform (phi = +u) and half lamellar (A cos kx).  Indicator per
sample:  x_u = M^2 / (M^2 + 2 P_max),  M^2 = |phi_0|^2/V^2, P_max = largest k != 0 shell power.
For pure uniform order x_u -> 1, pure lamellae x_u -> 0, the initial slab sits near 0.5.
A replica is classified from the mean over the last 20 % of samples:
  uniform   x_u > 0.85            lamellar  x_u < 0.15 and P_max > 0.02
  symmetric M^2 < 0.02 and P_max < 0.02 (both halves melted)        else  "slab"
Odd replicas: layers parallel to the interfaces; even: perpendicular.

Output: reports/ulam/summary.csv (one row per run) and replicas.csv; text table to stdout.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "cv_umbrella"
OUT = ROOT / "reports" / "ulam"


def classify(x: float, m2: float, p: float) -> str:
    if m2 < 0.02 and p < 0.02:
        return "symmetric"
    if x > 0.85:
        return "uniform"
    if x < 0.15 and p > 0.02:
        return "lamellar"
    return "slab"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    reps, runs = [], []
    for obs in sorted([*RUNS.glob("ulam/Z*/L*/*/obs.csv"), *RUNS.glob("ulam2/Z*/L*/*/obs.csv"),
                         *RUNS.glob("ulam3/Z*/L*/*/obs.csv")]):
        run = obs.parent
        d = pd.read_csv(obs, comment="#")
        if d.empty:
            continue
        meta = json.loads((run / "diagnostics.json").read_text())
        n = d["sample"].max()
        d["x_u"] = d.M2 / (d.M2 + 2 * d.P_max)
        late = d[d["sample"] > 0.8 * n].groupby("replica")[["x_u", "M2", "P_max", "q_max"]].mean()
        early = d[d["sample"] <= max(1, 0.05 * n)].groupby("replica").x_u.mean()
        for r, row in late.iterrows():
            reps.append({"run": run.relative_to(RUNS).as_posix(), "Z": meta["Z"], "m2": meta["m2"],
                         "replica": r, "layers": "parallel" if r % 2 else "perp",
                         "x_u_start": early.get(r), "x_u_end": row.x_u, "M2": row.M2,
                         "P_max": row.P_max, "q_max": row.q_max,
                         "state": classify(row.x_u, row.M2, row.P_max)})
        st = pd.Series([q["state"] for q in reps if q["run"] == run.relative_to(RUNS).as_posix()])
        runs.append({"Z": meta["Z"], "m2": meta["m2"], "samples": n, "complete": (run / "complete.json").is_file(),
                     **{k: int((st == k).sum()) for k in ("uniform", "lamellar", "slab", "symmetric")}})
    R = pd.DataFrame(reps)
    S = pd.DataFrame(runs).sort_values(["Z", "m2"])
    R.to_csv(OUT / "replicas.csv", index=False)
    S.to_csv(OUT / "summary.csv", index=False)
    print(S.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
