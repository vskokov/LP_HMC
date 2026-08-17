#!/usr/bin/env python3
"""Execute one manifest row of the umbrella-exchange workflow."""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import shlex
import socket
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def log_event(event: str, **fields: object) -> None:
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    details = " ".join(f"{key}={value}" for key, value in fields.items())
    print(f"umbrella_worker event={event} time={timestamp} {details}".rstrip(), flush=True)


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
    maximum_sweeps = row.get(
        "max_production_sweeps", str(5 * int(row["production_sweeps"]))
    )
    minimum_fraction = row.get("min_round_trip_fraction", "0.5")
    minimum_swap = row.get("min_swap_acceptance", "0.25")
    return [
        row["L"], f"--Z={row['Z']}", f"--mass={row['m2']}",
        f"--eps={row['eps']}", f"--n_lf={row['n_lf']}",
        f"--startup-eps={row['startup_eps']}",
        f"--startup-n-lf={row['startup_n_lf']}",
        f"--startup-sweeps={row['startup_sweeps']}",
        f"--production-sweeps={row['production_sweeps']}",
        f"--max-production-sweeps={maximum_sweeps}",
        f"--min-round-trip-fraction={minimum_fraction}",
        f"--min-swap-acceptance={minimum_swap}",
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
    log_event(
        "started", task_id=args.task_id, host=socket.gethostname(), pid=os.getpid(),
        phase=row["init_phase"], n_lf=row["n_lf"], resume=args.resume,
        checkpoint=checkpoint, checkpoint_exists=checkpoint.is_file(),
    )

    checkpoint_valid = False
    checkpoint_resumable = False
    minimum_fraction = row.get("min_round_trip_fraction", "0.5")
    minimum_swap = row.get("min_swap_acceptance", "0.25")
    if args.resume and checkpoint.is_file() and not args.dry_run:
        log_event("checkpoint_validation_started", task_id=args.task_id)
        validation = [
            args.julia, f"--project={REPO_ROOT}",
            str(REPO_ROOT / "scripts/validate_umbrella_checkpoint.jl"),
            str(checkpoint), row["L"], row["Z"], row["m2"], row["eps"],
            row["n_lf"], row["umbrella_replicas"], row["umbrella_min"],
            row["umbrella_max"], row["umbrella_kappa"],
            row["umbrella_power"],
            row["production_sweeps"], minimum_fraction, minimum_swap,
        ]
        print(shlex.join(validation), flush=True)
        validation_result = subprocess.run(validation, cwd=REPO_ROOT)
        checkpoint_valid = validation_result.returncode == 0
        checkpoint_resumable = validation_result.returncode == 10
        log_event(
            "checkpoint_validation_finished", task_id=args.task_id,
            returncode=validation_result.returncode, valid=checkpoint_valid,
            resumable=checkpoint_resumable,
        )
        if not checkpoint_valid and not checkpoint_resumable:
            raise subprocess.CalledProcessError(validation_result.returncode, validation)

    if (args.resume and checkpoint_valid and marker.is_file() and
            statistics.is_file() and diagnostics.is_file()):
        log_event("reusing_completed_task", task_id=args.task_id)
        return 0

    if not checkpoint_valid:
        log_event(
            "thermalization_started", task_id=args.task_id,
            resumed_from_checkpoint=checkpoint_resumable,
        )
        thermalize = [
            args.julia, f"--project={REPO_ROOT}",
            str(REPO_ROOT / "scripts/thermalize_umbrella.jl"),
            *common_arguments(row), f"--checkpoint={checkpoint}",
        ]
        if checkpoint_resumable:
            thermalize.append(f"--init={checkpoint}")
        invoke(thermalize, args.launcher, args.dry_run)
        log_event("thermalization_finished", task_id=args.task_id)

    log_event("collection_started", task_id=args.task_id)
    invoke([
        args.julia, f"--project={REPO_ROOT}",
        str(REPO_ROOT / "scripts/collect_umbrella_stats.jl"),
        *common_arguments(row), f"--init={checkpoint}",
        f"--samples={row['samples']}", f"--skip={row['skip']}",
        f"--warmup={row['warmup']}", f"--output={statistics}",
        f"--diagnostics={diagnostics}",
    ], args.launcher, args.dry_run)
    log_event("collection_finished", task_id=args.task_id)

    if not args.dry_run:
        marker.write_text(json.dumps({"task_id": args.task_id, "complete": True}) + "\n",
                          encoding="utf-8")
    log_event("completed", task_id=args.task_id, marker=marker)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
