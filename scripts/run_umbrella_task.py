#!/usr/bin/env python3
"""Execute one restartable, runtime-bounded umbrella manifest task."""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import shlex
import socket
import subprocess
import time
from pathlib import Path

from umbrella_runtime import PERMANENT_EXIT, RETRYABLE_EXIT, atomic_json, deterministic_seed, exclusive_task_lock


REPO_ROOT = Path(__file__).resolve().parents[1]
SHARD_COLLECTOR = REPO_ROOT / "scripts/collect_umbrella_shard.jl"


def log_event(event: str, **fields: object) -> None:
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    details = " ".join(f"{key}={value}" for key, value in fields.items())
    print(f"umbrella_worker event={event} time={timestamp} {details}".rstrip(), flush=True)


def load_row(path: Path, task_id: int) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not 0 <= task_id < len(rows) or int(rows[task_id]["task_id"]) != task_id:
        raise ValueError(f"invalid/non-contiguous task id {task_id}")
    return rows[task_id]


def run(command: list[str], launcher: str, dry_run: bool) -> int:
    full = [*shlex.split(launcher), *command] if launcher != "none" else command
    print(shlex.join(full), flush=True)
    return 0 if dry_run else subprocess.run(full, cwd=REPO_ROOT).returncode


def common_arguments(row: dict[str, str], seed_override: int | None = None) -> list[str]:
    return [
        row["L"], f"--Z={row['Z']}", f"--mass={row['m2']}",
        f"--eps={row['eps']}", f"--n_lf={row['n_lf']}",
        f"--startup-eps={row['startup_eps']}", f"--startup-n-lf={row['startup_n_lf']}",
        f"--startup-sweeps={row['startup_sweeps']}",
        f"--production-sweeps={row['production_sweeps']}",
        f"--max-production-sweeps={row.get('max_production_sweeps', str(5 * int(row['production_sweeps'])))}",
        f"--min-round-trip-fraction={row.get('min_round_trip_fraction', '0.5')}",
        f"--min-swap-acceptance={row.get('min_swap_acceptance', '0.25')}",
        f"--umbrella-replicas={row['umbrella_replicas']}",
        f"--umbrella-min={row['umbrella_min']}", f"--umbrella-max={row['umbrella_max']}",
        f"--umbrella-kappa={row['umbrella_kappa']}",
        f"--umbrella-power={row['umbrella_power']}", f"--swap-every={row['swap_every']}",
        f"--rng={seed_override if seed_override is not None else row['seed']}",
        f"--task-id={row['task_id']}", f"--init-phase={row['init_phase']}",
    ]


def validate_checkpoint(args: argparse.Namespace, row: dict[str, str], checkpoint: Path) -> int:
    command = [
        args.julia, f"--project={REPO_ROOT}", str(REPO_ROOT / "scripts/validate_umbrella_checkpoint.jl"),
        str(checkpoint), row["L"], row["Z"], row["m2"], row["eps"], row["n_lf"],
        row["umbrella_replicas"], row["umbrella_min"], row["umbrella_max"],
        row["umbrella_kappa"], row["umbrella_power"], row["production_sweeps"],
        row.get("min_round_trip_fraction", "0.5"), row.get("min_swap_acceptance", "0.25"),
    ]
    print(shlex.join(command), flush=True)
    return subprocess.run(command, cwd=REPO_ROOT).returncode


def metadata_lines(row: dict[str, str], samples: int) -> list[str]:
    replicas = int(row["umbrella_replicas"]); lower = float(row["umbrella_min"])
    upper = float(row["umbrella_max"]); power = float(row["umbrella_power"])
    centers = [lower + (upper - lower) * (index / (replicas - 1)) ** power
               for index in range(replicas)]
    values = {
        "schema_version": 3, "sampler": "umbrella_exchange", "L": row["L"],
        "Z": row["Z"], "m2": row["m2"], "epsilon": row["eps"], "n_lf": row["n_lf"],
        "seed": row["seed"], "samples_per_window": samples, "skip": row["skip"],
        "lambda": 4.0, "temperature": 1.0, "float_type": "Float32", "device": "cuda",
        "warmup": row["warmup"], "thermalization_sweeps": row["production_sweeps"],
        "transport_gate_passed": "true", "umbrella_replicas": row["umbrella_replicas"],
        "umbrella_coordinate": "M2", "umbrella_power": row["umbrella_power"],
        "umbrella_centers": ";".join(f"{value:.17g}" for value in centers),
        "umbrella_kappas": ";".join([row["umbrella_kappa"]] * replicas),
        "swap_every": row["swap_every"], "init_phase": row["init_phase"],
        "collection_shard_samples": row["collection_shard_samples"],
    }
    return [f"# {key}={value}\n" for key, value in values.items()]


