#!/usr/bin/env python3
"""Move run data between Hazel and the workstation through the shared research storage.

The NCSU research-storage share is mounted on both sides:

    Hazel:        /rsstu/users/v/vskokov/gluon
    workstation:  /hpc                      (NFS, krb5p: needs a valid Kerberos ticket)

Exchange directory on it: ``2026/lp_hmc_sync/``, holding

    cv_umbrella/<stage>/...   run directories without checkpoint.jld2
    OPS_JOURNAL.md, HPC_STATUS.md

``push`` (on Hazel): copy $LP_HMC_RUNS/cv_umbrella (all stages, no checkpoints) and the
journal to the share.  Runs in progress are copied too; only directories with
complete.json are final.

``push --checkpoints STAGE [...]`` (on Hazel, only when the run plan asks): copy just the
checkpoint.jld2 files of those stages to ``checkpoints/<stage>/`` on the share, for field
inspection on the workstation.  ``pull --checkpoints STAGE [...]`` puts them into the
matching local run directories.

``pull`` (on the workstation): copy the Hazel stages from /hpc into runs/cv_umbrella.
Only stages that run on Hazel are pulled (default: every stage present on the share
except the LOCAL ones), so local runs are never overwritten.
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARE_HAZEL = Path(os.environ.get("LP_HMC_SHARE", "/rsstu/users/v/vskokov/gluon"))
SHARE_LOCAL = Path("/hpc")
SUBDIR = Path("2026") / "lp_hmc_sync"
LOCAL_STAGES = {"s2_zm2", "s2_zm1172", "lro", "lro2", "pilot", "s2"}   # never pulled


def rsync(src: Path, dst: Path, extra: list[str], dry: bool) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    cmd = ["rsync", "-a", "--exclude", "checkpoint.jld2", "--exclude", "*.tmp",
           *extra, f"{src}/", f"{dst}/"]
    if dry:
        cmd.insert(1, "-n")
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)


def rsync_checkpoints(src: Path, dst: Path, dry: bool) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    cmd = ["rsync", "-a", "--include", "*/", "--include", "checkpoint.jld2", "--exclude", "*",
           "--prune-empty-dirs", f"{src}/", f"{dst}/"]
    if dry:
        cmd.insert(1, "-n")
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)


def push(args) -> int:
    runs = Path(os.environ["LP_HMC_RUNS"])
    share = args.share or SHARE_HAZEL
    if not share.is_dir():
        raise SystemExit(f"share {share} not mounted here; find it with `findmnt -t nfs,nfs4 | grep -i gluon` "
                         "or `df -h | grep rsstu` and set LP_HMC_SHARE (or --share)")
    dst = share / SUBDIR
    if args.checkpoints:
        for st in args.checkpoints:
            rsync_checkpoints(runs / "cv_umbrella" / st, dst / "checkpoints" / st, args.dry_run)
        return 0
    rsync(runs / "cv_umbrella", dst / "cv_umbrella", [], args.dry_run)
    for f in (runs / "OPS_JOURNAL.md", ROOT / "docs" / "HPC_STATUS.md"):
        if f.is_file() and not args.dry_run:
            subprocess.run(["cp", str(f), str(dst / f.name)], check=True)
    (dst / "LAST_PUSH").write_text(f"{socket.gethostname()} {subprocess.run(['date', '-Is'], capture_output=True, text=True).stdout}")
    return 0


def pull(args) -> int:
    src = (args.share or SHARE_LOCAL) / SUBDIR
    if args.checkpoints:
        for st in args.checkpoints:
            rsync_checkpoints(src / "checkpoints" / st, ROOT / "runs" / "cv_umbrella" / st, args.dry_run)
        return 0
    if not (src / "cv_umbrella").is_dir():
        raise SystemExit(f"{src}/cv_umbrella not found (mount or Kerberos ticket missing?)")
    stages = args.stage or sorted(p.name for p in (src / "cv_umbrella").iterdir()
                                  if p.is_dir() and p.name not in LOCAL_STAGES)
    for st in stages:
        if st in LOCAL_STAGES:
            print(f"skip LOCAL stage {st}")
            continue
        rsync(src / "cv_umbrella" / st, ROOT / "runs" / "cv_umbrella" / st,
              ["--exclude", "manifest.csv"], args.dry_run)
    for name in ("OPS_JOURNAL.md", "LAST_PUSH"):
        if (src / name).is_file():
            print(f"{name}: {(src / name).stat().st_size} bytes")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=("push", "pull"))
    ap.add_argument("--stage", nargs="+", help="pull: only these stages")
    ap.add_argument("--share", type=Path, help="override the share mount point")
    ap.add_argument("--checkpoints", nargs="+", metavar="STAGE",
                    help="transfer only the checkpoint.jld2 files of these stages")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    return push(args) if args.cmd == "push" else pull(args)


if __name__ == "__main__":
    raise SystemExit(main())
