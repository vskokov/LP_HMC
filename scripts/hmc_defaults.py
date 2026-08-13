"""Measured HMC defaults shared by the local and Slurm submitters."""

from __future__ import annotations


# Tuned on CUDA at Z=-0.6, m2=-1.85764 using ordered and disordered chains.
# epsilon was chosen near 70--80% acceptance; n_lf maximizes effective samples
# per force evaluation for the slower of M^2 and Q in the confirmation study.
HMC_DEFAULTS: dict[int, tuple[float, int]] = {
    6: (0.06558992039, 32),
    8: (0.05286071721, 16),
    12: (0.039, 6),
    16: (0.03143117051, 4),
    18: (0.02877372991, 6),
    24: (0.02318953874, 4),
    28: (0.02065770247, 4),
    32: (0.02070175658, 4),
}

# Cold-start values measured at Z=-0.6, m2=-1.85764 on the complete batched
# 17-slot, mass-span=0.6 ladder from both ordered and disordered starts.  Every
# selected pair was followed for L^3 sweeps in L^2 blocks; selected pairs have no
# zero-acceptance slots and >=70% worst-slot acceptance in every block.  Their
# trajectory lengths are near 0.24 and intentionally differ from equilibrium
# efficiency optima above.
STARTUP_HMC_DEFAULTS: dict[int, tuple[float, int]] = {
    6: (0.035, 7),
    8: (0.03, 8),
    12: (0.021, 11),
    16: (0.015, 16),
    18: (0.013, 18),
    24: (0.0095, 25),
    28: (0.0075, 32),
    32: (0.0065, 37),
}


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
