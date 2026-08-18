#!/usr/bin/env python3
"""Prepare, submit, and repair the LSF umbrella profile tuning campaign."""

from __future__ import annotations

import argparse
import csv
import json
import shlex
import subprocess
import sys
from pathlib import Path

from lsf_defaults import DEFAULT_MEM_GB, resolved_exclude_hosts, submit_bsub_script
from umbrella_campaign import active_lsf_tasks, claim, load_rows, preflight, repair_manifest
from umbrella_profiles import SUPPORTED_SIZES, load_profile, proposed_profile
from umbrella_runtime import atomic_json
from tune_umbrella_profile import (
    CANONICAL_POINT,
    LOCAL_JULIA,
    build_validation_report,
    canonical_gate_passes,
    confirmation_attempts,
    confirm_is_complete,
    nlf_candidates,
    pilot_is_complete,
    save_selected_nlf,
    stage_confirm_lsf,
    stage_pilot_lsf,
    stage_promote,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CAMPAIGN_DIR = REPO_ROOT / "runs/umbrella_tuning_lsf"
DEFAULT_PROFILE_DIR = REPO_ROOT / "configs/umbrella_profiles"
DEFAULT_REPORT_DIR = REPO_ROOT / "reports/umbrella_tuning"


def parse_sizes(text: str) -> list[int]:
    values = [int(value) for value in text.split(",")]
    if not values or len(values) != len(set(values)) or any(v not in SUPPORTED_SIZES for v in values):
        raise argparse.ArgumentTypeError(f"sizes must be unique members of {SUPPORTED_SIZES}")
    return values


def state_file(campaign_dir: Path, L: int) -> Path:
    return campaign_dir / f"L{L}" / "state.json"


def run_root_for(campaign_dir: Path, L: int) -> Path:
    return campaign_dir / f"L{L}"


def initial_state(L: int) -> dict[str, object]:
    return {
        "L": L,
        "stage": "pilot",
        "pilot_manifest": None,
        "nlf_output_dir": None,
        "nlf_candidates": [],
        "selected_n_lf": None,
        "n_lf_candidate_index": 0,
        "confirm_attempt_index": 0,
        "confirm_manifest": None,
        "confirm_dir": None,
        "confirm_samples": None,
        "confirm_thermalization_multiplier": 1.0,
        "validated": False,
    }


def load_state(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: dict[str, object]) -> None:
    atomic_json(path, state)


def tune_args_from_namespace(args: argparse.Namespace, L: int) -> argparse.Namespace:
    return argparse.Namespace(
        L=L,
        profile_dir=args.profile_dir,
        run_root=run_root_for(args.campaign_dir, L),
        report_dir=args.report_dir,
        julia=args.julia,
        tsp=args.tsp,
        scheduler="lsf",
        slots=1,
        dry_run=args.dry_run,
        fresh_pilot=args.fresh_pilot,
        pilot_max_thermalization_sweeps=args.pilot_max_thermalization_sweeps,
        pilot_thermalization_sweeps=args.pilot_thermalization_sweeps,
        pilot_continuations=args.max_continuations,
        pilot_samples=args.pilot_samples,
        confirm_samples=args.confirm_samples,
        confirm_attempts=args.confirm_attempts,
        confirm_samples_max=args.confirm_samples_max,
        confirm_sample_schedule=args.confirm_sample_schedule,
        confirm_thermalization_escalation=args.confirm_thermalization_escalation,
        nlf_probe_sweeps=args.nlf_probe_sweeps,
        runtime_budget_minutes=args.runtime_budget_minutes,
        skip=args.skip,
        n_lf=args.n_lf,
        try_alternate_nlf=args.try_alternate_nlf,
        walltime=args.walltime,
        max_continuations=args.max_continuations,
        gpu_select=args.gpu_select,
        queue=args.queue,
        exclude_host=args.exclude_host,
        mem_gb=getattr(args, "mem_gb", DEFAULT_MEM_GB),
        stage="all",
    )


def profile_validated(profile_dir: Path, L: int) -> bool:
    path = profile_dir / f"L{L}.json"
    if not path.is_file():
        return False
    return load_profile(path, L, require_validated=False).get("validated") is True


def write_profile_if_missing(directory: Path, L: int) -> Path:
    path = directory / f"L{L}.json"
    if not path.is_file():
        atomic_json(path, proposed_profile(L))
    return path


def manifest_complete(manifest: Path) -> bool:
    return confirm_is_complete(manifest.parent)


def nlf_pending_probe_ids(output_dir: Path) -> list[int]:
    manifest = output_dir / "sweep_manifest.csv"
    if not manifest.is_file():
        return []
    pending: list[int] = []
    with manifest.open(newline="", encoding="utf-8") as handle:
        for task in csv.DictReader(handle):
            if not Path(task["output"]).is_file():
                pending.append(int(task["probe_id"]))
    return pending


def nlf_all_probes_done(output_dir: Path) -> bool:
    manifest = output_dir / "sweep_manifest.csv"
    if not manifest.is_file():
        return False
    with manifest.open(newline="", encoding="utf-8") as handle:
        tasks = list(csv.DictReader(handle))
    if not tasks:
        return False
    return all(Path(task["output"]).is_file() for task in tasks)


def nlf_has_recommendations(output_dir: Path) -> bool:
    recommendations = output_dir / "recommendations.csv"
    if not recommendations.is_file():
        return False
    with recommendations.open(newline="", encoding="utf-8") as handle:
        return any(row.get("rank") == "1" for row in csv.DictReader(handle))


def summarize_nlf(output_dir: Path) -> int:
    command = [
        sys.executable, str(REPO_ROOT / "scripts/explore_umbrella_nlf.py"),
        f"--summarize-manifest={output_dir / 'sweep_manifest.csv'}",
    ]
    print("+", shlex.join(command))
    return subprocess.run(command, cwd=REPO_ROOT, check=False).returncode


def nlf_prepare_command(tune_args: argparse.Namespace, pilot_dir: Path,
                        output_dir: Path) -> list[str]:
    max_lag = min(500, tune_args.nlf_probe_sweeps)
    lags = ",".join(str(value) for value in (1, 10, 100, max_lag)
                    if value <= tune_args.nlf_probe_sweeps)
    return [
        sys.executable, str(REPO_ROOT / "scripts/explore_umbrella_nlf.py"),
        f"--run-dir={pilot_dir}",
        f"--probe-sweeps={tune_args.nlf_probe_sweeps}",
        f"--lags={lags}",
        "--scheduler=lsf",
        "--prepare-only",
        f"--slots=1",
        f"--julia={tune_args.julia}",
        f"--output-dir={output_dir}",
        f"--queue={tune_args.queue}",
        f"--walltime={tune_args.walltime}",
        f"--gpu-select={tune_args.gpu_select}",
        *[f"--exclude-host={host}" for host in tune_args.exclude_host],
        f"--mem-gb={getattr(tune_args, 'mem_gb', DEFAULT_MEM_GB):g}",
    ]


def ranked_nlf_candidates(output_dir: Path) -> list[int]:
    recommendations = output_dir / "recommendations.csv"
    if not recommendations.is_file():
        return []
    candidates: list[int] = []
    with recommendations.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("eligible") != "True":
                continue
            value = int(row["n_lf"])
            if value not in candidates:
                candidates.append(value)
    return candidates


def selected_nlf_from_recommendations(output_dir: Path) -> int | None:
    recommendations = output_dir / "recommendations.csv"
    if not recommendations.is_file():
        return None
    with recommendations.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("rank") == "1":
                return int(row["n_lf"])
    return None


def campaign_item_from_state(L: int, state: dict[str, object], path: Path) -> dict[str, object]:
    return {
        "L": L,
        "stage": state.get("stage"),
        "state_path": str(path.resolve()),
        "pilot_manifest": state.get("pilot_manifest"),
        "nlf_output_dir": state.get("nlf_output_dir"),
        "confirm_manifest": state.get("confirm_manifest"),
    }


def discover_state_files(campaign_dir: Path) -> list[tuple[int, Path, dict[str, object]]]:
    found: list[tuple[int, Path, dict[str, object]]] = []
    for path in sorted(campaign_dir.glob("L*/state.json")):
        state = load_state(path)
        try:
            L = int(state.get("L", path.parent.name[1:]))
        except (TypeError, ValueError):
            continue
        found.append((L, path, state))
    return found


def sync_campaign_index(args: argparse.Namespace) -> Path:
    args.campaign_dir.mkdir(parents=True, exist_ok=True)
    index_path = args.campaign_dir / "campaign.json"
    if index_path.is_file():
        index = json.loads(index_path.read_text(encoding="utf-8"))
    else:
        index = {
            "schema_version": 1,
            "campaign": "umbrella_tuning_lsf",
            "Z": CANONICAL_POINT[0],
            "m2": CANONICAL_POINT[1],
            "sizes": [],
        }
    by_lattice = {int(item["L"]): item for item in index.get("sizes", [])}
    for L, path, state in discover_state_files(args.campaign_dir):
        by_lattice[L] = campaign_item_from_state(L, state, path)
    index["sizes"] = [by_lattice[L] for L in sorted(by_lattice)]
    atomic_json(index_path, index)
    return index_path


def bsub_script(script_path: Path, *, dry_run: bool, job_name: str | None = None,
               task_ids: list[int] | None = None) -> None:
    submit_bsub_script(script_path, dry_run=dry_run, job_name=job_name, task_ids=task_ids)


def prepare_size(args: argparse.Namespace, L: int) -> dict[str, object]:
    write_profile_if_missing(args.profile_dir, L)
    L_dir = run_root_for(args.campaign_dir, L)
    L_dir.mkdir(parents=True, exist_ok=True)
    path = state_file(args.campaign_dir, L)
    if args.force_revalidate:
        state = initial_state(L)
    elif path.is_file():
        state = load_state(path)
    else:
        state = initial_state(L)
    if profile_validated(args.profile_dir, L) and not args.force_revalidate:
        state["stage"] = "validated"
        state["validated"] = True
        save_state(path, state)
        return {"L": L, "stage": "validated", "state_path": str(path.resolve())}

    tune_args = tune_args_from_namespace(args, L)
    campaign_dry_run = bool(args.dry_run)
    tune_args.dry_run = False
    tune_args.fresh_pilot = bool(args.force_revalidate or args.fresh_pilot) and not campaign_dry_run
    stage = str(state["stage"])
    if stage == "pilot":
        pilot_dir = stage_pilot_lsf(tune_args)
        state["pilot_manifest"] = str((pilot_dir / "manifest.csv").resolve())
    elif stage == "nlf":
        pilot_dir = L_dir / f"tune_L{L}_pilot"
        output_dir = Path(state["nlf_output_dir"]) if state.get("nlf_output_dir") else args.report_dir / f"L{L}_nlf"
        if not (output_dir / "sweep_manifest.csv").is_file():
            command = nlf_prepare_command(tune_args, pilot_dir, output_dir)
            print("+", shlex.join(command))
            subprocess.run(command, cwd=REPO_ROOT, check=True)
        state["nlf_output_dir"] = str(output_dir.resolve())
    elif stage == "confirm":
        selected = state.get("selected_n_lf")
        if selected is None:
            raise SystemExit(f"L={L} confirm stage without selected_n_lf")
        existing = Path(str(state["confirm_dir"])) if state.get("confirm_dir") else None
        if (
            existing is not None
            and (existing / "manifest.csv").is_file()
            and not args.force_revalidate
        ):
            state["confirm_manifest"] = str((existing / "manifest.csv").resolve())
            state["confirm_dir"] = str(existing.resolve())
        else:
            attempts = confirmation_attempts(tune_args)
            index = int(state.get("confirm_attempt_index", 0))
            if index >= len(attempts):
                raise SystemExit(f"L={L} confirm attempts exhausted")
            samples, multiplier = attempts[index]
            confirm_dir = stage_confirm_lsf(
                tune_args, int(selected),
                confirm_samples=samples,
                thermalization_multiplier=multiplier,
            )
            state["confirm_manifest"] = str((confirm_dir / "manifest.csv").resolve())
            state["confirm_dir"] = str(confirm_dir.resolve())
            state["confirm_samples"] = samples
            state["confirm_thermalization_multiplier"] = multiplier
    save_state(path, state)
    return {"L": L, "stage": state["stage"], "state_path": str(path.resolve())}


def prepare(args: argparse.Namespace) -> int:
    args.campaign_dir.mkdir(parents=True, exist_ok=True)
    args.report_dir.mkdir(parents=True, exist_ok=True)
    index_path = args.campaign_dir / "campaign.json"
    if index_path.is_file():
        index = json.loads(index_path.read_text(encoding="utf-8"))
    else:
        index = {
            "schema_version": 1,
            "campaign": "umbrella_tuning_lsf",
            "Z": CANONICAL_POINT[0],
            "m2": CANONICAL_POINT[1],
            "sizes": [],
        }
    by_lattice = {int(item["L"]): item for item in index.get("sizes", [])}
    for L, path, state in discover_state_files(args.campaign_dir):
        by_lattice[L] = campaign_item_from_state(L, state, path)
    for L in args.sizes:
        item = prepare_size(args, L)
        path = state_file(args.campaign_dir, L)
        state = load_state(path)
        by_lattice[L] = campaign_item_from_state(L, state, path)
        by_lattice[L].update({
            "pilot_manifest": state.get("pilot_manifest"),
            "nlf_output_dir": state.get("nlf_output_dir"),
            "confirm_manifest": state.get("confirm_manifest"),
        })
    index["sizes"] = [by_lattice[L] for L in sorted(by_lattice)]
    atomic_json(index_path, index)
    print(f"campaign_index={index_path}")
    return 0


def selected_states(args: argparse.Namespace) -> list[tuple[int, dict[str, object]]]:
    if args.L is not None:
        path = state_file(args.campaign_dir, args.L)
        if not path.is_file():
            raise SystemExit(f"missing state for L={args.L}: {path}")
        return [(args.L, load_state(path))]
    sync_campaign_index(args)
    by_lattice: dict[int, dict[str, object]] = {}
    for L, _path, state in discover_state_files(args.campaign_dir):
        by_lattice[L] = state
    if not by_lattice:
        campaign = json.loads((args.campaign_dir / "campaign.json").read_text(encoding="utf-8"))
        for item in campaign.get("sizes", []):
            L = int(item["L"])
            path = state_file(args.campaign_dir, L)
            if path.is_file():
                by_lattice[L] = load_state(path)
    return [(L, by_lattice[L]) for L in sorted(by_lattice)]


def status(args: argparse.Namespace) -> int:
    rows = []
    for L, state in selected_states(args):
        rows.append({
            "L": L,
            "stage": state.get("stage"),
            "validated": profile_validated(args.profile_dir, L),
            "selected_n_lf": state.get("selected_n_lf"),
            "confirm_attempt_index": state.get("confirm_attempt_index"),
            "pilot_manifest": state.get("pilot_manifest"),
            "nlf_output_dir": state.get("nlf_output_dir"),
            "confirm_manifest": state.get("confirm_manifest"),
        })
    print(json.dumps({"sizes": rows}, indent=2, sort_keys=True))
    return 0


def active_manifest_for_state(state: dict[str, object]) -> Path | None:
    stage = str(state.get("stage"))
    if stage == "pilot" and state.get("pilot_manifest"):
        return Path(str(state["pilot_manifest"]))
    if stage == "confirm" and state.get("confirm_manifest"):
        return Path(str(state["confirm_manifest"]))
    return None


def preflight_cmd(args: argparse.Namespace) -> int:
    if args.L is None:
        raise SystemExit("preflight requires --L")
    _, state = selected_states(args)[0]
    manifest = active_manifest_for_state(state)
    if manifest is None:
        raise SystemExit(f"no active pilot/confirm manifest for L={args.L} stage={state.get('stage')}")
    preflight_args = argparse.Namespace(manifest=manifest, dry_run=args.dry_run)
    return preflight(preflight_args)


def submit_nlf_jobs(output_dir: Path, *, dry_run: bool, bjobs: str) -> None:
    pending = nlf_pending_probe_ids(output_dir)
    script = output_dir / "lsf_job.sh"
    if not pending:
        print(f"L nlf probes already complete: {output_dir}")
        return
    if not script.is_file():
        raise SystemExit(f"missing nlf LSF script: {script}")
    submission_path = output_dir / "submission.json"
    run_name = (
        json.loads(submission_path.read_text(encoding="utf-8"))["run_name"]
        if submission_path.is_file() else output_dir.name
    )
    active = active_lsf_tasks(run_name, bjobs)
    pending = [probe for probe in pending if probe not in active]
    if not pending:
        print(f"pending nlf probes already queued: {run_name}")
        return
    bsub_script(script, dry_run=dry_run, task_ids=pending)


def submit_size(args: argparse.Namespace, L: int, state: dict[str, object]) -> None:
    stage = str(state.get("stage"))
    if stage == "validated":
        print(f"L={L} already validated; skipping submit")
        return
    if stage == "pilot":
        manifest = Path(str(state["pilot_manifest"]))
        script = manifest.parent / "lsf_job.sh"
        if manifest_complete(manifest):
            print(f"L={L} pilot already complete")
            return
        bsub_script(script, dry_run=args.dry_run)
        return
    if stage == "nlf":
        output_dir = Path(str(state["nlf_output_dir"]))
        if nlf_has_recommendations(output_dir):
            print(f"L={L} nlf recommendations already exist")
            return
        if nlf_all_probes_done(output_dir):
            print(f"L={L} nlf probes complete; run repair to summarize")
            return
        submit_nlf_jobs(output_dir, dry_run=args.dry_run, bjobs=args.bjobs)
        return
    if stage == "confirm":
        manifest = Path(str(state["confirm_manifest"]))
        if manifest_complete(manifest):
            print(f"L={L} confirm already complete")
            return
        script = manifest.parent / "lsf_job.sh"
        bsub_script(script, dry_run=args.dry_run)
        return
    print(f"L={L} stage={stage} has no GPU submission")


def submit(args: argparse.Namespace) -> int:
    for L, state in selected_states(args):
        submit_size(args, L, state)
    return 0


def advance_pilot(args: argparse.Namespace, L: int, state: dict[str, object]) -> bool:
    manifest = Path(str(state["pilot_manifest"]))
    if not pilot_is_complete(manifest.parent):
        repair_args = argparse.Namespace(
            manifest=manifest, dry_run=args.dry_run, active_task=[],
            evaluation_json=None, bjobs=args.bjobs,
        )
        repair_manifest(repair_args, manifest)
        return False
    state["stage"] = "nlf"
    tune_args = tune_args_from_namespace(args, L)
    output_dir = args.report_dir / f"L{L}_nlf"
    command = nlf_prepare_command(tune_args, manifest.parent, output_dir)
    print("+", shlex.join(command))
    subprocess.run(command, cwd=REPO_ROOT, check=True)
    state["nlf_output_dir"] = str(output_dir.resolve())
    save_state(state_file(args.campaign_dir, L), state)
    return True


def advance_nlf(args: argparse.Namespace, L: int, state: dict[str, object]) -> bool:
    output_dir = Path(str(state["nlf_output_dir"]))
    if not nlf_all_probes_done(output_dir):
        return False
    if not nlf_has_recommendations(output_dir):
        if summarize_nlf(output_dir) != 0:
            return False
    selected = selected_nlf_from_recommendations(output_dir)
    if selected is None:
        state["stage"] = "failed"
        save_state(state_file(args.campaign_dir, L), state)
        return False
    state["nlf_candidates"] = ranked_nlf_candidates(output_dir)
    state["selected_n_lf"] = selected
    state["n_lf_candidate_index"] = 0
    state["confirm_attempt_index"] = 0
    state["stage"] = "confirm"
    tune_args = tune_args_from_namespace(args, L)
    attempts = confirmation_attempts(tune_args)
    samples, multiplier = attempts[0]
    confirm_dir = stage_confirm_lsf(
        tune_args, selected,
        confirm_samples=samples,
        thermalization_multiplier=multiplier,
    ) if not args.dry_run else run_root_for(args.campaign_dir, L) / f"tune_L{L}_confirm_nlf{selected}"
    if args.dry_run:
        print(f"would prepare confirm for L={L} n_lf={selected}")
    else:
        state["confirm_manifest"] = str((confirm_dir / "manifest.csv").resolve())
        state["confirm_dir"] = str(confirm_dir.resolve())
        state["confirm_samples"] = samples
        state["confirm_thermalization_multiplier"] = multiplier
    save_state(state_file(args.campaign_dir, L), state)
    return True


def start_next_confirm_attempt(args: argparse.Namespace, L: int,
                               state: dict[str, object]) -> bool:
    tune_args = tune_args_from_namespace(args, L)
    candidates = nlf_candidates(tune_args, int(state["selected_n_lf"]))
    candidate_index = int(state.get("n_lf_candidate_index", 0))
    attempt_index = int(state.get("confirm_attempt_index", 0)) + 1
    attempts = confirmation_attempts(tune_args)
    if attempt_index < len(attempts):
        state["confirm_attempt_index"] = attempt_index
        samples, multiplier = attempts[attempt_index]
    elif candidate_index + 1 < len(candidates):
        state["n_lf_candidate_index"] = candidate_index + 1
        state["selected_n_lf"] = candidates[candidate_index + 1]
        state["confirm_attempt_index"] = 0
        samples, multiplier = attempts[0]
    else:
        state["stage"] = "failed"
        save_state(state_file(args.campaign_dir, L), state)
        return False
    selected = int(state["selected_n_lf"])
    if args.dry_run:
        print(
            f"would retry confirm for L={L} n_lf={selected} "
            f"samples={samples} thermalization_x={multiplier:g}"
        )
        return False
    confirm_dir = stage_confirm_lsf(
        tune_args, selected,
        confirm_samples=samples,
        thermalization_multiplier=multiplier,
    )
    state["confirm_manifest"] = str((confirm_dir / "manifest.csv").resolve())
    state["confirm_dir"] = str(confirm_dir.resolve())
    state["confirm_samples"] = samples
    state["confirm_thermalization_multiplier"] = multiplier
    save_state(state_file(args.campaign_dir, L), state)
    return True


def advance_confirm(args: argparse.Namespace, L: int, state: dict[str, object]) -> bool:
    manifest = Path(str(state["confirm_manifest"]))
    confirm_dir = Path(str(state["confirm_dir"]))
    if not confirm_is_complete(confirm_dir):
        repair_args = argparse.Namespace(
            manifest=manifest, dry_run=args.dry_run, active_task=[],
            evaluation_json=None, bjobs=args.bjobs,
        )
        repair_manifest(repair_args, manifest)
        return False
    tune_args = tune_args_from_namespace(args, L)
    selected = int(state["selected_n_lf"])
    report = build_validation_report(
        tune_args, selected, confirm_dir,
        confirm_samples=state.get("confirm_samples"),
        thermalization_multiplier=float(state.get("confirm_thermalization_multiplier", 1.0)),
    )
    if canonical_gate_passes(report):
        save_selected_nlf(tune_args, selected)
        if args.dry_run:
            print(f"would promote L={L} n_lf={selected}")
            state["stage"] = "validated"
            state["validated"] = True
            save_state(state_file(args.campaign_dir, L), state)
            return True
        rc = stage_promote(tune_args, selected, confirm_dir)
        if rc == 0:
            state["stage"] = "validated"
            state["validated"] = True
            save_state(state_file(args.campaign_dir, L), state)
            return True
    print(
        f"canonical gate failed for L={L} n_lf={selected} "
        f"z={report.get('canonical_combined_z')}",
        file=sys.stderr,
    )
    return start_next_confirm_attempt(args, L, state)


def advance_promote(args: argparse.Namespace, L: int, state: dict[str, object]) -> bool:
    if profile_validated(args.profile_dir, L):
        state["stage"] = "validated"
        state["validated"] = True
        save_state(state_file(args.campaign_dir, L), state)
        return True
    return False


def repair_size(args: argparse.Namespace, L: int, state: dict[str, object]) -> None:
    if state.get("validated") or state.get("stage") == "validated":
        return
    stage = str(state.get("stage"))
    if stage == "pilot":
        if advance_pilot(args, L, state):
            submit_size(args, L, state)
        return
    if stage == "nlf":
        output_dir = Path(str(state["nlf_output_dir"]))
        if nlf_all_probes_done(output_dir):
            if advance_nlf(args, L, state):
                submit_size(args, L, state)
            return
        submit_nlf_jobs(output_dir, dry_run=args.dry_run, bjobs=args.bjobs)
        return
    if stage == "confirm":
        if advance_confirm(args, L, state) and state.get("stage") == "confirm":
            submit_size(args, L, state)
        return
    if stage == "promote":
        advance_promote(args, L, state)


def repair(args: argparse.Namespace) -> int:
    sync_campaign_index(args)
    for L, state in selected_states(args):
        repair_size(args, L, state)
    sync_campaign_index(args)
    return 0


def claim_continuation(args: argparse.Namespace) -> int:
    return claim(args)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="command", required=True)

    def add_common(item: argparse.ArgumentParser) -> None:
        item.add_argument("--campaign-dir", type=Path, default=DEFAULT_CAMPAIGN_DIR)
        item.add_argument("--profile-dir", type=Path, default=DEFAULT_PROFILE_DIR)
        item.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
        item.add_argument("--julia", default=str(LOCAL_JULIA) if LOCAL_JULIA.is_file() else "julia")
        item.add_argument("--tsp", default="tsp")
        item.add_argument("--dry-run", action="store_true")
        item.add_argument("--force-revalidate", action="store_true",
                          help="restart tuning for a profile even if already validated")
        item.add_argument("--fresh-pilot", action="store_true")
        item.add_argument("--pilot-thermalization-sweeps", type=int, default=5000)
        item.add_argument("--pilot-max-thermalization-sweeps", type=int, default=0)
        item.add_argument("--pilot-samples", type=int, default=200)
        item.add_argument("--confirm-samples", type=int, default=1000)
        item.add_argument("--confirm-attempts", type=int, default=3)
        item.add_argument("--confirm-samples-max", type=int, default=10_000)
        item.add_argument("--confirm-sample-schedule", default="")
        item.add_argument("--confirm-thermalization-escalation",
                          dest="confirm_thermalization_escalation",
                          action=argparse.BooleanOptionalAction, default=True)
        item.add_argument("--nlf-probe-sweeps", type=int, default=3000)
        item.add_argument("--runtime-budget-minutes", type=float, default=95.0)
        item.add_argument("--skip", type=int, default=2)
        item.add_argument("--n-lf", type=int)
        item.add_argument("--try-alternate-nlf", dest="try_alternate_nlf",
                          action=argparse.BooleanOptionalAction, default=True)
        item.add_argument("--walltime", default="120")
        item.add_argument("--max-continuations", type=int, default=20)
        item.add_argument("--gpu-select", default="h200 || h100 || l40s")
        item.add_argument("--queue", default="short_gpu")
        item.add_argument("--exclude-host", action="append", default=None)
        item.add_argument("--bjobs", default="bjobs")
        item.add_argument("--mem-gb", type=float, default=DEFAULT_MEM_GB)

    prep = sub.add_parser("prepare")
    add_common(prep)
    prep.add_argument("--sizes", type=parse_sizes, default=list(SUPPORTED_SIZES))

    for name in ("status", "repair", "submit"):
        item = sub.add_parser(name)
        add_common(item)
        item.add_argument("--L", type=int)

    item = sub.add_parser("preflight")
    add_common(item)
    item.add_argument("--L", type=int, required=True)

    item = sub.add_parser("claim-continuation")
    item.add_argument("--manifest", type=Path, required=True)
    item.add_argument("--task-id", type=int, required=True)
    item.add_argument("--allocation", type=int, required=True)

    return result


def main() -> int:
    args = parser().parse_args()
    args.exclude_host = resolved_exclude_hosts(args.exclude_host)
    handlers = {
        "prepare": prepare,
        "status": status,
        "preflight": preflight_cmd,
        "submit": submit,
        "repair": repair,
        "claim-continuation": claim_continuation,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
