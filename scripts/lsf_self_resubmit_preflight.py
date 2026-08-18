#!/usr/bin/env python3
"""Prove that this compute node can submit and cancel an inert held LSF child."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from pathlib import Path

from umbrella_runtime import atomic_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--marker", type=Path, required=True)
    parser.add_argument("--bsub", default="bsub")
    parser.add_argument("--bkill", default="bkill")
    parser.add_argument("--queue", default="short_gpu")
    parser.add_argument("--runtime-home", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        print("held child submission/cancellation preflight")
        return 0
    env = os.environ.copy()
    if args.runtime_home is not None:
        home = args.runtime_home.resolve()
        (home / ".lsbatch").mkdir(parents=True, exist_ok=True)
        env["HOME"] = str(home)
        env["LSB_JOB_SPOOLDIR"] = str(home / ".lsbatch")
    result = subprocess.run(
        [args.bsub, "-H", "-J", "umbrella_child_preflight", "-q", args.queue,
         "-W", "1", "-n", "1", "-R", "rusage[mem=0.1]", "/bin/true"],
        check=True, text=True, capture_output=True, env=env,
    )
    match = re.search(r"Job <(\d+)>", result.stdout)
    if not match:
        raise RuntimeError(f"could not parse held child job id: {result.stdout!r}")
    job_id = match.group(1)
    subprocess.run([args.bkill, job_id], check=True, env=env)
    atomic_json(args.marker, {"success": True, "submitted_and_cancelled_job": job_id})
    print(f"self-resubmission preflight passed: {args.marker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
