#!/usr/bin/env python3
"""Interpolate 12×16, 16×20, and 20×24 Binder crossings and plot vs Z."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_by_L(path: Path) -> dict[int, list[tuple[float, float]]]:
    grouped: dict[int, list[tuple[float, float]]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            grouped[int(float(row["L"]))].append((float(row["m2"]), float(row["U4"])))
    for lattice in grouped:
        grouped[lattice].sort()
    return grouped


def crossings(left: list[tuple[float, float]], right: list[tuple[float, float]]):
    d1 = dict(left)
    d2 = dict(right)
    common = sorted(set(d1) & set(d2))
    found: list[tuple[float, float]] = []
    for i in range(len(common) - 1):
        m0, m1 = common[i], common[i + 1]
        delta0 = d1[m0] - d2[m0]
        delta1 = d1[m1] - d2[m1]
        if delta0 * delta1 >= 0:
            continue
        t = delta0 / (delta0 - delta1)
        m2 = m0 + t * (m1 - m0)
        u4 = d1[m0] + t * (d1[m1] - d1[m0])
        found.append((m2, u4))
    if not found:
        return None
    return max(found, key=lambda item: item[1])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv", type=Path, nargs="+",
        default=[
            REPO_ROOT / "plots/umbrella_binder_mZm0p5.csv",
            REPO_ROOT / "plots/umbrella_binder_mZm0p25.csv",
            REPO_ROOT / "plots/umbrella_binder_mZ0.csv",
            REPO_ROOT / "plots/umbrella_binder_mZ0p5.csv",
            REPO_ROOT / "plots/umbrella_binder_mZ1.csv",
            REPO_ROOT / "plots/umbrella_binder_mZ1p25.csv",
            REPO_ROOT / "plots/umbrella_binder_mZ2.csv",
        ],
    )
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "plots/binder_crossings_vs_Z")
    parser.add_argument("--dpi", type=int, default=180)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows: list[dict[str, object]] = []
    for path in args.csv:
        by_L = load_by_L(path)
        z_values = []
        with path.open(newline="", encoding="utf-8") as handle:
            z_values = [float(row["Z"]) for row in csv.DictReader(handle)]
        z_value = z_values[0]
        for name, pair in (("12x16", (12, 16)), ("16x20", (16, 20)), ("20x24", (20, 24))):
            if pair[0] not in by_L or pair[1] not in by_L:
                continue
            found = crossings(by_L[pair[0]], by_L[pair[1]])
            if found is None:
                continue
            m2, u4 = found
            rows.append({
                "Z": z_value, "pair": name, "m2_c": m2, "U4_star": u4, "source": str(path),
            })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    csv_path = Path(str(args.output) + ".csv")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Z", "pair", "m2_c", "U4_star", "source"])
        writer.writeheader()
        writer.writerows(rows)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 1, figsize=(6.6, 6.4), sharex=True)
    for name, marker in (("12x16", "o"), ("16x20", "s"), ("20x24", "^")):
        subset = [row for row in rows if row["pair"] == name]
        subset.sort(key=lambda row: float(row["Z"]))
        z_axis = [float(row["Z"]) for row in subset]
        axes[0].plot(z_axis, [float(row["m2_c"]) for row in subset], marker=marker, label=name)
        axes[1].plot(z_axis, [float(row["U4_star"]) for row in subset], marker=marker, label=name)
    axes[1].axhline(0.465, color="0.35", linestyle="--", linewidth=1.0, label=r"$U_4=0.465$")
    axes[0].set_ylabel(r"$m^2_c$")
    axes[1].set_ylabel(r"$U_4^*$")
    axes[1].set_xlabel(r"$Z$")
    axes[0].legend(frameon=False)
    axes[1].legend(frameon=False)
    axes[0].grid(alpha=0.25)
    axes[1].grid(alpha=0.25)
    fig.tight_layout()
    png = Path(str(args.output) + ".png")
    fig.savefig(png, dpi=args.dpi)
    plt.close(fig)
    print(f"csv={csv_path}")
    print(f"wrote {png}")
    for row in rows:
        print(
            f"Z={row['Z']:g} {row['pair']} m2_c={float(row['m2_c']):.5f} "
            f"U4={float(row['U4_star']):.4f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
