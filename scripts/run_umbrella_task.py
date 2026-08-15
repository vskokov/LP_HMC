#!/usr/bin/env python3
"""Execute one manifest row of the umbrella-exchange workflow."""

from __future__ import annotations

import argparse
import csv
import json
import shlex
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_row(path: Path, task_id: int) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not 0 <= task_id < len(rows):
        raise ValueError(f"task id {task_id} outside 0..{len(rows) - 1}")
    if int(rows[task_id]["task_id"]) != task_id:
        raise ValueError("manifest task ids are not contiguous")
    return rows[task_id]


def invoke(command: list[str], launcher: str, dry_run: bool) -> None:
    full = ([*shlex.split(launcher), *command] if launcher != "none" else command)
    print(shlex.join(full), flush=True)
    if not dry_run:
        subprocess.run(full, check=True, cwd=REPO_ROOT)


def common_arguments(row: dict[str, str]) -> list[str]:
    return [
        row["L"], f"--Z={row['Z']}", f"--mass={row['m2']}",
        f"--eps={row['eps']}", f"--n_lf={row['n_lf']}",
        f"--startup-eps={row['startup_eps']}",
        f"--startup-n-lf={row['startup_n_lf']}",
        f"--startup-sweeps={row['startup_sweeps']}",
        f"--production-sweeps={row['production_sweeps']}",
        f"--umbrella-replicas={row['umbrella_replicas']}",
        f"--umbrella-min={row['umbrella_min']}",
        f"--umbrella-max={row['umbrella_max']}",
        f"--umbrella-kappa={row['umbrella_kappa']}",
        f"--umbrella-power={row['umbrella_power']}",
        f"--swap-every={row['swap_every']}", f"--rng={row['seed']}",
        f"--init-phase={row['init_phase']}",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--task-id", type=int, required=True)
    parser.add_argument("--julia", default="julia")
    parser.add_argument("--launcher", default="none")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    row = load_row(args.manifest, args.task_id)
    checkpoint = Path(row["checkpoint_path"])
    statistics = Path(row["stats_path"])
    diagnostics = Path(row["diagnostics_path"])
    marker = Path(row["completion_marker"])
    for path in (checkpoint, statistics, diagnostics, marker):
        path.parent.mkdir(parents=True, exist_ok=True)

    checkpoint_valid = False
    if args.resume and checkpoint.is_file() and not args.dry_run:
        validation = [
            args.julia, f"--project={REPO_ROOT}",
            str(REPO_ROOT / "scripts/validate_umbrella_checkpoint.jl"),
            str(checkpoint), row["L"], row["Z"], row["m2"], row["eps"],
            row["n_lf"], row["umbrella_replicas"], row["umbrella_min"],
            row["umbrella_max"], row["umbrella_kappa"],
            row["umbrella_power"],
        ]
        checkpoint_valid = subprocess.run(validation, cwd=REPO_ROOT).returncode == 0

    if not checkpoint_valid:
        invoke([
            args.julia, f"--project={REPO_ROOT}",
            str(REPO_ROOT / "scripts/thermalize_umbrella.jl"),
            *common_arguments(row), f"--checkpoint={checkpoint}",
        ], args.launcher, args.dry_run)

    invoke([
        args.julia, f"--project={REPO_ROOT}",
        str(REPO_ROOT / "scripts/collect_umbrella_stats.jl"),
        *common_arguments(row), f"--init={checkpoint}",
        f"--samples={row['samples']}", f"--skip={row['skip']}",
        f"--warmup={row['warmup']}", f"--output={statistics}",
        f"--diagnostics={diagnostics}",
    ], args.launcher, args.dry_run)

    if not args.dry_run:
        marker.write_text(json.dumps({"task_id": args.task_id, "complete": True}) + "\n",
                          encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
