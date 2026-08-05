#!/usr/bin/env python3
"""Single-source Ferrenberg--Swendsen reweighting of Binder cumulants."""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np


SCHEMA_VERSION = 1
REQUIRED_METADATA = {
    "schema_version", "L", "Z", "m2", "epsilon", "n_lf", "seed",
    "lambda", "temperature", "float_type", "device", "samples", "skip", "warmup",
}
REQUIRED_COLUMNS = ("trajectory", "M", "M2", "M4", "Q", "G", "acceptance_rate")


@dataclass(frozen=True)
class RunData:
    path: Path
    L: int
    Z: float
    m2: float
    seed: int
    epsilon: float
    n_lf: int
    order: int
    M2: np.ndarray
    M4: np.ndarray
    Q: np.ndarray
    G: np.ndarray

    @property
    def size(self) -> int:
        return len(self.M2)


@dataclass
class SourceGroup:
    L: int
    Z: float
    m2: float
    runs: list[RunData]
    first_order: int

    @property
    def size(self) -> int:
        return sum(run.size for run in self.runs)


def _parse_metadata_value(text: str, kind, name: str):
    try:
        return kind(text)
    except ValueError as exc:
        raise ValueError(f"invalid {name} metadata value {text!r}") from exc


def read_stats(path: Path, order: int = 0) -> RunData:
    """Read and strictly validate a collector CSV."""
    metadata: dict[str, str] = {}
    with path.open(newline="") as handle:
        while True:
            position = handle.tell()
            line = handle.readline()
            if not line:
                raise ValueError(f"{path}: missing CSV header")
            if not line.startswith("#"):
                handle.seek(position)
                break
            payload = line[1:].strip()
            if "=" not in payload:
                raise ValueError(f"{path}: malformed metadata line {line.rstrip()!r}")
            key, value = payload.split("=", 1)
            metadata[key.strip()] = value.strip()

        missing = REQUIRED_METADATA - metadata.keys()
        if missing:
            raise ValueError(f"{path}: missing metadata: {', '.join(sorted(missing))}")
        if _parse_metadata_value(metadata["schema_version"], int, "schema_version") != SCHEMA_VERSION:
            raise ValueError(f"{path}: unsupported schema_version={metadata['schema_version']}")

        reader = csv.DictReader(handle)
        if reader.fieldnames != list(REQUIRED_COLUMNS):
            raise ValueError(
                f"{path}: columns must be exactly {','.join(REQUIRED_COLUMNS)}"
            )
        rows = list(reader)

    if not rows:
        raise ValueError(f"{path}: contains no samples")
    arrays: dict[str, np.ndarray] = {}
    for column in REQUIRED_COLUMNS:
        try:
            arrays[column] = np.asarray([float(row[column]) for row in rows], dtype=float)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{path}: non-numeric {column} value") from exc
        if not np.all(np.isfinite(arrays[column])):
            raise ValueError(f"{path}: non-finite {column} value")

    if np.any(arrays["M2"] < 0) or np.any(arrays["M4"] < 0):
        raise ValueError(f"{path}: M2 and M4 must be non-negative")
    if np.any((arrays["acceptance_rate"] < 0) | (arrays["acceptance_rate"] > 1)):
        raise ValueError(f"{path}: acceptance_rate must lie in [0, 1]")
    if _parse_metadata_value(metadata["samples"], int, "samples") != len(rows):
        raise ValueError(f"{path}: sample count disagrees with metadata")
    if _parse_metadata_value(metadata["lambda"], float, "lambda") != 4.0:
        raise ValueError(f"{path}: reweighting requires lambda=4")
    if _parse_metadata_value(metadata["temperature"], float, "temperature") != 1.0:
        raise ValueError(f"{path}: reweighting requires temperature=1")

    return RunData(
        path=path,
        L=_parse_metadata_value(metadata["L"], int, "L"),
        Z=_parse_metadata_value(metadata["Z"], float, "Z"),
        m2=_parse_metadata_value(metadata["m2"], float, "m2"),
        seed=_parse_metadata_value(metadata["seed"], int, "seed"),
        epsilon=_parse_metadata_value(metadata["epsilon"], float, "epsilon"),
        n_lf=_parse_metadata_value(metadata["n_lf"], int, "n_lf"),
        order=order,
        M2=arrays["M2"], M4=arrays["M4"], Q=arrays["Q"], G=arrays["G"],
    )


