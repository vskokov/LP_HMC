#!/usr/bin/env python3
"""Enqueue TSP Binder source collection at Z=-0.6 for a U(m²) production scan.

Uses measured HMC defaults (not umbrella n_lf). No mass tempering unless
--tempering-replicas is passed. Source masses come from
configs/reweight_sources_Zm0p6.csv (window [-1.95, -1.75] plus the canonical
point -1.86421).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SUBMITTER = REPO_ROOT / "scripts/submit_reweight_tsp.py"
DEFAULT_POINTS = REPO_ROOT / "configs/reweight_sources_Zm0p6.csv"
DEFAULT_JULIA = Path.home() / ".julia/juliaup/julia-1.12.6+0.x64.linux.gnu/bin/julia"
SUPPORTED = (6, 8, 12, 16, 18, 20, 24, 32)
SCAN_Z = -0.6
SCAN_M2_START = -1.95
SCAN_M2_END = -1.75


def samples_for(L: int) -> int:
    if L <= 12:
        return 2000
    if L <= 20:
        return 4000
    return 8000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("L", type=int, nargs="+", help="lattice sizes to enqueue")
    parser.add_argument("--points-csv", type=Path, default=DEFAULT_POINTS)
    parser.add_argument("--replicas", type=int, default=2)
    parser.add_argument("--skip", type=int, default=2)
    parser.add_argument("--samples", type=int, help="override per-L sample count")
    parser.add_argument("--run-root", type=Path, default=REPO_ROOT / "runs")
    parser.add_argument("--julia", default=str(DEFAULT_JULIA if DEFAULT_JULIA.is_file() else "julia"))
    parser.add_argument("--slots", type=int, default=1)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--tempering-replicas", type=int)
    parser.add_argument("--mass-span", type=float)
    parser.add_argument("--swap-every", type=int)
    parser.add_argument(
        "--init-schedule", choices=("hot", "disordered", "ordered", "split"),
    )
    args = parser.parse_args()
    if any(L not in SUPPORTED for L in args.L):
        parser.error(f"L must be in {SUPPORTED}")
    if args.replicas < 1 or args.skip < 1 or args.slots < 1:
        parser.error("replicas, skip, and slots must be positive")
    return args


def run_name(L: int, *, tempered: bool = False, tempering_replicas: int | None = None) -> str:
    if tempering_replicas is not None and tempering_replicas > 1:
        return f"binder_Zm06_temp{tempering_replicas}_L{L}"
    return f"binder_Zm06_temp_L{L}" if tempered else f"binder_Zm06_L{L}"


def main() -> int:
    args = parse_args()
    if not args.points_csv.is_file():
        raise SystemExit(f"missing points file: {args.points_csv}")
    for L in args.L:
        samples = args.samples if args.samples is not None else samples_for(L)
        tempered = args.tempering_replicas is not None and args.tempering_replicas > 1
        command = [
            sys.executable, str(SUBMITTER),
            f"--L={L}",
            f"--points-csv={args.points_csv}",
            f"--replicas={args.replicas}",
            f"--samples={samples}",
            f"--skip={args.skip}",
            f"--warmup={L ** 3}",
            f"--slots={args.slots}",
            f"--julia={args.julia}",
            f"--run-root={args.run_root}",
            f"--run-name={run_name(L, tempered=tempered, tempering_replicas=args.tempering_replicas)}",
        ]
        if args.tempering_replicas is not None:
            command.append(f"--tempering-replicas={args.tempering_replicas}")
        if args.mass_span is not None:
            command.append(f"--mass-span={args.mass_span}")
        if args.swap_every is not None:
            command.append(f"--swap-every={args.swap_every}")
        init_schedule = args.init_schedule
        if init_schedule is None and tempered:
            init_schedule = "split"
        if init_schedule is not None:
            command.append(f"--init-schedule={init_schedule}")
        if args.resume:
            command.append("--resume")
        if args.dry_run:
            command.append("--dry-run")
        print(
            f"=== collect Binder sources L={L} samples={samples} "
            f"warmup={L ** 3} tempered={tempered} "
            f"scan=Z={SCAN_Z:g} m2=[{SCAN_M2_START:g},{SCAN_M2_END:g}] ==="
        )
        subprocess.run(command, cwd=REPO_ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
