#!/usr/bin/env python3
"""Prepare, run, and analyze direct Binder scans near the finite-q junction.

The scan deliberately uses the established M^2-umbrella workflow.  Every
physical point has independent ordered and disordered starts.  The initial
stage covers L=12,16,20; L=24 is prepared as a confirmation stage and should
only be submitted after the smaller-size crossings locate the useful mass
window.
"""

from __future__ import annotations

import argparse
import csv
import shlex
import subprocess
import sys
from pathlib import Path

import numpy as np

from run_thermodynamic_integration_L16 import crossing_fit
from umbrella_tuning_campaign import enqueue_incomplete_manifest_tsp


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "scripts/umbrella_binder_campaign.py"
CROSSINGS = ROOT / "scripts/plot_binder_crossings_vs_z.py"
RUN_ROOT = ROOT / "runs/umbrella_binder_junction"
REPORT_ROOT = ROOT / "reports/umbrella_binder_junction"
CONFIG_ROOT = ROOT / "configs/binder_junction"
PLOT_ROOT = ROOT / "plots/binder_junction"
Z_VALUES = (-1.50, -1.55, -1.60, -1.65)
DEFAULT_SIZES = (12, 16, 20)
CONFIRMATION_SIZE = 24
MASS_OFFSETS = (-0.30, -0.20, -0.15, -0.10, -0.05, -0.025, 0.0,
                0.025, 0.05, 0.10, 0.15, 0.20, 0.30)


def tag(value: float) -> str:
    return str(abs(value)).replace(".", "p") if value >= 0 else "m" + str(abs(value)).replace(".", "p")


def paths_for(z_value: float) -> tuple[Path, Path, Path, Path]:
    suffix = f"Z{tag(z_value)}"
    return (
        CONFIG_ROOT / f"sources_{suffix}.csv",
        RUN_ROOT / suffix,
        REPORT_ROOT / suffix,
        PLOT_ROOT / f"binder_{suffix}",
    )


def source_rows() -> dict[float, list[tuple[float, float]]]:
    coefficients = crossing_fit()
    result: dict[float, list[tuple[float, float]]] = {}
    for z_value in Z_VALUES:
        center = float(np.polyval(coefficients, z_value))
        masses = sorted({round(center + offset, 6) for offset in MASS_OFFSETS})
        result[z_value] = [(z_value, mass) for mass in masses]
    return result


def write_sources() -> None:
    CONFIG_ROOT.mkdir(parents=True, exist_ok=True)
    for z_value, rows in source_rows().items():
        path, _, _, _ = paths_for(z_value)
        temporary = path.with_suffix(".tmp")
        with temporary.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(("Z", "m2"))
            writer.writerows(rows)
        temporary.replace(path)
        print(f"sources={path} center={rows[len(rows) // 2][1]:.6f} points={len(rows)}")


def run(command: list[str]) -> None:
    print("+", shlex.join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def campaign_command(action: str, z_value: float, sizes: list[int], args: argparse.Namespace) -> list[str]:
    points, campaign_dir, report_dir, output = paths_for(z_value)
    command = [
        sys.executable, str(CAMPAIGN), action, *(str(size) for size in sizes),
        f"--points-csv={points}", f"--campaign-dir={campaign_dir}",
        f"--report-dir={report_dir}", f"--output={output}",
        f"--tsp={args.tsp}", f"--runtime-budget-minutes={args.runtime_budget_minutes}",
        f"--max-continuations={args.max_continuations}",
    ]
    if action == "submit" and args.command == "prepare":
        command.append("--prepare-only")
    if args.dry_run:
        command.append("--dry-run")
    return command


def analyze(args: argparse.Namespace, sizes: list[int]) -> None:
    csv_paths: list[Path] = []
    for z_value in Z_VALUES:
        run(campaign_command("analyze", z_value, sizes, args))
        csv_paths.append(Path(str(paths_for(z_value)[3]) + ".csv"))
    command = [sys.executable, str(CROSSINGS), "--csv", *(str(path) for path in csv_paths),
               "--output", str(PLOT_ROOT / "direct_crossings_vs_Z")]
    run(command)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "submit", "status", "analyze"))
    parser.add_argument("--L", type=int, nargs="+", default=list(DEFAULT_SIZES))
    parser.add_argument("--include-L24", action="store_true",
                        help="also include the expensive L=24 confirmation stage")
    parser.add_argument(
        "--pilot-only", action="store_true",
        help="submit only the ordered/disordered pair at the central source mass",
    )
    parser.add_argument("--tsp", default="tsp")
    parser.add_argument("--slots", type=int, default=1)
    parser.add_argument("--runtime-budget-minutes", type=float, default=360.0)
    parser.add_argument("--max-continuations", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.include_L24 and CONFIRMATION_SIZE not in args.L:
        args.L.append(CONFIRMATION_SIZE)
    if any(size not in (12, 16, 20, 24) for size in args.L):
        parser.error("junction Binder sizes must be among 12, 16, 20, 24")
    if args.runtime_budget_minutes <= 0 or args.max_continuations < 1 or args.slots < 1:
        parser.error("runtime budget, continuation count, and slots must be positive")
    return args


def main() -> int:
    args = parse_args()
    sizes = sorted(set(args.L))
    write_sources()
    if args.command == "analyze":
        analyze(args, sizes)
        return 0
    if args.command == "submit":
        for z_value in Z_VALUES:
            _, campaign_dir, _, _ = paths_for(z_value)
            for size in sizes:
                manifest = campaign_dir / f"L{size}" / "manifest.csv"
                if not manifest.is_file():
                    raise SystemExit(f"missing prepared manifest: {manifest}")
                selected = {2 * (len(MASS_OFFSETS) // 2),
                            2 * (len(MASS_OFFSETS) // 2) + 1} if args.pilot_only else None
                enqueue_incomplete_manifest_tsp(manifest, args, task_ids=selected)
        return 0
    action = "submit" if args.command in ("prepare", "submit") else "status"
    for z_value in Z_VALUES:
        run(campaign_command(action, z_value, sizes, args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
