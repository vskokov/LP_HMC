"""Shared LSF defaults for umbrella and related GPU jobs."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path


DEFAULT_EXCLUDED_HOSTS = ("gpu31",)
DEFAULT_MODULE_INIT = "/usr/share/Modules/init/bash"
DEFAULT_CUDA_MODULE = "cuda/13.2"
DEFAULT_JULIA_MODULE = "julia/1.12.6"
DEFAULT_JULIA_DEPOT_PATH = "/usr/local/usrapps/$GROUP/$USER/julia_depot"
DEFAULT_MEM_GB = 24.0


def resolved_exclude_hosts(hosts: list[str] | None) -> list[str]:
    if hosts is None:
        return list(DEFAULT_EXCLUDED_HOSTS)
    return list(hosts)


def lsf_environment_shell_lines(
    *,
    module_init: str = DEFAULT_MODULE_INIT,
    cuda_module: str = DEFAULT_CUDA_MODULE,
    julia_module: str = DEFAULT_JULIA_MODULE,
    julia_depot_path: str = DEFAULT_JULIA_DEPOT_PATH,
    extra_modules: list[str] | None = None,
) -> list[str]:
    lines = [
        f"source {shlex.quote(module_init)}",
        f"module load {shlex.quote(cuda_module)}",
        f"module load {shlex.quote(julia_module)}",
        f'export JULIA_DEPOT_PATH="{julia_depot_path}"',
    ]
    if extra_modules:
        lines.extend(f"module load {shlex.quote(module)}" for module in extra_modules)
    return lines


def lsf_runtime_home(script_path: Path) -> Path:
    """GPFS directory used as HOME so LSF job files are not written under /home."""
    home = script_path.resolve().parent / "lsf_home"
    (home / ".lsbatch").mkdir(parents=True, exist_ok=True)
    return home


def lsf_submit_environment(script_path: Path) -> dict[str, str]:
    home = lsf_runtime_home(script_path)
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["LSB_JOB_SPOOLDIR"] = str(home / ".lsbatch")
    return env


def lsf_job_env_spec(script_path: Path, extra: str = "") -> str:
    home = lsf_runtime_home(script_path)
    spec = f"all,HOME={home},LSB_JOB_SPOOLDIR={home / '.lsbatch'}"
    extra = extra.strip().removeprefix("all,").strip(",")
    if extra:
        spec = f"{spec},{extra}"
    return spec


def bsub_command_for_script(
    script_path: Path,
    *,
    bsub: str = "bsub",
    job_name: str | None = None,
) -> list[str]:
    """Build a bsub argv that runs the script from shared storage via bash."""
    resolved = script_path.resolve()
    command = [bsub]
    for line in resolved.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#BSUB"):
            command.extend(shlex.split(stripped[len("#BSUB") :].strip()))
            continue
        if stripped.startswith("#!") or not stripped:
            continue
        break
    if job_name is not None:
        if "-J" in command:
            command[command.index("-J") + 1] = job_name
        else:
            command[1:1] = ["-J", job_name]
    command.extend(["bash", str(resolved)])
    return command


def submit_bsub_script(
    script_path: Path,
    *,
    bsub: str = "bsub",
    dry_run: bool = False,
    job_name: str | None = None,
) -> None:
    """Submit a #BSUB script by passing directives to bsub and running bash on GPFS."""
    command = bsub_command_for_script(script_path, bsub=bsub, job_name=job_name)
    command[1:1] = ["-env", lsf_job_env_spec(script_path)]
    env = lsf_submit_environment(script_path)
    print("+", f"HOME={env['HOME']}", shlex.join(command))
    if not dry_run:
        subprocess.run(command, check=True, env=env)
