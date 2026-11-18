#!/usr/bin/env python3
"""Analyze quadratic-CV umbrella runs (scripts/cv_umbrella.jl) at fixed (Z, L).

All completed runs of one (Z, L) directory -- any number of source masses and
seeds -- are combined: per-run binned WHAM in the CV s, then a Newton MBAR over
runs with mixture densities b_j = ldenom_j(s) - m_j Q/2, so that canonical
weights are available continuously in m^2.

Reported on an m^2 grid: <s>, chi_s = V(<s^2>-<s>^2), <Q>/V, Var(Q)/V, <M^2>,
<d_eff>, ESS, and the distribution P(s).  A two-peak P(s) (disordered low-s and
ordered high-s maxima separated by a minimum) is the coexistence signature; at
the equal-height point the barrier F(min)-F(peaks) and the latent jump of Q/V
are reported.  First-order scaling: barrier ~ L^2.

Usage:
  python3 scripts/analyze_cv_umbrella.py --dir runs/cv_umbrella/<campaign>/Zm2/L12 [--bootstrap 40]
  python3 scripts/analyze_cv_umbrella.py summary --root runs/cv_umbrella/<campaign>
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
from analyze_transition_order import solve_global  # noqa: E402
from analyze_umbrella import sample_log_denominator, solve_binned_wham  # noqa: E402

GRID = 8193


class CVRun:
    def __init__(self, path: Path):
        import pandas as pd
        meta = {}
        nhead = 0
        with path.open() as fh:
            for line in fh:
                if not line.startswith("#"):
                    break
                k, _, v = line[1:].strip().partition("=")
                meta[k.strip()] = v.strip()
                nhead += 1
        df = pd.read_csv(path, skiprows=nhead)
        self.meta = meta
        self.path = path
        self.L = int(meta["L"])
        self.V = float(self.L) ** 3
        self.Z = float(meta["Z"])
        self.m2 = float(meta["m2"])
        self.centers = np.array([float(x) for x in meta["centers"].split(";")])
        self.kappas = np.array([float(x) for x in meta["kappas"].split(";")])
        self.nw = len(self.centers)
        df = df.sort_values(["sample", "slot"], kind="stable")
        nsamp = int(df["sample"].max())
        if len(df) != nsamp * self.nw:
            raise ValueError(f"{path}: incomplete sample rows")
        self.spw = nsamp
        self.slot = df["slot"].to_numpy(np.int64)
        self.s = df["s"].to_numpy(np.float64)
        self.Q = df["Q"].to_numpy(np.float64)
        self.M = df["M"].to_numpy(np.float64)
        self.deff = df["d_eff"].to_numpy(np.float64)
        self.lam1 = df["lambda1"].to_numpy(np.float64)

    def rows_for_times(self, times: np.ndarray) -> np.ndarray:
        return (times[:, None] * self.nw + np.arange(self.nw)[None, :]).reshape(-1)


def solve_run(run: CVRun, rows: np.ndarray, grid: np.ndarray, init=None):
    s = run.s[rows]
    counts = np.bincount(run.slot[rows], minlength=run.nw + 1)[1:].astype(float)
    for bins in (256, 128, 64):
        try:
            free, _, _ = solve_binned_wham(s, run.centers, run.kappas, counts, bins,
                                           initial_free=init)
            break
        except RuntimeError:
            init = None
    else:
        raise RuntimeError(f"{run.path}: WHAM failed")
    return free, sample_log_denominator(grid, run.centers, run.kappas, counts, free)


def build(runs, grid, times=None, inits=None, f0=None):
    B_parts, counts, frees = [], [], []
    cols = {k: [] for k in ("s", "Q", "M", "deff", "lam1")}
    lds = []
    for k, r in enumerate(runs):
        t = np.arange(r.spw) if times is None else times[k]
        rows = r.rows_for_times(t)
        free, ld = solve_run(r, rows, grid, None if inits is None else inits[k])
        frees.append(free)
        lds.append(ld)
        for c in cols:
            cols[c].append(getattr(r, c)[rows])
        counts.append(len(rows))
    arr = {c: np.concatenate(v) for c, v in cols.items()}
    qshift = float(arr["Q"].mean())
    B = np.empty((len(runs), len(arr["s"])))
    for j, r in enumerate(runs):
        B[j] = np.interp(arr["s"], grid, lds[j]) - 0.5 * r.m2 * (arr["Q"] - qshift)
    f, denom = solve_global(B, np.asarray(counts, float), f0)
    return {**arr, "qshift": qshift, "denom": denom, "f": f, "frees": frees}


def peaks(p: np.ndarray) -> list[int]:
    sm = np.convolve(p, np.ones(5) / 5, mode="same")
    out = []
    for i in range(1, len(sm) - 1):
        if sm[i] > sm[i - 1] and sm[i] >= sm[i + 1] and sm[i] > 1e-4 * sm.max():
            out.append(i)
    if len(sm) > 1 and sm[0] > sm[1]:
        out.insert(0, 0)
    return out


def evaluate(st, V, m_grid, edges, keep=False):
    s, Q = st["s"], st["Q"]
    centers = 0.5 * (edges[1:] + edges[:-1])
    widths = np.diff(edges)
    idx = np.clip(np.searchsorted(edges, s, side="right") - 1, 0, len(widths) - 1)
    keys = ("s", "chi_s", "q", "cq", "M2", "deff", "ess", "Flo", "Fhi", "Fmin", "s_lo", "s_hi", "s_min")
    out = {k: np.full(len(m_grid), np.nan) for k in keys}
    hist = np.empty((len(m_grid), len(centers)))
    twopeak = np.zeros(len(m_grid), bool)
    for i, m in enumerate(m_grid):
        lw = -0.5 * m * (Q - st["qshift"]) - st["denom"]
        w = np.exp(lw - lw.max()); w /= w.sum()
        ms = float(w @ s); qm = float(w @ Q)
        out["s"][i] = ms
        out["chi_s"][i] = V * float(w @ (s - ms) ** 2)
        out["q"][i] = qm / V
        out["cq"][i] = float(w @ (Q - qm) ** 2) / V
        out["M2"][i] = float(w @ st["M"] ** 2)
        out["deff"][i] = float(w @ np.nan_to_num(st["deff"]))
        out["ess"][i] = 1.0 / float(w @ w)
        p = np.bincount(idx, weights=w, minlength=len(centers)) / widths
        hist[i] = p
        pk = peaks(p)
        if len(pk) >= 2:
            lo = pk[0]; hi = max(pk[1:], key=lambda j: p[j])
            mn = lo + int(np.argmin(p[lo:hi + 1]))
            if p[mn] < 0.9 * min(p[lo], p[hi]):
                F = -np.log(np.maximum(p, 1e-300))
                twopeak[i] = True
                out["Flo"][i], out["Fhi"][i], out["Fmin"][i] = F[lo], F[hi], F[mn]
                out["s_lo"][i], out["s_hi"][i], out["s_min"][i] = centers[lo], centers[hi], centers[mn]
    out["twopeak"] = twopeak
    out["m"] = m_grid
    out["hist"] = hist if keep else None
    out["centers"] = centers
    return out


def coexistence(ev):
    m, tp = ev["m"], ev["twopeak"]
    d = ev["Flo"] - ev["Fhi"]
    best = None
    for i in range(len(m) - 1):
        if tp[i] and tp[i + 1] and np.sign(d[i]) != np.sign(d[i + 1]):
            t = d[i] / (d[i] - d[i + 1])
            bar = lambda j: ev["Fmin"][j] - 0.5 * (ev["Flo"][j] + ev["Fhi"][j])
            cand = {"m_eq": float(m[i] + t * (m[i + 1] - m[i])),
                    "barrier": float((1 - t) * bar(i) + t * bar(i + 1)),
                    "s_lo": float(ev["s_lo"][i]), "s_hi": float(ev["s_hi"][i]),
                    "s_min": float((1 - t) * ev["s_min"][i] + t * ev["s_min"][i + 1])}
            if best is None or cand["barrier"] > best["barrier"]:
                best = cand
    return best


def latent(st, V, m, s_cut):
    lw = -0.5 * m * (st["Q"] - st["qshift"]) - st["denom"]
    w = np.exp(lw - lw.max())
    hi = st["s"] > s_cut
    if w[hi].sum() == 0 or w[~hi].sum() == 0:
        return float("nan"), float("nan")
    qd = (w[hi] @ st["Q"][hi] / w[hi].sum() - w[~hi] @ st["Q"][~hi] / w[~hi].sum()) / V
    deff_hi = float(w[hi] @ np.nan_to_num(st["deff"][hi]) / w[hi].sum())
    return float(qd), deff_hi


def summarize(st, V, ev, ess_min):
    good = ev["ess"] >= ess_min
    res = {"n_good": int(good.sum())}
    if not good.any():
        return res
    idx = np.where(good)[0]
    ic = idx[np.argmax(ev["chi_s"][idx])]
    res.update({"chi_s_max": float(ev["chi_s"][ic]), "m_chi_s_max": float(ev["m"][ic]),
                "chi_at_edge": bool(ic in (idx[0], idx[-1])),
                "n_twopeak": int(ev["twopeak"][idx].sum())})
    n = len(ev["m"])
    sub = {k: (v[idx] if isinstance(v, np.ndarray) and v.ndim == 1 and len(v) == n else v)
           for k, v in ev.items()}
    co = coexistence(sub)
    if co:
        co["latent_q"], co["deff_ordered"] = latent(st, V, co["m_eq"], co["s_min"])
        res["coexistence"] = co
    return res


def analyze(run_dir: Path, bootstrap: int, block: int, nbins: int, ngrid: int,
            ess_min: float, span: float, seed: int) -> Path:
    t0 = time.time()
    paths = sorted(p.parent / "statistics.csv" for p in run_dir.glob("*/complete.json"))
    runs = [CVRun(p) for p in paths]
    if not runs:
        raise SystemExit(f"no completed runs under {run_dir}")
    V = runs[0].V
    smax = max(float(r.s.max()) for r in runs)
    grid = np.linspace(min(0.0, min(float(r.s.min()) for r in runs)), smax * 1.0001, GRID)
    masses = sorted({r.m2 for r in runs})
    m_grid = np.linspace(masses[0] - span, masses[-1] + span, ngrid)
    edges = np.linspace(grid[0], grid[-1], nbins + 1)
    st = build(runs, grid)
    ev = evaluate(st, V, m_grid, edges, keep=True)
    summ = summarize(st, V, ev, ess_min)
    out_dir = ROOT / "reports" / "cv_umbrella" / run_dir.relative_to(ROOT / "runs" / "cv_umbrella")
    out_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out_dir / "hist.npz", m=m_grid, centers=ev["centers"], hist=ev["hist"],
                        twopeak=ev["twopeak"])
    result = {"dir": str(run_dir), "L": runs[0].L, "Z": runs[0].Z, "masses": masses,
              "cv": runs[0].meta.get("cv"), "runs": [str(p) for p in paths], "summary": summ}
    errs = {}
    if bootstrap:
        rng = np.random.default_rng(seed)
        draws = []
        for _ in range(bootstrap):
            times = []
            for r in runs:
                nb = math.ceil(r.spw / block)
                starts = rng.integers(0, max(1, r.spw - block + 1), size=nb)
                times.append(np.sort(np.concatenate([np.arange(a, a + block) for a in starts])[: r.spw]))
            sb = build(runs, grid, times, st["frees"], st["f"])
            eb = evaluate(sb, V, m_grid, edges)
            draws.append((summarize(sb, V, eb, ess_min), eb))
        for k in ("chi_s_max", "m_chi_s_max"):
            vals = [d[0].get(k) for d in draws if d[0].get(k) is not None]
            if len(vals) > 1:
                errs[k] = float(np.std(vals, ddof=1))
        cos = [d[0]["coexistence"] for d in draws if "coexistence" in d[0]]
        errs["coexistence_fraction"] = len(cos) / bootstrap
        for k in ("m_eq", "barrier", "latent_q"):
            vals = [c[k] for c in cos if np.isfinite(c.get(k, np.nan))]
            if len(vals) > 1:
                errs[k] = float(np.std(vals, ddof=1))
        for k in ("s", "chi_s", "q"):
            ev[f"{k}_err"] = np.std([d[1][k] for d in draws], axis=0, ddof=1)
    result["errors"] = errs
    with (out_dir / "curves.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        cols = ["s", "chi_s", "q", "cq", "M2", "deff", "ess"]
        errc = [c for c in ("s_err", "chi_s_err", "q_err") if c in ev]
        w.writerow(["m2", *cols, "twopeak", *errc])
        for i, m in enumerate(m_grid):
            w.writerow([f"{m:.8f}", *(f"{ev[c][i]:.8g}" for c in cols), int(ev["twopeak"][i]),
                        *(f"{ev[c][i]:.4g}" for c in errc)])
    result["elapsed_s"] = time.time() - t0
    out = out_dir / "analysis.json"
    out.write_text(json.dumps(result, indent=2))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", type=Path, required=True,
                    help="directory whose subdirectories are cv_umbrella runs of one (Z, L)")
    ap.add_argument("--bootstrap", type=int, default=40)
    ap.add_argument("--block", type=int, default=50)
    ap.add_argument("--bins", type=int, default=160)
    ap.add_argument("--grid", type=int, default=241)
    ap.add_argument("--ess-min", type=float, default=200.0)
    ap.add_argument("--span", type=float, default=0.15, help="m2 reweighting half-span")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args(argv)
    print(analyze(a.dir.resolve(), a.bootstrap, a.block, a.bins, a.grid, a.ess_min, a.span, a.seed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
