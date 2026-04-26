#!/usr/bin/env python3
"""
HPC submission script with fully configurable parameter grid.

Identical workflow to 1_hpc_submit.py (thermalize → measure_single chained
in a single bsub job) but every grid dimension is settable on the command line.

Seed formula: coordinate-based encoding of (L, Z, m²) rounded to 3 decimal
places — gives a unique, reproducible seed for any grid, including refined
or partially overlapping grids.

Usage:
    # Default grid (same as 1_hpc_submit.py), L=24 only
    python 1_hpc_submit_custom.py --L 24

    # Refined scan: narrow Z window, finer m² step
    python 1_hpc_submit_custom.py --L 24 --Z-min -0.5 --Z-max 0.5 --Z-step 0.05 \\
                                  --m2-min -2.0 --m2-max -1.0 --m2-step 0.05

    # Multiple L, custom wall time and queue
    python 1_hpc_submit_custom.py --L 24 36 --m2-min -2.5 --m2-max -1.5 \\
                                  --walltime 300 --queue gpu

    # Dry run: print job count without submitting
    python 1_hpc_submit_custom.py --L 24 --dry-run
"""

import argparse
import csv
import os
import stat
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT   = Path(__file__).parent.resolve()
SCRIPTS_DIR = REPO_ROOT / "scripts"
DATA_DIR    = REPO_ROOT / "data"
TMP_DIR     = REPO_ROOT / "tmp"

# ---------------------------------------------------------------------------
# HPC environment
# ---------------------------------------------------------------------------
JULIA_DEPOT_PATH = "/rsstu/users/v/vskokov/gluon/jd"
JULIA_BIN        = "/rsstu/users/v/vskokov/gluon/julia-1.10.3/bin"
CUDA_MODULE      = "cuda/12.3"

DEFAULT_WALLTIME = 120
DEFAULT_QUEUE    = "short_gpu"
GPU_SELECT       = "select[h200 || h100 || l40s]"
GPU_EXCLUDE      = "select[hname!='gpu16' && hname!='gpu33']"
MEM_GB           = 16

# ---------------------------------------------------------------------------
# Default grid bounds (match 1_hpc_submit.py)
# ---------------------------------------------------------------------------
DEFAULT_Z_MIN    = -2.0
DEFAULT_Z_MAX    =  1.0
DEFAULT_Z_STEP   =  0.1
DEFAULT_M2_MIN   = -3.0
DEFAULT_M2_MAX   =  0.0
DEFAULT_M2_STEP  =  0.1

# HMC tuning parameters per L (eps scales ~L^(-3/4) to keep acceptance at 70-80%)
HMC_PARAMS = {
    12: {"eps": 0.04, "n_lf": 20},
    24: {"eps": 0.02, "n_lf": 10},
    36: {"eps": 0.01, "n_lf": 20},  # estimated: L^(-3/4) scaling from L=24
}

# ---------------------------------------------------------------------------
# Seed: coordinate-based, grid-independent
# ---------------------------------------------------------------------------

def _seed(L: int, Z: float, m2: float) -> int:
    """
    Unique deterministic seed for any (L, Z, m²) with up to 3 decimal places.

    Encoding:
        z_enc  = round(Z  * 1000) + 5000   →  non-negative for Z  in (-5, +5)
        m2_enc = round(m2 * 1000) + 5000   →  non-negative for m² in (-5, +5)
        seed   = L * 100_000_000 + z_enc * 10_000 + m2_enc + 1
    """
    z_enc  = round(Z  * 1000) + 5000
    m2_enc = round(m2 * 1000) + 5000
    return L * 100_000_000 + z_enc * 10_000 + m2_enc + 1


def _val_str(v: float) -> str:
    return str(round(float(v), 3))


def _therm_path(L: int, Z: float, m2: float, seed: int) -> Path:
    return DATA_DIR / (f"thermalized_L_{L}_Z_{_val_str(Z)}"
                       f"_mass_{_val_str(m2)}_id_{seed}.jld2")


def _data_path(L: int, Z: float, m2: float, seed: int) -> Path:
    return DATA_DIR / (f"magnetization_L_{L}_Z_{_val_str(Z)}"
                       f"_mass_{_val_str(m2)}_id_{seed}.dat")


# ---------------------------------------------------------------------------
# bsub helpers
# ---------------------------------------------------------------------------

def _bsub_header(walltime: int, queue: str, job_name: str) -> str:
    return f"""\
#!/usr/bin/env bash
#BSUB -J {job_name}
#BSUB -W {walltime}
#BSUB -n 1
#BSUB -q {queue}
#BSUB -R "{GPU_SELECT}"
#BSUB -R "{GPU_EXCLUDE}"
#BSUB -R "rusage[mem={MEM_GB}.00]"
#BSUB -gpu "num=1:mode=shared:mps=no"
#BSUB -o {TMP_DIR}/out.%J
#BSUB -e {TMP_DIR}/err.%J

source /usr/share/Modules/init/bash
export JULIA_DEPOT_PATH={JULIA_DEPOT_PATH}
export PATH={JULIA_BIN}:$PATH
module load {CUDA_MODULE}

"""


def _julia_cmd(script: Path, L: int, Z: float, m2: float,
               seed: int, init_path: Optional[Path],
               eps: float, n_lf: int) -> str:
    flags = [
        #f"--project={REPO_ROOT}",
        str(script),
        "--fp64",
        f"--Z={Z}",
        f"--mass={m2}",
        f"--rng={seed}",
        f"--eps={eps}",
        f"--n_lf={n_lf}",
    ]
    if init_path is not None:
        flags.append(f"--init={init_path.resolve()}")
    flags.append(str(L))
    return "julia " + " ".join(flags)


