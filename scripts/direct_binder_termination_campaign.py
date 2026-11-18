#!/usr/bin/env python3
"""Direct Binder scan bracketing the uniform-to-finite-q termination region.

The initial scan follows the measured/extrapolated uniform Binder line at
Z=-0.80,-0.85,-0.90,-0.95 with five closely spaced masses and two independent
starts.  L=12,16,20 are the discovery stage; L=24 is prepared but deliberately
held back for confirmation after the bracket is narrowed.
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
RUN_ROOT = ROOT / "runs/umbrella_binder_termination"
REPORT_ROOT = ROOT / "reports/umbrella_binder_termination"
CONFIG_ROOT = ROOT / "configs/binder_termination"
PLOT_ROOT = ROOT / "plots/binder_termination"
Z_VALUES = (-0.80, -0.85, -0.90, -0.95)
DEFAULT_SIZES = (12, 16, 20)
CONFIRMATION_SIZE = 24
MASS_OFFSETS = (-0.06, -0.03, 0.0, 0.03, 0.06)


def tag(value: float) -> str:
    text = f"{abs(value):g}".replace(".", "p")
    return f"m{text}" if value < 0 else text


def paths_for(z_value: float) -> tuple[Path, Path, Path, Path]:
    suffix = f"Z{tag(z_value)}"
    return (
        CONFIG_ROOT / f"sources_{suffix}.csv",
        RUN_ROOT / suffix,
        REPORT_ROOT / suffix,
        PLOT_ROOT / f"binder_{suffix}",
    )


def source_rows(z_values: tuple[float, ...] = Z_VALUES) -> dict[float, list[tuple[float, float]]]:
    coefficients = crossing_fit()
    rows: dict[float, list[tuple[float, float]]] = {}
    for z_value in z_values:
        center = float(np.polyval(coefficients, z_value))
        masses = [round(center + offset, 6) for offset in MASS_OFFSETS]
        rows[z_value] = [(z_value, mass) for mass in masses]
    return rows


def write_sources(z_values: tuple[float, ...] = Z_VALUES) -> None:
    CONFIG_ROOT.mkdir(parents=True, exist_ok=True)
    for z_value, rows in source_rows(z_values).items():
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


def campaign_command(
    action: str, z_value: float, sizes: list[int], args: argparse.Namespace,
) -> list[str]:
    points, campaign_dir, report_dir, output = paths_for(z_value)
    command = [
        sys.executable, str(CAMPAIGN), action, *(str(size) for size in sizes),
        f"--points-csv={points}", f"--campaign-dir={campaign_dir}",
        f"--report-dir={report_dir}", f"--output={output}",
        "--umbrella-max=0.55", f"--tsp={args.tsp}",
        f"--runtime-budget-minutes={args.runtime_budget_minutes}",
        f"--max-continuations={args.max_continuations}",
    ]
    if action == "submit" and args.command == "prepare":
        command.append("--prepare-only")
    if args.dry_run:
        command.append("--dry-run")
    return command


def analyze(args: argparse.Namespace, sizes: list[int], z_values: tuple[float, ...]) -> None:
    csv_paths: list[Path] = []
    for z_value in z_values:
        run(campaign_command("analyze", z_value, sizes, args))
        csv_paths.append(Path(f"{paths_for(z_value)[3]}.csv"))
    run([
        sys.executable, str(CROSSINGS), "--csv", *(str(path) for path in csv_paths),
        "--output", str(PLOT_ROOT / "direct_crossings_vs_Z"),
    ])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "submit", "status", "analyze"))
    parser.add_argument(
        "--Z", type=float, action="append", dest="z_values",
        help="repeat to override the default Z grid",
    )
    parser.add_argument("--L", type=int, nargs="+", default=list(DEFAULT_SIZES))
    parser.add_argument("--include-L24", action="store_true")
    parser.add_argument(
        "--pilot-only", action="store_true",
        help="submit only the two starts at the extrapolated central mass",
    )
    parser.add_argument(
        "--crossing-side-only", action="store_true",
        help="submit both starts at the -0.06 and -0.03 mass offsets",
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
        parser.error("termination Binder sizes must be among 12, 16, 20, 24")
    if args.runtime_budget_minutes <= 0 or args.max_continuations < 1 or args.slots < 1:
        parser.error("runtime budget, continuation count, and slots must be positive")
    if args.pilot_only and args.crossing_side_only:
        parser.error("--pilot-only and --crossing-side-only are mutually exclusive")
    return args


def main() -> int:
    args = parse_args()
    sizes = sorted(set(args.L))
    z_values = tuple(dict.fromkeys(args.z_values or Z_VALUES))
    write_sources(z_values)
    if args.command == "analyze":
        analyze(args, sizes, z_values)
        return 0
    if args.command == "submit":
        central = len(MASS_OFFSETS) // 2
        if args.pilot_only:
            selected = {2 * central, 2 * central + 1}
        elif args.crossing_side_only:
            selected = {0, 1, 2, 3}
        else:
            selected = None
        for z_value in z_values:
            _, campaign_dir, _, _ = paths_for(z_value)
            for size in sizes:
                manifest = campaign_dir / f"L{size}" / "manifest.csv"
                if not manifest.is_file():
                    raise SystemExit(f"missing prepared manifest: {manifest}")
                enqueue_incomplete_manifest_tsp(manifest, args, task_ids=selected)
        return 0
    action = "submit" if args.command == "prepare" else "status"
    for z_value in z_values:
        run(campaign_command(action, z_value, sizes, args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
