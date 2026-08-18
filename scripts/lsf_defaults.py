"""Shared LSF defaults for umbrella and related GPU jobs."""

from __future__ import annotations

import shlex


DEFAULT_EXCLUDED_HOSTS = ("gpu31",)
DEFAULT_MODULE_INIT = "/usr/share/Modules/init/bash"
DEFAULT_CUDA_MODULE = "cuda/13.2"
DEFAULT_JULIA_MODULE = "julia/1.12.6"
DEFAULT_JULIA_DEPOT_PATH = "/usr/local/usrapps/$GROUP/$USER/julia_depot"


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
