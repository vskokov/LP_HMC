#!/usr/bin/env python3
"""Order of the symmetric -> uniform transition from existing M^2-umbrella data.

For one (campaign, L) every completed umbrella statistics file (all source masses,
both ordered and disordered starts) is combined into a single canonical estimate
that is continuous in m^2:

1. per file, the umbrella windows are unbiased with occupied-bin WHAM
   (``analyze_umbrella.solve_binned_wham``), giving ldenom_j(M^2);
2. each file j is then a mixture state with log density
   b_j(x) = ldenom_j(M^2) - m_j Q/2  (T = 1), and the file free energies are
   solved by a Newton MBAR over files;
3. canonical weights at any m^2 are  exp(-m Q/2 - logsumexp_j[f_j + b_j(x)]).

Observables on a fine m^2 grid: U4, chi = V(<M^2>-<|M|>^2), <Q>/V, Var(Q)/V,
ESS, and the full distribution P(|M|).  The distribution is classified as
'disordered' (maximum only at M=0), 'ordered/critical' (interior maximum only),
or 'three-peak' (maxima at M=0 *and* at M0>0 -> symmetric/broken coexistence).
At the equal-height point of a three-peak distribution the barrier
DeltaF = F(min) - F(peaks) and the latent jump of Q/V are reported.  First-order
transitions give DeltaF ~ L^2, chi_max ~ L^3, U4_min ~ -L^3.

Errors: synchronized time-block bootstrap inside each file, re-solving both the
per-file WHAM and the global MBAR in every draw.

Subcommands
-----------
  cache FILE.csv          convert a statistics CSV to a compact .npz cache
  analyze --dir RUNDIR    analyze one campaign volume (RUNDIR = .../L20)
  submit                  enqueue cache + analyze tasks on scripts/cpu_pool.py
  summary                 aggregate all analyses into one CSV
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
from analyze_umbrella import sample_log_denominator, solve_binned_wham  # noqa: E402

CACHE_ROOT = ROOT / "runs" / "_analysis_cache"
OUT_ROOT = ROOT / "reports" / "transition_order"
CAMPAIGN_GLOBS = ("runs/umbrella_binder_Z*/L*", "runs/umbrella_binder_Zm*/L*",
                  "runs/umbrella_binder_termination/Z*/L*")
LDENOM_GRID = 16385


# ----------------------------------------------------------------------------- I/O
def read_metadata(path: Path) -> tuple[dict[str, str], int]:
    meta: dict[str, str] = {}
    n = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.startswith("#"):
                break
            k, _, v = line[1:].strip().partition("=")
            meta[k.strip()] = v.strip()
            n += 1
    return meta, n


def cache_path(csv_path: Path) -> Path:
    rel = csv_path.resolve().relative_to(ROOT / "runs")
    return CACHE_ROOT / rel.with_suffix(".npz")


def build_cache(csv_path: Path) -> Path:
    import pandas as pd

    meta, nmeta = read_metadata(csv_path)
    if meta.get("schema_version") != "3" or meta.get("sampler") != "umbrella_exchange":
        raise ValueError(f"{csv_path}: not a schema-3 umbrella file")
    if meta.get("umbrella_coordinate", "M2") != "M2":
        raise ValueError(f"{csv_path}: umbrella coordinate is not M2")
    df = pd.read_csv(csv_path, skiprows=nmeta, usecols=["trajectory", "slot", "M", "Q", "G"],
                     dtype={"trajectory": np.int64, "slot": np.int32, "M": np.float64,
                            "Q": np.float64, "G": np.float64}, engine="c")
    nrep = int(meta["umbrella_replicas"])
    spw = int(meta["samples_per_window"])
    counts = np.bincount(df["slot"].to_numpy(), minlength=nrep + 1)[1:]
    if len(df) != nrep * spw or np.any(counts != spw):
        raise ValueError(f"{csv_path}: expected {nrep}x{spw} rows, got {len(df)}")
    order = np.lexsort((df["slot"].to_numpy(), df["trajectory"].to_numpy()))
    out = cache_path(csv_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp.npz")
    np.savez(
        tmp,
        trajectory=df["trajectory"].to_numpy()[order].astype(np.int64),
        slot=df["slot"].to_numpy()[order].astype(np.int16),
        M=df["M"].to_numpy()[order].astype(np.float32),
        Q=df["Q"].to_numpy()[order].astype(np.float32),
        G=df["G"].to_numpy()[order].astype(np.float32),
        centers=np.array([float(x) for x in meta["umbrella_centers"].split(";")]),
        kappas=np.array([float(x) for x in meta["umbrella_kappas"].split(";")]),
        meta=json.dumps(meta),
        source=str(csv_path),
    )
    tmp.replace(out)
    return out


class FileData:
    """One umbrella statistics file, rows ordered time-major (trajectory, slot)."""

    def __init__(self, npz: Path):
        with np.load(npz, allow_pickle=False) as d:
            self.meta = json.loads(str(d["meta"]))
            self.slot = d["slot"].astype(np.int64)
            self.M = d["M"].astype(np.float64)
            self.Q = d["Q"].astype(np.float64)
            self.centers = d["centers"]
            self.kappas = d["kappas"]
        self.path = npz
        self.L = int(self.meta["L"])
        self.V = float(self.L) ** 3
        self.Z = float(self.meta["Z"])
        self.m2 = float(self.meta["m2"])
        self.phase = self.meta.get("init_phase", "unknown")
        self.nrep = int(self.meta["umbrella_replicas"])
        self.spw = int(self.meta["samples_per_window"])
        if len(self.centers) != self.nrep:
            raise ValueError(f"{npz}: centers/replica mismatch")

    def rows_for_times(self, times: np.ndarray) -> np.ndarray:
        """Row indices for the given sample-time indices (all windows)."""
        return (times[:, None] * self.nrep + np.arange(self.nrep)[None, :]).reshape(-1)


# ------------------------------------------------------------------ per-file WHAM
def solve_file(fd: FileData, rows: np.ndarray, m2_grid: np.ndarray,
               initial_free: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Return (window free energies, ldenom on m2_grid) for the chosen rows."""
    m2 = fd.M[rows] ** 2
    slots = fd.slot[rows]
    counts = np.bincount(slots, minlength=fd.nrep + 1)[1:].astype(float)
    if np.any(counts == 0):
        raise RuntimeError("empty umbrella window")
    last = None
    for bins in (256, 128, 64):
        try:
            free, _, _ = solve_binned_wham(m2, fd.centers, fd.kappas, counts, bins,
                                           initial_free=initial_free,
                                           sample_denominator=False)
            break
        except RuntimeError as err:  # pragma: no cover - fallback path
            last = err
            initial_free = None
    else:
        raise RuntimeError(f"{fd.path}: WHAM failed: {last}")
    ld = sample_log_denominator(m2_grid, fd.centers, fd.kappas, counts, free)
    return free, ld


