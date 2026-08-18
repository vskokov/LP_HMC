"""Shared Julia/CUDA launch preflight for local and batch submitters."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path


MINIMUM_JULIA = "1.12"
JULIA_CHECK = (
    'VERSION >= v"1.12" || error("Julia 1.12 or newer is required; got $(VERSION)"); '
    'using CUDA; CUDA.functional(true) || error("CUDA is not functional"); '
    'println("preflight Julia=", VERSION, " GPU=", CUDA.name(CUDA.device())); '
    'CUDA.versioninfo()'
)


def command(julia: str, project: Path) -> list[str]:
    return [julia, "--startup-file=no", f"--project={project}", "-e", JULIA_CHECK]


def shell_command(julia: str, project: Path) -> str:
    return shlex.join(command(julia, project))


def lsf_julia_launch_lines(julia: str, project: Path) -> list[str]:
    return [
        'echo "julia=$(command -v julia)"',
        "julia --version",
        'echo "checking CUDA runtime and device"',
        shell_command(julia, project),
    ]


def run(julia: str, project: Path) -> None:
    try:
        subprocess.run(command(julia, project), check=True)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Julia executable not found: {julia}") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Julia/CUDA preflight failed for {julia}; use Julia {MINIMUM_JULIA}+ "
            "with a functional CUDA environment"
        ) from exc
