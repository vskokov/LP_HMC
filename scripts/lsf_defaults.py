"""Shared LSF defaults for umbrella and related GPU jobs."""

from __future__ import annotations

import os
import re
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


ARRAY_JOB_NAME = re.compile(r"^(?P<base>.+)\[(?P<spec>[^\]]+)\]$")


def expand_lsf_index_spec(spec: str) -> list[int]:
    """Expand an LSF array index list such as ``1-2``, ``1,4,7``, or ``1-2%4``."""
    spec = spec.split("%", 1)[0]
    indices: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            if end < start:
                raise ValueError(f"invalid LSF array range: {part!r}")
            indices.extend(range(start, end + 1))
        else:
            indices.append(int(part))
    if not indices or any(index < 1 for index in indices):
        raise ValueError(f"invalid LSF array spec: {spec!r}")
    return indices


def _set_option(command: list[str], flag: str, value: str) -> None:
    if flag in command:
        command[command.index(flag) + 1] = value
    else:
        command[1:1] = [flag, value]


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
    task_ids: list[int] | None = None,
) -> None:
    """Submit one scalar LSF job per task. Array ``-J name[1-N]`` specs are expanded.

    Hazel GPU nodes cannot open ``~/.lsbatch/*.JOBID.INDEX`` array wrappers, so
    we never submit ``bsub -J 'name[1-N]'``.
    """
    command = bsub_command_for_script(script_path, bsub=bsub, job_name=job_name)
    name = job_name
    if name is None and "-J" in command:
        name = command[command.index("-J") + 1]
    name = name or "job"
    match = ARRAY_JOB_NAME.match(name)
    base = match.group("base") if match else name
    if task_ids is not None:
        jobs = list(task_ids)
    elif match:
        jobs = [index - 1 for index in expand_lsf_index_spec(match.group("spec"))]
    else:
        jobs = [None]
    env = lsf_submit_environment(script_path)
    for task_id in jobs:
        cmd = list(command)
        extra = ""
        scalar_name = name
        if task_id is not None:
            scalar_name = f"{base}_t{task_id}"
            extra = (
                f"UMBRELLA_TASK_ID={task_id},UMBRELLA_CONTINUATION=0,"
                f"PROBE_ID={task_id}"
            )
        _set_option(cmd, "-J", scalar_name)
        _set_option(cmd, "-env", lsf_job_env_spec(script_path, extra=extra))
        print("+", f"HOME={env['HOME']}", shlex.join(cmd))
        if not dry_run:
            subprocess.run(cmd, check=True, env=env)
