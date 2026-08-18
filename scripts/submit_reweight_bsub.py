#!/usr/bin/env python3
"""Materialize and submit a reproducible LSF job array for reweighting ensembles."""

from __future__ import annotations

import argparse
import csv
import math
import re
import shlex
import subprocess
from pathlib import Path

from hmc_defaults import (
    resolve_hmc_parameters, resolve_startup_hmc_parameters,
    resolve_tempering_parameters,
)
from runtime_preflight import shell_command as preflight_shell_command
from reweight_manifest import (
    REPO_ROOT,
    build_rows,
    parse_point,
    read_points_csv,
    write_manifest,
)


DEFAULT_DEPOT = "/rsstu/users/v/vskokov/gluon/jd"
DEFAULT_JULIAUP_DEPOT = "/rsstu/users/v/vskokov/gluon/.julia"
DEFAULT_JULIA_BIN_DIR = "/rsstu/users/v/vskokov/gluon/juliaup/bin"
DEFAULT_EXCLUDED_HOSTS = ("gpu16", "gpu33")


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
    if args.cpus < 1:
        parser.error("--cpus must be positive")
    if args.mem_gb <= 0 or not math.isfinite(args.mem_gb):
        parser.error("--mem-gb must be finite and positive")
    if args.max_concurrent is not None and args.max_concurrent < 1:
        parser.error("--max-concurrent must be positive")
    for host in args.exclude_host:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", host):
            parser.error(f"unsafe excluded host name: {host!r}")


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def rows_as_text(rows: list[dict[str, object]]) -> list[dict[str, str]]:
    return [{key: str(value) for key, value in row.items()} for row in rows]


def exclusion_expression(hosts: list[str]) -> str:
    return " && ".join(f"hname!='{host}'" for host in hosts)


