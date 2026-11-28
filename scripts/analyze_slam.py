#!/usr/bin/env python3
"""Direct-coexistence runs for the symmetric <-> lamellar line (stage slam): which phase invades.

Each replica starts with x <= L/2 disordered (small noise) and x > L/2 lamellar (A cos kc);
odd replicas: layers parallel to the interfaces, even: perpendicular.  P_max = largest
k != 0 shell power sum_shell |phi_k|^2 / V^2 (a full lamella has ~4x the power of the half
box it starts with).  The interface usually resolves already during the 2000 thermalization
trajectories (Z=-2 calibration), so P_end (last 20 % of samples) is compared with the
full-lamella power P_ref = largest P_end at the same (Z, L) (needs one lamellar run per Z):
  lamellar   P_end > 0.6 P_ref            symmetric  P_end < 0.1 P_ref
  else "slab" (half-filled box, P ~ 0.25 P_ref: interface not resolved on the run time scale)
P_start (first 5 %) is reported to show replicas still drifting.

Output: reports/slam/summary.csv (one row per run) and replicas.csv; text table to stdout.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "cv_umbrella"
OUT = ROOT / "reports" / "slam"


def classify(p1: float, pref: float) -> str:
    if p1 > 0.6 * pref:
        return "lamellar"
    if p1 < 0.1 * pref:
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
                         "samples": n, "complete": (run / "complete.json").is_file()})
    if not reps:
        print("no slam runs yet")
        return 0
    R = pd.DataFrame(reps)
    R["Z"] = R.Z.round(4)
    pref = R.groupby(["Z", "L"]).P_end.transform("max")
    R["state"] = [classify(p, q) for p, q in zip(R.P_end, pref)]
    R.to_csv(OUT / "replicas.csv", index=False)
    S = (R.groupby(["Z", "L", "m2", "layers"]).state.value_counts().unstack(fill_value=0)
         .reindex(columns=["lamellar", "symmetric", "slab"], fill_value=0).unstack("layers", fill_value=0))
    S.columns = [f"{a}_{b}" for a, b in S.columns]
    S = S.join(R.groupby(["Z", "L", "m2"])[["samples", "complete"]].first()).reset_index()
    S.to_csv(OUT / "summary.csv", index=False)
    print(S.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
