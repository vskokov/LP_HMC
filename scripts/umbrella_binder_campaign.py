#!/usr/bin/env python3
"""TSP production suite: discrete M² umbrella Binder at several masses.

Uses validated umbrella profiles (not HMC reweight n_lf). Each lattice gets one
run directory with the five Z=-0.6 source masses and two split-phase replicas,
the same protocol as umbrella confirm. Subcommands: submit, status, analyze,
extend.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shlex
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from analyze_umbrella import (
    block_bootstrap,
    estimate_with_bin_fallback,
    read_umbrella,
)
from collect_binder_m2 import SCAN_M2_END, SCAN_M2_START, SCAN_Z, samples_for
from reweight_manifest import read_points_csv
from umbrella_profiles import (
    CANONICAL_Z_MAX,
    SUPPORTED_SIZES,
    binder_canonical_combined_z,
    load_profile,
)
from umbrella_campaign import load_rows
from umbrella_runtime import atomic_json
from umbrella_tuning_campaign import (
    active_tsp_task_ids,
    enqueue_incomplete_manifest_tsp,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SUBMITTER = REPO_ROOT / "scripts/submit_umbrella_tsp.py"
DEFAULT_POINTS = REPO_ROOT / "configs/reweight_sources_Zm0p6.csv"
DEFAULT_PROFILE_DIR = REPO_ROOT / "configs/umbrella_profiles"
DEFAULT_CAMPAIGN_DIR = REPO_ROOT / "runs/umbrella_binder_Zm06"
DEFAULT_REPORT_DIR = REPO_ROOT / "reports/umbrella_binder_Zm06"
DEFAULT_OUTPUT = REPO_ROOT / "plots/umbrella_binder_mZ0.6"
CANONICAL_M2 = -1.86421
LOCAL_JULIA = Path.home() / ".julia/juliaup/julia-1.12.6+0.x64.linux.gnu/bin/julia"


def profile_path(profile_dir: Path, L: int) -> Path:
    return profile_dir / f"L{L}.json"


def run_dir_for(campaign_dir: Path, L: int) -> Path:
    return campaign_dir / f"L{L}"


def samples_for_profile(profile: dict[str, object], L: int, override: int | None) -> int:
    if override is not None:
        return override
    validation = profile.get("validation")
    if isinstance(validation, dict) and validation.get("confirm_samples") is not None:
        return int(validation["confirm_samples"])
    return samples_for(L)


def thermalization_multiplier_for(
    profile: dict[str, object], override: float | None,
) -> float:
    if override is not None:
        return float(override)
    validation = profile.get("validation")
    if isinstance(validation, dict) and validation.get("confirm_thermalization_multiplier") is not None:
        return float(validation["confirm_thermalization_multiplier"])
    return 1.0


def submit_command(args: argparse.Namespace, L: int, profile: dict[str, object]) -> list[str]:
    n_lf = int(profile["n_lf"])
    profile_min = float(profile["umbrella_min"])
    profile_max = float(profile["umbrella_max"])
    umbrella_max = profile_max if args.umbrella_max is None else float(args.umbrella_max)
    if umbrella_max <= profile_min:
        raise SystemExit("--umbrella-max must exceed the profile umbrella minimum")
    range_scale = (umbrella_max - profile_min) / (profile_max - profile_min)
    profile_edges = int(profile["umbrella_windows"]) - 1
    umbrella_windows = max(2, round(profile_edges * range_scale) + 1)
    transport_scale = ((umbrella_windows - 1) / profile_edges) ** 2
    multiplier = thermalization_multiplier_for(profile, args.thermalization_multiplier)
    minimum = max(
        1,
        int(float(profile["minimum_thermalization_sweeps"]) * multiplier * transport_scale),
    )
    maximum = max(
        minimum,
        int(float(profile["maximum_thermalization_sweeps"]) * multiplier * transport_scale),
    )
    samples = samples_for_profile(profile, L, args.samples)
    command = [
        sys.executable, str(SUBMITTER),
        f"--L={L}",
        f"--points-csv={args.points_csv}",
        f"--eps={profile['epsilon']}", f"--n-lf={n_lf}",
        f"--startup-eps={profile['startup_epsilon']}",
        f"--startup-n-lf={profile['startup_n_lf']}",
        f"--startup-sweeps={profile['startup_sweeps']}",
        f"--thermalization-sweeps={minimum}",
        f"--max-thermalization-sweeps={maximum}",
        f"--umbrella-windows={umbrella_windows}",
        f"--umbrella-min={profile['umbrella_min']}",
        f"--umbrella-max={umbrella_max}",
        f"--umbrella-kappa={profile['umbrella_kappa']}",
        f"--umbrella-power={profile['umbrella_power']}",
        f"--swap-every={profile['swap_every']}",
        "--min-round-trip-fraction=0.5", "--min-swap-acceptance=0.25",
        "--replicas=2", "--init-schedule=split",
        f"--samples={samples}", f"--skip={args.skip}",
        f"--runtime-budget-minutes={args.runtime_budget_minutes}",
        f"--max-continuations={args.max_continuations}",
        f"--run-root={args.campaign_dir}", f"--run-name=L{L}",
        f"--julia={args.julia}", f"--tsp={args.tsp}",
    ]
    if args.dry_run:
        command.append("--dry-run")
    else:
        command.append("--prepare-only")
    return command


def prepare_manifest(args: argparse.Namespace, L: int) -> Path:
    try:
        profile = load_profile(profile_path(args.profile_dir, L), L, require_validated=True)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    run_dir = run_dir_for(args.campaign_dir, L)
    manifest = run_dir / "manifest.csv"
    command = submit_command(args, L, profile)
    print("+", shlex.join(command), flush=True)
    result = subprocess.run(command, cwd=REPO_ROOT, check=False, text=True)
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    return manifest


def cmd_submit(args: argparse.Namespace) -> int:
    if not args.points_csv.is_file():
        raise SystemExit(f"missing points file: {args.points_csv}")
    points = read_points_csv(args.points_csv)
    if not points:
        raise SystemExit(f"no source masses in {args.points_csv}")
    args.campaign_dir.mkdir(parents=True, exist_ok=True)
    for L in args.L:
        print(
            f"=== umbrella Binder L={L} points={len(points)} "
            f"replicas=2 schedule=split ===",
            flush=True,
        )
        manifest = prepare_manifest(args, L)
        if not manifest.is_file() and args.dry_run:
            continue
        if args.prepare_only:
            print(f"prepared={manifest}")
            continue
        enqueue_incomplete_manifest_tsp(manifest, args)
    return 0


def completion_counts(manifest: Path) -> tuple[int, int]:
    with manifest.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    expected = len(rows)
    found = 0
    for row in rows:
        marker = Path(row["completion_marker"])
        if not marker.is_file():
            continue
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if payload.get("complete") is True:
            found += 1
    return found, expected


def cmd_status(args: argparse.Namespace) -> int:
    for L in args.L:
        run_dir = run_dir_for(args.campaign_dir, L)
        manifest = run_dir / "manifest.csv"
        if not manifest.is_file():
            print(f"L={L} missing manifest {manifest}")
            continue
        found, expected = completion_counts(manifest)
        active = active_tsp_task_ids(args.tsp, str(run_dir.resolve()))
        print(
            f"L={L} complete={found}/{expected} tsp_active={len(active)} "
            f"run_dir={run_dir}"
        )
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    """Enqueue incomplete tasks from existing manifests without rewriting them."""
    for L in args.L:
        manifest = run_dir_for(args.campaign_dir, L) / "manifest.csv"
        if not manifest.is_file():
            raise SystemExit(f"missing manifest {manifest}")
        enqueue_incomplete_manifest_tsp(manifest, args)
    return 0


def jsonable(value):
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    return value


def scan_t(m2: float) -> float:
    span = SCAN_M2_END - SCAN_M2_START
    if span == 0:
        return 0.0
    return (m2 - SCAN_M2_START) / span


def combined_row(
    L: int, z_value: float, m2: float, binders: list[float],
    errors: list[float], *, bootstrap: int,
) -> dict[str, object]:
    mean = float(sum(binders) / len(binders))
    z_score = binder_canonical_combined_z(binders)
    warning = "ok" if z_score <= CANONICAL_Z_MAX else "source_disagreement"
    if bootstrap >= 2 and errors:
        uncertainty = math.hypot(*errors) / math.sqrt(len(errors))
    else:
        uncertainty = abs(binders[0] - binders[1]) / 2.0
    return {
        "t": scan_t(m2),
        "Z": z_value,
        "m2": m2,
        "L": L,
        "U4": mean,
        "uncertainty": uncertainty,
        "warning_status": warning,
        "source_U4_min": min(binders),
        "source_U4_max": max(binders),
        "canonical_combined_z": z_score,
    }


def analyze_run_dir(
    run_dir: Path, report_dir: Path, *, bootstrap: int, dry_run: bool,
    reuse_existing: bool = False,
) -> list[dict[str, object]]:
    stats_dir = run_dir / "statistics"
    if not stats_dir.is_dir():
        return []
    grouped: dict[tuple[int, float, float], list[tuple[Path, dict[str, str]]]] = defaultdict(list)
    for path in sorted(stats_dir.glob("*.csv")):
        metadata: dict[str, str] = {}
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.startswith("#"):
                    break
                key, separator, value = line[1:].strip().partition("=")
                if separator:
                    metadata[key.strip()] = value.strip()
        key = (int(metadata["L"]), float(metadata["Z"]), float(metadata["m2"]))
        grouped[key].append((path, metadata))
    rows: list[dict[str, object]] = []
    report_dir.mkdir(parents=True, exist_ok=True)
    for (L, z_value, m2), items in sorted(grouped.items()):
        if len(items) < 2:
            print(
                f"L={L} m2={m2:g}: {len(items)} replica file(s); need 2",
                file=sys.stderr,
            )
            continue
        binders: list[float] = []
        errors: list[float] = []
        for index, (path, metadata) in enumerate(items[:2]):
            cached_path = report_dir / f"{path.stem}.json"
            if reuse_existing and cached_path.is_file():
                fit = json.loads(cached_path.read_text(encoding="utf-8"))
            else:
                _, arrays = read_umbrella(path)
                fit = estimate_with_bin_fallback(arrays)
                if bootstrap >= 2:
                    fit.update(block_bootstrap(
                        metadata, arrays, bootstrap, 10, 1729 + index, int(fit["wham_bins"]),
                    ))
            binders.append(float(fit["binder"]))
            errors.append(float(fit.get("binder_error") or 0.0))
            payload = {
                "L": L, "Z": z_value, "m2": m2, "source": str(path.resolve()),
                **{key: value for key, value in fit.items()
                   if key not in {
                       "free_energies", "profile_centers", "profile_free_energy",
                       "profile_density", "profile_edges",
                   }},
            }
            if not dry_run and not (reuse_existing and cached_path.is_file()):
                atomic_json(
                    cached_path,
                    jsonable(payload),
                )
        rows.append(combined_row(L, z_value, m2, binders, errors, bootstrap=bootstrap))
    by_scan: dict[tuple[int, float], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_scan[(int(row["L"]), float(row["Z"]))].append(row)
    for scan in by_scan.values():
        low = min(float(row["m2"]) for row in scan)
        high = max(float(row["m2"]) for row in scan)
        for row in scan:
            row["t"] = ((float(row["m2"]) - low) / (high - low)
                        if high > low else 0.0)
    return rows


def print_canonical_crosscheck(rows: list[dict[str, object]], profile_dir: Path) -> None:
    by_L: dict[int, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_L[int(row["L"])].append(row)
    print("canonical m2=-1.86421 vs umbrella confirm:")
    for L in sorted(by_L):
        closest = min(by_L[L], key=lambda row: abs(float(row["m2"]) - CANONICAL_M2))
        try:
            profile = load_profile(profile_path(profile_dir, L), L, require_validated=True)
        except ValueError as error:
            print(f"  L={L} skipped ({error})")
            continue
        estimates = profile.get("validation", {}).get("binder_estimates") if isinstance(
            profile.get("validation"), dict
        ) else None
        if not estimates:
            print(f"  L={L} U={float(closest['U4']):.4f} (no confirm table)")
            continue
        umb = sum(float(value) for value in estimates) / len(estimates)
        u = float(closest["U4"])
        print(
            f"  L={L} umbrella={umb:.4f} discrete={u:.4f} delta={u - umb:.4f} "
            f"warn={closest['warning_status']}"
        )


def cmd_analyze(args: argparse.Namespace) -> int:
    rows: list[dict[str, object]] = []
    for L in args.L:
        run_dir = run_dir_for(args.campaign_dir, L)
        report_dir = args.report_dir / f"L{L}"
        print(f"L={L} analyzing {run_dir}")
        if args.dry_run:
            stats = list((run_dir / "statistics").glob("*.csv")) if (run_dir / "statistics").is_dir() else []
            print(f"  dry-run: {len(stats)} statistics file(s)")
            continue
        rows.extend(analyze_run_dir(
            run_dir, report_dir, bootstrap=args.bootstrap, dry_run=False,
        ))
    if args.dry_run:
        return 0
    if not rows:
        raise SystemExit("no complete two-replica umbrella masses to analyze")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    csv_path = Path(str(args.output) + ".csv")
    fieldnames = [
        "t", "Z", "m2", "L", "U4", "uncertainty", "warning_status",
        "source_U4_min", "source_U4_max", "canonical_combined_z",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    overlay = Path(str(args.output) + "_overlay.png")
    z_values = sorted({float(row["Z"]) for row in rows})
    z_label = f"{z_values[0]:g}" if len(z_values) == 1 else "multiple Z"
    plot = [
        sys.executable, str(REPO_ROOT / "scripts/plot_reweight_csv.py"),
        str(csv_path), "--x", "m2",
        "--title", rf"Umbrella Binder $U_4$ vs $m^2$ at $Z={z_label}$",
        "--output", str(overlay),
    ]
    print("+", shlex.join(plot), flush=True)
    subprocess.run(plot, cwd=REPO_ROOT, check=True)
    print(f"csv={csv_path}")
    print(f"overlay={overlay}")
    if len(z_values) == 1 and math.isclose(z_values[0], SCAN_Z):
        print_canonical_crosscheck(rows, args.profile_dir)
    return 0


def mass_key(value: str | float) -> float:
    return round(float(value), 6)


def disagreement_masses(csv_path: Path, L: int) -> set[float]:
    masses: set[float] = set()
    with csv_path.open(newline="", encoding="utf-8") as handle:
        for record in csv.DictReader(handle):
            if int(float(record["L"])) != L:
                continue
            if (record.get("warning_status") or "").strip().lower() != "source_disagreement":
                continue
            masses.add(mass_key(record["m2"]))
    return masses


def write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise SystemExit(f"{path}: no manifest rows")
    fieldnames = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def aligned_target(current: int, extra: int, shard: int) -> int:
    if extra < 1 or shard < 1:
        raise SystemExit("extra samples and shard size must be positive")
    target = current + extra
    remainder = target % shard
    if remainder:
        target += shard - remainder
    return target


def extend_row(row: dict[str, str], extra: int, *, dry_run: bool) -> int | None:
    progress_path = Path(row["progress_marker"])
    marker = Path(row["completion_marker"])
    shard = int(row["collection_shard_samples"])
    if progress_path.is_file():
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
    else:
        progress = {
            "schema_version": 1, "task_id": int(row["task_id"]),
            "samples": int(row["samples"]), "target_samples": int(row["min_samples"]),
            "committed_shards": [], "checkpoint": row["checkpoint_path"],
            "decision": "collecting",
        }
    current = int(progress.get("samples") or row["samples"])
    extra_count = extra if extra > 0 else current
    target = aligned_target(current, extra_count, shard)
    if target <= current:
        return None
    print(
        f"task={row['task_id']} m2={row['m2']} phase={row['init_phase']} "
        f"samples={current} -> {target}",
        flush=True,
    )
    row["samples"] = str(target)
    row["min_samples"] = str(target)
    row["max_samples"] = str(max(int(row["max_samples"]), target))
    progress["target_samples"] = target
    progress["decision"] = "collecting"
    if dry_run:
        return target
    atomic_json(progress_path, progress)
    if marker.is_file():
        marker.unlink()
    return target


def cmd_extend(args: argparse.Namespace) -> int:
    csv_path = Path(str(args.output) + ".csv")
    if not csv_path.is_file():
        raise SystemExit(
            f"missing analysis CSV {csv_path}; run analyze first so disagreements are known"
        )
    extra = 0 if args.extra_samples is None else int(args.extra_samples)
    extended = 0
    for L in args.L:
        masses = disagreement_masses(csv_path, L)
        if not masses:
            print(f"L={L} no source_disagreement masses in {csv_path}")
            continue
        manifest = run_dir_for(args.campaign_dir, L) / "manifest.csv"
        if not manifest.is_file():
            raise SystemExit(f"missing manifest {manifest}")
        rows = load_rows(manifest)
        selected = 0
        for row in rows:
            if mass_key(row["m2"]) not in masses:
                continue
            if extend_row(row, extra, dry_run=args.dry_run) is not None:
                selected += 1
                extended += 1
        if selected and not args.dry_run:
            write_manifest(manifest, rows)
        if selected:
            enqueue_incomplete_manifest_tsp(manifest, args)
    if extended == 0:
        raise SystemExit("no disagreeing replica tasks to extend")
    return 0


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--points-csv", type=Path, default=DEFAULT_POINTS)
    parser.add_argument("--profile-dir", type=Path, default=DEFAULT_PROFILE_DIR)
    parser.add_argument("--campaign-dir", type=Path, default=DEFAULT_CAMPAIGN_DIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--julia", default=str(LOCAL_JULIA if LOCAL_JULIA.is_file() else "julia"))
    parser.add_argument("--tsp", default="tsp")
    parser.add_argument("--slots", type=int, default=1)
    parser.add_argument("--skip", type=int, default=2)
    parser.add_argument("--samples", type=int)
    parser.add_argument("--thermalization-multiplier", type=float)
    parser.add_argument(
        "--umbrella-max", type=float,
        help=(
            "override the validated profile ceiling; window count is scaled linearly "
            "and thermalization bounds quadratically to preserve ladder resolution"
        ),
    )
    parser.add_argument("--runtime-budget-minutes", type=float, default=360.0)
    parser.add_argument("--max-continuations", type=int, default=20)
    parser.add_argument("--bootstrap", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--prepare-only", action="store_true",
        help="write manifests without adding their tasks to task-spooler",
    )
    parser.add_argument(
        "--extra-samples", type=int,
        help="additional samples_per_window (default: double the current count)",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("submit", "prepare manifests and enqueue incomplete TSP umbrella jobs"),
        ("resume", "enqueue incomplete tasks from existing manifests"),
        ("status", "print complete-marker counts and active tsp tasks"),
        ("analyze", "WHAM complete replica pairs and plot discrete U vs m²"),
        ("extend", "collect more samples on masses with ordered/disordered disagreement"),
    ):
        item = sub.add_parser(name, help=help_text)
        item.add_argument("L", type=int, nargs="+")
        add_common(item)
    args = parser.parse_args()
    if any(L not in SUPPORTED_SIZES for L in args.L):
        parser.error(f"L must be in {SUPPORTED_SIZES}")
    if args.slots < 1 or args.skip < 1 or args.max_continuations < 1:
        parser.error("slots, skip, and max-continuations must be positive")
    if args.runtime_budget_minutes <= 0 or args.bootstrap < 1:
        parser.error("runtime budget must be positive and bootstrap >= 1")
    if args.umbrella_max is not None and args.umbrella_max <= 0:
        parser.error("--umbrella-max must be positive")
    if args.extra_samples is not None and args.extra_samples < 1:
        parser.error("--extra-samples must be positive")
    return args


def main() -> int:
    args = parse_args()
    if args.command == "submit":
        return cmd_submit(args)
    if args.command == "resume":
        return cmd_resume(args)
    if args.command == "status":
        return cmd_status(args)
    if args.command == "extend":
        return cmd_extend(args)
    return cmd_analyze(args)


if __name__ == "__main__":
    raise SystemExit(main())
