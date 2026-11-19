#!/usr/bin/env python3
"""Convert completed M^2-CV runs of scripts/cv_umbrella.jl into the schema-3 umbrella
layout read by scripts/analyze_transition_order.py.

  runs/cv_umbrella/uline/Z<z>/L<L>/m2<m>_s<seed>_<init>/statistics.csv
    -> runs/uline/Z<z>/L<L>/statistics/<run>.csv   (+ complete/<run>.complete)

The campaign name seen by the analysis is then ``uline__Z<z>``.  Only completed
runs (complete.json) with cv=M2 are converted; existing outputs are skipped unless
the source is newer.

Usage: python3 scripts/cv_to_schema3.py [--src runs/cv_umbrella/uline] [--dst runs/uline]
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RUNS = Path(os.environ.get("LP_HMC_RUNS", ROOT / "runs"))


def read_header(path: Path) -> tuple[dict[str, str], int]:
    meta, n = {}, 0
    with path.open() as fh:
        for line in fh:
            if not line.startswith("#"):
                break
            k, _, v = line[1:].strip().partition("=")
            meta[k.strip()] = v.strip()
            n += 1
    return meta, n


def convert(run: Path, dst_root: Path) -> Path | None:
    src = run / "statistics.csv"
    if not (run / "complete.json").is_file() or not src.is_file():
        return None
    meta, n = read_header(src)
    if meta.get("cv") != "M2":
        raise ValueError(f"{src}: cv={meta.get('cv')} is not M2")
    init = run.name.rsplit("_", 1)[-1]
    if init not in ("ordered", "disordered"):
        init = "umbrella"
    L = int(meta["L"])
    out_dir = dst_root / run.parent.parent.name / f"L{L}"
    out = out_dir / "statistics" / f"{run.name}.csv"
    done = out_dir / "complete" / f"{run.name}.complete"
    if done.is_file() and out.is_file() and out.stat().st_mtime >= src.stat().st_mtime:
        return out
    df = pd.read_csv(src, skiprows=n)
    nw, spw = int(meta["windows"]), int(meta["samples_per_window"])
    if len(df) != nw * spw:
        raise ValueError(f"{src}: expected {nw}x{spw} rows, got {len(df)}")
    M = df["M"].to_numpy()
    body = pd.DataFrame({"trajectory": df["sample"], "slot": df["slot"],
                         "walker_id": df["walker_id"], "umbrella_center": df["center"],
                         "umbrella_kappa": df["kappa"], "M": M, "M2": M * M, "M4": M ** 4,
                         "Q": df["Q"], "G": df["G"], "acceptance_rate": np.nan})
    header = {"schema_version": "3", "sampler": "umbrella_exchange", "L": L, "Z": meta["Z"],
              "m2": meta["m2"], "epsilon": meta["epsilon"], "n_lf": meta["n_lf"],
              "seed": meta["seed"], "samples_per_window": spw, "skip": meta["skip"],
              "lambda": meta["lambda"], "temperature": meta["temperature"],
              "float_type": meta["float_type"], "device": meta["device"],
              "umbrella_replicas": nw, "umbrella_coordinate": "M2",
              "umbrella_centers": meta["centers"], "umbrella_kappas": meta["kappas"],
              "init_phase": init, "converted_from": str(src)}
    out.parent.mkdir(parents=True, exist_ok=True)
    done.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    with tmp.open("w") as fh:
        for k, v in header.items():
            fh.write(f"# {k}={v}\n")
        body.to_csv(fh, index=False)
    tmp.replace(out)
    done.write_text("converted\n")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=RUNS / "cv_umbrella" / "uline")
    ap.add_argument("--dst", type=Path, default=RUNS / "uline")
    args = ap.parse_args()
    n = 0
    for run in sorted(p.parent for p in args.src.glob("*/L*/*/statistics.csv")):
        out = convert(run, args.dst)
        if out is not None:
            print(out); n += 1
    print(f"{n} runs converted/up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
