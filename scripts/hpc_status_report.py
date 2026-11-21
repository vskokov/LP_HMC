#!/usr/bin/env python3
"""Write docs/HPC_STATUS.md: campaign progress on the cluster, for the workstation to follow.

Reads only run directories under $LP_HMC_RUNS/cv_umbrella (manifest.csv, diagnostics.json,
complete.json, slurm/continuations) and squeue.  Stdlib only; cheap (runs on the login node).

    python3 scripts/hpc_status_report.py [--out docs/HPC_STATUS.md] [--journal-lines 60]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = Path(os.environ.get("LP_HMC_RUNS", ROOT / "runs"))
BASE = RUNS / "cv_umbrella"


def squeue() -> dict[str, tuple[str, str]]:
    try:
        out = subprocess.run(["squeue", "--me", "-h", "-o", "%j|%t|%b"], capture_output=True,
                             text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    q = {}
    for line in out.splitlines():
        name, state, gres = (line.split("|") + ["", ""])[:3]
        q[name] = (state, gres.replace("gres/gpu:", "").replace(":1", ""))
    return q


def label(r: dict) -> str:                    # must match scripts/cv_campaign.py label()
    def tag(x):
        s = f"{x:g}".replace("-", "m").replace(".", "p")
        return s
    return f"cvu_{r['stage']}_Z{tag(round(float(r['Z']), 4))}_L{r['L']}_m2{tag(float(r['m2']))}_s{r['seed']}"


def load(p: Path):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "HPC_STATUS.md")
    ap.add_argument("--journal-lines", type=int, default=60)
    a = ap.parse_args()
    q = squeue()
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"# Hazel campaign status", "",
             f"Generated {now} by `scripts/hpc_status_report.py` on the cluster (branch `hazel-ops`). "
             "Run data are not in git; copy completed stages with rsync (docs/HPC.md §4).", ""]
    stages = sorted(p.parent.name for p in BASE.glob("*/manifest.csv"))
    summary, detail = [], []
    running = {}
    for name, (state, gres) in q.items():
        if state == "R":
            running[gres] = running.get(gres, 0) + 1
    for st in stages:
        rows = list(csv.DictReader(open(BASE / st / "manifest.csv")))
        done = sum((Path(r["out"]) / "complete.json").is_file() for r in rows)
        act = sum(label(r) in q for r in rows)
        summary.append(f"| `{st}` | {done}/{len(rows)} | {act} | {len(rows) - done - act} |")
        detail.append(f"\n### `{st}` ({done}/{len(rows)} complete)\n")
        detail.append("| run | state | phase | sweeps | collected | HMC acc (mean / min window) | min swap | round-trip walkers | ε median | cont |")
        detail.append("|---|---|---|---|---|---|---|---|---|---|")
        for r in rows:
            out = Path(r["out"])
            d = load(out / "complete.json") or load(out / "diagnostics.json") or {}
            comp = (out / "complete.json").is_file()
            lab = label(r)
            state = "complete" if comp else (f"{q[lab][0]} {q[lab][1]}" if lab in q else "IDLE")
            cont = (out / "slurm" / "continuations")
            cont = cont.read_text().strip() if cont.is_file() else "0"
            if d:
                if comp or d.get("phase") == "collect":
                    acc = f"{d.get('hmc_acceptance_mean', float('nan')):.3f} / {d.get('hmc_acceptance_min', float('nan')):.3f}"
                else:
                    acc = (f"{d.get('hmc_recent_mean', d.get('hmc_acceptance_mean', float('nan'))):.3f} / "
                           f"{d.get('hmc_recent_min', d.get('hmc_acceptance_min', float('nan'))):.3f}")
                eps = d.get("eps_median")
                detail.append(f"| {out.relative_to(BASE / st)} | {state} | {d.get('phase', '')} | {d.get('sweeps', '')} | "
                              f"{d.get('collected', '')} | {acc} | {d.get('min_swap', float('nan')):.3f} | "
                              f"{d.get('round_trip_walkers', '')} | {eps:.4g} | {cont} |" if eps else
                              f"| {out.relative_to(BASE / st)} | {state} | {d.get('phase', '')} | {d.get('sweeps', '')} | "
                              f"{d.get('collected', '')} | {acc} | {d.get('min_swap', float('nan')):.3f} | "
                              f"{d.get('round_trip_walkers', '')} | | {cont} |")
            else:
                detail.append(f"| {out.relative_to(BASE / st)} | {state} | not started | | | | | | | {cont} |")
    notes = RUNS / "ops" / "status_notes.md"          # hand-maintained operator notes
    if notes.is_file():
        lines += ["## Operator notes", "", notes.read_text().strip(), ""]
    lines += ["## Summary", "", "| stage | complete | queued/running | idle |", "|---|---|---|---|", *summary, "",
              "Running GPUs: " + (", ".join(f"{k} {v}" for k, v in sorted(running.items())) or "none"), "",
              "During thermalization the HMC columns show the last check interval (ε adapts per window); "
              "for completed/collecting rows they show the whole collect phase. Round-trip walkers reset when collection starts.",
              "", "## Runs", *detail]
    journal = RUNS / "OPS_JOURNAL.md"
    if journal.is_file():
        tail = journal.read_text().splitlines()[-a.journal_lines:]
        lines += ["", f"## Operations journal (last {a.journal_lines} lines of `$LP_HMC_RUNS/OPS_JOURNAL.md`)", "", *tail]
    a.out.write_text("\n".join(lines) + "\n")
    print(a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