def merge_shards(row: dict[str, str], progress: dict[str, object]) -> None:
    stats = Path(row["stats_path"]); diagnostics = Path(row["diagnostics_path"])
    stats_tmp = stats.with_name(stats.name + ".tmp"); diag_tmp = diagnostics.with_name(diagnostics.name + ".tmp")
    shards = progress["committed_shards"]
    with stats_tmp.open("w", encoding="utf-8") as output:
        output.writelines(metadata_lines(row, int(progress["samples"])))
        for index, shard in enumerate(shards):
            with Path(shard["statistics"]).open(encoding="utf-8") as source:
                if index:
                    next(source)
                output.writelines(source)
    with diag_tmp.open("w", encoding="utf-8") as output:
        for index, shard in enumerate(shards):
            with Path(shard["diagnostics"]).open(encoding="utf-8") as source:
                if index:
                    next(source)
                output.writelines(source)
    os.replace(stats_tmp, stats); os.replace(diag_tmp, diagnostics)


def legacy_collection(args: argparse.Namespace, row: dict[str, str], checkpoint: Path) -> int:
    return run([args.julia, f"--project={REPO_ROOT}", str(REPO_ROOT / "scripts/collect_umbrella_stats.jl"),
                *common_arguments(row), f"--init={checkpoint}", f"--samples={row['samples']}",
                f"--skip={row['skip']}", f"--warmup={row['warmup']}",
                f"--output={row['stats_path']}", f"--diagnostics={row['diagnostics_path']}"],
               args.launcher, args.dry_run)


