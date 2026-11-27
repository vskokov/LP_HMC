#!/usr/bin/env python3
"""Direct-coexistence runs for the symmetric <-> lamellar line (stage slam): which phase invades.

Each replica starts with x <= L/2 disordered (small noise) and x > L/2 lamellar (A cos kc);
odd replicas: layers parallel to the interfaces, even: perpendicular.  P_max = largest
k != 0 shell power sum_shell |phi_k|^2 / V^2 (a full lamella has ~4x the power of the half
box it starts with).  A replica is classified from P_max averaged over the last 20 % of
samples against the first 5 %:
  lamellar   P_end > 1.6 P_start          symmetric  P_end < 0.25 P_start and P_end < 0.05
  else "slab" (interface not resolved on the run time scale)

Output: reports/slam/summary.csv (one row per run) and replicas.csv; text table to stdout.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "cv_umbrella"
OUT = ROOT / "reports" / "slam"


def classify(p0: float, p1: float) -> str:
    if p1 > 1.6 * p0:
        return "lamellar"
    if p1 < 0.25 * p0 and p1 < 0.05:
        return "symmetric"
    return "slab"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    reps, runs = [], []
    for obs in sorted(RUNS.glob("slam*/Z*/L*/*/obs.csv")):
        run = obs.parent
        d = pd.read_csv(obs, comment="#")
        if d.empty:
            continue
        meta = json.loads((run / "diagnostics.json").read_text())
        n = d["sample"].max()
        late = d[d["sample"] > 0.8 * n].groupby("replica")[["M2", "P_max", "q_max"]].mean()
        early = d[d["sample"] <= max(1, 0.05 * n)].groupby("replica").P_max.mean()
        tag = run.relative_to(RUNS).as_posix()
        for r, row in late.iterrows():
            reps.append({"run": tag, "Z": meta["Z"], "L": meta["L"], "m2": meta["m2"], "replica": r,
                         "layers": "parallel" if r % 2 else "perp", "P_start": early.get(r),
                         "P_end": row.P_max, "M2": row.M2, "q_max": row.q_max,
                         "state": classify(early.get(r), row.P_max)})
        st = pd.Series([q["state"] for q in reps if q["run"] == tag])
        runs.append({"Z": round(meta["Z"], 4), "L": meta["L"], "m2": meta["m2"], "samples": n,
                     "complete": (run / "complete.json").is_file(),
                     **{k: int((st == k).sum()) for k in ("lamellar", "symmetric", "slab")}})
    if not runs:
        print("no slam runs yet")
        return 0
    pd.DataFrame(reps).to_csv(OUT / "replicas.csv", index=False)
    S = pd.DataFrame(runs).sort_values(["Z", "L", "m2"])
    S.to_csv(OUT / "summary.csv", index=False)
    print(S.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
