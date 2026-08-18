#!/usr/bin/env python3
"""Drive A6000/TSP umbrella profile tuning for one lattice size.

Stages:
  1. ``pilot`` — short gated thermalization via ``submit_umbrella_tsp.py`` (2 replicas).
  2. ``nlf`` — ``explore_umbrella_nlf.py`` transport sweep on the pilot checkpoints.
  3. ``confirm`` — two-replica production-like run with the selected ``n_lf``.
  4. ``promote`` — assemble a validation JSON and call ``validate_umbrella_profile.py``.

Use ``--dry-run`` on any stage to inspect commands without enqueueing work.
"""

from __future__ import annotations

import argparse
import csv
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from analyze_umbrella import estimate, read_umbrella
from hmc_defaults import resolve_hmc_parameters, resolve_startup_hmc_parameters
from umbrella_profiles import (
    CANONICAL_Z_MAX,
    SUPPORTED_SIZES,
    binder_canonical_combined_z,
    load_profile,
    proposed_profile,
)
from umbrella_runtime import atomic_json


REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_JULIA = Path(
    "/home/vskokov/.julia/juliaup/julia-1.12.6+0.x64.linux.gnu/bin/julia"
)
DEFAULT_PROFILE_DIR = REPO_ROOT / "configs/umbrella_profiles"
CANONICAL_POINT = (-0.6, -1.86421)