# --------------------------------------------------------------------- global MBAR
def _logsumexp_rows(a: np.ndarray) -> np.ndarray:
    mx = np.max(a, axis=0)
    return mx + np.log(np.sum(np.exp(a - mx[None, :]), axis=0))


def _newton_terms(f: np.ndarray, B: np.ndarray, chunk: int = 200_000):
    """Chunked MBAR objective pieces: sum(denom), expected counts, R R^T, denom."""
    F, N = B.shape
    denom = np.empty(N)
    expected = np.zeros(F)
    RRt = np.zeros((F, F))
    for a in range(0, N, chunk):
        blk = f[:, None] + B[:, a:a + chunk]
        d = _logsumexp_rows(blk)
        denom[a:a + chunk] = d
        R = np.exp(blk - d[None, :])
        expected += R.sum(axis=1)
        RRt += R @ R.T
    return denom, expected, RRt


def _solve_global_dense(B, counts, f, tol, max_iter):
    F = B.shape[0]
    total = float(np.sum(counts))

    def obj_and_denom(fv):
        d = np.empty(B.shape[1])
        for a in range(0, B.shape[1], 200_000):
            d[a:a + 200_000] = _logsumexp_rows(fv[:, None] + B[:, a:a + 200_000])
        return (float(np.sum(d)) - float(np.dot(counts, fv))) / total, d

    obj, denom = obj_and_denom(f)
    for _ in range(max_iter):
        denom, expected, RRt = _newton_terms(f, B)
        grad = (expected - counts) / total
        if np.max(np.abs(grad[1:])) * total < tol * max(1.0, counts.min()):
            break
        H = (np.diag(expected) - RRt) / total
        try:
            step = np.linalg.solve(H[1:, 1:] + 1e-12 * np.eye(F - 1), -grad[1:])
        except np.linalg.LinAlgError:
            step = -grad[1:]
        slope = float(np.dot(grad[1:], step))
        if not np.isfinite(slope) or slope >= 0:
            step, slope = -grad[1:], -float(np.dot(grad[1:], grad[1:]))
        scale = 1.0
        while scale > 1e-10:
            cand = f.copy()
            cand[1:] += scale * step
            o2, d2 = obj_and_denom(cand)
            if o2 <= obj + 1e-4 * scale * slope:
                f, obj, denom = cand, o2, d2
                break
            scale *= 0.5
        else:
            break
    return f, denom


