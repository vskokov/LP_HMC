#!/usr/bin/env python3
"""Plot the unbiased umbrella P(M²) and M P(M²) at a fixed (Z, m², L).

M = √(M²). A pile-up of P(M²) at zero that vanishes in M P(M²) is the
M → M² Jacobian; a peak that survives is a genuine disordered-phase weight.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import numpy as np

from analyze_umbrella import estimate_with_bin_fallback, read_umbrella
from umbrella_binder_campaign import DEFAULT_CAMPAIGN_DIR, mass_key


REPO_ROOT = Path(__file__).resolve().parents[1]


def density_from_fit(fit: dict[str, object]) -> tuple[np.ndarray, np.ndarray]:
    centers = np.asarray(fit["profile_centers"], dtype=float)
    if "profile_density" in fit:
        density = np.asarray(fit["profile_density"], dtype=float)
    else:
        free = np.asarray(fit["profile_free_energy"], dtype=float)
        density = np.exp(-free)
        density[~np.isfinite(density)] = 0.0
    if "profile_edges" in fit:
        widths = np.diff(np.asarray(fit["profile_edges"], dtype=float))
    else:
        widths = np.full(len(centers), centers[1] - centers[0] if len(centers) > 1 else 1.0)
    total = float(np.dot(np.clip(density, 0.0, np.inf), widths))
    if total > 0:
        density = density / total
    return centers, density


def find_statistics(
    campaign_dir: Path, L: int, z_value: float, m2: float,
) -> list[tuple[str, Path]]:
    stats_dir = campaign_dir / f"L{L}" / "statistics"
    if not stats_dir.is_dir():
        raise SystemExit(f"missing statistics directory {stats_dir}")
    matches: list[tuple[str, Path]] = []
    for path in sorted(stats_dir.glob("*.csv")):
        metadata, _ = read_umbrella(path)
        if int(metadata["L"]) != L:
            continue
        if not math.isclose(float(metadata["Z"]), z_value, rel_tol=0.0, abs_tol=1e-8):
            continue
        if mass_key(metadata["m2"]) != mass_key(m2):
            continue
        matches.append((str(metadata.get("init_phase") or path.stem), path))
    if not matches:
        raise SystemExit(
            f"no umbrella statistics for L={L} Z={z_value:g} m2={m2:g} under {stats_dir}"
        )
    return matches


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--L", type=int, nargs="+", required=True)
    parser.add_argument("--Z", type=float, default=-0.6)
    parser.add_argument("--m2", type=float, required=True)
    parser.add_argument("--campaign-dir", type=Path, default=DEFAULT_CAMPAIGN_DIR)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--csv-output", type=Path)
    parser.add_argument("--title")
    parser.add_argument("--dpi", type=int, default=180)
    parser.add_argument(
        "--log", action="store_true",
        help="plot P(M²) on a log10 y-axis",
    )
    args = parser.parse_args()
    if args.dpi < 1:
        parser.error("--dpi must be positive")
    return args


def main() -> int:
    args = parse_args()
    series: list[tuple[int, str, np.ndarray, np.ndarray]] = []
    rows: list[dict[str, object]] = []
    for L in args.L:
        for phase, path in find_statistics(args.campaign_dir, L, args.Z, args.m2):
            metadata, arrays = read_umbrella(path)
            fit = estimate_with_bin_fallback(arrays)
            centers, density = density_from_fit(fit)
            series.append((L, phase, centers, density))
            for m2_value, p_value in zip(centers, density):
                magnetization = math.sqrt(max(float(m2_value), 0.0))
                rows.append({
                    "L": L, "Z": args.Z, "m2": args.m2, "init_phase": phase,
                    "M2": float(m2_value), "M": magnetization,
                    "P": float(p_value),
                    "MP": magnetization * float(p_value),
                    "M2P": float(m2_value) * float(p_value),
                    "source": str(path.resolve()),
                })

    output = args.output or (
        REPO_ROOT / "plots" /
        f"umbrella_PM2_Z{args.Z:g}_m2{args.m2:g}_L{'-'.join(str(L) for L in args.L)}.png"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    csv_path = args.csv_output or output.with_suffix(".csv")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 1, figsize=(6.5, 6.6), sharex=True)
    for L, phase, centers, density in series:
        label = f"L={L}" if len(args.L) == 1 else f"L={L}, {phase}"
        if len(args.L) == 1:
            label = phase
        linestyle = "--" if phase == "ordered" else "-"
        magnetization = np.sqrt(np.clip(centers, 0.0, None))
        p_plot = np.where(density > 0.0, density, np.nan) if args.log else density
        axes[0].plot(centers, p_plot, linestyle=linestyle, label=label)
        axes[1].plot(centers, magnetization * density, linestyle=linestyle, label=label)
    axes[0].set_ylabel(r"$P(M^2)$")
    axes[1].set_ylabel(r"$M\,P(M^2)$")
    axes[1].set_xlabel(r"$M^2$")
    axes[0].set_title(
        args.title or rf"$P(M^2)$ and $M\,P(M^2)$ at $Z={args.Z:g}$, $m^2={args.m2:g}$"
    )
    axes[0].legend(frameon=False, fontsize=8)
    axes[0].set_xlim(left=0.0)
    if args.log:
        axes[0].set_yscale("log")
    else:
        axes[0].set_ylim(bottom=0.0)
    axes[1].set_ylim(bottom=0.0)
    fig.tight_layout()
    fig.savefig(output, dpi=args.dpi)
    plt.close(fig)

    mp_output = output.with_name(output.stem + "_MP" + output.suffix)
    fig, axis = plt.subplots(figsize=(6.5, 4.2))
    for L, phase, centers, density in series:
        label = f"L={L}" if len(args.L) == 1 else f"L={L}, {phase}"
        if len(args.L) == 1:
            label = phase
        linestyle = "--" if phase == "ordered" else "-"
        magnetization = np.sqrt(np.clip(centers, 0.0, None))
        axis.plot(centers, magnetization * density, linestyle=linestyle, label=label)
    axis.set_xlabel(r"$M^2$")
    axis.set_ylabel(r"$M\,P(M^2)$")
    axis.set_title(
        rf"$M\,P(M^2)$ at $Z={args.Z:g}$, $m^2={args.m2:g}$"
    )
    axis.legend(frameon=False, fontsize=8)
    axis.set_xlim(left=0.0)
    axis.set_ylim(bottom=0.0)
    fig.tight_layout()
    fig.savefig(mp_output, dpi=args.dpi)
    plt.close(fig)

    m2p_output = output.with_name(output.stem + "_M2P" + output.suffix)
    fig, axis = plt.subplots(figsize=(6.5, 4.2))
    for L, phase, centers, density in series:
        label = f"L={L}" if len(args.L) == 1 else f"L={L}, {phase}"
        if len(args.L) == 1:
            label = phase
        linestyle = "--" if phase == "ordered" else "-"
        axis.plot(centers, centers * density, linestyle=linestyle, label=label)
    axis.set_xlabel(r"$M^2$")
    axis.set_ylabel(r"$M^2\,P(M^2)$")
    axis.set_title(
        rf"$M^2\,P(M^2)$ at $Z={args.Z:g}$, $m^2={args.m2:g}$"
    )
    axis.legend(frameon=False, fontsize=8)
    axis.set_xlim(left=0.0)
    axis.set_ylim(bottom=0.0)
    fig.tight_layout()
    fig.savefig(m2p_output, dpi=args.dpi)
    plt.close(fig)

    print(f"wrote {output}")
    print(f"wrote {mp_output}")
    print(f"wrote {m2p_output}")
    print(f"csv={csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