def lsf_script(
    args: argparse.Namespace, manifest: Path, task_count: int, logs: Path
) -> str:
    array_spec = f"{args.run_name}[1-{task_count}]"
    if args.max_concurrent is not None:
        array_spec += f"%{args.max_concurrent}"
    directives = [
        "#!/usr/bin/env bash",
        f'#BSUB -J "{array_spec}"',
        f"#BSUB -W {args.walltime}",
        f"#BSUB -n {args.cpus}",
        f"#BSUB -q {args.queue}",
        f'#BSUB -R "select[{args.gpu_select}]"',
    ]
    if args.exclude_host:
        directives.append(f'#BSUB -R "select[{exclusion_expression(args.exclude_host)}]"')
    directives.extend([
        f'#BSUB -R "rusage[mem={args.mem_gb:g}]"',
        f'#BSUB -gpu "{args.gpu_request}"',
        f'#BSUB -o "{logs.resolve()}/%J_%I.out"',
        f'#BSUB -e "{logs.resolve()}/%J_%I.err"',
    ])
    if args.project_code:
        directives.append(f"#BSUB -P {args.project_code}")

    worker = REPO_ROOT / "scripts/run_reweight_task.py"
    command = [
        args.python,
        str(worker),
        "--manifest",
        str(manifest.resolve()),
        "--task-id",
        '"${TASK_ID}"',
        "--julia",
        args.julia,
        "--launcher",
        "none",
    ]
    if args.resume:
        command.append("--resume")
    command_text = " ".join(
        item if item == '"${TASK_ID}"' else shlex.quote(item) for item in command
    )
    cuda_check = preflight_shell_command(args.julia, REPO_ROOT)

    body = [
        "",
        "set -euo pipefail",
        f"source {shlex.quote(args.module_init)}",
        f"export JULIA_DEPOT_PATH={shlex.quote(args.julia_depot)}",
        f"export JULIAUP_DEPOT_PATH={shlex.quote(args.juliaup_depot)}",
        f"export PATH={shlex.quote(args.julia_bin_dir)}:\"$PATH\"",
        f"module load {shlex.quote(args.cuda_module)}",
    ]
    body.extend(f"module load {shlex.quote(module)}" for module in args.module)
    body.extend([
        "",
        'echo "julia=$(command -v julia)"',
        "julia --version",
        'echo "checking CUDA runtime and device"',
        cuda_check,
        'TASK_ID="$((LSB_JOBINDEX - 1))"',
        command_text,
        "",
    ])
    return "\n".join(directives + body)


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
    parser.add_argument("--tempering-replicas", type=int)
    parser.add_argument("--mass-span", type=float)
    parser.add_argument("--swap-every", type=int)
    parser.add_argument("--tempering-profile", choices=("critical",))
    parser.add_argument("--tempering-profile-file", type=Path)
    parser.add_argument(
        "--init-schedule", choices=("hot", "disordered", "ordered", "split"),
        default="hot",
    )
    parser.add_argument("--phase-threshold", type=float, default=0.25)

    lsf = parser.add_argument_group("LSF resources")
    lsf.add_argument("--queue", default="short_gpu")
    lsf.add_argument("--walltime", default="120", help="LSF -W value, usually minutes")
    lsf.add_argument("--cpus", type=int, default=1)
    lsf.add_argument("--mem-gb", type=float, default=16.0)
    lsf.add_argument("--gpu-select", default="h200 || h100 || l40s")
    lsf.add_argument(
        "--exclude-host", action="append", default=None,
        help="excluded LSF host; repeat to replace the default gpu16/gpu33 list",
    )
    lsf.add_argument("--gpu-request", default="num=1:mode=shared:mps=no")
    lsf.add_argument("--max-concurrent", type=int, help="maximum active array elements")
    lsf.add_argument("--project-code", help="optional LSF project/account passed with -P")

    environment = parser.add_argument_group("cluster environment")
    environment.add_argument("--module-init", default="/usr/share/Modules/init/bash")
    environment.add_argument("--cuda-module", default="cuda/12.3")
    environment.add_argument("--module", action="append", default=[])
    environment.add_argument("--julia-depot", default=DEFAULT_DEPOT)
    environment.add_argument("--juliaup-depot", default=DEFAULT_JULIAUP_DEPOT)
    environment.add_argument("--julia-bin-dir", default=DEFAULT_JULIA_BIN_DIR)
    environment.add_argument("--julia", default="julia")
    environment.add_argument("--python", default="python3")
    environment.add_argument("--bsub", default="bsub")

    parser.add_argument("--run-name")
    parser.add_argument("--run-root", type=Path, default=REPO_ROOT / "runs")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    args.exclude_host = list(DEFAULT_EXCLUDED_HOSTS if args.exclude_host is None
                             else args.exclude_host)
    try:
        (args.tempering_replicas, args.mass_span, args.swap_every,
         used_tempering_profile) = resolve_tempering_parameters(
            args.L, args.tempering_profile, args.tempering_profile_file,
            args.tempering_replicas, args.mass_span, args.swap_every,
        )
    except ValueError as exc:
        parser.error(str(exc))
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

    args.run_name = args.run_name or f"reweight_lsf_L{args.L}"
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.run_name):
        parser.error("--run-name may contain only letters, digits, dot, underscore, and hyphen")

    run_dir = (args.run_root / args.run_name).resolve()
    manifest = run_dir / "manifest.csv"
    logs = run_dir / "logs"
    rows = build_rows(args, points, run_dir)
    if manifest.exists():
        if not args.resume:
            parser.error(f"{manifest} already exists; choose a new --run-name or use --resume")
        if read_manifest(manifest) != rows_as_text(rows):
            parser.error(
                f"{manifest} does not exactly match the requested parameters; "
                "choose a new --run-name"
            )
    else:
        for directory in (
            run_dir / "checkpoints", run_dir / "statistics",
            run_dir / "diagnostics", run_dir / "complete", logs,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        write_manifest(manifest, rows)

    script_path = run_dir / "lsf_array_job.sh"
    script_text = lsf_script(args, manifest, len(rows), logs)
    temporary = script_path.with_name(script_path.name + ".tmp")
    temporary.write_text(script_text, encoding="utf-8")
    temporary.replace(script_path)

    source = "measured L default" if used_hmc_default else "command line"
    print(f"manifest: {manifest}")
    print(f"HMC: eps={args.eps:.11g} n_lf={args.n_lf} ({source})")
    startup_source = "startup L default" if used_startup_default else "command line"
    print(f"startup HMC: eps={args.startup_eps:.11g} n_lf={args.startup_n_lf} "
          f"sweeps={args.startup_sweeps} ({startup_source})")
    tempering_source = "validated critical profile" if used_tempering_profile else "command line/default"
    print(f"tempering: replicas={args.tempering_replicas} span={args.mass_span:g} "
          f"swap_every={args.swap_every} ({tempering_source})")
    print(f"tasks: {len(rows)} ({len(points)} points x {args.replicas} replicas)")
    print(f"excluded hosts: {', '.join(args.exclude_host) or 'none'}")
    print(f"job script: {script_path}")
    print(script_text)
    if args.dry_run:
        print("dry-run: bsub was not invoked")
        return 0

    with script_path.open("rb") as handle:
        subprocess.run([args.bsub], stdin=handle, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
