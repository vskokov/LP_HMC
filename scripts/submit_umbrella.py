#!/usr/bin/env python3
"""Create and submit TSP, Slurm, or LSF M²-umbrella exchange jobs."""

from __future__ import annotations

import argparse
import csv
import math
import re
import shlex
import subprocess
from pathlib import Path

from hmc_defaults import resolve_hmc_parameters, resolve_startup_hmc_parameters
from submit_reweight_array import parse_point, read_points_csv, write_manifest


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKER = REPO_ROOT / "scripts/run_umbrella_task.py"
LOCAL_JULIA = Path(
    "/home/vskokov/.julia/juliaup/julia-1.12.6+0.x64.linux.gnu/bin/julia"
)
UMBRELLA_PROFILES = {
    24: {
        "windows": 241, "minimum": 0.0, "maximum": 0.4,
        "kappa": 160_000.0, "power": 1.3,
        "startup_eps": 0.002, "startup_n_lf": 25, "startup_sweeps": 1024,
        "production_sweeps": 120_000, "max_production_sweeps": 600_000,
        "min_round_trip_fraction": 0.5,
        "min_swap_acceptance": 0.25,
    },
    32: {
        "windows": 369, "minimum": 0.0, "maximum": 0.4,
        "kappa": 380_000.0, "power": 1.3,
        "startup_eps": 0.0015, "startup_n_lf": 37, "startup_sweeps": 2048,
        "production_sweeps": 280_000, "max_production_sweeps": 1_400_000,
        "min_round_trip_fraction": 0.5,
        "min_swap_acceptance": 0.25,
    },
}


def parser_for(scheduler_default: str | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scheduler", choices=("tsp", "slurm", "lsf"),
                        default=scheduler_default, required=scheduler_default is None)
    parser.add_argument("--L", type=int, required=True)
    parser.add_argument("--point", action="append", type=parse_point, default=[])
    parser.add_argument("--points-csv", type=Path, action="append", default=[])
    parser.add_argument("--eps", type=float)
    parser.add_argument("--n-lf", type=int)
    parser.add_argument("--startup-eps", type=float)
    parser.add_argument("--startup-n-lf", type=int)
    parser.add_argument("--startup-sweeps", type=int)
    parser.add_argument("--thermalization-sweeps", type=int)
    parser.add_argument("--max-thermalization-sweeps", type=int)
    parser.add_argument("--min-round-trip-fraction", type=float)
    parser.add_argument("--min-swap-acceptance", type=float)
    parser.add_argument("--samples", type=int, default=2000)
    parser.add_argument("--skip", type=int, default=2)
    parser.add_argument("--warmup", type=int, default=0)
    parser.add_argument("--replicas", type=int, default=1,
                        help="independent jobs per physical point")
    parser.add_argument("--umbrella-windows", type=int)
    parser.add_argument("--umbrella-min", type=float)
    parser.add_argument("--umbrella-max", type=float)
    parser.add_argument("--umbrella-kappa", type=float)
    parser.add_argument("--umbrella-power", type=float)
    parser.add_argument("--swap-every", type=int, default=1)
    parser.add_argument("--init-schedule",
                        choices=("umbrella", "hot", "disordered", "ordered", "split"),
                        default="umbrella")
    parser.add_argument("--run-name")
    parser.add_argument("--run-root", type=Path, default=REPO_ROOT / "runs")
    parser.add_argument("--julia")
    parser.add_argument("--python", default="python3")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--tsp", default="tsp")
    parser.add_argument("--partition", default="gpu")
    parser.add_argument("--account")
    parser.add_argument("--time", default="04:00:00")
    parser.add_argument("--mem", default="24G")
    parser.add_argument("--cpus", type=int, default=1)
    parser.add_argument("--gpu-resource", default="gpu:1")
    parser.add_argument("--sbatch", default="sbatch")
    parser.add_argument("--queue", default="short_gpu")
    parser.add_argument("--walltime", default="240")
    parser.add_argument("--gpu-request", default="num=1:mode=shared:mps=no")
    parser.add_argument("--bsub", default="bsub")
    return parser


