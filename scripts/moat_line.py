#!/usr/bin/env python3
"""Symmetric -> moat crossover in the symmetric phase: the line Z_eff(Z, m2) = 0, where the
curvature of the renormalized dispersion 1/S(k) at k = 0 changes sign (Z_eff < 0: the
maximum of S(k) sits at k != 0, the moat regime).

Per Z, Z_eff(m2) at the largest L is read from the S(k) fits of analyze_sk_symmetric.py,
from both the small-k fit (khat^2 <= 0.8, summary_kfit0p8.csv; primary) and the global fit
(khat^2 <= 3, summary.csv); the difference is quoted as the fit-range systematic.  The zero
is found by linear interpolation between the two masses that bracket the sign change.
Where Z_eff keeps one sign over the whole scan, the row records a bound:
  kind = "crossing"   m2_moat interpolated
  kind = "below"      Z_eff < 0 down to the deepest symmetric mass: the moat persists to
                      within (m2_min - m_c) of the transition (m2_moat < m2_min)
  kind = "none"       Z_eff > 0 everywhere scanned: no moat at this Z
  kind = "shift"      deep in the symmetric phase (Z = 0, m2 >= 0): the momentum-dependent
                      self-energy shifts the line by dZ = -Z_eff(Z=0, m2) (global fit, which
                      reproduces the Z = -0.01..-0.1 crossings); row gives Z = -Z_eff, Z_err,
                      and m2_moat = m2

Output: reports/sk_symmetric/moat_line.csv
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REP = ROOT / "reports" / "sk_symmetric"


def load(name: str) -> pd.DataFrame:
    t = pd.read_csv(REP / name)
    t = t[t.replicas_used > 0].copy()
    t["Z"] = t.Z.round(4)
    return t.loc[t.groupby(["Z", "m2"]).L.idxmax()]


def zero(g: pd.DataFrame) -> tuple[str, float]:
    g = g.sort_values("m2", ascending=False)
    m, z = g.m2.values, g.Zeff.values
    for i in range(len(m) - 1):
        if np.sign(z[i]) != np.sign(z[i + 1]):
            return "crossing", float(m[i] + (m[i + 1] - m[i]) * z[i] / (z[i] - z[i + 1]))
    return ("below" if z[-1] < 0 else "none"), float(m[-1])


def main() -> int:
    small, glob = load("summary_kfit0p8.csv"), load("summary.csv")
    rows = []
    for Z, g in small.groupby("Z"):
        kind, m = zero(g)
        gg = glob[glob.Z == Z]
        kind2, m2g = zero(gg) if len(gg) > 1 else ("", np.nan)
        rows.append({"Z": Z, "kind": kind, "m2_moat": m, "m2_moat_global_fit": m2g if kind2 == kind else np.nan,
                     "sys": abs(m - m2g) if kind2 == kind == "crossing" else np.nan,
                     "m2_min": g.m2.min(), "m2_max": g.m2.max(), "n": len(g), "L": int(g.L.max())})
    raw = pd.read_csv(REP / "summary.csv")
    raw = raw[(raw.replicas_used > 0) & (raw.Z.round(4) == 0.0) & (raw.m2 >= 0.0)]
    for m2, g in raw.groupby("m2"):          # inverse-variance mean over repeated runs
        g = g[g.L == g.L.max()]
        w = 1.0 / g.Zeff_err**2
        ze, er = float((w * g.Zeff).sum() / w.sum()), float(w.sum() ** -0.5)
        rows.append({"Z": -ze, "kind": "shift", "m2_moat": m2, "m2_moat_global_fit": np.nan, "sys": np.nan,
                     "Z_err": er, "m2_min": m2, "m2_max": m2, "n": len(g), "L": int(g.L.max())})
    out = pd.DataFrame(rows)
    out.to_csv(REP / "moat_line.csv", index=False)
    print(out.round(4).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
