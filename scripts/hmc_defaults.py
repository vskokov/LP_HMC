"""Measured HMC defaults shared by the LSF and TSP submitters."""

from __future__ import annotations

import csv
from pathlib import Path


# Tuned on CUDA at Z=-0.6, m2=-1.86421 (canonical production point). Values for
# L=6,8,12,16,18,24,32 were measured at the nearby point m2=-1.85764; the shift
# is sub-percent and leaves acceptance inside the 70--80% band. L=20 is log-space
# interpolated between L=18 and L=24. Re-run scripts/hmc_tune_suite.jl to refresh.
HMC_DEFAULTS: dict[int, tuple[float, int]] = {
    6: (0.06558992039, 32),
    8: (0.05286071721, 16),
    12: (0.039, 6),
    16: (0.03143117051, 4),
    18: (0.02877372991, 6),
    20: (0.02658753317, 5),
    24: (0.02318953874, 4),
    28: (0.02065770247, 4),
    32: (0.02070175658, 4),
}

# Cold-start values measured at Z=-0.6, m2=-1.85764 on the complete batched
# 17-slot, mass-span=0.6 ladder from both ordered and disordered starts.  Every
# selected pair was followed for L^3 sweeps in L^2 blocks; selected pairs have no
# zero-acceptance slots and >=70% worst-slot acceptance in every block.  Their
# trajectory lengths are near 0.24 and intentionally differ from equilibrium
# efficiency optima above.  L=20 is interpolated between L=18 and L=24.
STARTUP_HMC_DEFAULTS: dict[int, tuple[float, int]] = {
    6: (0.035, 7),
    8: (0.03, 8),
    12: (0.021, 11),
    16: (0.015, 16),
    18: (0.013, 18),
    20: (0.01158922277, 21),
    24: (0.0095, 25),
    28: (0.0075, 32),
    32: (0.0065, 37),
}


def resolve_tempering_parameters(
    lattice_size: int,
    profile: str | None,
    profile_file: Path | None,
    replicas: int | None,
    mass_span: float | None,
    swap_every: int | None,
) -> tuple[int, float, int, bool]:
    """Resolve exchange settings, requiring validated data for critical profiles.

    Explicit command-line values override profile fields.  With no profile this
    preserves the historical single-replica defaults.
    """

    if profile is None:
        return (
            1 if replicas is None else replicas,
            0.0 if mass_span is None else mass_span,
            1 if swap_every is None else swap_every,
            False,
        )
    if profile != "critical":
        raise ValueError(f"unknown tempering profile: {profile}")
    if replicas is not None and mass_span is not None and swap_every is not None:
        return replicas, mass_span, swap_every, False
    if profile_file is None:
        raise ValueError(
            "--tempering-profile=critical needs --tempering-profile-file unless "
            "all three exchange settings are explicit"
        )
    try:
        with profile_file.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as exc:
        raise ValueError(f"cannot read tempering profile file {profile_file}: {exc}") from exc
    matches = [
        row for row in rows
        if row.get("profile", "critical").strip().lower() == "critical"
        and int(row["L"]) == lattice_size
        and row.get("validated", "").strip().lower() in {"1", "true", "yes"}
    ]
    if len(matches) != 1:
        raise ValueError(
            f"{profile_file}: expected exactly one validated critical row for L={lattice_size}"
        )
    selected = matches[0]
    return (
        int(selected["tempering_replicas"]) if replicas is None else replicas,
        float(selected["mass_span"]) if mass_span is None else mass_span,
        int(selected["swap_every"]) if swap_every is None else swap_every,
        True,
    )


def resolve_hmc_parameters(
    lattice_size: int, epsilon: float | None, leapfrog_steps: int | None
) -> tuple[float, int, bool]:
    """Fill omitted parameters from the measured table.

    Return ``(epsilon, leapfrog_steps, used_default)``.  Explicit values always
    win, including when only one of the two parameters is supplied.
    """

    used_default = epsilon is None or leapfrog_steps is None
    if used_default and lattice_size not in HMC_DEFAULTS:
        supported = ", ".join(str(value) for value in sorted(HMC_DEFAULTS))
        raise ValueError(
            f"no tuned HMC defaults for L={lattice_size}; provide both --eps and "
            f"--n-lf (available default L values: {supported})"
        )
    default_epsilon, default_steps = HMC_DEFAULTS.get(lattice_size, (0.0, 0))
    return (
        default_epsilon if epsilon is None else epsilon,
        default_steps if leapfrog_steps is None else leapfrog_steps,
        used_default,
    )


def resolve_startup_hmc_parameters(
    lattice_size: int,
    epsilon: float | None,
    leapfrog_steps: int | None,
    sweeps: int | None,
) -> tuple[float, int, int, bool]:
    """Fill omitted cold-start controls from the measured startup table."""

    used_default = epsilon is None or leapfrog_steps is None or sweeps is None
    if (epsilon is None or leapfrog_steps is None) and lattice_size not in STARTUP_HMC_DEFAULTS:
        supported = ", ".join(str(value) for value in sorted(STARTUP_HMC_DEFAULTS))
        raise ValueError(
            f"no startup HMC defaults for L={lattice_size}; provide --startup-eps "
            f"and --startup-n-lf (available default L values: {supported})"
        )
    default_epsilon, default_steps = STARTUP_HMC_DEFAULTS.get(lattice_size, (0.0, 0))
    return (
        default_epsilon if epsilon is None else epsilon,
        default_steps if leapfrog_steps is None else leapfrog_steps,
        lattice_size**3 if sweeps is None else sweeps,
        used_default,
    )
