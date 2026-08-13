#!/usr/bin/env python3
"""Create a local reweighting manifest and enqueue its tasks with task-spooler."""

from __future__ import annotations

import argparse
import csv
import math
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from submit_reweight_array import (
    build_rows,
    parse_point,
    read_points_csv,
    write_manifest,
)
from hmc_defaults import resolve_hmc_parameters, resolve_startup_hmc_parameters


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKER = REPO_ROOT / "scripts/run_reweight_task.py"


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.L < 2:
        parser.error("--L must be at least 2")
    if args.eps <= 0 or not math.isfinite(args.eps):
        parser.error("--eps must be finite and positive")
    if args.startup_eps <= 0 or not math.isfinite(args.startup_eps):
        parser.error("--startup-eps must be finite and positive")
    if (
        args.n_lf < 1 or args.samples < 1 or args.skip < 1
        or args.warmup < 0 or args.replicas < 1 or args.startup_n_lf < 1
        or args.startup_sweeps < 0
    ):
        parser.error(
            "n-lf, samples, skip, and replicas must be positive; warmup may be zero"
        )
    if args.tempering_replicas != 1 and (
        args.tempering_replicas < 3 or args.tempering_replicas % 2 == 0
    ):
        parser.error("--tempering-replicas must be 1 or an odd integer at least 3")
    if args.tempering_replicas > 1:
        if args.mass_span <= 0 or not math.isfinite(args.mass_span):
            parser.error("--mass-span must be finite and positive when tempering is enabled")
    elif args.mass_span != 0:
        parser.error("--mass-span must be zero when --tempering-replicas=1")
    if args.tempering_replicas == 1 and args.init_schedule != "hot":
        parser.error("--init-schedule requires replica exchange (--tempering-replicas > 1)")
    if args.swap_every < 1:
        parser.error("--swap-every must be positive")
    if args.init_schedule == "split" and args.replicas % 2 != 0:
        parser.error("--init-schedule=split requires an even --replicas count")
    if args.phase_threshold <= 0 or not math.isfinite(args.phase_threshold):
        parser.error("--phase-threshold must be finite and positive")
    if args.slots < 1:
        parser.error("--slots must be positive")


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def rows_as_text(rows: list[dict[str, object]]) -> list[dict[str, str]]:
    return [{key: str(value) for key, value in row.items()} for row in rows]


def task_command(
    manifest: Path, task_id: int, julia: str, *, resume: bool
) -> list[str]:
    command = [
        sys.executable,
        str(WORKER),
        "--manifest",
        str(manifest),
        "--task-id",
        str(task_id),
        "--julia",
        julia,
        "--launcher",
        "none",
    ]
    if resume:
        command.append("--resume")
    return command


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--L", type=int, required=True)
    parser.add_argument("--point", action="append", type=parse_point, default=[])
    parser.add_argument("--points-csv", type=Path, action="append", default=[])
    parser.add_argument(
        "--eps", type=float,
        help="HMC step size; omitted values use the measured default for L",
    )
    parser.add_argument(
        "--n-lf", type=int,
        help="leapfrog steps; omitted values use the measured default for L",
    )
    parser.add_argument("--startup-eps", type=float)
    parser.add_argument("--startup-n-lf", type=int)
    parser.add_argument("--startup-sweeps", type=int)
    parser.add_argument("--samples", type=int, default=1000)
    parser.add_argument("--skip", type=int, default=1)
    parser.add_argument("--warmup", type=int, default=0)
    parser.add_argument("--replicas", type=int, default=1)
    parser.add_argument("--tempering-replicas", type=int, default=1)
    parser.add_argument("--mass-span", type=float, default=0.0)
    parser.add_argument("--swap-every", type=int, default=1)
    parser.add_argument(
        "--init-schedule", choices=("hot", "disordered", "ordered", "split"),
        default="hot",
    )
    parser.add_argument("--phase-threshold", type=float, default=0.25)
    parser.add_argument(
        "--slots", type=int, default=1,
        help="maximum number of these local tasks that tsp may run concurrently",
    )
    parser.add_argument("--tsp", default="tsp", help="task-spooler executable")
    parser.add_argument("--julia", default="julia", help="Julia executable")
    parser.add_argument("--run-name")
    parser.add_argument("--run-root", type=Path, default=REPO_ROOT / "runs")
    parser.add_argument(
        "--resume", action="store_true",
        help="reuse an exactly matching manifest and ask each task to reuse valid output",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        args.eps, args.n_lf, used_hmc_default = resolve_hmc_parameters(
            args.L, args.eps, args.n_lf
        )
    except ValueError as exc:
        parser.error(str(exc))
    try:
        (args.startup_eps, args.startup_n_lf, args.startup_sweeps,
         used_startup_default) = resolve_startup_hmc_parameters(
            args.L, args.startup_eps, args.startup_n_lf, args.startup_sweeps
        )
    except ValueError as exc:
        parser.error(str(exc))
    validate_args(parser, args)

    points = list(args.point)
    try:
        for points_file in args.points_csv:
            points.extend(read_points_csv(points_file))
    except (OSError, ValueError, argparse.ArgumentTypeError) as exc:
        parser.error(str(exc))
    if not points:
        parser.error("provide at least one --point=Z,m2 or --points-csv")
    if len(set(points)) != len(points):
        parser.error("duplicate source points are not allowed; use --replicas instead")

    args.run_name = args.run_name or f"local_reweight_L{args.L}"
    if not all(character.isalnum() or character in "._-" for character in args.run_name):
        parser.error("--run-name may contain only letters, digits, dot, underscore, and hyphen")

    run_dir = (args.run_root / args.run_name).resolve()
    manifest = run_dir / "manifest.csv"
    rows = build_rows(args, points, run_dir)
    if manifest.exists():
        if not args.resume:
            parser.error(
                f"{manifest} already exists; choose a new --run-name or use --resume"
            )
        if read_manifest(manifest) != rows_as_text(rows):
            parser.error(
                f"{manifest} does not exactly match the requested parameters; "
                "choose a new --run-name"
            )
    elif not args.dry_run:
        for directory in (
            run_dir / "checkpoints", run_dir / "statistics",
            run_dir / "diagnostics", run_dir / "complete", run_dir / "logs",
        ):
            directory.mkdir(parents=True, exist_ok=True)
        write_manifest(manifest, rows)

    commands = [
        task_command(manifest, int(row["task_id"]), args.julia, resume=args.resume)
        for row in rows
    ]
    print(f"manifest: {manifest}")
    source = "measured L default" if used_hmc_default else "command line"
    print(f"HMC: eps={args.eps:.11g} n_lf={args.n_lf} ({source})")
    startup_source = "startup L default" if used_startup_default else "command line"
    print(f"startup HMC: eps={args.startup_eps:.11g} n_lf={args.startup_n_lf} "
          f"sweeps={args.startup_sweeps} ({startup_source})")
    print(f"tasks: {len(commands)} ({len(points)} points x {args.replicas} replicas)")
    print(f"tsp concurrency: {args.slots}")
    for command in commands:
        print("+", shlex.join([args.tsp, *command]))

    if args.dry_run:
        print("dry-run: no tsp settings were changed and no tasks were enqueued")
        return 0
    if shutil.which(args.tsp) is None:
        parser.error(f"task-spooler executable not found: {args.tsp}")

    subprocess.run([args.tsp, "-S", str(args.slots)], check=True)
    for command in commands:
        subprocess.run([args.tsp, *command], check=True)
    print(f"enqueued {len(commands)} tasks; inspect them with `{args.tsp}`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
