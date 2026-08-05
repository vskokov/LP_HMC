#!/usr/bin/env python3
"""Materialize and submit a reproducible Slurm array for reweighting ensembles."""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import re
import shlex
import subprocess
from decimal import Decimal, InvalidOperation
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def canonical_number(text: str) -> str:
    try:
        value = Decimal(text.strip())
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError(f"invalid number {text!r}") from exc
    if not value.is_finite():
        raise argparse.ArgumentTypeError(f"number must be finite: {text!r}")
    if value == 0:
        return "0"
    result = format(value, "f")
    if "." in result:
        result = result.rstrip("0").rstrip(".")
    return result


def parse_point(text: str) -> tuple[str, str]:
    fields = [field.strip() for field in text.split(",")]
    if len(fields) != 2:
        raise argparse.ArgumentTypeError("--point must be Z,m2")
    return canonical_number(fields[0]), canonical_number(fields[1])


def read_points_csv(path: Path) -> list[tuple[str, str]]:
    points: list[tuple[str, str]] = []
    with path.open(newline="") as handle:
        rows = list(csv.reader(handle))
    for index, row in enumerate(rows):
        if not row or all(not item.strip() for item in row):
            continue
        if len(row) != 2:
            raise ValueError(f"{path}:{index + 1}: expected exactly two columns")
        if not points and row[0].strip().lower() == "z" and row[1].strip().lower() in {"m2", "m²"}:
            continue
        points.append((canonical_number(row[0]), canonical_number(row[1])))
    return points


def deterministic_seed(run_name: str, L: int, Z: str, m2: str, replica: int) -> int:
    payload = f"{run_name}\0{L}\0{Z}\0{m2}\0{replica}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") % 2_147_483_646 + 1


def build_rows(args: argparse.Namespace, points: list[tuple[str, str]], run_dir: Path):
    rows = []
    used_seeds: set[int] = set()
    task_id = 0
    for point_index, (Z, m2) in enumerate(points):
        for replica in range(args.replicas):
            seed = deterministic_seed(args.run_name, args.L, Z, m2, replica)
            while seed in used_seeds:
                seed = seed % 2_147_483_646 + 1
            used_seeds.add(seed)
            base = f"task_{task_id:06d}"
            rows.append({
                "schema_version": 1, "task_id": task_id, "point_index": point_index,
                "replica": replica, "L": args.L, "Z": Z, "m2": m2,
                "eps": canonical_number(str(args.eps)), "n_lf": args.n_lf, "seed": seed,
                "samples": args.samples, "skip": args.skip, "warmup": args.warmup,
                "checkpoint_path": str((run_dir / "checkpoints" / f"{base}.jld2").resolve()),
                "stats_path": str((run_dir / "statistics" / f"{base}.csv").resolve()),
                "completion_marker": str((run_dir / "complete" / f"{base}.complete").resolve()),
            })
            task_id += 1
    return rows


