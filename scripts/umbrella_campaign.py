#!/usr/bin/env python3
"""Prepare, inspect, and safely repair the restartable all-L umbrella campaign."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from analyze_umbrella import block_bootstrap, estimate, read_umbrella
from run_umbrella_task import merge_shards
from hmc_defaults import resolve_hmc_parameters
from umbrella_profiles import SUPPORTED_SIZES, load_profile, proposed_profile
from umbrella_runtime import atomic_json, claim_continuation


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE_DIR = REPO_ROOT / "configs/umbrella_profiles"


def parse_sizes(text: str) -> list[int]:
    values = [int(value) for value in text.split(",")]
    if not values or len(values) != len(set(values)) or any(v not in SUPPORTED_SIZES for v in values):
        raise argparse.ArgumentTypeError(f"sizes must be unique members of {SUPPORTED_SIZES}")
    return values


def write_profile_if_missing(directory: Path, L: int) -> Path:
    path = directory / f"L{L}.json"
    if not path.exists():
        atomic_json(path, proposed_profile(L))
    return path


def prepare(args: argparse.Namespace) -> int:
    args.campaign_dir.mkdir(parents=True, exist_ok=True)
    index = {"schema_version": 1, "campaign": "all_L_umbrella", "Z": -0.6,
             "m2": -1.86421, "sizes": [], "policy": {
                 "replicas": 4, "phases": {"ordered": 2, "disordered": 2},
                 "skip": 2, "binder_mcse_target": 0.005,
                 "min_samples": 10_000, "max_samples": 40_000, "increment": 5_000}}
    blocked = []
    for L in args.sizes:
        profile_path = write_profile_if_missing(args.profile_dir, L)
        profile = load_profile(profile_path, L, require_validated=False)
        epsilon, n_lf, _ = resolve_hmc_parameters(
            L, float(profile["epsilon"]), profile.get("n_lf")
        )
        run_dir = args.campaign_dir / f"L{L}"
        command = [
            sys.executable, str(REPO_ROOT / "scripts/submit_umbrella_bsub.py"), f"--L={L}",
            "--point=-0.6,-1.86421", f"--eps={epsilon}",
            f"--n-lf={n_lf}",
            f"--startup-eps={profile['startup_epsilon']}",
            f"--startup-n-lf={profile['startup_n_lf']}", f"--startup-sweeps={profile['startup_sweeps']}",
            f"--thermalization-sweeps={profile['minimum_thermalization_sweeps']}",
            f"--max-thermalization-sweeps={profile['maximum_thermalization_sweeps']}",
            f"--umbrella-windows={profile['umbrella_windows']}",
            f"--umbrella-min={profile['umbrella_min']}", f"--umbrella-max={profile['umbrella_max']}",
            f"--umbrella-kappa={profile['umbrella_kappa']}",
            f"--umbrella-power={profile['umbrella_power']}", "--swap-every=1",
            "--replicas=4", "--init-schedule=split", "--min-samples=10000",
            "--max-samples=40000", "--sample-increment=5000", "--samples=10000",
            "--collection-shard-samples=500", "--binder-mcse-target=0.005", "--skip=2",
            "--runtime-budget-minutes=95", "--walltime=120", "--max-continuations=20",
            "--self-resubmit", "--exclude-host=gpu31", f"--run-root={args.campaign_dir}",
            f"--run-name=L{L}", "--dry-run",
        ]
        print("+", shlex.join(command))
        subprocess.run(command, cwd=REPO_ROOT, check=True)
        state = "validated" if profile.get("validated") is True else "tuning_required"
        if state != "validated":
            blocked.append(L)
        index["sizes"].append({"L": L, "profile": str(profile_path.resolve()),
                               "manifest": str((run_dir / "manifest.csv").resolve()), "state": state})
    atomic_json(args.campaign_dir / "campaign.json", index)
    print(f"campaign_index={args.campaign_dir / 'campaign.json'}")
    if blocked:
        print("production_blocked_unvalidated_L=" + ",".join(map(str, blocked)))
    if args.submit:
        if blocked:
            raise SystemExit("production submission blocked: validate every requested profile first")
        missing_preflight = [Path(item["manifest"]).parent for item in index["sizes"]
                             if not (Path(item["manifest"]).parent / "self_resubmit_preflight.ok").is_file()]
        if missing_preflight:
            raise SystemExit("production submission blocked: run and pass the compute-node "
                             "self-resubmission preflight for every requested L")
        for item in index["sizes"]:
            script = Path(item["manifest"]).parent / "lsf_job.sh"
            subprocess.run(["bsub"], input=script.read_text(encoding="utf-8"), text=True, check=True)
    return 0


def load_rows(manifest: Path) -> list[dict[str, str]]:
    with manifest.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def task_status(row: dict[str, str], active: set[int]) -> dict[str, object]:
    task = int(row["task_id"]); marker = Path(row["completion_marker"])
    progress_path = Path(row.get("progress_marker", ""))
    progress = json.loads(progress_path.read_text()) if progress_path.is_file() else {}
    state = "active" if task in active else "pending"
    if progress:
        state = str(progress.get("decision", "collecting"))
    if marker.is_file():
        state = json.loads(marker.read_text()).get("state", "complete")
    return {"task_id": task, "state": state, "samples": int(progress.get("samples", 0)),
            "target_samples": int(progress.get("target_samples", 0)), "active": task in active,
            "checkpoint": Path(row["checkpoint_path"]).is_file()}


def active_lsf_tasks(run_name: str, bjobs: str = "bjobs") -> set[int]:
    try:
        result = subprocess.run([bjobs, "-noheader", "-o", "job_name stat"],
                                text=True, capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return set()
    active = set()
    for line in result.stdout.splitlines():
        if not any(status in line.split() for status in ("PEND", "RUN", "PSUSP", "USUSP", "SSUSP")):
            continue
        match = re.search(rf"{re.escape(run_name)}(?:\[(\d+)\]|_t(\d+))", line)
        if match:
            active.add(int(match.group(1) or match.group(2)) - (1 if match.group(1) else 0))
    return active


def selected_manifests(args: argparse.Namespace) -> list[Path]:
    if args.manifest:
        return [args.manifest]
    campaign = json.loads(args.campaign_index.read_text(encoding="utf-8"))
    return [Path(item["manifest"]) for item in campaign["sizes"]]


def status(args: argparse.Namespace) -> int:
    summary = []
    for manifest in selected_manifests(args):
        rows = load_rows(manifest); submission_path = manifest.parent / "submission.json"
        run_name = json.loads(submission_path.read_text())["run_name"] if submission_path.is_file() else manifest.parent.name
        active = set(args.active_task) | active_lsf_tasks(run_name, args.bjobs)
        for row in rows:
            item = task_status(row, active); item["L"] = int(row["L"])
            item["manifest"] = str(manifest.resolve()); summary.append(item)
    print(json.dumps({"tasks": summary}, indent=2, sort_keys=True))
    return 0


def evaluate_cohort(rows: list[dict[str, str]], evaluation_json: Path | None) -> dict[str, object] | None:
    paths = [Path(row["progress_marker"]) for row in rows]
    if not all(path.is_file() for path in paths):
        return None
    progresses = [json.loads(path.read_text()) for path in paths]
    if not all(p.get("decision") == "awaiting_cohort" for p in progresses):
        return None
    samples = {int(p["samples"]) for p in progresses}
    if len(samples) != 1:
        return None
    if evaluation_json:
        result = json.loads(evaluation_json.read_text())
    else:
        binders = []; errors = []; overlaps = []; shifts = []
        with tempfile.TemporaryDirectory(dir=rows[0]["shard_dir"]) as directory:
            for row, progress in zip(rows, progresses):
                staged = dict(row); staged["stats_path"] = str(Path(directory) / f"{row['task_id']}.csv")
                staged["diagnostics_path"] = str(Path(directory) / f"{row['task_id']}_diag.csv")
                merge_shards(staged, progress)
                metadata, arrays = read_umbrella(Path(staged["stats_path"]))
                fit512 = estimate(arrays, 512); fit1024 = estimate(arrays, 1024)
                error = block_bootstrap(metadata, arrays, 50, 10, 1729 + int(row["task_id"]), 512)["binder_error"]
                binders.append(float(fit512["binder"])); errors.append(float(error))
                overlaps.append(min(fit512["neighbor_overlap"])); shifts.append(abs(float(fit512["binder"]) - float(fit1024["binder"])))
        phase_values = {}
        for phase in ("ordered", "disordered"):
            indices = [i for i, row in enumerate(rows) if row["init_phase"] == phase]
            phase_values[phase] = (float(np.mean([binders[i] for i in indices])),
                                   float(np.sqrt(sum(errors[i] ** 2 for i in indices)) / len(indices)))
        difference = abs(phase_values["ordered"][0] - phase_values["disordered"][0])
        combined = float(np.hypot(phase_values["ordered"][1], phase_values["disordered"][1]))
        result = {"binder_mcse": max(errors), "minimum_overlap": min(overlaps),
                  "maximum_bin_shift": max(shifts), "phase_difference": difference,
                  "phase_combined_error": combined}
    passed = (float(result["binder_mcse"]) <= float(rows[0]["binder_mcse_target"]) and
              float(result["minimum_overlap"]) >= 0.30 and
              float(result["maximum_bin_shift"]) <= 0.00125 and
              float(result["phase_difference"]) <= 2 * float(result["phase_combined_error"]))
    result["passed"] = passed; result["samples_per_window"] = samples.pop()
    return result


def scalar_submit(manifest: Path, task: int, allocation: int, dry_run: bool) -> None:
    config = json.loads((manifest.parent / "submission.json").read_text())
    selections = [f"({config['gpu_select']})", *[f"hname!='{h}'" for h in config["exclude_host"]]]
    resource = f"select[{' && '.join(selections)}] rusage[mem={config['mem_gb']:g}]"
    command = [config["bsub"], "-J", f"{config['run_name']}_t{task}", "-q", config["queue"],
               "-W", config["walltime"], "-n", str(config["cpus"]), "-R", resource,
               "-gpu", config["gpu_request"], "-env", f"all,UMBRELLA_TASK_ID={task},UMBRELLA_CONTINUATION={allocation}",
               "bash", str((manifest.parent / "lsf_job.sh").resolve())]
    print("+", shlex.join(command))
    if not dry_run:
        subprocess.run(command, check=True)


def preflight(args: argparse.Namespace) -> int:
    config = json.loads((args.manifest.parent / "submission.json").read_text())
    selections = [f"({config['gpu_select']})", *[f"hname!='{h}'" for h in config["exclude_host"]]]
    resource = f"select[{' && '.join(selections)}] rusage[mem={config['mem_gb']:g}]"
    marker = (args.manifest.parent / "self_resubmit_preflight.ok").resolve()
    payload = [sys.executable, str(REPO_ROOT / "scripts/lsf_self_resubmit_preflight.py"),
               "--marker", str(marker), "--bsub", config["bsub"], "--queue", config["queue"]]
    command = [config["bsub"], "-J", f"{config['run_name']}_preflight", "-q", config["queue"],
               "-W", "10", "-n", "1", "-R", resource, "-gpu", config["gpu_request"], *payload]
    print("+", shlex.join(command))
    if not args.dry_run:
        subprocess.run(command, check=True)
    return 0


def repair_manifest(args: argparse.Namespace, manifest: Path) -> None:
    rows = load_rows(manifest)
    evaluation = evaluate_cohort(rows, args.evaluation_json)
    if evaluation:
        samples = int(evaluation["samples_per_window"]); maximum = int(rows[0]["max_samples"])
        if evaluation["passed"]:
            decision, target = "complete", samples
        elif samples >= maximum:
            decision, target = "precision_failed", samples
        else:
            decision, target = "collecting", min(maximum, samples + int(rows[0]["sample_increment"]))
        for row in rows:
            path = Path(row["progress_marker"]); progress = json.loads(path.read_text())
            progress.update({"decision": decision, "target_samples": target, "last_evaluation": evaluation})
            atomic_json(path, progress)
        atomic_json(manifest.parent / f"evaluation_{samples:05d}.json", evaluation)
    config = json.loads((manifest.parent / "submission.json").read_text())
    active = set(args.active_task) | active_lsf_tasks(config["run_name"], args.bjobs)
    for row in rows:
        task = int(row["task_id"])
        marker = Path(row["completion_marker"])
        if task not in active and not marker.is_file():
            state = Path(row.get("progress_marker", row["completion_marker"]))
            claims = list(state.parent.glob(state.name + ".continuation-*"))
            allocation = max([int(path.name.rsplit("-", 1)[1]) for path in claims], default=0)
            if allocation >= int(row.get("max_continuations", "20")):
                print(f"task={task} state=continuation_limit_reached", file=sys.stderr)
                continue
            scalar_submit(manifest, task, allocation, args.dry_run)


def repair(args: argparse.Namespace) -> int:
    for manifest in selected_manifests(args):
        repair_manifest(args, manifest)
    return 0


def claim(args: argparse.Namespace) -> int:
    row = load_rows(args.manifest)[args.task_id]
    maximum = int(row.get("max_continuations", "20"))
    state = Path(row.get("progress_marker", row["completion_marker"]))
    return 0 if claim_continuation(state, args.allocation, maximum) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare"); prep.add_argument("--sizes", type=parse_sizes, default=list(SUPPORTED_SIZES))
    prep.add_argument("--campaign-dir", type=Path, default=REPO_ROOT / "runs/umbrella_allL_production")
    prep.add_argument("--profile-dir", type=Path, default=DEFAULT_PROFILE_DIR); prep.add_argument("--submit", action="store_true")
    for name in ("status", "repair"):
        item = sub.add_parser(name)
        source = item.add_mutually_exclusive_group(required=True)
        source.add_argument("--manifest", type=Path); source.add_argument("--campaign-index", type=Path)
        item.add_argument("--active-task", type=int, action="append", default=[]); item.add_argument("--bjobs", default="bjobs")
        if name == "repair":
            item.add_argument("--dry-run", action="store_true"); item.add_argument("--evaluation-json", type=Path)
    item = sub.add_parser("claim-continuation"); item.add_argument("--manifest", type=Path, required=True)
    item.add_argument("--task-id", type=int, required=True); item.add_argument("--allocation", type=int, required=True)
    item = sub.add_parser("preflight"); item.add_argument("--manifest", type=Path, required=True)
    item.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return {"prepare": prepare, "status": status, "repair": repair,
            "claim-continuation": claim, "preflight": preflight}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
