#!/usr/bin/env python3
"""Create and submit TSP or LSF M²-umbrella exchange jobs."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import shlex
import subprocess
from pathlib import Path

from hmc_defaults import resolve_hmc_parameters, resolve_startup_hmc_parameters
from lsf_defaults import (
    DEFAULT_CUDA_MODULE,
    DEFAULT_JULIA_DEPOT_PATH,
    DEFAULT_JULIA_MODULE,
    DEFAULT_MODULE_INIT,
    lsf_environment_shell_lines,
    lsf_runtime_home,
    resolved_exclude_hosts,
    submit_bsub_script,
)
from reweight_manifest import parse_point, read_points_csv, write_manifest
from runtime_preflight import lsf_julia_launch_lines
from umbrella_profiles import load_profile


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
    parser.add_argument("--scheduler", choices=("tsp", "lsf"),
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
    parser.add_argument("--min-samples", type=int)
    parser.add_argument("--max-samples", type=int)
    parser.add_argument("--sample-increment", type=int, default=5000)
    parser.add_argument("--binder-mcse-target", type=float, default=0.005)
    parser.add_argument("--collection-shard-samples", type=int, default=500)
    parser.add_argument("--runtime-budget-minutes", type=float, default=95.0)
    parser.add_argument("--self-resubmit", action="store_true")
    parser.add_argument("--max-continuations", type=int, default=20)
    parser.add_argument("--profile-file", type=Path)
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
    parser.add_argument("--prepare-only", action="store_true",
                        help="write manifest and exit without submitting jobs")
    parser.add_argument("--tsp", default="tsp")
    parser.add_argument("--queue", default="short_gpu")
    parser.add_argument("--cpus", type=int, default=1)
    parser.add_argument("--walltime", default="120")
    parser.add_argument("--mem-gb", type=float, default=24.0,
                        help="LSF memory requested per host, in GB")
    parser.add_argument("--gpu-select", default="h200 || h100 || l40s",
                        help="LSF select expression for eligible GPU families")
    parser.add_argument("--exclude-host", action="append", default=None,
                        help="LSF host to exclude; repeat to replace the default gpu31 list")
    parser.add_argument("--gpu-request", default="num=1:mode=shared:mps=no")
    parser.add_argument("--bsub", default="bsub")
    cluster = parser.add_argument_group("cluster environment (LSF)")
    cluster.add_argument("--module-init", default=DEFAULT_MODULE_INIT)
    cluster.add_argument("--cuda-module", default=DEFAULT_CUDA_MODULE)
    cluster.add_argument("--julia-module", default=DEFAULT_JULIA_MODULE)
    cluster.add_argument("--julia-depot", default=DEFAULT_JULIA_DEPOT_PATH)
    cluster.add_argument("--module", action="append", default=[],
                         help="extra environment modules to load after Julia/CUDA")
    return parser


def validate(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    finite_positive = (args.eps, args.startup_eps, args.umbrella_kappa)
    if args.L < 2 or args.n_lf < 1 or args.startup_n_lf < 1:
        parser.error("L must be >=2 and leapfrog counts positive")
    if any(not math.isfinite(value) or value <= 0 for value in finite_positive):
        parser.error("epsilon and umbrella kappa values must be finite and positive")
    if args.startup_sweeps < 0 or args.samples < 1 or args.skip < 1 or args.warmup < 0:
        parser.error("invalid sweep/sample counts")
    if (args.min_samples < 1 or args.max_samples < args.min_samples or
            args.sample_increment < 1 or args.collection_shard_samples < 1):
        parser.error("invalid adaptive collection sample counts")
    if (args.adaptive_collection and
            (args.min_samples % args.collection_shard_samples or args.max_samples % args.collection_shard_samples)):
        parser.error("minimum and maximum samples must be multiples of shard samples")
    if not (math.isfinite(args.binder_mcse_target) and args.binder_mcse_target > 0):
        parser.error("--binder-mcse-target must be finite and positive")
    if not (math.isfinite(args.runtime_budget_minutes) and args.runtime_budget_minutes > 0):
        parser.error("--runtime-budget-minutes must be finite and positive")
    if args.max_continuations < 1:
        parser.error("--max-continuations must be positive")
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
    if not math.isfinite(args.mem_gb) or args.mem_gb <= 0:
        parser.error("--mem-gb must be finite and positive")
    for host in args.exclude_host:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", host):
            parser.error(f"unsafe excluded host name: {host!r}")


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
                "min_samples": args.min_samples, "max_samples": args.max_samples,
                "sample_increment": args.sample_increment,
                "binder_mcse_target": f"{args.binder_mcse_target:.17g}",
                "collection_shard_samples": args.collection_shard_samples,
                "adaptive_collection": str(args.adaptive_collection).lower(),
                "runtime_budget_minutes": f"{args.runtime_budget_minutes:.17g}",
                "max_continuations": args.max_continuations,
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
                "progress_marker": str((run_dir / "progress" / f"{base}.json").resolve()),
                "lock_path": str((run_dir / "locks" / f"{base}.lock").resolve()),
                "shard_dir": str((run_dir / "shards" / base).resolve()),
            })
            task += 1
    return rows


def worker_command(args, manifest: Path, task_token: str) -> str:
    values = [args.python, str(WORKER), "--manifest", str(manifest.resolve()),
              "--task-id", task_token, "--julia", args.julia,
              "--runtime-budget-minutes", str(args.runtime_budget_minutes)]
    if args.resume:
        values.append("--resume")
    return " ".join(task_token if value == task_token else shlex.quote(value) for value in values)


def lsf_script(args, manifest: Path, count: int, logs: Path) -> str:
    selections = [f"({args.gpu_select})"]
    selections.extend(f"hname!='{host}'" for host in args.exclude_host)
    resource = f"select[{' && '.join(selections)}] rusage[mem={args.mem_gb:g}]"
    script_path = (manifest.parent / "lsf_job.sh").resolve()
    runtime_home = lsf_runtime_home(script_path)
    env_spec = (
        f'all,HOME={runtime_home},LSB_JOB_SPOOLDIR={runtime_home / ".lsbatch"},'
        'UMBRELLA_TASK_ID=${TASK_ID},UMBRELLA_CONTINUATION=${NEXT}'
    )
    continuation_command = " ".join([
        f"HOME={shlex.quote(str(runtime_home))}",
        f"LSB_JOB_SPOOLDIR={shlex.quote(str(runtime_home / '.lsbatch'))}",
        shlex.quote(args.bsub), f'-J "{args.run_name}_t${{TASK_ID}}"',
        f"-q {shlex.quote(args.queue)}", f"-W {shlex.quote(args.walltime)}",
        f"-n {args.cpus}", f"-R {shlex.quote(resource)}", f"-gpu {shlex.quote(args.gpu_request)}",
        f"-o {shlex.quote(str(logs.resolve()) + '/%J.out')}",
        f"-e {shlex.quote(str(logs.resolve()) + '/%J.err')}",
        f'-env "{env_spec}"',
        "bash", shlex.quote(str(script_path)),
    ])
    lines = ["#!/usr/bin/env bash", f'#BSUB -J "{args.run_name}[1-{count}]"',
             f"#BSUB -q {args.queue}", f"#BSUB -W {args.walltime}",
             f"#BSUB -n {args.cpus}", f'#BSUB -R "{resource}"',
             f'#BSUB -gpu "{args.gpu_request}"',
             f"#BSUB -o {logs.resolve()}/%J_%I.out",
             f"#BSUB -e {logs.resolve()}/%J_%I.err", "", "set -euo pipefail",
             "export PYTHONUNBUFFERED=1",
             *lsf_environment_shell_lines(
                 module_init=args.module_init,
                 cuda_module=args.cuda_module,
                 julia_module=args.julia_module,
                 julia_depot_path=args.julia_depot,
                 extra_modules=args.module,
             ),
             *lsf_julia_launch_lines("julia", REPO_ROOT),
             'TASK_ID="${UMBRELLA_TASK_ID:-$((LSB_JOBINDEX - 1))}"',
             'ALLOCATION="${UMBRELLA_CONTINUATION:-0}"',
             "set +e",
             worker_command(args, manifest, '"${TASK_ID}"') + ' --resume --allocation "${ALLOCATION}"',
             "RC=$?", "set -e",
             'if [[ "$RC" -eq 75 ]]; then']
    if args.self_resubmit:
        marker = (manifest.parent / "self_resubmit_preflight.ok").resolve()
        lines.extend([
            f'  if [[ ! -f {shlex.quote(str(marker))} ]]; then echo "missing self-resubmit preflight marker" >&2; exit 2; fi',
            '  NEXT="$((ALLOCATION + 1))"',
            '  if ' + " ".join([
                shlex.quote(args.python), shlex.quote(str(REPO_ROOT / "scripts/umbrella_campaign.py")),
                "claim-continuation", "--manifest", shlex.quote(str(manifest.resolve())),
                '--task-id "${TASK_ID}"', '--allocation "${ALLOCATION}"']) + '; then',
            f'    {continuation_command}',
            '    exit 0',
            '  fi',
            '  echo "continuation chain exhausted or already claimed" >&2',
            '  exit 2',
        ])
    else:
        lines.append('  exit 75')
    lines.extend(['fi', 'exit "$RC"', ""])
    return "\n".join(lines)


def main(scheduler_default: str | None = None) -> int:
    parser = parser_for(scheduler_default)
    args = parser.parse_args()
    args.exclude_host = resolved_exclude_hosts(args.exclude_host)
    requested_adaptive = args.min_samples is not None or args.max_samples is not None
    if requested_adaptive and not args.dry_run and args.profile_file is None:
        parser.error("adaptive production submission requires --profile-file with validated evidence")
    if args.julia is None:
        args.julia = str(LOCAL_JULIA) if args.scheduler == "tsp" and LOCAL_JULIA.is_file() else "julia"
    selected_profile = load_profile(args.profile_file, args.L) if args.profile_file else None
    profile = selected_profile or UMBRELLA_PROFILES.get(args.L, {
        "windows": 25, "minimum": 0.0, "maximum": 0.45,
        "kappa": 2500.0, "power": 1.0,
    })
    if selected_profile:
        profile = {
            "windows": selected_profile["umbrella_windows"],
            "minimum": selected_profile["umbrella_min"],
            "maximum": selected_profile["umbrella_max"],
            "kappa": selected_profile["umbrella_kappa"],
            "power": selected_profile["umbrella_power"],
            "startup_eps": selected_profile["startup_epsilon"],
            "startup_n_lf": selected_profile["startup_n_lf"],
            "startup_sweeps": selected_profile["startup_sweeps"],
            "production_sweeps": selected_profile["minimum_thermalization_sweeps"],
            "max_production_sweeps": selected_profile["maximum_thermalization_sweeps"],
            "min_round_trip_fraction": 0.5,
            "min_swap_acceptance": selected_profile["transport_gates"]["minimum_edge_swap_acceptance"],
        }
        args.eps = selected_profile["epsilon"] if args.eps is None else args.eps
        args.n_lf = selected_profile["n_lf"] if args.n_lf is None else args.n_lf
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
    args.adaptive_collection = requested_adaptive
    args.min_samples = args.samples if args.min_samples is None else args.min_samples
    args.max_samples = args.samples if args.max_samples is None else args.max_samples
    if not args.adaptive_collection:
        args.collection_shard_samples = min(args.collection_shard_samples, args.samples)
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
    for name in ("checkpoints", "statistics", "diagnostics", "complete", "progress",
                 "locks", "shards", "logs"):
        (run_dir / name).mkdir(parents=True, exist_ok=True)
    manifest = run_dir / "manifest.csv"
    rows = build_rows(args, points, run_dir)
    write_manifest(manifest, rows)
    if args.scheduler == "lsf":
        submission = {
            "run_name": args.run_name, "queue": args.queue, "walltime": args.walltime,
            "cpus": args.cpus, "mem_gb": args.mem_gb, "gpu_select": args.gpu_select,
            "exclude_host": args.exclude_host, "gpu_request": args.gpu_request,
            "bsub": args.bsub, "self_resubmit": args.self_resubmit,
            "max_continuations": args.max_continuations,
        }
        (run_dir / "submission.json").write_text(
            json.dumps(submission, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
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
            if args.prepare_only:
                continue
            if not args.dry_run:
                subprocess.run([args.tsp, "bash", "-lc", command], check=True)
        return 0
    script = lsf_script(args, manifest, len(rows), run_dir / "logs")
    script_path = run_dir / "lsf_job.sh"
    script_path.write_text(script, encoding="utf-8")
    print(script)
    if args.prepare_only:
        return 0
    if not args.dry_run:
        submit_bsub_script(script_path, bsub=args.bsub)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