def _make_grid(vmin: float, vmax: float, step: float) -> np.ndarray:
    return np.round(np.arange(vmin, vmax + step * 0.5, step), decimals=6)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Submit phase-diagram scan jobs to LSF with a configurable grid.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Grid
    parser.add_argument("--L", type=int, nargs="+", required=True,
                        metavar="L",
                        help=f"Lattice size(s). Supported: {sorted(HMC_PARAMS)}.")
    parser.add_argument("--Z-min",   type=float, default=DEFAULT_Z_MIN,
                        help="Minimum Z value.")
    parser.add_argument("--Z-max",   type=float, default=DEFAULT_Z_MAX,
                        help="Maximum Z value.")
    parser.add_argument("--Z-step",  type=float, default=DEFAULT_Z_STEP,
                        help="Z grid spacing.")
    parser.add_argument("--m2-min",  type=float, default=DEFAULT_M2_MIN,
                        help="Minimum m² value.")
    parser.add_argument("--m2-max",  type=float, default=DEFAULT_M2_MAX,
                        help="Maximum m² value.")
    parser.add_argument("--m2-step", type=float, default=DEFAULT_M2_STEP,
                        help="m² grid spacing.")

    # LSF
    parser.add_argument("--walltime", type=int, default=DEFAULT_WALLTIME,
                        help="Wall time in minutes.")
    parser.add_argument("--queue", type=str, default=DEFAULT_QUEUE,
                        help="LSF queue name.")

    # Misc
    parser.add_argument("--dry-run", action="store_true",
                        help="Print job count and grid summary without submitting.")
    parser.add_argument("--index", type=str, default=None,
                        help="Path for jobs_index.csv "
                             "(default: jobs_index_custom.csv in repo root).")
    args = parser.parse_args()

    z_grid  = _make_grid(args.Z_min,  args.Z_max,  args.Z_step)
    m2_grid = _make_grid(args.m2_min, args.m2_max, args.m2_step)

    n_jobs = len(args.L) * len(z_grid) * len(m2_grid)

    invalid = [v for v in args.L if v not in HMC_PARAMS]
    if invalid:
        parser.error(f"--L values {invalid} are not in the supported set {sorted(HMC_PARAMS)}.")

    print(f"Grid summary:")
    print(f"  L       : {args.L}")
    print(f"  Z       : {len(z_grid)} points in [{z_grid[0]:.4g}, {z_grid[-1]:.4g}]"
          f"  step={args.Z_step}")
    print(f"  m²      : {len(m2_grid)} points in [{m2_grid[0]:.4g}, {m2_grid[-1]:.4g}]"
          f"  step={args.m2_step}")
    print(f"  Total   : {n_jobs} jobs")
    print(f"  Queue   : {args.queue}  |  Wall time: {args.walltime} min")

    if args.dry_run:
        print("\n(dry-run — nothing submitted)")
        return

    TMP_DIR.mkdir(exist_ok=True)

    index_path = Path(args.index) if args.index else REPO_ROOT / "jobs_index_custom.csv"
    n_submitted = 0
    n_skipped   = 0
    n_measure_only = 0

    with open(index_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["seed", "L", "Z", "m2", "therm_file", "data_file"])

        for L in args.L:
            hmc = HMC_PARAMS[L]
            for Z in z_grid:
                for m2 in m2_grid:
                    Z_f  = float(Z)
                    m2_f = float(m2)
                    seed       = _seed(L, Z_f, m2_f)
                    therm_file = _therm_path(L, Z_f, m2_f, seed)
                    data_file  = _data_path(L, Z_f, m2_f, seed)

                    writer.writerow([seed, L, Z_f, m2_f,
                                     str(therm_file), str(data_file)])

                    if data_file.exists():
                        n_skipped += 1
                        continue

                    job_name = (f"phi4_L{L}_Z{_val_str(Z_f)}"
                                f"_m{_val_str(m2_f)}")

                    cmd_measure = _julia_cmd(SCRIPTS_DIR / "measure_single.jl",
                                             L, Z_f, m2_f, seed,
                                             init_path=therm_file,
                                             eps=hmc["eps"], n_lf=hmc["n_lf"])

                    if therm_file.exists():
                        # Thermalization already done — only measure
                        payload_body = f"{cmd_measure}\n"
                        n_measure_only += 1
                    else:
                        cmd_therm = _julia_cmd(SCRIPTS_DIR / "thermalize.jl",
                                               L, Z_f, m2_f, seed,
                                               init_path=None,
                                               eps=hmc["eps"], n_lf=hmc["n_lf"])
                        payload_body = f"{cmd_therm} && {cmd_measure}\n"

                    header  = _bsub_header(args.walltime, args.queue, job_name)
                    payload = header + payload_body

                    with tempfile.NamedTemporaryFile(
                        mode="w", dir=TMP_DIR, suffix=".sh", delete=False
                    ) as tf:
                        tf.write(payload)
                        tmp_path = Path(tf.name)

                    tmp_path.chmod(tmp_path.stat().st_mode | stat.S_IXUSR)
                    os.system(f"bsub < {tmp_path}")
                    tmp_path.unlink()

                    n_submitted += 1

    print(f"\nSubmitted {n_submitted} jobs  "
          f"({n_measure_only} measure-only, {n_submitted - n_measure_only} full).")
    print(f"Skipped   {n_skipped} already-complete points.")
    print(f"Index written to: {index_path}")


if __name__ == "__main__":
    main()
