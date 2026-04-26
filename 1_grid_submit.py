#!/usr/bin/env python3
"""
Script 1: The Execution Agent
Submits all (L, Z, m²) HMC simulation jobs to the task-spooler (tsp) queue.

Workflow for each parameter point:
  1. julia thermalize.jl  → saves data/thermalized_L_{L}_Z_{Z}_mass_{m2}_id_{seed}.jld2
  2. julia measure_single.jl --init=<jld2>  → saves data/magnetization_L_{L}_Z_{Z}_mass_{m2}_id_{seed}.dat

Both steps are chained in a single tsp job via bash -c "cmd1 && cmd2" so that
measurement only starts after successful thermalization.

A jobs_index.csv is written that maps every seed → (L, Z, m², expected_data_file),
which is consumed by 2_analyze_data.py.

HMC step size (--eps) and leapfrog count (--n_lf) are chosen per L to target
70–80% acceptance (see CLAUDE.md for tuning details).

Usage:
    python 1_grid_submit.py                    # full grid, default L=24 (961 jobs)
    python 1_grid_submit.py --L 12             # L=12 only (961 jobs)
    python 1_grid_submit.py --L 12 24          # L=12 and L=24
    python 1_grid_submit.py --test             # Z=1.0 only, default L (31 jobs)
    python 1_grid_submit.py --test --L 12      # Z=1.0 only, L=12 (31 jobs)
    python 1_grid_submit.py --cpu              # force CPU mode (adds --cpu to Julia)
"""

import argparse
import csv
import os
from pathlib import Path
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.resolve()
SCRIPTS_DIR = REPO_ROOT / "scripts"
DATA_DIR = REPO_ROOT / "data"

# ---------------------------------------------------------------------------
# Physics parameter grid (defaults)
# ---------------------------------------------------------------------------
L_VALUES = [24]

M2_DEFAULT = (-3.0, 0.0, 0.1)   # (min, max, step)
Z_DEFAULT  = (-2.0, 1.0, 0.1)   # (min, max, step)

# Reference indices (used for deterministic seed generation)
_L_IDX = {12: 0, 24: 1, 36: 2}

# HMC tuning parameters per L (eps scales ~L^(-3/4) to keep acceptance at 70-80%)
HMC_PARAMS = {
    12: {"eps": 0.04, "n_lf": 20},
    24: {"eps": 0.02, "n_lf": 10},
    36: {"eps": 0.01, "n_lf": 20},  # estimated: L^(-3/4) scaling from L=24
}
_Z0 = -2.0   # Z grid origin
_M2_0 = -3.0  # m² grid origin
_DZ = 0.1
_DM2 = 0.1


def _seed(L: int, Z: float, m2: float) -> int:
    """
    Deterministic seed encoding: unique integer per (L, Z, m²) point.

    seed = L_idx * 100_000 + z_idx * 100 + m2_idx + 1
      (+ 1 ensures seed != 0, which Julia treats as "no seeding")

    Max value: 2*100_000 + 60*100 + 40 + 1 = 206_041  (well within Int range)
    """
    L_idx = _L_IDX[L]
    z_idx = round((Z - _Z0) / _DZ)
    m2_idx = round((m2 - _M2_0) / _DM2)
    return L_idx * 100_000 + z_idx * 100 + m2_idx + 1


def _mass_id_str(m2: float) -> str:
    """
    Reproduce Julia's `round(m², digits=3)` filename fragment.
    For values with ≤ 1 decimal place this is just the value itself.
    """
    val = round(float(m2), 3)
    # Julia string interpolation of a Float64 prints '-4.0', '-0.1', '0.0', etc.
    # Python's str() of a float already does this for these clean values.
    return str(val)


def _therm_path(L: int, Z: float, m2: float, seed: int) -> Path:
    return DATA_DIR / f"thermalized_L_{L}_Z_{_mass_id_str(Z)}_mass_{_mass_id_str(m2)}_id_{seed}.jld2"


def _data_path(L: int, Z: float, m2: float, seed: int) -> Path:
    return DATA_DIR / f"magnetization_L_{L}_Z_{_mass_id_str(Z)}_mass_{_mass_id_str(m2)}_id_{seed}.dat"


def _julia_cmd(script: Path, L: int, Z: float, m2: float, seed: int,
               init_path: Optional[Path], cpu: bool,
               eps: float, n_lf: int) -> str:
    """Build the julia command string for a single script invocation."""
    flags = [
        f"--project={REPO_ROOT}",
        str(script),
        f"--fp64",
        f"--Z={Z}",
        f"--mass={m2}",
        f"--rng={seed}",
        f"--eps={eps}",
        f"--n_lf={n_lf}",
    ]
    if init_path is not None:
        # Use absolute path so it resolves correctly after Julia's cd(@__DIR__)
        flags.append(f"--init={init_path.resolve()}")
    if cpu:
        flags.append("--cpu")
    flags.append(str(L))

    return "julia " + " ".join(flags)


