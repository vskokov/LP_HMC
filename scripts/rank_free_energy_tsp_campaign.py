#!/usr/bin/env python3
"""Prepare, submit, and inspect rank-resolved free-energy continuations."""

from __future__ import annotations

import argparse
import csv
import json
import math
import shlex
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = ROOT / "runs/modulation_rank_free_energy_gpu"
REPORT = ROOT / "reports/structure_factor_cpu/modulation_rank_free_energy_gpu"
MANIFEST = REPORT / "manifest.csv"
JULIA = "/home/vskokov/.julia/juliaup/julia-1.12.6+0.x64.linux.gnu/bin/julia"
DEPOT = "/tmp/lp_hmc_julia_depot:/home/vskokov/.julia"

# The low endpoint retains the modulated branches.  The high endpoint obeys
# m2 > Z^2/4, so the bare quadratic kernel is positive at every momentum and
# supplies a common disordered anchor.  A 0.5 mass spacing is supplemented by
# the three previously classified mass points at every Z.
SETTINGS = {
    -1.5: (-4.0, 1.75, 0.824429495415,
           (-3.2230651515, -2.4230651515, -1.6230651515)),
    -2.0: (-6.5, 2.0, 0.824429495415,
           (-5.7866118766, -3.1866118766, -0.5866118766)),
    -2.5: (-11.0, 2.75, 1.38196601125,
           (-10.6337943546, -5.4337943546, -0.4337943546)),
    -3.0: (-10.0, 3.5, 1.5, (-8.0, -4.5, -1.0)),
    -4.0: (-15.0, 5.25, 2.0, (-14.0, -8.0, -2.0)),
}
SIZES = (16, 20)
REPLICAS = (1, 2)


def tag(value: float) -> str:
    return f"{value:g}".replace("-", "m").replace(".", "p")


def mass_grid(low: float, high: float, extra: tuple[float, ...]) -> list[float]:
    count = int(math.floor((high - low) / 0.5 + 1e-12))
    regular = [round(low + 0.5 * index, 12) for index in range(count + 1)]
    if regular[-1] < high - 1e-12:
        regular.append(high)
    return sorted(set(regular + [high, *extra]))


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def prepare(_: argparse.Namespace) -> int:
    rows: list[dict[str, object]] = []
    task_id = 0
    for L in SIZES:
        for Z, (low, high, target_q, extra) in SETTINGS.items():
            masses = mass_grid(low, high, extra)
            for replica in REPLICAS:
                output = (RUN_ROOT / f"L{L}" / f"Z{tag(Z)}" /
                          f"replica_{replica}" / "statistics.csv")
                rows.append({
                    "task_id": task_id, "L": L, "Z": Z,
                    "masses": ";".join(f"{value:.12g}" for value in masses),
                    "mass_count": len(masses), "target_q": target_q,
                    "anchor_m2": high, "replica": replica,
                    "seed": 3141592 + 100003 * replica + 7919 * task_id,
                    "eps": 0.010 if L == 16 else 0.0085, "n_lf": 15,
                    "settle": 150, "initial_settle": 500,
                    "samples": 150, "skip": 2, "shell_count": 1,
                    "rank_starts": "true", "gpu": "true",
                    "expected_rows": 5 * len(masses), "output": str(output),
                })
                task_id += 1
    write_rows(MANIFEST, rows)
    total = sum(int(row["expected_rows"]) for row in rows)
    print(f"manifest={MANIFEST} tasks={len(rows)} branch_mass_rows={total}")
    return 0


def load_manifest() -> list[dict[str, str]]:
    if not MANIFEST.is_file():
        raise SystemExit(f"missing {MANIFEST}; run prepare first")
    with MANIFEST.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def output_valid(row: dict[str, str]) -> bool:
    path = Path(row["output"])
    if not path.is_file():
        return False
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            records = list(csv.DictReader(handle))
        return (len(records) == int(row["expected_rows"]) and records and
                "rank_effective_dimension" in records[0])
    except (OSError, ValueError):
        return False


def command(row: dict[str, str]) -> list[str]:
    environment = {
        "CUDA_VISIBLE_DEVICES": "0", "TI_GPU": row["gpu"], "TI_L": row["L"],
        "TI_Z": row["Z"], "TI_MASSES": row["masses"],
        "TI_TARGET_Q": row["target_q"], "TI_SEED": row["seed"],
        "TI_OUTPUT": row["output"], "TI_EPS": row["eps"],
        "TI_N_LF": row["n_lf"], "TI_SETTLE": row["settle"],
        "TI_INITIAL_SETTLE": row["initial_settle"], "TI_SAMPLES": row["samples"],
        "TI_SKIP": row["skip"], "TI_SHELL_COUNT": row["shell_count"],
        "TI_RANK_STARTS": row["rank_starts"], "JULIA_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1", "FFTW_NUM_THREADS": "1",
        "JULIA_DEPOT_PATH": DEPOT,
    }
    flattened = [f"{key}={value}" for key, value in environment.items()]
    return ["env", *flattened, JULIA, "--startup-file=no", f"--project={ROOT}",
            str(ROOT / "scripts/thermodynamic_integration_multishell.jl")]


def submit(args: argparse.Namespace) -> int:
    rows = load_manifest()
    pending = [row for row in rows if not output_valid(row)]
    print(f"pending={len(pending)} completed={len(rows) - len(pending)} tsp_slots=1")
    for row in pending:
        label = f"rankfe_L{row['L']}_Z{tag(float(row['Z']))}_r{row['replica']}"
        launch = [args.tsp, "-L", label, *command(row)]
        if args.dry_run:
            print("+", shlex.join(launch))
        else:
            Path(row["output"]).parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(launch, cwd=ROOT, check=True)
    if not args.dry_run:
        subprocess.run([args.tsp, "-S", "1"], check=True)
        print(f"enqueued={len(pending)}; inspect with `{args.tsp}`")
    return 0


def status(_: argparse.Namespace) -> int:
    rows = load_manifest()
    valid = sum(output_valid(row) for row in rows)
    print(json.dumps({"tasks": len(rows), "completed_valid": valid,
                      "pending_or_invalid": len(rows) - valid}, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare").set_defaults(function=prepare)
    submit_parser = commands.add_parser("submit")
    submit_parser.add_argument("--tsp", default="tsp")
    submit_parser.add_argument("--dry-run", action="store_true")
    submit_parser.set_defaults(function=submit)
    commands.add_parser("status").set_defaults(function=status)
    return result


if __name__ == "__main__":
    arguments = parser().parse_args()
    raise SystemExit(arguments.function(arguments))
