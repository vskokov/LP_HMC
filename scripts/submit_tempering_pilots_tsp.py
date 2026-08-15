#!/usr/bin/env python3
"""Materialize and optionally enqueue the critical-ladder pilot grid with TSP."""

from __future__ import annotations

import argparse
import csv
import itertools
import math
import shlex
import shutil
import subprocess
from pathlib import Path

from hmc_defaults import resolve_startup_hmc_parameters
from runtime_preflight import run as run_preflight
from submit_reweight_array import REPO_ROOT, parse_point


BENCHMARK = REPO_ROOT / "scripts/benchmark_hmc_startup.jl"


def comma_values(text: str, value_type):
    try:
        values = [value_type(value.strip()) for value in text.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid comma-separated list: {text}") from exc
    if not values:
        raise argparse.ArgumentTypeError("candidate list cannot be empty")
    return values


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--L", type=int, choices=(24, 32), required=True)
    parser.add_argument("--point", action="append", type=parse_point, required=True)
    parser.add_argument("--replica-counts", default="17,25,33,49,65")
    parser.add_argument("--mass-spans", default="0.2,0.3,0.4,0.6")
    parser.add_argument("--swap-every-values", default="1,2")
    parser.add_argument("--eps", type=float, help="fixed cold-start epsilon")
    parser.add_argument("--n-lf", type=int, help="fixed cold-start leapfrog count")
    parser.add_argument("--sweeps", type=int, default=4096)
    parser.add_argument("--block-size", type=int, default=512)
    parser.add_argument("--slots", type=int, default=1)
    parser.add_argument("--run-name")
    parser.add_argument("--run-root", type=Path, default=REPO_ROOT / "runs")
    parser.add_argument("--julia", default="julia")
    parser.add_argument("--tsp", default="tsp")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    counts = comma_values(args.replica_counts, int)
    spans = comma_values(args.mass_spans, float)
    cadences = comma_values(args.swap_every_values, int)
    if any(count < 3 or count % 2 == 0 for count in counts):
        parser.error("all replica counts must be odd integers at least 3")
    if any(span <= 0 or not math.isfinite(span) for span in spans):
        parser.error("all mass spans must be finite and positive")
    if any(cadence < 1 for cadence in cadences):
        parser.error("all swap cadences must be positive")
    if args.sweeps < 1 or args.block_size < 1 or args.slots < 1:
        parser.error("sweeps, block size, and slots must be positive")
    try:
        epsilon, leapfrog, _, _ = resolve_startup_hmc_parameters(
            args.L, args.eps, args.n_lf, args.sweeps
        )
    except ValueError as exc:
        parser.error(str(exc))

    args.run_name = args.run_name or f"tempering_pilots_L{args.L}"
    if not all(character.isalnum() or character in "._-" for character in args.run_name):
        parser.error("--run-name contains unsafe characters")
    run_dir = (args.run_root / args.run_name).resolve()
    manifest = run_dir / "pilot_manifest.csv"
    if manifest.exists():
        parser.error(f"{manifest} already exists; choose a new --run-name")

    rows: list[dict[str, object]] = []
    commands: list[list[str]] = []
    for task_id, ((z_value, mass), count, span, cadence) in enumerate(
        itertools.product(args.point, counts, spans, cadences)
    ):
        output = run_dir / "pilots" / f"task_{task_id:04d}.csv"
        row = {
            "task_id": task_id, "L": args.L, "Z": z_value, "m2": mass,
            "epsilon": epsilon, "n_lf": leapfrog, "tempering_replicas": count,
            "mass_span": span, "swap_every": cadence, "sweeps": args.sweeps,
            "block_size": args.block_size, "output": output,
        }
        rows.append(row)
        commands.append([
            args.julia, f"--project={REPO_ROOT}", str(BENCHMARK), str(args.L),
            f"--Z={z_value}", f"--mass={mass}", f"--eps-values={epsilon}",
            f"--fixed-n-lf={leapfrog}", f"--sweeps={args.sweeps}",
            f"--block-size={args.block_size}", f"--tempering-replicas={count}",
            f"--mass-span={span}", f"--swap-every={cadence}", f"--output={output}",
        ])

    print(f"manifest: {manifest}\ntasks: {len(rows)}\ntsp concurrency: {args.slots}")
    for command in commands:
        print("+", shlex.join([args.tsp, *command]))
    if args.dry_run:
        print("dry-run: no files were written and no tasks were enqueued")
        return 0
    if shutil.which(args.tsp) is None:
        parser.error(f"task-spooler executable not found: {args.tsp}")
    try:
        run_preflight(args.julia, REPO_ROOT)
    except RuntimeError as exc:
        parser.error(str(exc))
    (run_dir / "pilots").mkdir(parents=True)
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    subprocess.run([args.tsp, "-S", str(args.slots)], check=True)
    for command in commands:
        subprocess.run([args.tsp, *command], cwd=REPO_ROOT, check=True)
    print(f"enqueued {len(commands)} pilot tasks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
