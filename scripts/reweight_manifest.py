"""Shared manifest utilities for LSF and TSP reweighting submitters."""

from __future__ import annotations

import argparse
import csv
import hashlib
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
            if args.init_schedule == "split":
                init_phase = "disordered" if replica < args.replicas // 2 else "ordered"
            else:
                init_phase = args.init_schedule
            rows.append({
                "schema_version": 1, "task_id": task_id, "point_index": point_index,
                "replica": replica, "L": args.L, "Z": Z, "m2": m2,
                "eps": canonical_number(str(args.eps)), "n_lf": args.n_lf, "seed": seed,
                "startup_eps": canonical_number(str(args.startup_eps)),
                "startup_n_lf": args.startup_n_lf,
                "startup_sweeps": args.startup_sweeps,
                "samples": args.samples, "skip": args.skip, "warmup": args.warmup,
                "tempering_replicas": args.tempering_replicas,
                "mass_span": canonical_number(str(args.mass_span)),
                "swap_every": args.swap_every,
                "init_phase": init_phase,
                "phase_threshold": canonical_number(str(args.phase_threshold)),
                "checkpoint_path": str((run_dir / "checkpoints" / f"{base}.jld2").resolve()),
                "stats_path": str((run_dir / "statistics" / f"{base}.csv").resolve()),
                "diagnostics_path": str((run_dir / "diagnostics" / f"{base}.csv").resolve()),
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