def main() -> None:
    parser = argparse.ArgumentParser(description="Submit phase-diagram scan jobs to tsp.")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Only submit jobs for Z = 1.0 to test the pipeline end-to-end.",
    )
    parser.add_argument(
        "--cpu",
        action="store_true",
        help="Pass --cpu to Julia (CPU parallelism instead of GPU).",
    )
    parser.add_argument(
        "--L",
        type=int,
        nargs="+",
        default=L_VALUES,
        metavar="L",
        help=(
            "Lattice sizes to submit (space-separated). "
            f"Must be a subset of {sorted(HMC_PARAMS)}. Default: {L_VALUES}."
        ),
    )
    parser.add_argument("--m2-min",  type=float, default=M2_DEFAULT[0],
                        help=f"m² grid minimum (default: {M2_DEFAULT[0]}).")
    parser.add_argument("--m2-max",  type=float, default=M2_DEFAULT[1],
                        help=f"m² grid maximum inclusive (default: {M2_DEFAULT[1]}).")
    parser.add_argument("--m2-step", type=float, default=M2_DEFAULT[2],
                        help=f"m² grid step size (default: {M2_DEFAULT[2]}).")
    parser.add_argument("--z-min",   type=float, default=Z_DEFAULT[0],
                        help=f"Z grid minimum (default: {Z_DEFAULT[0]}).")
    parser.add_argument("--z-max",   type=float, default=Z_DEFAULT[1],
                        help=f"Z grid maximum inclusive (default: {Z_DEFAULT[1]}).")
    parser.add_argument("--z-step",  type=float, default=Z_DEFAULT[2],
                        help=f"Z grid step size (default: {Z_DEFAULT[2]}).")
    args = parser.parse_args()

    n_dec = lambda s: len(str(s).rstrip("0").split(".")[-1]) if "." in str(s) else 0
    m2_dec = n_dec(args.m2_step)
    z_dec  = n_dec(args.z_step)

    invalid = [v for v in args.L if v not in HMC_PARAMS]
    if invalid:
        parser.error(f"--L values {invalid} are not in the supported set {sorted(HMC_PARAMS)}.")

    m2_grid = np.round(
        np.arange(args.m2_min, args.m2_max + args.m2_step * 1e-9, args.m2_step),
        decimals=m2_dec,
    )
    z_grid_full = np.round(
        np.arange(args.z_min, args.z_max + args.z_step * 1e-9, args.z_step),
        decimals=z_dec,
    )

    # Limit tsp concurrency to 3 simultaneous GPU jobs
    os.system("tsp -S 3")

    z_grid = z_grid_full if not args.test else np.array([1.0])

    index_path = REPO_ROOT / "jobs_index.csv"
    n_submitted = 0

    with open(index_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["seed", "L", "Z", "m2", "therm_file", "data_file"])

        for L in args.L:
            hmc = HMC_PARAMS[L]
            for Z in z_grid:
                for m2 in m2_grid:
                    seed = _seed(L, float(Z), float(m2))
                    therm_file = _therm_path(L, float(Z), float(m2), seed)
                    data_file = _data_path(L, float(Z), float(m2), seed)

                    # Record the mapping so the analysis script can find files
                    writer.writerow([
                        seed, L, float(Z), float(m2),
                        str(therm_file), str(data_file),
                    ])

                    # Step 1: thermalize
                    cmd_therm = _julia_cmd(
                        SCRIPTS_DIR / "thermalize.jl",
                        L, float(Z), float(m2), seed,
                        init_path=None,
                        cpu=args.cpu,
                        eps=hmc["eps"],
                        n_lf=hmc["n_lf"],
                    )

                    # Step 2: measure (depends on thermalized state)
                    cmd_measure = _julia_cmd(
                        SCRIPTS_DIR / "measure_single.jl",
                        L, float(Z), float(m2), seed,
                        init_path=therm_file,
                        cpu=args.cpu,
                        eps=hmc["eps"],
                        n_lf=hmc["n_lf"],
                    )

                    # Chain into a single tsp job so measurement only runs
                    # after successful thermalization.
                    # Single-quote the inner command to avoid shell expansion issues.
                    inner = f"{cmd_therm} && {cmd_measure}"
                    tsp_cmd = f"tsp bash -c '{inner}'"

                    os.system(tsp_cmd)
                    n_submitted += 1

    print(f"Submitted {n_submitted} jobs to tsp.")
    print(f"  L  values : {args.L}")
    print(f"  Z  values : {'Z=1.0 only (test mode)' if args.test else f'{len(z_grid)} points in [{z_grid[0]}, {z_grid[-1]}], step={args.z_step}'}")
    print(f"  m² values : {len(m2_grid)} points in [{m2_grid[0]}, {m2_grid[-1]}], step={args.m2_step}")
    print(f"Parameter index written to: {index_path}")


if __name__ == "__main__":
    main()
