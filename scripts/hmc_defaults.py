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
