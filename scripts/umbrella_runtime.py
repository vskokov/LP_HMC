#!/usr/bin/env python3
"""Runtime state primitives shared by restartable umbrella jobs."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Iterator


RETRYABLE_EXIT = 75
PERMANENT_EXIT = 2


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(name)


def deterministic_seed(base_seed: int, task_id: int, stage: str, block: int) -> int:
    """Return a stable positive 31-bit seed for one indivisible compute block."""
    digest = hashlib.sha256(
        f"umbrella-v1\0{base_seed}\0{task_id}\0{stage}\0{block}".encode()
    ).digest()
    return int.from_bytes(digest[:8], "big") % 2_147_483_646 + 1


@contextlib.contextmanager
def exclusive_task_lock(path: Path, blocking: bool = False) -> Iterator[None]:
    """Own a per-task advisory lock for the complete worker lifetime."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        operation = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        try:
            fcntl.flock(handle, operation)
        except BlockingIOError as exc:
            raise RuntimeError(f"task is already active: {path}") from exc
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()}\n")
        handle.flush()
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def claim_continuation(state_path: Path, allocation: int, maximum: int) -> bool:
    """Atomically claim one successor allocation, rejecting duplicates/overruns."""
    # Allocation zero is the initial job; the largest allowed index is max-1.
    if allocation >= maximum - 1:
        return False
    claim = state_path.with_name(f"{state_path.name}.continuation-{allocation + 1:02d}")
    claim.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(claim, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        return False
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(f"from={allocation}\nto={allocation + 1}\n")
    return True