def write_manifest(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def job_script(args: argparse.Namespace, manifest: Path, count: int, logs: Path) -> str:
    worker = REPO_ROOT / "scripts/run_reweight_task.py"
    command = [
        "python3", str(worker), "--manifest", str(manifest.resolve()),
        "--task-id", '"${SLURM_ARRAY_TASK_ID}"', "--julia", args.julia,
        "--launcher", "srun",
    ]
    if args.resume:
        command.append("--resume")
    command_text = " ".join(item if item.startswith('"${') else shlex.quote(item) for item in command)
    directives = [
        "#!/usr/bin/env bash", f"#SBATCH --job-name={args.run_name}",
        f"#SBATCH --array=0-{count - 1}", f"#SBATCH --partition={args.partition}",
        f"#SBATCH --time={args.time}", f"#SBATCH --mem={args.mem}",
        f"#SBATCH --cpus-per-task={args.cpus}", f"#SBATCH --gres={args.gpu_resource}",
        f'#SBATCH --output="{logs.resolve()}/%x_%A_%a.out"',
        f'#SBATCH --error="{logs.resolve()}/%x_%A_%a.err"',
    ]
    if args.account:
        directives.append(f"#SBATCH --account={args.account}")
    body = ["", "set -euo pipefail"]
    if args.julia_depot:
        body.append(f"export JULIA_DEPOT_PATH={shlex.quote(args.julia_depot)}")
    if args.module:
        body.extend([
            "if ! type module >/dev/null 2>&1; then",
            "    source /usr/share/Modules/init/bash 2>/dev/null || source /etc/profile.d/modules.sh",
            "fi",
        ])
    body.extend(f"module load {shlex.quote(module)}" for module in args.module)
    body.extend(["", command_text, ""])
    return "\n".join(directives + body)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--L", type=int, required=True)
    parser.add_argument("--point", action="append", type=parse_point, default=[])
    parser.add_argument("--points-csv", type=Path, action="append", default=[])
    parser.add_argument("--eps", type=float, required=True)
    parser.add_argument("--n-lf", type=int, required=True)
    parser.add_argument("--samples", type=int, default=1000)
    parser.add_argument("--skip", type=int, default=1)
    parser.add_argument("--warmup", type=int, default=0)
    parser.add_argument("--replicas", type=int, default=1)
    parser.add_argument("--partition", default="gpu")
    parser.add_argument("--account")
    parser.add_argument("--gpu-resource", default="gpu:1")
    parser.add_argument("--time", default="02:00:00")
    parser.add_argument("--mem", default="16G")
    parser.add_argument("--cpus", type=int, default=1)
    parser.add_argument("--julia", default="julia")
    parser.add_argument("--julia-depot")
    parser.add_argument("--module", action="append", default=[])
    parser.add_argument("--run-name", default=None)
    parser.add_argument("--run-root", type=Path, default=REPO_ROOT / "runs")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.L < 2:
        parser.error("--L must be at least 2")
    if args.eps <= 0 or not math.isfinite(args.eps):
        parser.error("--eps must be finite and positive")
    if args.n_lf < 1 or args.samples < 1 or args.skip < 1 or args.warmup < 0 or args.replicas < 1:
        parser.error("n-lf, samples, skip, and replicas must be positive; warmup may be zero")
    args.run_name = args.run_name or f"reweight_L{args.L}"
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.run_name):
        parser.error("--run-name may contain only letters, digits, dot, underscore, and hyphen")

    points = list(args.point)
    try:
        for points_file in args.points_csv:
            points.extend(read_points_csv(points_file))
    except (OSError, ValueError, argparse.ArgumentTypeError) as exc:
        parser.error(str(exc))
    if not points:
        parser.error("provide at least one --point=Z,m2 or --points-csv")
    if len(set(points)) != len(points):
        parser.error("duplicate source points are not allowed; use --replicas instead")

    run_dir = (args.run_root / args.run_name).resolve()
    logs = run_dir / "logs"
    for directory in (run_dir / "checkpoints", run_dir / "statistics", run_dir / "complete", logs):
        directory.mkdir(parents=True, exist_ok=True)
    manifest = run_dir / "manifest.csv"
    rows = build_rows(args, points, run_dir)
    write_manifest(manifest, rows)
    script_path = run_dir / "array_job.sh"
    temporary = script_path.with_name(script_path.name + ".tmp")
    temporary.write_text(job_script(args, manifest, len(rows), logs), encoding="utf-8")
    temporary.replace(script_path)

    print(f"manifest: {manifest}")
    print(f"tasks: {len(rows)} ({len(points)} points x {args.replicas} replicas)")
    print(f"job script: {script_path}")
    print(script_path.read_text(encoding="utf-8"))
    if args.dry_run:
        print("# Per-task commands:")
        for row in rows:
            command = [
                "python3", str(REPO_ROOT / "scripts/run_reweight_task.py"),
                "--manifest", str(manifest), "--task-id", str(row["task_id"]),
                "--julia", args.julia, "--launcher", "srun", "--dry-run",
            ]
            if args.resume:
                command.append("--resume")
            subprocess.run(command, check=True)
        print("dry-run: sbatch was not invoked")
        return 0

    subprocess.run(["sbatch", str(script_path)], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