def execute(args: argparse.Namespace, row: dict[str, str]) -> int:
    started = time.monotonic(); deadline = started + args.runtime_budget_minutes * 60
    checkpoint = Path(row["checkpoint_path"]); marker = Path(row["completion_marker"])
    for path in (checkpoint, Path(row["stats_path"]), Path(row["diagnostics_path"]), marker):
        path.parent.mkdir(parents=True, exist_ok=True)
    log_event("started", task_id=args.task_id, host=socket.gethostname(), pid=os.getpid(),
              phase=row["init_phase"], n_lf=row["n_lf"], resume=args.resume,
              allocation=args.allocation, checkpoint=checkpoint, checkpoint_exists=checkpoint.is_file())
    if marker.is_file():
        log_event("reusing_completed_task", task_id=args.task_id)
        return 0

    valid = resumable = False
    if args.resume and checkpoint.is_file() and not args.dry_run:
        code = validate_checkpoint(args, row, checkpoint)
        valid, resumable = code == 0, code == 10
        if not valid and not resumable:
            log_event("permanent_checkpoint_failure", returncode=code)
            return PERMANENT_EXIT
    if not valid:
        remaining = max(1, int(deadline - time.monotonic() - 45))
        command = [args.julia, f"--project={REPO_ROOT}", str(REPO_ROOT / "scripts/thermalize_umbrella.jl"),
                   *common_arguments(row), f"--checkpoint={checkpoint}", f"--runtime-seconds={remaining}"]
        if resumable:
            command.append(f"--init={checkpoint}")
        log_event("thermalization_started", resumed_from_checkpoint=resumable)
        code = run(command, args.launcher, args.dry_run)
        if code == RETRYABLE_EXIT:
            log_event("continuation_required", stage="thermalization")
            return RETRYABLE_EXIT
        if code:
            log_event("permanent_thermalization_failure", returncode=code)
            return PERMANENT_EXIT
        log_event("thermalization_finished")

    if "collection_shard_samples" not in row:
        log_event("collection_started", mode="legacy")
        code = legacy_collection(args, row, checkpoint)
        if code:
            return PERMANENT_EXIT
        if not args.dry_run:
            atomic_json(marker, {"task_id": args.task_id, "complete": True, "mode": "legacy"})
        log_event("completed", marker=marker)
        return 0

    progress_path = Path(row["progress_marker"]); shard_dir = Path(row["shard_dir"])
    log_event("collection_started", mode="sharded")
    shard_dir.mkdir(parents=True, exist_ok=True)
    if progress_path.is_file():
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
    else:
        progress = {"schema_version": 1, "task_id": args.task_id, "samples": 0,
                    "target_samples": int(row["min_samples"]), "committed_shards": [],
                    "checkpoint": str(checkpoint), "decision": "collecting"}
        if not args.dry_run:
            atomic_json(progress_path, progress)
    target = int(progress["target_samples"]); shard_samples = int(row["collection_shard_samples"])
    while int(progress["samples"]) < target:
        if time.monotonic() + 60 >= deadline:
            log_event("continuation_required", stage="collection", samples=progress["samples"])
            return RETRYABLE_EXIT
        index = len(progress["committed_shards"])
        stats_shard = shard_dir / f"statistics_{index:06d}.csv"
        diag_shard = shard_dir / f"diagnostics_{index:06d}.csv"
        next_checkpoint = shard_dir / f"collection_checkpoint_{(index + 1) % 2}.jld2"
        block_seed = deterministic_seed(int(row["seed"]), args.task_id, "collection", index)
        command = [args.julia, f"--project={REPO_ROOT}", str(SHARD_COLLECTOR),
                   *common_arguments(row, block_seed), f"--init={progress['checkpoint']}",
                   f"--samples={shard_samples}", f"--skip={row['skip']}",
                   f"--block-index={index}", f"--output={stats_shard}",
                   f"--diagnostics={diag_shard}", f"--collection-checkpoint={next_checkpoint}",
                   f"--runtime-seconds={max(1, int(deadline - time.monotonic() - 30))}"]
        log_event("collection_shard_started", shard=index, seed=block_seed)
        code = run(command, args.launcher, args.dry_run)
        if code == RETRYABLE_EXIT:
            log_event("continuation_required", stage="collection", shard=index)
            return RETRYABLE_EXIT
        if code:
            return PERMANENT_EXIT
        if args.dry_run:
            log_event("completed", dry_run=True)
            return 0
        progress["committed_shards"].append({"index": index, "statistics": str(stats_shard),
                                              "diagnostics": str(diag_shard),
                                              "checkpoint": str(next_checkpoint), "seed": block_seed})
        progress["samples"] = int(progress["samples"]) + shard_samples
        progress["checkpoint"] = str(next_checkpoint)
        atomic_json(progress_path, progress)
        log_event("collection_shard_committed", shard=index, samples=progress["samples"])

    if row.get("adaptive_collection", "false").lower() != "true":
        progress["decision"] = "complete"
        if not args.dry_run:
            atomic_json(progress_path, progress)
    if progress.get("decision") in ("complete", "precision_failed"):
        merge_shards(row, progress)
        state = str(progress["decision"])
        atomic_json(marker, {"task_id": args.task_id, "complete": state == "complete",
                             "state": state, "samples_per_window": progress["samples"]})
        log_event(state, marker=marker)
    else:
        progress["decision"] = "awaiting_cohort"
        atomic_json(progress_path, progress)
        log_event("awaiting_cohort", samples=progress["samples"])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--task-id", type=int, required=True)
    parser.add_argument("--julia", default="julia"); parser.add_argument("--launcher", default="none")
    parser.add_argument("--resume", action="store_true"); parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--runtime-budget-minutes", type=float, default=95.0)
    parser.add_argument("--allocation", type=int, default=0)
    args = parser.parse_args()
    try:
        row = load_row(args.manifest, args.task_id)
        lock = Path(row.get("lock_path", row["completion_marker"] + ".lock"))
        with exclusive_task_lock(lock):
            return execute(args, row)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        log_event("permanent_configuration_failure", error=repr(exc))
        return PERMANENT_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
