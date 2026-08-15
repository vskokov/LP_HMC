#!/usr/bin/env python3
"""Submit a flexible LSF array for CUDA Binder reweighting analysis."""

from __future__ import annotations

import argparse
import math
import re
import shlex
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXCLUDED_HOSTS = ("gpu16", "gpu33")
DEFAULT_SCANS = (
    (-0.6, -1.95, -1.75, "mZ0.6"),
    (-0.77, -2.25, -2.0, "mZ0.77"),
    (-0.9, -2.45, -2.2, "mZ0.9"),
)
SAFE_NAME = re.compile(r"[A-Za-z0-9_.-]+")


def parse_scan(text: str) -> tuple[float, float, float, str]:
    parts = text.split(",")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("scan must be Z,M2_START,M2_END,LABEL")
    try:
        Z, start, end = map(float, parts[:3])
    except ValueError as exc:
        raise argparse.ArgumentTypeError("scan coordinates must be numeric") from exc
    label = parts[3]
    if not all(math.isfinite(value) for value in (Z, start, end)):
        raise argparse.ArgumentTypeError("scan coordinates must be finite")
    if start == end:
        raise argparse.ArgumentTypeError("scan start and end must differ")
    if not SAFE_NAME.fullmatch(label):
        raise argparse.ArgumentTypeError("scan label contains unsafe characters")
    return Z, start, end, label


def safe_name(parser: argparse.ArgumentParser, value: str, option: str) -> None:
    if not value or not SAFE_NAME.fullmatch(value):
        parser.error(f"{option} may contain only letters, digits, dot, underscore, and hyphen")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--data-prefix", required=True,
        help="common simulation run prefix; binder_lsf_ selects runs/binder_lsf_L*/manifest.csv",
    )
    parser.add_argument("--L", type=int, nargs="+", required=True, metavar="L")
    parser.add_argument(
        "--scan", action="append", type=parse_scan,
        help="Z,M2_START,M2_END,LABEL; repeat to replace the three default scans",
    )
    parser.add_argument(
        "--output-prefix",
        help="plot/CSV prefix (default: same as --data-prefix)",
    )
    parser.add_argument("--run-root", type=Path, default=Path("runs"))
    parser.add_argument("--output-root", type=Path, default=Path("plots"))
    parser.add_argument("--log-dir", type=Path, default=Path("runs/reweight_binder_lsf/logs"))
    parser.add_argument("--job-name", default="reweight_binder")

    analysis = parser.add_argument_group("reweighting analysis")
    analysis.add_argument("--num", type=int, default=301)
    analysis.add_argument("--bootstrap", type=int, default=1000)
    analysis.add_argument("--block-size", default="auto")
    analysis.add_argument("--cuda-batch-size", type=int, default=32)

    lsf = parser.add_argument_group("LSF resources")
    lsf.add_argument("--queue", default="short_gpu")
    lsf.add_argument("--walltime", default="120", help="LSF -W value")
    lsf.add_argument("--cpus", type=int, default=1)
    lsf.add_argument("--mem-gb", type=float, default=32.0)
    lsf.add_argument("--gpu-select", default="h200 || h100 || l40s")
    lsf.add_argument(
        "--exclude-host", action="append",
        help="excluded host; repeat to replace the default gpu16/gpu33 list",
    )
    lsf.add_argument("--gpu-request", default="num=1:mode=shared:mps=no")
    lsf.add_argument("--max-concurrent", type=int, default=4)
    lsf.add_argument("--project-code", help="optional LSF project passed with -P")
    lsf.add_argument("--bsub", default="bsub")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    safe_name(parser, args.data_prefix, "--data-prefix")
    args.output_prefix = args.output_prefix or args.data_prefix
    safe_name(parser, args.output_prefix, "--output-prefix")
    safe_name(parser, args.job_name, "--job-name")
    if any(L < 2 for L in args.L):
        parser.error("all --L values must be at least 2")
    if len(set(args.L)) != len(args.L):
        parser.error("--L values must be unique")
    if args.cpus < 1 or args.max_concurrent < 1:
        parser.error("--cpus and --max-concurrent must be positive")
    if args.num < 2 or args.bootstrap < 1 or args.cuda_batch_size < 1:
        parser.error("--num must be at least 2; bootstrap and CUDA batch size must be positive")
    if args.block_size != "auto":
        try:
            if int(args.block_size) < 1:
                raise ValueError
        except ValueError:
            parser.error("--block-size must be 'auto' or a positive integer")
    if not math.isfinite(args.mem_gb) or args.mem_gb <= 0:
        parser.error("--mem-gb must be finite and positive")

    excluded = list(DEFAULT_EXCLUDED_HOSTS if args.exclude_host is None
                    else args.exclude_host)
    for host in excluded:
        safe_name(parser, host, "--exclude-host")
    scans = args.scan or list(DEFAULT_SCANS)
    task_count = len(args.L) * len(scans)
    concurrency = min(args.max_concurrent, task_count)
    array_name = f"{args.job_name}[1-{task_count}]%{concurrency}"

    args.log_dir.mkdir(parents=True, exist_ok=True)
    args.output_root.mkdir(parents=True, exist_ok=True)
    select_parts = [f"({args.gpu_select})"]
    select_parts.extend(f"hname!='{host}'" for host in excluded)
    resource = f"select[{' && '.join(select_parts)}] rusage[mem={args.mem_gb:g}]"
    command = [
        args.bsub,
        "-J", array_name,
        "-W", args.walltime,
        "-n", str(args.cpus),
        "-q", args.queue,
        "-R", resource,
        "-gpu", args.gpu_request,
        "-o", str(args.log_dir / "%J_%I.out"),
        "-e", str(args.log_dir / "%J_%I.err"),
    ]
    if args.project_code:
        command.extend(("-P", args.project_code))
    worker = REPO_ROOT / "scripts" / "reweight_binder_bsub.sh"
    command.extend((
        "/bin/bash", str(worker),
        "--data-prefix", args.data_prefix,
        "--output-prefix", args.output_prefix,
        "--lattice-sizes", ",".join(map(str, args.L)),
        "--run-root", str(args.run_root),
        "--output-root", str(args.output_root),
        "--num", str(args.num),
        "--bootstrap", str(args.bootstrap),
        "--block-size", args.block_size,
        "--cuda-batch-size", str(args.cuda_batch_size),
    ))
    for Z, start, end, label in scans:
        command.extend(("--scan", f"{Z:.17g},{start:.17g},{end:.17g},{label}"))

    print(f"lattice sizes: {', '.join(map(str, args.L))}")
    print(f"scans: {len(scans)}")
    print(f"tasks: {task_count} ({len(args.L)} lattice sizes x {len(scans)} scans)")
    print(f"array: {array_name}")
    print(f"data manifests: {args.run_root}/{args.data_prefix}L*/manifest.csv")
    print(f"outputs: {args.output_root}/{args.output_prefix}<scan>_L*")
    print(f"excluded hosts: {', '.join(excluded) or 'none'}")
    print("array task mapping:")
    task_index = 1
    for L in args.L:
        for Z, start, end, label in scans:
            print(
                f"  {task_index:3d}: L={L:<3d} Z={Z:g} "
                f"m2={start:g}..{end:g} label={label}"
            )
            task_index += 1
    print(shlex.join(command))
    if args.dry_run:
        print("dry-run: bsub was not invoked")
        return 0
    subprocess.run(command, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