def read_manifests(paths: Sequence[Path]) -> list[RunData]:
    runs: list[RunData] = []
    for manifest in paths:
        with manifest.open(newline="") as handle:
            reader = csv.DictReader(handle)
            fields = set(reader.fieldnames or ())
            stats_field = next(
                (name for name in ("stats_path", "stats_file", "stats", "output") if name in fields),
                None,
            )
            if stats_field is None:
                raise ValueError(f"{manifest}: no stats_path column")
            for row_number, row in enumerate(reader, start=2):
                raw_path = row.get(stats_field, "")
                if not raw_path:
                    raise ValueError(f"{manifest}:{row_number}: empty {stats_field}")
                stats_path = Path(raw_path)
                if not stats_path.is_absolute():
                    stats_path = manifest.parent / stats_path
                run = read_stats(stats_path, len(runs))
                for key, actual, kind in (
                    ("L", run.L, int), ("Z", run.Z, float), ("m2", run.m2, float),
                    ("seed", run.seed, int),
                ):
                    if key in row and row[key] != "" and kind(row[key]) != actual:
                        raise ValueError(
                            f"{manifest}:{row_number}: {key} disagrees with {stats_path} metadata"
                        )
                runs.append(run)
    if not runs:
        raise ValueError("the manifests contain no runs")
    return runs


def group_sources(runs: Iterable[RunData]) -> dict[int, list[SourceGroup]]:
    grouped: dict[tuple[int, float, float], SourceGroup] = {}
    for run in runs:
        key = (run.L, run.Z, run.m2)
        if key not in grouped:
            grouped[key] = SourceGroup(run.L, run.Z, run.m2, [], run.order)
        grouped[key].runs.append(run)
    by_lattice: dict[int, list[SourceGroup]] = {}
    for group in grouped.values():
        by_lattice.setdefault(group.L, []).append(group)
    return by_lattice


def select_source(groups: Sequence[SourceGroup], Z: float, m2: float) -> SourceGroup:
    """Select by distance, then larger sample count, then manifest order."""
    return min(
        groups,
        key=lambda group: (
            math.hypot(group.Z - Z, group.m2 - m2),
            -group.size,
            group.first_order,
        ),
    )


def normalize_logweights(logw: np.ndarray) -> np.ndarray:
    logw = np.asarray(logw, dtype=float)
    if logw.ndim != 1 or logw.size == 0:
        raise ValueError("log weights must be a non-empty one-dimensional array")
    if not np.all(np.isfinite(logw)):
        raise ValueError("non-finite log weight")
    shifted = logw - np.max(logw)
    weights = np.exp(shifted)
    total = np.sum(weights)
    if not np.isfinite(total) or total <= 0:
        raise ValueError("weights cannot be normalized")
    return weights / total


def binder_from_weights(M2: np.ndarray, M4: np.ndarray, weights: np.ndarray) -> float:
    mean_m2 = float(np.dot(weights, M2))
    if not np.isfinite(mean_m2) or mean_m2 <= 16 * np.finfo(float).tiny:
        raise ValueError("weighted <M2> is numerically zero; Binder ratio is undefined")
    mean_m4 = float(np.dot(weights, M4))
    binder = 1.0 - mean_m4 / (3.0 * mean_m2**2)
    if not np.isfinite(binder):
        raise ValueError("non-finite Binder ratio")
    return binder


