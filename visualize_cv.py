#!/usr/bin/env python3
"""
Intermediate visualization: specific heat C_V vs m².

Reads the energy time-series files produced by measure_single.jl and computes
    C_V = (1/L³) · (⟨H²⟩ - ⟨H⟩²)
for each m² value at a given (L, Z), then plots C_V vs m².

File format (from measure_single.jl):
    col 0 : MC step
    col 1 : total lattice energy H

Usage:
    python visualize_cv.py --L 12 --Z 1.0
    python visualize_cv.py --L 12 --Z 1.0 --data /path/to/data
    python visualize_cv.py --L 12 --Z 1.0 --data /mcmc/data /hmc/data --labels MCMC HMC
    python visualize_cv.py --L 12 --Z -1.0 --burnin 0.3 --out my_plot.pdf
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).parent.resolve()
DATA_DIR = REPO_ROOT / "data"
BURNIN_FRACTION = 0.01

COLORS = ["#377eb8", "#e41a1c", "#4daf4a", "#984ea3"]


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def _z_str(Z: float) -> str:
    """Reproduce Julia's round(Z, digits=3) filename fragment."""
    return str(round(Z, 3))


def find_files(L: int, Z: float, data_dir: Path) -> List[Tuple[float, Path]]:
    """
    Return list of (m², path) for every matching energy file in data_dir,
    sorted by m².
    """
    pattern = f"energy_L_{L}_Z_{_z_str(Z)}_mass_*_id_*.dat"
    files = list(data_dir.glob(pattern))
    if not files:
        return []

    results = []
    for p in files:
        stem = p.stem
        parts = stem.split("_mass_")
        if len(parts) != 2:
            continue
        mass_str = parts[1].split("_id_")[0]
        try:
            m2 = float(mass_str)
        except ValueError:
            continue
        results.append((m2, p))

    results.sort(key=lambda x: x[0])
    return results


def load_energy(path: Path, burnin: float) -> Optional[np.ndarray]:
    """Load energy column from a .dat file, dropping the first `burnin` fraction."""
    try:
        data = np.loadtxt(path)
    except Exception as e:
        print(f"  Warning: could not read {path.name}: {e}", file=sys.stderr)
        return None
    if data.ndim == 1:
        data = data.reshape(1, -1)
    n_drop = int(len(data) * burnin)
    return data[n_drop:, 1]   # energy column


# ---------------------------------------------------------------------------
# Observable
# ---------------------------------------------------------------------------

N_BOOTSTRAP = 1000
RNG_SEED = 42


def specific_heat(H: np.ndarray, L: int) -> float:
    """C_V = (1/L³) · (⟨H²⟩ - ⟨H⟩²)."""
    return float((np.mean(H**2) - np.mean(H)**2) / L**3)


def bootstrap_cv(H: np.ndarray, L: int,
                 n_boot: int = N_BOOTSTRAP,
                 rng: Optional[np.random.Generator] = None) -> Tuple[float, float]:
    """Return (cv_mean, cv_err) via bootstrap resampling."""
    if rng is None:
        rng = np.random.default_rng(RNG_SEED)
    n = len(H)
    cv_central = specific_heat(H, L)
    boots = np.array([specific_heat(H[rng.integers(0, n, size=n)], L)
                      for _ in range(n_boot)])
    return cv_central, float(np.std(boots, ddof=1))


def compute_curve(pairs: List[Tuple[float, Path]], L: int, burnin: float,
                  rng: np.random.Generator):
    """Return (m2_vals, cv_vals, cv_errs) arrays for a list of (m², path) pairs."""
    m2_vals, cv_vals, cv_errs = [], [], []
    for m2, path in pairs:
        H = load_energy(path, burnin)
        if H is None or len(H) < 5:
            print(f"  Skipping {path.name} (too few samples).", file=sys.stderr)
            continue
        cv_mean, cv_err = bootstrap_cv(H, L, rng=rng)
        m2_vals.append(m2)
        cv_vals.append(cv_mean)
        cv_errs.append(cv_err)
    return np.array(m2_vals), np.array(cv_vals), np.array(cv_errs)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot C_V vs m² for given L and Z."
    )
    parser.add_argument("--L", type=int, required=True, help="Lattice size")
    parser.add_argument("--Z", type=float, required=True, help="Kinetic coefficient Z")
    parser.add_argument(
        "--data",
        type=Path,
        nargs="+",
        default=[DATA_DIR],
        metavar="DIR",
        help="Data director(y/ies). Pass two to overlay curves (default: repo data/).",
    )
    parser.add_argument(
        "--labels",
        type=str,
        nargs="+",
        default=None,
        metavar="LABEL",
        help="Legend labels, one per --data directory.",
    )
    parser.add_argument(
        "--burnin",
        type=float,
        default=BURNIN_FRACTION,
        help=f"Burn-in fraction to discard (default: {BURNIN_FRACTION})",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Output file (default: cv_L<L>_Z<Z>.pdf)",
    )
    args = parser.parse_args()

    if len(args.data) > len(COLORS):
        parser.error(f"At most {len(COLORS)} data directories are supported.")

    labels = args.labels
    if labels is None:
        if len(args.data) == 1:
            labels = [None]
        else:
            labels = [d.name for d in args.data]
    elif len(labels) != len(args.data):
        parser.error("--labels must have the same number of entries as --data.")

    L, Z = args.L, args.Z
    rng = np.random.default_rng(RNG_SEED)

    fig, ax = plt.subplots(figsize=(8, 5), constrained_layout=True)
    any_data = False

    for data_dir, label, color in zip(args.data, labels, COLORS):
        pairs = find_files(L, Z, data_dir)
        if not pairs:
            print(f"Warning: no energy files found in {data_dir} for L={L}, Z={Z}",
                  file=sys.stderr)
            continue
        print(f"Found {len(pairs)} m² points in {data_dir}")

        m2_vals, cv_vals, cv_errs = compute_curve(pairs, L, args.burnin, rng)
        if len(m2_vals) == 0:
            continue

        ax.errorbar(m2_vals, cv_vals, yerr=cv_errs,
                    fmt="o-", markersize=4, linewidth=1.4, capsize=3,
                    color=color, label=label)
        any_data = True

    if not any_data:
        sys.exit("No usable data found.")

    if any(l is not None for l in labels):
        ax.legend(fontsize=11)

    ax.set_xlabel(r"$m^2$", fontsize=13)
    ax.set_ylabel(r"$C_V = \frac{1}{L^3}(\langle H^2\rangle - \langle H\rangle^2)$",
                  fontsize=12)
    ax.set_title(rf"Specific heat,  $L={L}$,  $Z={Z}$", fontsize=12)

    out_path = Path(args.out) if args.out else REPO_ROOT / f"cv_L{L}_Z{Z}.pdf"
    fig.savefig(out_path, dpi=200)
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
