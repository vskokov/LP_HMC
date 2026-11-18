#!/usr/bin/env python3
"""MBAR-reweight collected Z=-0.6 Binder sources and plot U vs m²."""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path

from collect_binder_m2 import SCAN_M2_END, SCAN_M2_START, SCAN_Z, run_name


REPO_ROOT = Path(__file__).resolve().parents[1]


def _complete_count(manifest: Path) -> tuple[int, int]:
    with manifest.open(newline="", encoding="utf-8") as handle:
        expected = sum(1 for _ in csv.DictReader(handle))
    complete = manifest.parent / "complete"
    found = len(list(complete.glob("*.complete"))) if complete.is_dir() else 0
    return found, expected


def _tempering_replicas(manifest: Path) -> int:
    with manifest.open(newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle), None)
    if not row:
        return 1
    return int(float(row.get("tempering_replicas") or 1))


def manifest_for(run_root: Path, L: int) -> Path:
    options = []
    seen: set[Path] = set()
    candidates = [
        run_root / run_name(L) / "manifest.csv",
        run_root / run_name(L, tempered=True) / "manifest.csv",
    ]
    candidates.extend(sorted(run_root.glob(f"binder_Zm06_temp*_L{L}/manifest.csv")))
    for path in candidates:
        resolved = path.resolve() if path.exists() else path
        if not path.is_file() or resolved in seen:
            continue
        seen.add(resolved)
        found, expected = _complete_count(path)
        nrep = _tempering_replicas(path)
        options.append((nrep > 1, found >= expected and expected > 0, nrep, found, path))
    if not options:
        raise SystemExit(f"missing manifest for L={L} under {run_root}")
    complete = [item for item in options if item[1]]
    pool = complete or options
    # Prefer a finished denser m² ladder over a shorter tempered or untempered run.
    pool.sort(key=lambda item: (not item[0], -item[2], -item[3]))
    return pool[0][4]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("L", type=int, nargs="+")
    parser.add_argument("--run-root", type=Path, default=REPO_ROOT / "runs")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "plots/binder_mZ0.6")
    parser.add_argument("--num", type=int, default=201)
    parser.add_argument(
        "--bootstrap", type=int, default=1,
        help="bootstrap draws; 1 skips error bars. Full MBAR resamples can fail "
             "when a draw has poor source overlap — then this helper retries nearest-source mode",
    )
    parser.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--source-mode", choices=("mbar", "nearest", "fixed"), default="mbar")
    args = parser.parse_args()
    if args.num < 2 or args.bootstrap < 1:
        parser.error("--num must be >= 2 and --bootstrap must be positive")
    return args


def main() -> int:
    args = parse_args()
    manifests = []
    for L in args.L:
        manifest = manifest_for(args.run_root, L)
        complete = manifest.parent / "complete"
        n_complete = len(list(complete.glob("*.complete"))) if complete.is_dir() else 0
        print(f"L={L} complete markers={n_complete} manifest={manifest}")
        manifests.append(manifest)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    def reweight_command(source_mode: str) -> list[str]:
        command = [
            sys.executable, str(REPO_ROOT / "reweight_binder.py"),
            "--start", str(SCAN_Z), str(SCAN_M2_START),
            "--end", str(SCAN_Z), str(SCAN_M2_END),
            "--num", str(args.num),
            "--bootstrap", str(args.bootstrap),
            "--backend", args.backend if source_mode == "mbar" else "cpu",
            "--jobs", str(args.jobs),
            "--source-mode", source_mode,
            "--output", str(args.output),
        ]
        for manifest in manifests:
            command.extend(["--manifest", str(manifest)])
        return command

    command = reweight_command(args.source_mode)
    print("+", " ".join(command))
    result = subprocess.run(command, cwd=REPO_ROOT)
    if result.returncode != 0 and args.source_mode == "mbar":
        print("MBAR failed; retrying with --source-mode nearest", file=sys.stderr)
        command = reweight_command("nearest")
        print("+", " ".join(command))
        subprocess.run(command, cwd=REPO_ROOT, check=True)
    elif result.returncode != 0:
        raise SystemExit(result.returncode)

    csv_path = Path(str(args.output) + ".csv")
    overlay = Path(str(args.output) + "_overlay.png")
    subprocess.run(
        [
            sys.executable, str(REPO_ROOT / "scripts/plot_reweight_csv.py"),
            str(csv_path), "--x", "m2",
            "--title", r"Binder $U_4$ vs $m^2$ at $Z=-0.6$",
            "--output", str(overlay),
        ],
        cwd=REPO_ROOT, check=True,
    )
    crossings = Path(str(args.output) + "_crossings.csv")
    subprocess.run(
        [
            sys.executable, str(REPO_ROOT / "scripts/find_binder_crossings.py"),
            str(csv_path), "--output", str(crossings),
        ],
        cwd=REPO_ROOT, check=True,
    )
    suggestions = Path(str(args.output) + "_suggestions.csv")
    result = subprocess.run(
        [
            sys.executable, str(REPO_ROOT / "scripts/validate_critical_window.py"),
            str(csv_path), "--margin", "0.01", "--suggestions", str(suggestions),
        ],
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        print(
            f"validate_critical_window exited {result.returncode} "
            "(expected when U=1/3 and 0.465 are not crossed in this window)",
            file=sys.stderr,
        )
    print(f"csv={csv_path}")
    print(f"overlay={overlay}")
    print(f"crossings={crossings}")
    print(f"suggestions={suggestions}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
