#!/usr/bin/env python3
"""Execute one row of a reweighting Slurm manifest."""

from __future__ import annotations

import argparse
import csv
import shlex
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from reweight_binder import read_stats  # noqa: E402


def read_task(manifest: Path, task_id: int) -> dict[str, str]:
    with manifest.open(newline="") as handle:
        matches = [row for row in csv.DictReader(handle) if int(row["task_id"]) == task_id]
    if len(matches) != 1:
        raise ValueError(f"manifest has {len(matches)} rows for task_id={task_id}")
    return matches[0]


def valid_stats(path: Path, row: dict[str, str]) -> bool:
    try:
        run = read_stats(path)
        return (
            run.L == int(row["L"])
            and run.Z == float(row["Z"])
            and run.m2 == float(row["m2"])
            and run.seed == int(row["seed"])
            and run.epsilon == float(row["eps"])
            and run.n_lf == int(row["n_lf"])
            and run.size == int(row["samples"])
        )
    except (OSError, ValueError):
        return False


def invoke(command: list[str], dry_run: bool) -> None:
    print("+", shlex.join(command), flush=True)
    if not dry_run:
        subprocess.run(command, check=True)


def mark_complete(marker: Path, row: dict[str, str]) -> None:
    marker.parent.mkdir(parents=True, exist_ok=True)
    temporary = marker.with_name(marker.name + ".tmp")
    temporary.write_text(
        f"schema_version=1\ntask_id={row['task_id']}\nseed={row['seed']}\n",
        encoding="utf-8",
    )
    temporary.replace(marker)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--task-id", type=int, required=True)
    parser.add_argument("--julia", default="julia")
    parser.add_argument("--launcher", choices=("srun", "none"), default="srun")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    row = read_task(args.manifest.resolve(), args.task_id)
    checkpoint = Path(row["checkpoint_path"])
    stats = Path(row["stats_path"])
    marker = Path(row["completion_marker"])
    prefix = [] if args.launcher == "none" else [args.launcher]
    project = str(REPO_ROOT)

    if args.resume and stats.is_file() and valid_stats(stats, row):
        print(f"task {args.task_id}: valid statistics already exist at {stats}")
        if not args.dry_run:
            mark_complete(marker, row)
        return 0

    if not args.dry_run:
        marker.unlink(missing_ok=True)

    checkpoint_valid = False
    validate = prefix + [
        args.julia, f"--project={project}", str(REPO_ROOT / "scripts/validate_checkpoint.jl"),
        str(checkpoint), row["L"], row["Z"], row["m2"], row["eps"], row["n_lf"], row["seed"],
    ]
    if args.resume and checkpoint.is_file() and not args.dry_run:
        print("+", shlex.join(validate), flush=True)
        checkpoint_valid = subprocess.run(validate, check=False).returncode == 0
    elif args.resume and args.dry_run:
        print("# if the checkpoint exists, validate it with:")
        print("+", shlex.join(validate))

    if not checkpoint_valid:
        thermalize = prefix + [
            args.julia, f"--project={project}", str(REPO_ROOT / "scripts/thermalize.jl"),
            "--fp64", f"--Z={row['Z']}", f"--mass={row['m2']}", f"--rng={row['seed']}",
            f"--eps={row['eps']}", f"--n_lf={row['n_lf']}",
            f"--checkpoint={checkpoint}", row["L"],
        ]
        invoke(thermalize, args.dry_run)
    else:
        print(f"task {args.task_id}: reusing valid checkpoint {checkpoint}")

    collect = prefix + [
        args.julia, f"--project={project}", str(REPO_ROOT / "scripts/collect_reweight_stats.jl"),
        "--fp64", f"--Z={row['Z']}", f"--mass={row['m2']}", f"--rng={row['seed']}",
        f"--eps={row['eps']}", f"--n_lf={row['n_lf']}", f"--init={checkpoint}",
        f"--samples={row['samples']}", f"--skip={row['skip']}", f"--warmup={row['warmup']}",
        f"--output={stats}", row["L"],
    ]
    invoke(collect, args.dry_run)

    if not args.dry_run:
        if not valid_stats(stats, row):
            raise RuntimeError(f"collector did not produce valid statistics: {stats}")
        mark_complete(marker, row)
        print(f"task {args.task_id}: complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