def solve_global(B: np.ndarray, counts: np.ndarray, f0: np.ndarray | None = None,
                 tol: float = 1e-7, max_iter: int = 200,
                 fit_max: int = 300_000) -> tuple[np.ndarray, np.ndarray]:
    """Newton MBAR over mixture states. B[j,x] = log unnormalised density of state j.

    Columns of B are grouped by file in the order of ``counts``.  For large N the
    free energies are first converged on a strided subsample (same stride in every
    file, so the count ratios are preserved), then refined by a few full-data Newton
    steps -- the fixed point is the full-data MBAR solution."""
    F = B.shape[0]
    if F == 1:
        return np.zeros(1), B[0].copy()
    f = np.zeros(F) if f0 is None else f0.copy()
    f -= f[0]
    N = B.shape[1]
    counts = np.asarray(counts, float)
    if N > 2 * fit_max:
        # Coarse-to-fine cascade: cheap cold start on a small subsample, then a larger
        # one, then a few Newton steps on the full data.
        edges = np.concatenate([[0], np.cumsum(counts.astype(int))])
        for target in (fit_max // 16, fit_max):
            if f0 is not None and target < fit_max:
                continue  # warm start: skip the coarsest level
            stride = int(math.ceil(N / target))
            idx = np.concatenate([np.arange(edges[j], edges[j + 1], stride) for j in range(F)])
            sub_counts = np.array([len(range(edges[j], edges[j + 1], stride)) for j in range(F)], float)
            f, _ = _solve_global_dense(B[:, idx], sub_counts, f, tol, max_iter)
        return _solve_global_dense(B, counts, f, tol, 8)
    return _solve_global_dense(B, counts, f, tol, max_iter)


# ------------------------------------------------------------------ observables
def _local_maxima(p: np.ndarray) -> list[int]:
    s = np.convolve(p, np.ones(3) / 3.0, mode="same")
    s[0] = (2 * p[0] + p[1]) / 3.0
    s[-1] = (p[-2] + 2 * p[-1]) / 3.0
    peaks = []
    for i in range(len(s)):
        left = s[i - 1] if i > 0 else -np.inf
        right = s[i + 1] if i + 1 < len(s) else -np.inf
        if s[i] > left and s[i] >= right and s[i] > 0:
            peaks.append(i)
    return peaks


def classify(p: np.ndarray, centers: np.ndarray) -> dict:
    """Classify P(|M|) on uniform |M| bins."""
    if not np.any(p > 0):
        return {"kind": "empty"}
    peaks = _local_maxima(p)
    pmax = p.max()
    # Discard noise peaks below 1e-3 of the global maximum.
    peaks = [i for i in peaks if p[i] > 1e-3 * pmax]
    zero_peak = peaks and peaks[0] <= 1
    interior = [i for i in peaks if i > 1]
    if zero_peak and interior:
        i0 = peaks[0]
        i1 = max(interior, key=lambda i: p[i])
        imin = i0 + int(np.argmin(p[i0:i1 + 1]))
        F = -np.log(np.maximum(p, 1e-300))
        return {"kind": "three-peak", "i0": i0, "i1": i1, "imin": imin,
                "M0": float(centers[i1]), "Mmin": float(centers[imin]),
                "F0": float(F[i0]), "F1": float(F[i1]), "Fmin": float(F[imin])}
    if zero_peak:
        return {"kind": "disordered"}
    i1 = max(interior, key=lambda i: p[i]) if interior else int(np.argmax(p))
    F = -np.log(np.maximum(p, 1e-300))
    return {"kind": "ordered", "i1": i1, "M0": float(centers[i1]),
            "dF_zero": float(F[0] - F[i1])}


class Ensemble:
    """Combined canonical ensemble for a set of files at one L."""

    def __init__(self, files: list[FileData], thin_target: int = 3_000_000,
                 seed: int = 1, time_index: list[np.ndarray] | None = None):
        self.files = files
        self.L = files[0].L
        self.V = files[0].V
        m2max = max(float(np.max(fd.M.astype(np.float64) ** 2)) for fd in files)
        self.m2_grid = np.linspace(0.0, m2max * 1.0001 + 1e-12, LDENOM_GRID)
        total_rows = sum(len(fd.M) for fd in files)
        self.thin = max(1, int(math.ceil(total_rows / thin_target)))
        self.rng = np.random.default_rng(seed)
        self.time_index = time_index
        self.free_init = [None] * len(files)
        self.f_init = None

    def build(self, times_per_file: list[np.ndarray] | None = None):
        Ms, Qs, Bcols, counts, frees = [], [], [], [], []
        lds = []
        for k, fd in enumerate(self.files):
            times = (np.arange(fd.spw) if times_per_file is None else times_per_file[k])
            rows_all = fd.rows_for_times(times)
            free, ld = solve_file(fd, rows_all, self.m2_grid, self.free_init[k])
            frees.append(free)
            lds.append(ld)
            thinned_times = times[:: self.thin]
            rows = fd.rows_for_times(thinned_times)
            Ms.append(fd.M[rows])
            Qs.append(fd.Q[rows])
            counts.append(len(rows))
        M = np.concatenate(Ms)
        Q = np.concatenate(Qs)
        m2 = M * M
        F = len(self.files)
        qshift = float(np.mean(Q))
        B = np.empty((F, len(M)))
        for j, fd in enumerate(self.files):
            B[j] = np.interp(m2, self.m2_grid, lds[j]) - 0.5 * fd.m2 * (Q - qshift)
        f, denom = solve_global(B, np.asarray(counts, float), self.f_init)
        return {"M": M, "Q": Q, "qshift": qshift, "denom": denom, "f": f,
                "wham_free": frees, "counts": counts}

    def evaluate(self, state: dict, m_grid: np.ndarray, nbins: int,
                 keep_hist: bool = False) -> dict:
        M, Q, qshift, denom = state["M"], state["Q"], state["qshift"], state["denom"]
        absM = np.abs(M)
        m2 = M * M
        m4 = m2 * m2
        edges = np.linspace(0.0, float(np.sqrt(self.m2_grid[-1])), nbins + 1)
        centers = 0.5 * (edges[1:] + edges[:-1])
        bin_index = np.clip(np.searchsorted(edges, absM, side="right") - 1, 0, nbins - 1)
        widths = np.diff(edges)
        out = {k: np.empty(len(m_grid)) for k in
               ("U4", "M2", "absM", "chi", "q", "cq", "ess",
                "F0", "F1", "Fmin", "M0", "Mmin")}
        hists = np.empty((len(m_grid), nbins))
        kinds = []
        cls_list = []
        from scipy import sparse
        N = len(M)
        ind = sparse.csr_matrix((np.ones(N), (np.arange(N), bin_index)), shape=(N, nbins))
        Qc = Q - qshift
        cols = np.stack([m2, m4, absM, Qc, Qc * Qc])           # (5, N)
        chunk = max(1, int(2.0e7 // max(N, 1)))
        for a in range(0, len(m_grid), chunk):
            mm = m_grid[a:a + chunk]
            lw = -0.5 * mm[:, None] * Qc[None, :] - denom[None, :]
            lw -= lw.max(axis=1, keepdims=True)
            W = np.exp(lw)
            W /= W.sum(axis=1, keepdims=True)
            mom = W @ cols.T                                    # (chunk, 5)
            ess = 1.0 / np.einsum("ij,ij->i", W, W)
            H = np.asarray((ind.T @ W.T).T) / widths[None, :]
            for r in range(len(mm)):
                i = a + r
                a2, a4, a1, qc, qc2 = mom[r]
                out["U4"][i] = 1.0 - a4 / (3.0 * a2 * a2)
                out["M2"][i] = a2
                out["absM"][i] = a1
                out["chi"][i] = self.V * (a2 - a1 * a1)
                out["q"][i] = (qc + qshift) / self.V
                out["cq"][i] = (qc2 - qc * qc) / self.V
                out["ess"][i] = ess[r]
                p = H[r]
                hists[i] = p
                c = classify(p, centers)
                cls_list.append(c)
                kinds.append(c["kind"])
                for key in ("F0", "F1", "Fmin", "M0", "Mmin"):
                    out[key][i] = c.get(key, np.nan)
        out["kind"] = np.array(kinds)
        out["hist"] = hists if keep_hist else None
        out["hist_centers"] = centers
        out["m"] = m_grid
        return out


def equal_height(ev: dict) -> dict | None:
    """Locate the equal-height point of a three-peak P(|M|) by linear interpolation."""
    m = ev["m"]
    tp = ev["kind"] == "three-peak"
    d = ev["F0"] - ev["F1"]   # >0: ordered peak higher (ordered favoured)
    best = None
    for i in range(len(m) - 1):
        if tp[i] and tp[i + 1] and np.sign(d[i]) != np.sign(d[i + 1]):
            t = d[i] / (d[i] - d[i + 1])
            mi = m[i] + t * (m[i + 1] - m[i])
            barrier = (1 - t) * (ev["Fmin"][i] - 0.5 * (ev["F0"][i] + ev["F1"][i])) + \
                t * (ev["Fmin"][i + 1] - 0.5 * (ev["F0"][i + 1] + ev["F1"][i + 1]))
            cand = {"m_eq": float(mi), "barrier": float(barrier),
                    "M0": float((1 - t) * ev["M0"][i] + t * ev["M0"][i + 1]),
                    "Mmin": float((1 - t) * ev["Mmin"][i] + t * ev["Mmin"][i + 1])}
            if best is None or cand["barrier"] > best["barrier"]:
                best = cand
    return best


def latent_jump(ens: Ensemble, state: dict, m: float, Mmin: float) -> float:
    """Difference of <Q>/V between the broken (|M|>Mmin) and symmetric basins at m."""
    M, Q = state["M"], state["Q"]
    lw = -0.5 * m * (Q - state["qshift"]) - state["denom"]
    w = np.exp(lw - lw.max())
    hi = np.abs(M) > Mmin
    if w[hi].sum() == 0 or w[~hi].sum() == 0:
        return float("nan")
    return float((w[hi] @ Q[hi] / w[hi].sum() - w[~hi] @ Q[~hi] / w[~hi].sum()) / ens.V)


def summarize(ens: Ensemble, state: dict, ev: dict, ess_min: float) -> dict:
    good = ev["ess"] >= ess_min
    res = {"n_grid_good": int(good.sum())}
    if not good.any():
        return res
    idx = np.where(good)[0]
    i_u = idx[np.argmin(ev["U4"][idx])]
    i_c = idx[np.argmax(ev["chi"][idx])]
    i_cq = idx[np.argmax(ev["cq"][idx])]
    res.update({
        "U4_min": float(ev["U4"][i_u]), "m_U4_min": float(ev["m"][i_u]),
        "chi_max": float(ev["chi"][i_c]), "m_chi_max": float(ev["m"][i_c]),
        "cq_max": float(ev["cq"][i_cq]), "m_cq_max": float(ev["m"][i_cq]),
        "kind_at_chi_max": str(ev["kind"][i_c]),
        "n_three_peak": int(np.sum(ev["kind"][idx] == "three-peak")),
        "ess_at_chi_max": float(ev["ess"][i_c]),
        "U4_min_at_edge": bool(i_u in (idx[0], idx[-1])),
        "chi_max_at_edge": bool(i_c in (idx[0], idx[-1])),
    })
    n = len(ev["m"])
    sub = {k: (v[idx] if isinstance(v, np.ndarray) and v.ndim == 1 and len(v) == n else v)
           for k, v in ev.items()}
    eq = equal_height(sub)
    if eq is not None:
        eq["latent_q"] = latent_jump(ens, state, eq["m_eq"], eq["Mmin"])
        res["equal_height"] = eq
    return res


# --------------------------------------------------------------------- analysis
def discover(run_dir: Path) -> list[Path]:
    stats = sorted((run_dir / "statistics").glob("*.csv"))
    complete = run_dir / "complete"
    return [p for p in stats if (complete / (p.stem + ".complete")).exists()]


def campaign_name(run_dir: Path) -> str:
    rel = run_dir.resolve().relative_to(ROOT / "runs")
    return "__".join(rel.parts[:-1])


def analyze_dir(run_dir: Path, bootstrap: int, block: int, nbins: int, ngrid: int,
                ess_min: float, seed: int, thin_target: int) -> Path:
    t0 = time.time()
    files = [FileData(cache_path(p)) for p in discover(run_dir)]
    if not files:
        raise SystemExit(f"{run_dir}: no completed statistics")
    L = files[0].L
    out_dir = OUT_ROOT / campaign_name(run_dir) / f"L{L}"
    out_dir.mkdir(parents=True, exist_ok=True)
    masses = sorted({fd.m2 for fd in files})
    spacing = np.min(np.diff(masses)) if len(masses) > 1 else 0.04
    pad = max(0.5 * spacing, 0.01)
    m_grid = np.linspace(masses[0] - pad, masses[-1] + pad, ngrid)
    groups = {"all": files,
              "disordered": [f for f in files if f.phase == "disordered"],
              "ordered": [f for f in files if f.phase == "ordered"]}
    result = {"run_dir": str(run_dir), "L": L, "Z": files[0].Z, "masses": masses,
              "files": [str(f.path) for f in files], "groups": {}}
    curves = {}
    for name, fl in groups.items():
        if not fl:
            continue
        ens = Ensemble(fl, thin_target=thin_target, seed=seed)
        st = ens.build()
        ev = ens.evaluate(st, m_grid, nbins, keep_hist=(name == "all"))
        summ = summarize(ens, st, ev, ess_min)
        summ["thin"] = ens.thin
        summ["n_files"] = len(fl)
        result["groups"][name] = summ
        curves[name] = ev
        if name == "all":
            ens_all, st_all = ens, st
            np.savez_compressed(out_dir / "hist_all.npz", m=m_grid, centers=ev["hist_centers"],
                                hist=ev["hist"], kind=ev["kind"])
            # Joint P(|M|, Q/V) at chi_max and (if present) the equal-height point.
            for tag, mm in (("chi_max", summ.get("m_chi_max")),
                            ("equal_height", summ.get("equal_height", {}).get("m_eq"))):
                if mm is None:
                    continue
                lw = -0.5 * mm * (st["Q"] - st["qshift"]) - st["denom"]
                w = np.exp(lw - lw.max())
                H, xe, ye = np.histogram2d(np.abs(st["M"]), st["Q"] / ens.V, bins=80, weights=w)
                np.savez_compressed(out_dir / f"joint_{tag}.npz", H=H / H.sum(), xedges=xe,
                                    yedges=ye, m=mm)
    # Bootstrap on the combined ensemble.
    boots = []
    if bootstrap > 0 and "all" in groups and groups["all"]:
        rng = np.random.default_rng(seed + 17)
        ens = ens_all
        ens.free_init = st_all["wham_free"]
        ens.f_init = st_all["f"]
        for b in range(bootstrap):
            times = []
            for fd in ens.files:
                nb = int(math.ceil(fd.spw / block))
                starts = rng.integers(0, max(1, fd.spw - block + 1), size=nb)
                t = np.concatenate([np.arange(s, s + block) for s in starts])[: fd.spw]
                times.append(np.sort(t))
            st_b = ens.build(times)
            ev_b = ens.evaluate(st_b, m_grid, nbins)
            sb = summarize(ens, st_b, ev_b, ess_min)
            boots.append({"summary": sb, "U4": ev_b["U4"].tolist(), "chi": ev_b["chi"].tolist(),
                          "cq": ev_b["cq"].tolist()})
        result["bootstrap"] = {"draws": bootstrap, "block": block}
        keys = ("U4_min", "m_U4_min", "chi_max", "m_chi_max", "cq_max", "m_cq_max")
        errs = {}
        for k in keys:
            vals = [bb["summary"].get(k) for bb in boots if bb["summary"].get(k) is not None]
            if len(vals) > 1:
                errs[k] = float(np.std(vals, ddof=1))
        eqs = [bb["summary"]["equal_height"] for bb in boots if "equal_height" in bb["summary"]]
        errs["equal_height_fraction"] = len(eqs) / bootstrap
        for k in ("m_eq", "barrier", "latent_q"):
            vals = [e[k] for e in eqs if np.isfinite(e.get(k, np.nan))]
            if len(vals) > 1:
                errs[f"eq_{k}"] = float(np.std(vals, ddof=1))
        result["errors"] = errs
        for k in ("U4", "chi", "cq"):
            arr = np.array([bb[k] for bb in boots])
            curves["all"][f"{k}_err"] = np.std(arr, axis=0, ddof=1)
    # Source agreement on the robust observables.
    agree = {}
    g = result["groups"]
    if "ordered" in g and "disordered" in g:
        for k in ("m_chi_max", "U4_min", "chi_max"):
            a, b = g["ordered"].get(k), g["disordered"].get(k)
            if a is not None and b is not None:
                agree[k] = float(a - b)
    result["source_difference"] = agree
    # Curves CSV.
    import csv
    with (out_dir / "curves.csv").open("w", newline="") as fh:
        wr = csv.writer(fh)
        cols = ["U4", "chi", "q", "cq", "ess", "M2", "absM", "kind"]
        header = ["group", "m2"] + cols + ["U4_err", "chi_err", "cq_err"]
        wr.writerow(header)
        for name, ev in curves.items():
            for i, m in enumerate(ev["m"]):
                row = [name, f"{m:.8f}"] + [ev[c][i] if c == "kind" else f"{ev[c][i]:.8g}"
                                            for c in cols]
                for e in ("U4_err", "chi_err", "cq_err"):
                    row.append(f"{ev[e][i]:.4g}" if e in ev else "")
                wr.writerow(row)
    result["elapsed_s"] = time.time() - t0
    out = out_dir / "analysis.json"
    out.write_text(json.dumps(result, indent=2, default=float))
    return out


# -------------------------------------------------------------------------- CLI
def all_run_dirs() -> list[Path]:
    dirs = set()
    for g in CAMPAIGN_GLOBS:
        for p in ROOT.glob(g):
            if p.is_dir() and re.match(r"L\d+$", p.name) and (p / "statistics").is_dir():
                if "junction" in str(p):
                    continue
                dirs.add(p.resolve())
    return sorted(dirs)


def cmd_submit(args) -> int:
    import cpu_pool
    py = sys.executable
    n_cache = n_an = 0
    for run_dir in all_run_dirs():
        stats = discover(run_dir)
        if not stats:
            continue
        deps = []
        for p in stats:
            name = "toc_cache__" + re.sub(r"[^A-Za-z0-9_.+-]", "_",
                                          str(cache_path(p).relative_to(CACHE_ROOT)))
            name = name[:160]
            size_gb = p.stat().st_size / 1e9
            cpu_pool.submit_task(name, [py, str(Path(__file__)), "cache", str(p)],
                                 done_marker=cache_path(p), mem_gb=max(1.0, 1.2 * size_gb),
                                 priority=20, group="toc_cache")
            deps.append(name)
            n_cache += 1
        L = int(run_dir.name[1:])
        out = OUT_ROOT / campaign_name(run_dir) / run_dir.name / "analysis.json"
        name = f"toc_analyze__{campaign_name(run_dir)}__{run_dir.name}"
        rows = sum(p.stat().st_size for p in stats) / 120.0
        mem = 1.5 + rows * 28 / 1e9 + 4 * len(stats) * min(rows, 3e6) * 8 / 1e9
        cmd = [py, str(Path(__file__)), "analyze", "--dir", str(run_dir),
               "--bootstrap", str(args.bootstrap)]
        cpu_pool.submit_task(name, cmd, done_marker=out, mem_gb=round(mem, 1),
                             priority=10 if L >= 20 else 5, group="toc_analyze", after=deps,
                             replace=args.replace)
        n_an += 1
    print(f"submitted cache={n_cache} analyze={n_an}")
    return 0


def cmd_summary(args) -> int:
    import csv
    rows = []
    for p in sorted(OUT_ROOT.glob("*/L*/analysis.json")):
        r = json.loads(p.read_text())
        g = r["groups"].get("all", {})
        e = r.get("errors", {})
        eq = g.get("equal_height", {})
        rows.append({
            "campaign": p.parent.parent.name, "Z": r["Z"], "L": r["L"],
            "n_files": g.get("n_files"),
            "m_chi_max": g.get("m_chi_max"), "m_chi_max_err": e.get("m_chi_max"),
            "chi_max": g.get("chi_max"), "chi_max_err": e.get("chi_max"),
            "U4_min": g.get("U4_min"), "U4_min_err": e.get("U4_min"),
            "m_U4_min": g.get("m_U4_min"),
            "cq_max": g.get("cq_max"), "cq_max_err": e.get("cq_max"),
            "kind_at_chi_max": g.get("kind_at_chi_max"),
            "n_three_peak": g.get("n_three_peak"),
            "m_eq": eq.get("m_eq"), "barrier": eq.get("barrier"),
            "barrier_err": e.get("eq_barrier"), "latent_q": eq.get("latent_q"),
            "eq_fraction": e.get("equal_height_fraction"),
            "dm_chi_ord_minus_dis": r.get("source_difference", {}).get("m_chi_max"),
            "dU4min_ord_minus_dis": r.get("source_difference", {}).get("U4_min"),
            "U4_min_at_edge": g.get("U4_min_at_edge"), "chi_max_at_edge": g.get("chi_max_at_edge"),
        })
    rows.sort(key=lambda r: (-r["Z"], r["L"]))
    out = OUT_ROOT / "summary.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    print(f"wrote {out} ({len(rows)} rows)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cache")
    c.add_argument("csv", type=Path)
    a = sub.add_parser("analyze")
    a.add_argument("--dir", type=Path, required=True)
    a.add_argument("--bootstrap", type=int, default=40)
    a.add_argument("--block", type=int, default=50, help="time-block length in samples")
    a.add_argument("--bins", type=int, default=120)
    a.add_argument("--grid", type=int, default=241)
    a.add_argument("--ess-min", type=float, default=300.0)
    a.add_argument("--seed", type=int, default=12345)
    a.add_argument("--thin-target", type=int, default=3_000_000)
    s = sub.add_parser("submit")
    s.add_argument("--bootstrap", type=int, default=40)
    s.add_argument("--replace", action="store_true")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    if args.cmd == "cache":
        print(build_cache(args.csv))
    elif args.cmd == "analyze":
        print(analyze_dir(args.dir, args.bootstrap, args.block, args.bins, args.grid,
                          args.ess_min, args.seed, args.thin_target))
    elif args.cmd == "submit":
        return cmd_submit(args)
    elif args.cmd == "summary":
        return cmd_summary(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