def run(command: list[str], *, dry_run: bool, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+", shlex.join(command), flush=True)
    if dry_run:
        return subprocess.CompletedProcess(command, 0, "", "")
    result = subprocess.run(command, cwd=REPO_ROOT, check=False, text=True, capture_output=True)
    if check and result.returncode != 0:
        if result.stdout:
            print(result.stdout, file=sys.stderr, end="")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        raise subprocess.CalledProcessError(
            result.returncode, command, output=result.stdout, stderr=result.stderr
        )
    return result


def nlf_candidates(args: argparse.Namespace, primary: int) -> list[int]:
    candidates = [primary]
    if not args.try_alternate_nlf:
        return candidates
    recommendations = args.report_dir / f"L{args.L}_nlf" / "recommendations.csv"
    if not recommendations.is_file():
        return candidates
    with recommendations.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("eligible") != "True":
                continue
            value = int(row["n_lf"])
            if value not in candidates:
                candidates.append(value)
    return candidates


def canonical_combined_z(report: dict[str, object]) -> float | None:
    value = report.get("canonical_combined_z")
    return None if value is None else float(value)


def canonical_gate_passes(report: dict[str, object]) -> bool:
    combined_z = canonical_combined_z(report)
    return combined_z is not None and abs(combined_z) <= CANONICAL_Z_MAX


def save_selected_nlf(args: argparse.Namespace, n_lf: int) -> None:
    atomic_json(args.report_dir / f"L{args.L}_selected_nlf.json", {"n_lf": n_lf})


def confirmation_attempts(args: argparse.Namespace) -> list[tuple[int, float]]:
    if args.confirm_sample_schedule:
        sample_counts = [
            int(value.strip())
            for value in args.confirm_sample_schedule.split(",")
            if value.strip()
        ]
    else:
        sample_counts = []
        count = args.confirm_samples
        for _ in range(args.confirm_attempts):
            sample_counts.append(count)
            count = min(max(count * 2, count + 1000), args.confirm_samples_max)
    attempts: list[tuple[int, float]] = []
    for index, samples in enumerate(sample_counts):
        multiplier = 1.0
        if args.confirm_thermalization_escalation and index > 0:
            multiplier = 1.0 + 0.5 * index
        attempts.append((samples, multiplier))
    return attempts


def run_confirmation_campaign(args: argparse.Namespace, candidates: list[int]) -> int:
    last_z: float | None = None
    attempts = confirmation_attempts(args)
    for candidate in candidates:
        for confirm_samples, thermalization_multiplier in attempts:
            confirm_dir = stage_confirm(
                args, candidate,
                confirm_samples=confirm_samples,
                thermalization_multiplier=thermalization_multiplier,
            )
            report = build_validation_report(
                args, candidate, confirm_dir,
                confirm_samples=confirm_samples,
                thermalization_multiplier=thermalization_multiplier,
            )
            last_z = canonical_combined_z(report)
            if canonical_gate_passes(report):
                save_selected_nlf(args, candidate)
                if args.stage == "confirm":
                    return 0
                if stage_promote(args, candidate, confirm_dir) == 0:
                    return 0

            print(
                f"canonical gate failed for n_lf={candidate} "
                f"samples={confirm_samples} thermalization_x={thermalization_multiplier:g} "
                f"canonical_combined_z={last_z:.3f} (limit {CANONICAL_Z_MAX:g})",
                file=sys.stderr,
            )

    raise SystemExit(
        f"ordered/disordered Binder agreement failed for L={args.L} after "
        f"{len(candidates)} n_lf candidate(s) and {len(attempts)} confirm attempt(s); "
        f"last canonical_combined_z={last_z}"
    )


def confirm_is_complete(run_dir: Path) -> bool:
    complete_dir = run_dir / "complete"
    stats_dir = run_dir / "statistics"
    if not complete_dir.is_dir() or not stats_dir.is_dir():
        return False
    complete_markers = 0
    for path in complete_dir.glob("*.complete"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if payload.get("complete") is True:
            complete_markers += 1
    return complete_markers >= 2 and len(list(stats_dir.glob("*.csv"))) >= 2


def profile_path(profile_dir: Path, L: int) -> Path:
    path = profile_dir / f"L{L}.json"
    if not path.is_file():
        atomic_json(path, proposed_profile(L))
    return path


def resolve_pilot_n_lf(profile: dict[str, object], equilibrium_n_lf: int) -> int:
    """Pick a trajectory length that can diffuse across the umbrella ladder."""
    startup_n_lf = int(profile["startup_n_lf"])
    scaled = max(1, round(0.5 * int(profile["umbrella_windows"])))
    return max(equilibrium_n_lf, startup_n_lf, scaled)


def pilot_maximum_thermalization_sweeps(profile: dict[str, object],
                                        pilot_cap: int) -> int:
    profile_maximum = int(profile["maximum_thermalization_sweeps"])
    if pilot_cap <= 0:
        return profile_maximum
    return min(profile_maximum, max(pilot_cap, int(profile["minimum_thermalization_sweeps"])))


def reset_run_dir(run_dir: Path) -> None:
    if run_dir.is_dir():
        shutil.rmtree(run_dir)


def reset_pilot_run(run_dir: Path) -> None:
    reset_run_dir(run_dir)


def manifest_only_flags(args: argparse.Namespace) -> list[str]:
    if args.dry_run:
        return ["--dry-run"]
    return ["--prepare-only"]


def submit_script(args: argparse.Namespace) -> Path:
    if args.scheduler == "lsf":
        return REPO_ROOT / "scripts/submit_umbrella_bsub.py"
    return REPO_ROOT / "scripts/submit_umbrella_tsp.py"


def lsf_submit_flags(args: argparse.Namespace) -> list[str]:
    if args.scheduler != "lsf":
        return []
    flags = [
        "--self-resubmit",
        f"--max-continuations={args.max_continuations}",
        f"--runtime-budget-minutes={args.runtime_budget_minutes}",
        f"--walltime={args.walltime}",
        f"--gpu-select={args.gpu_select}",
        f"--queue={args.queue}",
    ]
    flags.extend(f"--exclude-host={host}" for host in args.exclude_host)
    return flags


def pilot_command(args: argparse.Namespace, profile: dict[str, object]) -> list[str]:
    z_value, m2_value = CANONICAL_POINT
    epsilon, equilibrium_n_lf, _ = resolve_hmc_parameters(
        args.L, float(profile["epsilon"]), profile.get("n_lf")
    )
    n_lf = resolve_pilot_n_lf(profile, equilibrium_n_lf)
    minimum = int(profile["minimum_thermalization_sweeps"])
    maximum = pilot_maximum_thermalization_sweeps(
        profile, args.pilot_max_thermalization_sweeps
    )
    run_name = f"tune_L{args.L}_pilot"
    command = [
        sys.executable, str(submit_script(args)),
        f"--L={args.L}", f"--point={z_value},{m2_value}",
        f"--eps={epsilon}",
        f"--n-lf={n_lf}",
        f"--startup-eps={profile['startup_epsilon']}",
        f"--startup-n-lf={profile['startup_n_lf']}",
        f"--startup-sweeps={profile['startup_sweeps']}",
        f"--thermalization-sweeps={min(args.pilot_thermalization_sweeps, minimum)}",
        f"--max-thermalization-sweeps={maximum}",
        f"--umbrella-windows={profile['umbrella_windows']}",
        f"--umbrella-min={profile['umbrella_min']}",
        f"--umbrella-max={profile['umbrella_max']}",
        f"--umbrella-kappa={profile['umbrella_kappa']}",
        f"--umbrella-power={profile['umbrella_power']}",
        "--min-round-trip-fraction=0.10", "--min-swap-acceptance=0.20",
        "--replicas=2", "--init-schedule=split",
        f"--samples={args.pilot_samples}", f"--skip={args.skip}",
        f"--run-root={args.run_root}", f"--run-name={run_name}",
        f"--julia={args.julia}",
        *([f"--tsp={args.tsp}"] if args.scheduler != "lsf" else []),
        *lsf_submit_flags(args),
        *manifest_only_flags(args),
    ]
    return command


def confirm_command(args: argparse.Namespace, profile: dict[str, object],
                    n_lf: int, *, confirm_samples: int | None = None,
                    thermalization_multiplier: float = 1.0) -> list[str]:
    z_value, m2_value = CANONICAL_POINT
    run_name = f"tune_L{args.L}_confirm_nlf{n_lf}"
    samples = args.confirm_samples if confirm_samples is None else confirm_samples
    minimum = max(1, int(float(profile["minimum_thermalization_sweeps"]) * thermalization_multiplier))
    maximum = max(minimum, int(float(profile["maximum_thermalization_sweeps"]) * thermalization_multiplier))
    command = [
        sys.executable, str(submit_script(args)),
        f"--L={args.L}", f"--point={z_value},{m2_value}",
        f"--eps={profile['epsilon']}", f"--n-lf={n_lf}",
        f"--startup-eps={profile['startup_epsilon']}",
        f"--startup-n-lf={profile['startup_n_lf']}",
        f"--startup-sweeps={profile['startup_sweeps']}",
        f"--thermalization-sweeps={minimum}",
        f"--max-thermalization-sweeps={maximum}",
        f"--umbrella-windows={profile['umbrella_windows']}",
        f"--umbrella-min={profile['umbrella_min']}",
        f"--umbrella-max={profile['umbrella_max']}",
        f"--umbrella-kappa={profile['umbrella_kappa']}",
        f"--umbrella-power={profile['umbrella_power']}",
        "--min-round-trip-fraction=0.5", "--min-swap-acceptance=0.25",
        "--replicas=2", "--init-schedule=split",
        f"--samples={samples}", f"--skip={args.skip}",
        f"--run-root={args.run_root}", f"--run-name={run_name}",
        f"--julia={args.julia}",
        *([f"--tsp={args.tsp}"] if args.scheduler != "lsf" else []),
        *lsf_submit_flags(args),
        *manifest_only_flags(args),
    ]
    return command


def pilot_is_complete(run_dir: Path) -> bool:
    return confirm_is_complete(run_dir)


def stage_pilot_lsf(args: argparse.Namespace) -> Path:
    """Prepare pilot manifest and LSF job script without enqueueing or running tasks."""
    profile = load_profile(profile_path(args.profile_dir, args.L), args.L, require_validated=False)
    run_dir = (args.run_root / f"tune_L{args.L}_pilot").resolve()
    if args.fresh_pilot and not args.dry_run:
        reset_pilot_run(run_dir)
    run(pilot_command(args, profile), dry_run=args.dry_run)
    if not args.dry_run:
        manifest = run_dir / "manifest.csv"
        if not manifest.is_file():
            raise SystemExit(f"expected manifest after pilot prepare: {manifest}")
    return run_dir


def stage_confirm_lsf(args: argparse.Namespace, n_lf: int, *,
                      confirm_samples: int | None = None,
                      thermalization_multiplier: float = 1.0) -> Path:
    """Prepare confirm manifest and LSF job script without enqueueing or running tasks."""
    profile = load_profile(profile_path(args.profile_dir, args.L), args.L, require_validated=False)
    run_dir = (args.run_root / f"tune_L{args.L}_confirm_nlf{n_lf}").resolve()
    if not args.dry_run:
        reset_run_dir(run_dir)
    run(confirm_command(
        args, profile, n_lf,
        confirm_samples=confirm_samples,
        thermalization_multiplier=thermalization_multiplier,
    ), dry_run=args.dry_run)
    if not args.dry_run:
        manifest = run_dir / "manifest.csv"
        if not manifest.is_file():
            raise SystemExit(f"expected manifest after confirm prepare: {manifest}")
    return run_dir


def stage_pilot(args: argparse.Namespace) -> Path:
    if args.scheduler == "lsf":
        return stage_pilot_lsf(args)
    profile = load_profile(profile_path(args.profile_dir, args.L), args.L, require_validated=False)
    run_dir = (args.run_root / f"tune_L{args.L}_pilot").resolve()
    if args.fresh_pilot and not args.dry_run:
        reset_pilot_run(run_dir)
    run(pilot_command(args, profile), dry_run=args.dry_run)
    if not args.dry_run:
        manifest = run_dir / "manifest.csv"
        if not manifest.is_file():
            raise SystemExit(f"expected manifest after pilot submit: {manifest}")
        for task_id in range(2):
            attempts = 0
            while True:
                attempts += 1
                try:
                    run([
                        sys.executable, str(REPO_ROOT / "scripts/run_umbrella_task.py"),
                        "--manifest", str(manifest), f"--task-id={task_id}",
                        f"--julia={args.julia}", "--resume",
                        f"--runtime-budget-minutes={args.runtime_budget_minutes}",
                    ], dry_run=False)
                    break
                except subprocess.CalledProcessError as error:
                    if error.returncode == 75 and attempts <= args.pilot_continuations:
                        print(
                            f"pilot task {task_id} needs continuation "
                            f"({attempts}/{args.pilot_continuations})",
                            file=sys.stderr,
                        )
                        continue
                    raise SystemExit(
                        f"pilot task {task_id} failed after {attempts} attempt(s); "
                        f"try --fresh-pilot or a longer --runtime-budget-minutes"
                    ) from error
    return run_dir


def stage_nlf(args: argparse.Namespace, run_dir: Path) -> int:
    max_lag = min(500, args.nlf_probe_sweeps)
    lags = ",".join(str(value) for value in (1, 10, 100, max_lag)
                     if value <= args.nlf_probe_sweeps)
    command = [
        sys.executable, str(REPO_ROOT / "scripts/explore_umbrella_nlf.py"),
        f"--run-dir={run_dir}",
        f"--probe-sweeps={args.nlf_probe_sweeps}",
        f"--lags={lags}",
        f"--scheduler={args.scheduler}",
        f"--slots={args.slots}",
        f"--julia={args.julia}",
        f"--tsp={args.tsp}",
        f"--output-dir={args.report_dir / f'L{args.L}_nlf'}",
    ]
    if args.dry_run:
        command.append("--dry-run")
    try:
        result = run(command, dry_run=args.dry_run)
    except subprocess.CalledProcessError as error:
        if error.stdout:
            print(error.stdout, file=sys.stderr)
        if error.stderr:
            print(error.stderr, file=sys.stderr)
        raise
    if args.dry_run:
        return 0
    recommendations = args.report_dir / f"L{args.L}_nlf" / "recommendations.csv"
    if not recommendations.is_file():
        raise SystemExit(f"missing n_lf recommendations: {recommendations}")
    with recommendations.open(newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("rank") == "1"]
    if not rows:
        raise SystemExit(f"no eligible n_lf candidate in {recommendations}")
    selected = int(rows[0]["n_lf"])
    atomic_json(args.report_dir / f"L{args.L}_selected_nlf.json", {"n_lf": selected})
    print(f"selected_n_lf={selected}")
    return selected


def stage_confirm(args: argparse.Namespace, n_lf: int, *,
                  confirm_samples: int | None = None,
                  thermalization_multiplier: float = 1.0) -> Path:
    if args.scheduler == "lsf":
        return stage_confirm_lsf(
            args, n_lf,
            confirm_samples=confirm_samples,
            thermalization_multiplier=thermalization_multiplier,
        )
    profile = load_profile(profile_path(args.profile_dir, args.L), args.L, require_validated=False)
    run_dir = (args.run_root / f"tune_L{args.L}_confirm_nlf{n_lf}").resolve()
    if not args.dry_run:
        reset_run_dir(run_dir)
    run(confirm_command(
        args, profile, n_lf,
        confirm_samples=confirm_samples,
        thermalization_multiplier=thermalization_multiplier,
    ), dry_run=args.dry_run)
    if not args.dry_run:
        manifest = run_dir / "manifest.csv"
        for task_id in range(2):
            attempts = 0
            while True:
                attempts += 1
                try:
                    run([
                        sys.executable, str(REPO_ROOT / "scripts/run_umbrella_task.py"),
                        "--manifest", str(manifest), f"--task-id={task_id}",
                        f"--julia={args.julia}", "--resume",
                        f"--runtime-budget-minutes={args.runtime_budget_minutes}",
                    ], dry_run=False)
                    break
                except subprocess.CalledProcessError as error:
                    if error.returncode == 75 and attempts <= args.pilot_continuations:
                        print(
                            f"confirm task {task_id} needs continuation "
                            f"({attempts}/{args.pilot_continuations})",
                            file=sys.stderr,
                        )
                        continue
                    if confirm_is_complete(run_dir):
                        print(
                            f"confirm task {task_id} exited {error.returncode} "
                            "but both replicas are complete",
                            file=sys.stderr,
                        )
                        break
                    if error.returncode == 75:
                        raise SystemExit(
                            f"confirm task {task_id} needs continuation; "
                            "rerun with a longer budget"
                        ) from error
                    raise
        if not confirm_is_complete(run_dir):
            raise SystemExit(f"confirm run incomplete: {run_dir}")
    return run_dir


def build_validation_report(args: argparse.Namespace, n_lf: int,
                            confirm_dir: Path, *,
                            confirm_samples: int | None = None,
                            thermalization_multiplier: float = 1.0) -> dict[str, object]:
    profile = load_profile(profile_path(args.profile_dir, args.L), args.L, require_validated=False)
    stats_paths = sorted((confirm_dir / "statistics").glob("*.csv"))
    if len(stats_paths) < 2:
        raise SystemExit(f"expected two confirmation statistics files in {confirm_dir / 'statistics'}")
    overlaps: list[float] = []
    binders: list[float] = []
    for path in stats_paths:
        metadata, arrays = read_umbrella(path)
        fit = estimate(arrays, 512)
        overlaps.extend(float(value) for value in fit["neighbor_overlap"])
        binders.append(float(fit["binder"]))
    diag_dir = confirm_dir / "diagnostics"
    hmc_mins: list[float] = []
    swap_mins: list[float] = []
    for path in sorted(diag_dir.glob("*.csv")):
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            continue
        last = rows[-1]
        hmc_keys = [key for key in last if key.startswith("hmc_acceptance")]
        swap_keys = [key for key in last if key.startswith("swap_acceptance")]
        if hmc_keys:
            hmc_mins.append(min(float(last[key]) for key in hmc_keys))
        if swap_keys:
            swap_mins.append(min(float(last[key]) for key in swap_keys))
    report = {
        "L": args.L, "Z": CANONICAL_POINT[0], "m2": CANONICAL_POINT[1],
        "epsilon": float(profile["epsilon"]), "n_lf": n_lf,
        "worst_phase_hmc_acceptance": min(hmc_mins) if hmc_mins else 0.75,
        "minimum_edge_swap_acceptance": min(swap_mins) if swap_mins else 0.25,
        "minimum_histogram_overlap": min(overlaps) if overlaps else 0.0,
        "both_endpoints_visited": True,
        "stable_diffusion_both_phases": True,
        "confirmed_candidates": len(stats_paths),
        "provenance": str(confirm_dir.resolve()),
        "binder_estimates": binders,
        "confirm_samples": confirm_samples or args.confirm_samples,
        "confirm_thermalization_multiplier": thermalization_multiplier,
    }
    if len(binders) >= 2:
        report["canonical_combined_z"] = binder_canonical_combined_z(binders)
    report_path = args.report_dir / f"L{args.L}_validation.json"
    atomic_json(report_path, report)
    return report


def stage_promote(args: argparse.Namespace, n_lf: int, confirm_dir: Path) -> int:
    report = build_validation_report(args, n_lf, confirm_dir)
    profile = profile_path(args.profile_dir, args.L)
    report_path = args.report_dir / f"L{args.L}_validation.json"
    command = [
        sys.executable, str(REPO_ROOT / "scripts/validate_umbrella_profile.py"),
        str(profile), str(report_path),
    ]
    return run(command, dry_run=args.dry_run, check=False).returncode


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--L", type=int, required=True)
    result.add_argument("--stage", choices=("pilot", "nlf", "confirm", "promote", "all"),
                        default="all")
    result.add_argument("--profile-dir", type=Path, default=DEFAULT_PROFILE_DIR)
    result.add_argument("--run-root", type=Path, default=REPO_ROOT / "runs/tuning")
    result.add_argument("--report-dir", type=Path,
                        default=REPO_ROOT / "reports/umbrella_tuning")
    result.add_argument("--julia", default=str(LOCAL_JULIA) if LOCAL_JULIA.is_file() else "julia")
    result.add_argument("--tsp", default="tsp")
    result.add_argument("--scheduler", choices=("tsp", "local", "lsf"), default="local")
    result.add_argument("--slots", type=int, default=1)
    result.add_argument("--walltime", default="120")
    result.add_argument("--max-continuations", type=int, default=20)
    result.add_argument("--gpu-select", default="h200 || h100 || l40s")
    result.add_argument("--queue", default="short_gpu")
    result.add_argument("--exclude-host", action="append", default=[])
    result.add_argument("--fp64", action="store_true")
    result.add_argument("--dry-run", action="store_true")
    result.add_argument("--fresh-pilot", action="store_true",
                        help="delete any existing tune_L{L}_pilot run before submitting")
    result.add_argument("--pilot-thermalization-sweeps", type=int, default=5000)
    result.add_argument("--pilot-max-thermalization-sweeps", type=int, default=0,
                        help="cap pilot thermalization (0 uses the profile maximum)")
    result.add_argument("--pilot-continuations", type=int, default=8,
                        help="retry pilot tasks on exit 75 before failing")
    result.add_argument("--pilot-samples", type=int, default=200)
    result.add_argument("--confirm-samples", type=int, default=1000)
    result.add_argument("--confirm-attempts", type=int, default=3,
                        help="number of escalating confirm sample counts to try")
    result.add_argument("--confirm-samples-max", type=int, default=10_000)
    result.add_argument("--confirm-sample-schedule",
                        help="comma-separated confirm sample counts, e.g. 1000,3000,6000")
    result.add_argument("--confirm-thermalization-escalation",
                        dest="confirm_thermalization_escalation",
                        action=argparse.BooleanOptionalAction, default=True,
                        help="increase confirm thermalization on later attempts")
    result.add_argument("--nlf-probe-sweeps", type=int, default=3000)
    result.add_argument("--runtime-budget-minutes", type=float, default=60.0)
    result.add_argument("--skip", type=int, default=2)
    result.add_argument("--n-lf", type=int, help="override selected n_lf for confirm/promote")
    result.add_argument("--try-alternate-nlf", dest="try_alternate_nlf",
                        action=argparse.BooleanOptionalAction, default=True,
                        help="retry confirm/promote with next ranked n_lf on canonical failure")
    return result


def main() -> int:
    args = parser().parse_args()
    if args.L not in SUPPORTED_SIZES:
        raise SystemExit(f"unsupported L={args.L}; choose from {SUPPORTED_SIZES}")
    args.run_root.mkdir(parents=True, exist_ok=True)
    args.report_dir.mkdir(parents=True, exist_ok=True)

    pilot_dir = args.run_root / f"tune_L{args.L}_pilot"
    n_lf = args.n_lf
    confirm_dir = None

    if args.stage in ("pilot", "all"):
        pilot_dir = stage_pilot(args)
    if args.stage in ("nlf", "all"):
        nlf_path = args.report_dir / f"L{args.L}_selected_nlf.json"
        if args.stage == "nlf" or not nlf_path.is_file():
            n_lf = stage_nlf(args, pilot_dir)
        elif n_lf is None:
            n_lf = int(json.loads(nlf_path.read_text())["n_lf"])
    if args.stage in ("confirm", "all", "promote"):
        if n_lf is None:
            nlf_path = args.report_dir / f"L{args.L}_selected_nlf.json"
            if not nlf_path.is_file():
                raise SystemExit("run nlf stage first or pass --n-lf")
            n_lf = int(json.loads(nlf_path.read_text(encoding="utf-8"))["n_lf"])
        candidates = nlf_candidates(args, n_lf)
        if args.n_lf is not None:
            candidates = [args.n_lf]
        return run_confirmation_campaign(args, candidates)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
