#!/usr/bin/env python3
"""Shared helpers for manifest-driven GPU campaigns queued through task-spooler.

A campaign driver supplies rows (dicts), a ``command(row) -> list[str]`` builder,
an ``is_complete(row) -> bool`` predicate and a ``label(row) -> str``.  This module
handles the manifest I/O, idempotent submission (pending rows only, skipping rows
whose label is already queued or running), and status reporting.
"""

from __future__ import annotations

import csv
import shlex
import subprocess
from pathlib import Path
from typing import Callable, Iterable

ROOT = Path(__file__).resolve().parents[1]
JULIA = "/home/vskokov/.julia/juliaup/julia-1.12.6+0.x64.linux.gnu/bin/julia"
DEPOT = "/tmp/lp_hmc_julia_depot:/home/vskokov/.julia"
GPU_ENV = {
    "CUDA_VISIBLE_DEVICES": "0",
    "JULIA_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "FFTW_NUM_THREADS": "1",
    "JULIA_DEPOT_PATH": DEPOT,
}


def tag(value: float) -> str:
    """Directory-safe coupling tag: -0.95 -> m0p95."""
    return f"{value:g}".replace("-", "m").replace(".", "p")


def write_manifest(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError("refusing to write an empty manifest")
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        fields.extend(k for k in row if k not in fields)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def read_manifest(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise SystemExit(f"missing {path}; run prepare first")
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def julia_command(script: str | Path, args: Iterable[str] = (), env: dict[str, object] | None = None,
                  julia: str = JULIA) -> list[str]:
    merged = dict(GPU_ENV)
    merged.update({k: str(v) for k, v in (env or {}).items()})
    return ["env", *(f"{k}={v}" for k, v in merged.items()), julia, "--startup-file=no",
            f"--project={ROOT}", str(script), *map(str, args)]


def queued_labels(tsp: str = "tsp") -> set[str]:
    """Labels of tsp jobs that are queued or running (not finished)."""
    try:
        out = subprocess.run([tsp], capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return set()
    labels = set()
    for line in out.splitlines()[1:]:
        parts = line.split(None, 2)
        if len(parts) < 3 or parts[1] not in ("queued", "running", "allocating"):
            continue
        rest = line.split("[", 1)
        if len(rest) == 2 and "]" in rest[1]:
            labels.add(rest[1].split("]", 1)[0])
    return labels


def submit_rows(rows: list[dict[str, str]], *, command: Callable[[dict], list[str]],
                is_complete: Callable[[dict], bool], label: Callable[[dict], str],
                tsp: str = "tsp", dry_run: bool = False, slots: int = 1,
                prepare_row: Callable[[dict], None] | None = None) -> int:
    active = queued_labels(tsp)
    pending = [r for r in rows if not is_complete(r) and label(r) not in active]
    print(f"rows={len(rows)} complete={sum(map(is_complete, rows))} "
          f"already_queued={sum(label(r) in active for r in rows)} to_submit={len(pending)}")
    for row in pending:
        launch = [tsp, "-L", label(row), *command(row)]
        if dry_run:
            print("+", shlex.join(launch))
            continue
        if prepare_row:
            prepare_row(row)
        subprocess.run(launch, cwd=ROOT, check=True)
    if not dry_run and pending:
        subprocess.run([tsp, "-S", str(slots)], check=True)
    return len(pending)


def status_rows(rows: list[dict[str, str]], *, is_complete: Callable[[dict], bool],
                label: Callable[[dict], str], tsp: str = "tsp") -> int:
    active = queued_labels(tsp)
    done = [r for r in rows if is_complete(r)]
    queued = [r for r in rows if not is_complete(r) and label(r) in active]
    print(f"complete={len(done)}/{len(rows)} queued_or_running={len(queued)} "
          f"missing={len(rows) - len(done) - len(queued)}")
    return 0 if len(done) == len(rows) else 1