def evaluate_group(group: SourceGroup, target_Z: float, target_m2: float):
    M2 = np.concatenate([run.M2 for run in group.runs])
    M4 = np.concatenate([run.M4 for run in group.runs])
    Q = np.concatenate([run.Q for run in group.runs])
    G = np.concatenate([run.G for run in group.runs])
    with np.errstate(over="ignore", invalid="ignore"):
        logw = -0.5 * ((target_m2 - group.m2) * Q + (target_Z - group.Z) * G)
    weights = normalize_logweights(logw)
    binder = binder_from_weights(M2, M4, weights)
    ess = 1.0 / float(np.dot(weights, weights))
    return binder, ess, float(np.max(weights)), weights


def integrated_autocorrelation_time(values: np.ndarray) -> float:
    """Estimate τ_int by summing the autocorrelation through its positive window."""
    x = np.asarray(values, dtype=float)
    n = len(x)
    if n < 2:
        return 0.5
    x = x - np.mean(x)
    variance = float(np.dot(x, x))
    if variance <= 0 or not np.isfinite(variance):
        return 0.5
    nfft = 1 << (2 * n - 1).bit_length()
    spectrum = np.fft.rfft(x, nfft)
    autocov = np.fft.irfft(spectrum * np.conjugate(spectrum), nfft)[:n]
    autocov /= np.arange(n, 0, -1)
    rho = autocov / autocov[0]
    positive = rho[1:]
    stop = np.flatnonzero(positive <= 0)
    window = int(stop[0]) if stop.size else len(positive)
    return max(0.5, 0.5 + float(np.sum(positive[:window])))


