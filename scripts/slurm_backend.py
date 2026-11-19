#!/usr/bin/env python3
"""Slurm backend for manifest-driven GPU campaigns (NCSU Hazel and similar clusters).

Each manifest row becomes one self-continuing job chain:

  * ``<out>/slurm/job.sh`` is written once per row.  It loads the modules, exports the
    row environment, sets a runtime budget below the walltime, and runs the command.
  * Exit code 75 means "budget exhausted, checkpoint saved".  The script then
    resubmits itself (``sbatch job.sh``) until the run writes its completion marker
    or the continuation cap is reached.  Any other non-zero code stops the chain.
  * ``submit`` is idempotent: rows that are complete, or whose job name is already
    queued/running (``squeue --me``), are skipped, so it can be rerun at any time to
    restart chains that died (node failure, preemption).

The cluster settings come from a JSON config (default ``configs/hpc/hazel.json``);
every key can be overridden on the command line of the campaign driver.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "hpc" / "hazel.json"

DEFAULTS = {
    "partition": "gpu_partners",
    "qos": "short_gpu",
    "gpu_type": "l40s",
    "time": "02:00:00",
    "runtime_minutes": 100,          # budget handed to the simulation (exit 75 after it)
    "mem": "16G",
    "cpus_per_task": 1,
    "max_continuations": 400,
    "module_init": "",               # e.g. /usr/share/Modules/init/bash if `module` is absent
    "modules": ["julia/1.12.6"],           # no cuda module: CUDA.jl ships its own runtime
    "julia": "julia",
    "julia_depot_path": "/usr/local/usrapps/${GROUP:-$(id -gn)}/$USER/julia_depot",
    "account": "",
    "exclude": "",
    "extra_sbatch": [],
}


def load_config(path: Path | None = None, overrides: dict | None = None) -> dict:
    cfg = dict(DEFAULTS)
    path = path or Path(os.environ.get("LP_HMC_HPC_CONFIG", DEFAULT_CONFIG))
    if path.is_file():
        cfg.update(json.loads(path.read_text()))
    cfg.update({k: v for k, v in (overrides or {}).items() if v is not None})
    return cfg


def gpu_types(cfg: dict) -> list[str]:
    """``gpu_type`` may be one type ("l40s") or a comma list ("l40s,h100,h200")."""
    return [t.strip().lower() for t in str(cfg["gpu_type"]).split(",") if t.strip()]


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=True,
                              timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def pick_gpu_type(types: list[str], partition: str, qos: str) -> str:
    """Choose one of ``types`` for the next submission.

    Hazel rejects typed-OR and untyped GPU requests, so every job names one type.
    Preference: most GPUs we could start on now = min(idle GPUs of the type,
    remaining per-user QOS cap); then most remaining cap relative to the cap
    (queued jobs count); then list order.
    Any query failure falls back to the first type.
    """
    if len(types) == 1:
        return types[0]
    idle = dict.fromkeys(types, 0)
    out = _run(["sinfo", "-h", "-N", "-p", partition,
                "-O", "NodeHost:30,Gres:80,GresUsed:120,StateCompact:20"])
    seen = set()
    for line in out.splitlines():
        f = line.split()
        if len(f) < 4 or f[0] in seen:
            continue
        seen.add(f[0])
        if not re.match(r"^(idle|mix)$", f[3].rstrip("~#!%$@^*-+")):
            continue
        tot = re.search(r"gpu:([\w]+):(\d+)", f[1])
        used = re.search(r"gpu:([\w]+):(\d+)", f[2])
        if tot and tot.group(1).lower() in idle:
            idle[tot.group(1).lower()] += int(tot.group(2)) - (int(used.group(2)) if used else 0)
    caps = {}
    for item in _run(["sacctmgr", "-n", "-P", "show", "qos", qos,
                      "format=MaxTRESPU"]).strip().split(","):
        m = re.match(r"gres/gpu:(\w+)=(\d+)", item)
        if m:
            caps[m.group(1).lower()] = int(m.group(2))
    mine = dict.fromkeys(types, 0)
    for line in _run(["squeue", "--me", "-h", "-o", "%b"]).splitlines():
        m = re.search(r"gpu:(\w+):?(\d*)", line)
        if m and m.group(1).lower() in mine:
            mine[m.group(1).lower()] += int(m.group(2) or 1)
    def score(t):
        cap = caps.get(t, 1 << 30)
        head = cap - mine[t]
        # then the least-loaded type relative to its cap, so a backlog splits
        # in proportion to the per-user caps (L40S 4 : H100 2 : H200 2)
        return (min(idle[t], max(head, 0)), head / max(cap, 1), -types.index(t))
    return max(types, key=score)


def pick_main(argv: list[str]) -> int:
    """`slurm_backend.py pick-gpu TYPES PARTITION QOS` -> prints the chosen type."""
    types = [t for t in argv[0].lower().split(",") if t]
    try:
        print(pick_gpu_type(types, argv[1], argv[2] if len(argv) > 2 else ""))
    except Exception:  # never break a chain over the heuristic
        print(types[0])
    return 0


def gpu_sbatch_lines(cfg: dict, gpu: str | None = None) -> list[str]:
    """--gres (and --exclude) lines for one concrete GPU type."""
    gpu = gpu or gpu_types(cfg)[0]
    lines = [f"#SBATCH --gres=gpu:{gpu}:1"]
    if cfg.get("exclude"):
        lines.append(f"#SBATCH --exclude={cfg['exclude']}")
    return lines

def active_job_names() -> set[str]:
    try:
        out = subprocess.run(["squeue", "--me", "--noheader", "--format=%j"],
                             capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return set()
    return {line.strip() for line in out.splitlines() if line.strip()}


def job_script(*, label: str, env: dict, command: list[str], workdir: Path,
               done_marker: Path, cfg: dict) -> str:
    """Self-resubmitting batch script for one row."""
    sdir = workdir / "slurm"
    lines = ["#!/bin/bash",
             f"#SBATCH --job-name={label}",
             f"#SBATCH --partition={cfg['partition']}",
             *gpu_sbatch_lines(cfg),
             "#SBATCH --ntasks=1",
             f"#SBATCH --cpus-per-task={cfg['cpus_per_task']}",
             f"#SBATCH --mem={cfg['mem']}",
             f"#SBATCH --time={cfg['time']}",
             f"#SBATCH --output={sdir}/%j.out",
             f"#SBATCH --error={sdir}/%j.out"]
    if cfg.get("qos"):
        lines.append(f"#SBATCH --qos={cfg['qos']}")
    if cfg.get("account"):
        lines.append(f"#SBATCH --account={cfg['account']}")
    lines += [f"#SBATCH {x}" for x in cfg.get("extra_sbatch", [])]
    lines += ["", "set -u"]
    if cfg.get("module_init"):
        lines.append(f"source {shlex.quote(cfg['module_init'])}")
    lines += [f"module load {shlex.quote(m)}" for m in cfg.get("modules", [])]
    lines += [f'export JULIA_DEPOT_PATH="{cfg["julia_depot_path"]}"',
              "export JULIA_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 FFTW_NUM_THREADS=1"]
    for k, v in env.items():
        lines.append(f"export {k}={shlex.quote(str(v))}")
    lines += [
        f"SELF={shlex.quote(str(sdir / 'job.sh'))}",
        f"DONE={shlex.quote(str(done_marker))}",
        f"COUNT={shlex.quote(str(sdir / 'continuations'))}",
        f"MAXC={int(cfg['max_continuations'])}",
        '[[ -f "$DONE" ]] && { echo "already complete"; exit 0; }',
        'echo "host=$(hostname) job=${SLURM_JOB_ID:-} start=$(date -Is)"',
        "nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader || true",
        f"cd {shlex.quote(str(ROOT))}",
        shlex.join(command),
        "rc=$?",
        'echo "exit=$rc end=$(date -Is)"',
        'if [[ $rc -eq 75 ]]; then',
        '  n=$(( $(cat "$COUNT" 2>/dev/null || echo 0) + 1 )); echo $n > "$COUNT"',
        *resubmit_lines(cfg),
        '  exit 0',
        'fi',
        'exit $rc',
        ""]
    return "\n".join(lines)


def resubmit_lines(cfg: dict) -> list[str]:
    """Bash lines that resubmit the chain; re-pick the GPU type if several are allowed."""
    types = gpu_types(cfg)
    if len(types) == 1:
        sub = 'sbatch "$SELF"'
    else:
        pick = (f"python3 {shlex.quote(str(Path(__file__).resolve()))} pick-gpu "
                f"{','.join(types)} {shlex.quote(cfg['partition'])} {shlex.quote(cfg.get('qos') or '')}")
        sub = (f'G=$({pick} 2>/dev/null || echo {types[0]}); G=${{G:-{types[0]}}}; '
               'echo "resubmit gpu=$G"; sbatch --gres=gpu:$G:1 "$SELF"')
    return [f'  if (( n < MAXC )); then {sub}; else echo "continuation cap $MAXC reached"; fi']


def submit_rows_slurm(rows: list[dict], *, env_of: Callable[[dict], dict],
                      command: list[str], workdir_of: Callable[[dict], Path],
                      done_of: Callable[[dict], Path], label: Callable[[dict], str],
                      cfg: dict, dry_run: bool = False) -> int:
    active = set() if dry_run else active_job_names()
    n = 0
    for row in rows:
        lab = label(row)
        if done_of(row).is_file():
            continue
        if lab in active:
            print(f"active   {lab}")
            continue
        wd = workdir_of(row)
        (wd / "slurm").mkdir(parents=True, exist_ok=True)
        script = wd / "slurm" / "job.sh"
        env = dict(env_of(row))
        env["CVU_RUNTIME"] = str(int(cfg["runtime_minutes"]) * 60)
        script.write_text(job_script(label=lab, env=env, command=command, workdir=wd,
                                     done_marker=done_of(row), cfg=cfg))
        script.chmod(0o755)
        if dry_run:
            print(f"dry-run  {lab}  -> {script}")
        else:
            gpu = pick_gpu_type(gpu_types(cfg), cfg["partition"], cfg.get("qos") or "")
            subprocess.run(["sbatch", f"--gres=gpu:{gpu}:1", str(script)], check=True)
            print(f"submit   {lab}  gpu={gpu}")
        n += 1
    return n


def status_rows_slurm(rows: list[dict], *, done_of, label) -> None:
    active = active_job_names()
    done = sum(done_of(r).is_file() for r in rows)
    run = sum(label(r) in active for r in rows)
    print(f"{done}/{len(rows)} complete, {run} queued/running")
    for r in rows:
        if not done_of(r).is_file():
            wd = done_of(r).parent
            cont = wd / "slurm" / "continuations"
            c = cont.read_text().strip() if cont.is_file() else "0"
            diag = wd / "diagnostics.json"
            info = ""
            if diag.is_file():
                d = json.loads(diag.read_text())
                info = f"phase={d.get('phase')} sweeps={d.get('sweeps')} collected={d.get('collected')}"
            state = "active" if label(r) in active else "IDLE"
            print(f"  {state:6s} {label(r)}  cont={c} {info}")


def selftest_script(cfg: dict, out: Path) -> str:
    """One GPU job that instantiates the project and runs the correctness tests."""
    out.mkdir(parents=True, exist_ok=True)
    lines = ["#!/bin/bash", "#SBATCH --job-name=lp_hmc_selftest",
             f"#SBATCH --partition={cfg['partition']}",
             *gpu_sbatch_lines(cfg), "#SBATCH --ntasks=1",
             f"#SBATCH --mem={cfg['mem']}", f"#SBATCH --time={cfg['time']}",
             f"#SBATCH --output={out}/%j.out", f"#SBATCH --error={out}/%j.out"]
    if cfg.get("qos"):
        lines.append(f"#SBATCH --qos={cfg['qos']}")
    if cfg.get("account"):
        lines.append(f"#SBATCH --account={cfg['account']}")
    lines += ["", "set -u"]
    if cfg.get("module_init"):
        lines.append(f"source {shlex.quote(cfg['module_init'])}")
    lines += [f"module load {shlex.quote(m)}" for m in cfg.get("modules", [])]
    j = shlex.quote(cfg["julia"])
    lines += [f'export JULIA_DEPOT_PATH="{cfg["julia_depot_path"]}"',
              'mkdir -p "${JULIA_DEPOT_PATH%%:*}"',
              f"cd {shlex.quote(str(ROOT))}",
              "nvidia-smi", f"{j} --version",
              f"{j} --project=. -e 'using Pkg; Pkg.instantiate(); Pkg.precompile(); using CUDA; CUDA.versioninfo()'"]
    for t in ("test_hmc.jl", "test_replica_exchange.jl", "test_quadratic_cv.jl",
              "test_umbrella_gpu.jl"):
        lines.append(f'echo "=== {t}"; {j} --startup-file=no --project=. scripts/{t}; echo "=== {t} exit=$?"')
    return "\n".join(lines) + "\n"


def main() -> int:
    import argparse
    import sys
    if sys.argv[1:2] == ["pick-gpu"]:
        return pick_main(sys.argv[2:])
    ap = argparse.ArgumentParser(description="Cluster self-test (instantiate + correctness tests).")
    ap.add_argument("cmd", choices=("selftest",))
    ap.add_argument("--config", type=Path)
    ap.add_argument("--gpu")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    cfg = load_config(args.config, {"gpu_type": args.gpu})
    out = Path(os.environ.get("LP_HMC_RUNS", ROOT / "runs")) / "hpc_selftest"
    script = out / "selftest.sh"
    out.mkdir(parents=True, exist_ok=True)
    script.write_text(selftest_script(cfg, out))
    print(script)
    if not args.dry_run:
        gpu = pick_gpu_type(gpu_types(cfg), cfg["partition"], cfg.get("qos") or "")
        print(f"gpu={gpu}")
        subprocess.run(["sbatch", f"--gres=gpu:{gpu}:1", str(script)], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