def validate(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    finite_positive = (args.eps, args.startup_eps, args.umbrella_kappa)
    if args.L < 2 or args.n_lf < 1 or args.startup_n_lf < 1:
        parser.error("L must be >=2 and leapfrog counts positive")
    if any(not math.isfinite(value) or value <= 0 for value in finite_positive):
        parser.error("epsilon and umbrella kappa values must be finite and positive")
    if args.startup_sweeps < 0 or args.samples < 1 or args.skip < 1 or args.warmup < 0:
        parser.error("invalid sweep/sample counts")
    if args.thermalization_sweeps < 1:
        parser.error("--thermalization-sweeps must be positive")
    if args.max_thermalization_sweeps < args.thermalization_sweeps:
        parser.error("--max-thermalization-sweeps must be at least the minimum")
    if not 0.0 <= args.min_round_trip_fraction <= 1.0:
        parser.error("--min-round-trip-fraction must be between 0 and 1")
    if not 0.0 <= args.min_swap_acceptance <= 1.0:
        parser.error("--min-swap-acceptance must be between 0 and 1")
    if args.replicas < 1 or args.umbrella_windows < 2 or args.swap_every < 1:
        parser.error("replicas/swap cadence invalid")
    if not (math.isfinite(args.umbrella_min) and args.umbrella_min >= 0 and
            math.isfinite(args.umbrella_max) and args.umbrella_max > args.umbrella_min):
        parser.error("umbrella bounds must be finite, non-negative, and increasing")
    if not math.isfinite(args.umbrella_power) or args.umbrella_power <= 0:
        parser.error("--umbrella-power must be finite and positive")
    if args.init_schedule == "split" and args.replicas % 2:
        parser.error("--init-schedule=split requires an even --replicas count")
    if args.cpus < 1:
        parser.error("--cpus must be positive")


def build_rows(args: argparse.Namespace, points: list[tuple[float, float]], run_dir: Path):
    rows = []
    task = 0
    for point_index, (z_text, mass_text) in enumerate(points):
        z_value, mass = float(z_text), float(mass_text)
        for replica in range(args.replicas):
            phase = args.init_schedule
            if phase == "split":
                phase = "disordered" if replica < args.replicas // 2 else "ordered"
            seed = 1_000_003 + args.L * 10_007 + point_index * 1_009 + replica * 97
            base = f"L{args.L}_Z{z_value:g}_m2{mass:g}_r{replica}_{phase}"
            rows.append({
                "task_id": task, "L": args.L, "Z": f"{z_value:.17g}",
                "m2": f"{mass:.17g}", "replica": replica, "seed": seed,
                "eps": f"{args.eps:.17g}", "n_lf": args.n_lf,
                "startup_eps": f"{args.startup_eps:.17g}",
                "startup_n_lf": args.startup_n_lf,
                "startup_sweeps": args.startup_sweeps,
                "production_sweeps": args.thermalization_sweeps,
                "max_production_sweeps": args.max_thermalization_sweeps,
                "min_round_trip_fraction": f"{args.min_round_trip_fraction:.17g}",
                "min_swap_acceptance": f"{args.min_swap_acceptance:.17g}",
                "samples": args.samples, "skip": args.skip, "warmup": args.warmup,
                "umbrella_replicas": args.umbrella_windows,
                "umbrella_min": f"{args.umbrella_min:.17g}",
                "umbrella_max": f"{args.umbrella_max:.17g}",
                "umbrella_kappa": f"{args.umbrella_kappa:.17g}",
                "umbrella_power": f"{args.umbrella_power:.17g}",
                "swap_every": args.swap_every, "init_phase": phase,
                "checkpoint_path": str((run_dir / "checkpoints" / f"{base}.jld2").resolve()),
                "stats_path": str((run_dir / "statistics" / f"{base}.csv").resolve()),
                "diagnostics_path": str((run_dir / "diagnostics" / f"{base}.csv").resolve()),
                "completion_marker": str((run_dir / "complete" / f"{base}.complete").resolve()),
            })
            task += 1
    return rows


def worker_command(args, manifest: Path, task_token: str) -> str:
    values = [args.python, str(WORKER), "--manifest", str(manifest.resolve()),
              "--task-id", task_token, "--julia", args.julia]
    if args.resume:
        values.append("--resume")
    return " ".join(task_token if value == task_token else shlex.quote(value) for value in values)


def slurm_script(args, manifest: Path, count: int, logs: Path) -> str:
    lines = ["#!/usr/bin/env bash", f"#SBATCH --job-name={args.run_name}",
             f"#SBATCH --array=0-{count - 1}", f"#SBATCH --partition={args.partition}",
             f"#SBATCH --time={args.time}", f"#SBATCH --mem={args.mem}",
             f"#SBATCH --cpus-per-task={args.cpus}", f"#SBATCH --gres={args.gpu_resource}",
             f"#SBATCH --output={logs.resolve()}/%x_%A_%a.out",
             f"#SBATCH --error={logs.resolve()}/%x_%A_%a.err"]
    if args.account:
        lines.append(f"#SBATCH --account={args.account}")
    lines.extend(["", "set -euo pipefail", worker_command(args, manifest,
                                                           '"${SLURM_ARRAY_TASK_ID}"'), ""])
    return "\n".join(lines)


def lsf_script(args, manifest: Path, count: int, logs: Path) -> str:
    lines = ["#!/usr/bin/env bash", f'#BSUB -J "{args.run_name}[1-{count}]"',
             f"#BSUB -q {args.queue}", f"#BSUB -W {args.walltime}",
             f"#BSUB -n {args.cpus}", f'#BSUB -R "rusage[mem=24000]"',
             f'#BSUB -gpu "{args.gpu_request}"',
             f"#BSUB -o {logs.resolve()}/%J_%I.out",
             f"#BSUB -e {logs.resolve()}/%J_%I.err", "", "set -euo pipefail",
             'TASK_ID="$((LSB_JOBINDEX - 1))"',
             worker_command(args, manifest, '"${TASK_ID}"'), ""]
    return "\n".join(lines)


def main(scheduler_default: str | None = None) -> int:
    parser = parser_for(scheduler_default)
    args = parser.parse_args()
    if args.julia is None:
        args.julia = str(LOCAL_JULIA) if args.scheduler == "tsp" and LOCAL_JULIA.is_file() else "julia"
    profile = UMBRELLA_PROFILES.get(args.L, {
        "windows": 25, "minimum": 0.0, "maximum": 0.45,
        "kappa": 2500.0, "power": 1.0,
    })
    args.umbrella_windows = (profile["windows"] if args.umbrella_windows is None
                             else args.umbrella_windows)
    args.umbrella_min = profile["minimum"] if args.umbrella_min is None else args.umbrella_min
    args.umbrella_max = profile["maximum"] if args.umbrella_max is None else args.umbrella_max
    args.umbrella_kappa = profile["kappa"] if args.umbrella_kappa is None else args.umbrella_kappa
    args.umbrella_power = profile["power"] if args.umbrella_power is None else args.umbrella_power
    if args.thermalization_sweeps is None:
        args.thermalization_sweeps = profile.get(
            "production_sweeps", max(args.L**3, 2 * args.umbrella_windows**2)
        )
    if args.max_thermalization_sweeps is None:
        args.max_thermalization_sweeps = max(
            args.thermalization_sweeps,
            profile.get("max_production_sweeps", 5 * args.thermalization_sweeps),
        )
    if args.min_round_trip_fraction is None:
        args.min_round_trip_fraction = profile.get("min_round_trip_fraction", 0.5)
    if args.min_swap_acceptance is None:
        args.min_swap_acceptance = profile.get("min_swap_acceptance", 0.25)
    try:
        args.eps, args.n_lf, _ = resolve_hmc_parameters(args.L, args.eps, args.n_lf)
        if (args.startup_eps is None and args.startup_n_lf is None and
                args.startup_sweeps is None and "startup_eps" in profile):
            args.startup_eps = profile["startup_eps"]
            args.startup_n_lf = profile["startup_n_lf"]
            args.startup_sweeps = profile["startup_sweeps"]
        else:
            args.startup_eps, args.startup_n_lf, args.startup_sweeps, _ = \
                resolve_startup_hmc_parameters(args.L, args.startup_eps,
                                               args.startup_n_lf, args.startup_sweeps)
    except ValueError as error:
        parser.error(str(error))
    validate(parser, args)
    points = list(args.point)
    for path in args.points_csv:
        points.extend(read_points_csv(path))
    if not points or len(set(points)) != len(points):
        parser.error("provide unique --point=Z,m2 values")
    args.run_name = args.run_name or f"umbrella_L{args.L}"
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.run_name):
        parser.error("unsafe run name")
    run_dir = (args.run_root / args.run_name).resolve()
    for name in ("checkpoints", "statistics", "diagnostics", "complete", "logs"):
        (run_dir / name).mkdir(parents=True, exist_ok=True)
    manifest = run_dir / "manifest.csv"
    rows = build_rows(args, points, run_dir)
    write_manifest(manifest, rows)
    print(f"manifest: {manifest}")
    print(f"HMC: eps={args.eps:.11g} n_lf={args.n_lf}")
    print(f"umbrella: windows={args.umbrella_windows} range=[{args.umbrella_min:g},"
          f"{args.umbrella_max:g}] kappa={args.umbrella_kappa:g} "
          f"power={args.umbrella_power:g}")
    print(f"thermalization: startup={args.startup_sweeps} "
          f"minimum={args.thermalization_sweeps} maximum="
          f"{args.max_thermalization_sweeps} sweeps "
          f"round_trip_fraction={args.min_round_trip_fraction:g} "
          f"min_swap_acceptance={args.min_swap_acceptance:g}")

    if args.scheduler == "tsp":
        commands = [worker_command(args, manifest, str(index)) for index in range(len(rows))]
        for command in commands:
            print(command)
            if not args.dry_run:
                subprocess.run([args.tsp, "bash", "-lc", command], check=True)
        return 0
    script = (slurm_script(args, manifest, len(rows), run_dir / "logs")
              if args.scheduler == "slurm" else
              lsf_script(args, manifest, len(rows), run_dir / "logs"))
    script_path = run_dir / ("array_job.sh" if args.scheduler == "slurm" else "lsf_job.sh")
    script_path.write_text(script, encoding="utf-8")
    print(script)
    if not args.dry_run:
        if args.scheduler == "slurm":
            subprocess.run([args.sbatch, str(script_path)], check=True)
        else:
            subprocess.run([args.bsub], input=script, text=True, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