def automatic_block_size(group: SourceGroup) -> int:
    max_tau = 0.5
    for run in group.runs:
        for values in (run.M2, run.Q, run.G):
            max_tau = max(max_tau, integrated_autocorrelation_time(values))
    proposed = max(1, int(math.ceil(2.0 * max_tau)))
    cap = max(1, min(run.size // 4 for run in group.runs))
    return min(proposed, cap)


def _circular_block_indices(n: int, block_size: int, rng: np.random.Generator) -> np.ndarray:
    block_size = min(max(1, block_size), n)
    n_blocks = math.ceil(n / block_size)
    starts = rng.integers(0, n, size=n_blocks)
    offsets = np.arange(block_size)
    return ((starts[:, None] + offsets) % n).reshape(-1)[:n]


def bootstrap_error(
    group: SourceGroup,
    target_Z: float,
    target_m2: float,
    block_size: int,
    draws: int,
    rng: np.random.Generator,
) -> float:
    estimates = np.empty(draws, dtype=float)
    for draw in range(draws):
        M2_parts, M4_parts, Q_parts, G_parts = [], [], [], []
        for run in group.runs:
            indices = _circular_block_indices(run.size, block_size, rng)
            M2_parts.append(run.M2[indices])
            M4_parts.append(run.M4[indices])
            Q_parts.append(run.Q[indices])
            G_parts.append(run.G[indices])
        M2, M4 = np.concatenate(M2_parts), np.concatenate(M4_parts)
        Q, G = np.concatenate(Q_parts), np.concatenate(G_parts)
        with np.errstate(over="ignore", invalid="ignore"):
            logw = -0.5 * ((target_m2 - group.m2) * Q + (target_Z - group.Z) * G)
        weights = normalize_logweights(logw)
        estimates[draw] = binder_from_weights(M2, M4, weights)
    return float(np.std(estimates, ddof=1)) if draws > 1 else 0.0


def analyze(
    runs: Sequence[RunData], start: tuple[float, float], end: tuple[float, float],
    num: int, bootstrap: int, block_size: str, min_ess: float,
    min_ess_fraction: float, seed: int,
) -> list[dict[str, object]]:
    if num < 2:
        raise ValueError("--num must be at least 2")
    if bootstrap < 1:
        raise ValueError("--bootstrap must be positive")
    by_lattice = group_sources(runs)
    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []
    block_cache: dict[tuple[int, float, float], int] = {}

    for L in sorted(by_lattice):
        groups = by_lattice[L]
        for t in np.linspace(0.0, 1.0, num):
            target_Z = start[0] + float(t) * (end[0] - start[0])
            target_m2 = start[1] + float(t) * (end[1] - start[1])
            group = select_source(groups, target_Z, target_m2)
            key = (group.L, group.Z, group.m2)
            if block_size == "auto":
                if key not in block_cache:
                    block_cache[key] = automatic_block_size(group)
                chosen_block = block_cache[key]
            else:
                chosen_block = int(block_size)
                if chosen_block < 1:
                    raise ValueError("--block-size must be positive or 'auto'")
                chosen_block = min(chosen_block, min(run.size for run in group.runs))

            binder, ess, max_weight, _ = evaluate_group(group, target_Z, target_m2)
            uncertainty = bootstrap_error(
                group, target_Z, target_m2, chosen_block, bootstrap, rng
            )
            fraction = ess / group.size
            warning = "low_ess" if ess < min_ess or fraction < min_ess_fraction else "ok"
            rows.append({
                "t": float(t), "Z": target_Z, "m2": target_m2, "L": L,
                "U4": binder, "uncertainty": uncertainty,
                "source_Z": group.Z, "source_m2": group.m2,
                "sample_count": group.size, "kish_ess": ess,
                "ess_fraction": fraction, "max_normalized_weight": max_weight,
                "block_size": chosen_block, "warning_status": warning,
            })
    return rows


def write_csv(rows: Sequence[dict[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def plot_rows(rows: Sequence[dict[str, object]], path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path.parent.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(7.0, 4.8))
    lattice_sizes = sorted({int(row["L"]) for row in rows})
    for L in lattice_sizes:
        selected = [row for row in rows if row["L"] == L]
        t = np.asarray([row["t"] for row in selected])
        u4 = np.asarray([row["U4"] for row in selected])
        error = np.asarray([row["uncertainty"] for row in selected])
        line = axis.errorbar(t, u4, yerr=error, marker=".", capsize=2, label=f"L={L}")
        warning = np.asarray([row["warning_status"] != "ok" for row in selected])
        if np.any(warning):
            axis.scatter(t[warning], u4[warning], marker="x", s=55,
                         color=line[0].get_color(), linewidths=1.5)
    axis.set(xlabel="line parameter t", ylabel=r"$U_4$",
             title="Reweighted uniform-magnetization Binder cumulant")
    axis.grid(alpha=0.25)
    axis.legend()
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, action="extend", nargs="+", required=True)
    parser.add_argument("--start", type=float, nargs=2, required=True, metavar=("Z", "M2"))
    parser.add_argument("--end", type=float, nargs=2, required=True, metavar=("Z", "M2"))
    parser.add_argument("--num", type=int, default=201)
    parser.add_argument("--output", type=Path, required=True, help="output path prefix")
    parser.add_argument("--bootstrap", type=int, default=500)
    parser.add_argument("--block-size", default="auto")
    parser.add_argument("--min-ess", type=float, default=50.0)
    parser.add_argument("--min-ess-fraction", type=float, default=0.01)
    parser.add_argument("--seed", type=int, default=12345)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    runs = read_manifests(args.manifest)
    rows = analyze(runs, tuple(args.start), tuple(args.end), args.num,
                   args.bootstrap, args.block_size, args.min_ess,
                   args.min_ess_fraction, args.seed)
    csv_path = Path(str(args.output) + ".csv")
    plot_path = Path(str(args.output) + ".png")
    write_csv(rows, csv_path)
    plot_rows(rows, plot_path)
    warnings = sum(row["warning_status"] != "ok" for row in rows)
    print(f"wrote {csv_path} and {plot_path}; {warnings}/{len(rows)} points have overlap warnings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
