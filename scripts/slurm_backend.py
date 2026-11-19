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
    "modules": ["cuda/13.2", "julia/1.12.6"],
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
             f"#SBATCH --gres=gpu:{cfg['gpu_type']}:1",
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
    if cfg.get("exclude"):
        lines.append(f"#SBATCH --exclude={cfg['exclude']}")
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
        '  if (( n < MAXC )); then sbatch "$SELF"; else echo "continuation cap $MAXC reached"; fi',
        '  exit 0',
        'fi',
        'exit $rc',
        ""]
    return "\n".join(lines)


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
            subprocess.run(["sbatch", str(script)], check=True)
            print(f"submit   {lab}")
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
             f"#SBATCH --gres=gpu:{cfg['gpu_type']}:1", "#SBATCH --ntasks=1",
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
        subprocess.run(["sbatch", str(script)], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
