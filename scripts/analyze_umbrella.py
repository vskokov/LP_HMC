#!/usr/bin/env python3
"""Unbias an M² umbrella-exchange CSV with MBAR and report overlap diagnostics."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reweight_binder import read_stats  # noqa: E402


REQUIRED = (
    "trajectory", "slot", "walker_id", "umbrella_center", "umbrella_kappa",
    "M", "M2", "M4", "Q", "G", "acceptance_rate",
)


def logsumexp(values: np.ndarray, axis: int) -> np.ndarray:
    maximum = np.max(values, axis=axis, keepdims=True)
    return np.squeeze(maximum + np.log(np.sum(np.exp(values - maximum), axis=axis,
                                               keepdims=True)), axis=axis)


def read_umbrella(path: Path) -> tuple[dict[str, str], dict[str, np.ndarray]]:
    metadata: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        while True:
            position = handle.tell()
            line = handle.readline()
            if not line:
                raise ValueError(f"{path}: missing CSV header")
            if not line.startswith("#"):
                handle.seek(position)
                break
            key, separator, value = line[1:].strip().partition("=")
            if not separator:
                raise ValueError(f"{path}: malformed metadata line")
            metadata[key.strip()] = value.strip()
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != REQUIRED:
            raise ValueError(f"{path}: unexpected columns")
        rows = list(reader)
    if metadata.get("schema_version") != "3" or metadata.get("sampler") != "umbrella_exchange":
        raise ValueError(f"{path}: not an umbrella-exchange schema-3 file")
    if not rows:
        raise ValueError(f"{path}: no samples")
    arrays = {
        column: np.asarray([float(row[column]) for row in rows], dtype=float)
        for column in REQUIRED
    }
    if not all(np.all(np.isfinite(values)) for values in arrays.values()):
        raise ValueError(f"{path}: non-finite values")
    slots = arrays["slot"].astype(int)
    replicas = int(metadata["umbrella_replicas"])
    if set(slots) != set(range(1, replicas + 1)):
        raise ValueError(f"{path}: incomplete umbrella slots")
    counts = np.bincount(slots, minlength=replicas + 1)[1:]
    if len(set(counts)) != 1 or counts[0] != int(metadata["samples_per_window"]):
        raise ValueError(f"{path}: unequal or incorrect per-window sample counts")
    return metadata, arrays


def solve_mbar(reduced: np.ndarray, counts: np.ndarray, tolerance: float = 1e-11,
               max_iterations: int = 20_000) -> tuple[np.ndarray, np.ndarray, int]:
    log_counts = np.log(counts)
    free = np.zeros(len(counts))
    for iteration in range(1, max_iterations + 1):
        denominator = logsumexp(log_counts[:, None] + free[:, None] - reduced, axis=0)
        updated = -logsumexp(-reduced - denominator[None, :], axis=1)
        updated -= updated[0]
        if np.max(np.abs(updated - free)) < tolerance:
            free = updated
            break
        free = 0.5 * free + 0.5 * updated
    else:
        raise RuntimeError("umbrella MBAR did not converge; window overlap is inadequate")
    denominator = logsumexp(log_counts[:, None] + free[:, None] - reduced, axis=0)
    return free, denominator, iteration


def sample_log_denominator(m2_values: np.ndarray, centers: np.ndarray,
                           kappas: np.ndarray, counts: np.ndarray,
                           free: np.ndarray) -> np.ndarray:
    maximum = np.full(len(m2_values), -np.inf)
    total = np.zeros(len(m2_values))
    for center, kappa, count, free_energy in zip(centers, kappas, counts, free):
        term = math.log(count) + free_energy - 0.5 * kappa * (m2_values - center) ** 2
        new_maximum = np.maximum(maximum, term)
        total = total * np.exp(maximum - new_maximum) + np.exp(term - new_maximum)
        maximum = new_maximum
    return maximum + np.log(total)


def solve_binned_wham(m2_values: np.ndarray, centers: np.ndarray,
                      kappas: np.ndarray, counts: np.ndarray, bins: int,
                      tolerance: float = 1e-11,
                      max_iterations: int = 20_000) -> tuple[np.ndarray, np.ndarray, int]:
    edges = np.linspace(float(np.min(m2_values)), float(np.max(m2_values)), bins + 1)
    histogram, _ = np.histogram(m2_values, bins=edges)
    occupied = histogram > 0
    positions = 0.5 * (edges[:-1] + edges[1:])
    positions = positions[occupied]
    multiplicities = histogram[occupied].astype(float)
    reduced = 0.5 * kappas[:, None] * (positions[None, :] - centers[:, None]) ** 2
    log_counts = np.log(counts)
    free = np.zeros(len(counts))
    for iteration in range(1, max_iterations + 1):
        denominator = logsumexp(log_counts[:, None] + free[:, None] - reduced, axis=0)
        updated = -logsumexp(
            np.log(multiplicities)[None, :] - reduced - denominator[None, :], axis=1
        )
        updated -= updated[0]
        if np.max(np.abs(updated - free)) < tolerance:
            free = updated
            break
        free = 0.5 * free + 0.5 * updated
    else:
        raise RuntimeError("binned umbrella WHAM did not converge; overlap is inadequate")
    return free, sample_log_denominator(m2_values, centers, kappas, counts, free), iteration


def estimate(arrays: dict[str, np.ndarray], bins: int = 0) -> dict[str, object]:
    slots = arrays["slot"].astype(int)
    order = np.argsort(slots, kind="stable")
    slots = slots[order]
    m2_values = arrays["M2"][order]
    m4_values = arrays["M4"][order]
    centers = np.asarray([
        arrays["umbrella_center"][order][slots == slot][0]
        for slot in sorted(set(slots))
    ])
    kappas = np.asarray([
        arrays["umbrella_kappa"][order][slots == slot][0]
        for slot in sorted(set(slots))
    ])
    counts = np.bincount(slots)[1:].astype(float)
    if bins > 0:
        free, denominator, iterations = solve_binned_wham(
            m2_values, centers, kappas, counts, bins
        )
    else:
        reduced = 0.5 * kappas[:, None] * (m2_values[None, :] - centers[:, None]) ** 2
        free, denominator, iterations = solve_mbar(reduced, counts)
    log_weights = -denominator
    log_weights -= np.max(log_weights)
    weights = np.exp(log_weights)
    weights /= np.sum(weights)
    mean_m2 = float(np.dot(weights, m2_values))
    mean_m4 = float(np.dot(weights, m4_values))
    binder = 1.0 - mean_m4 / (3.0 * mean_m2**2)
    ess = 1.0 / float(np.dot(weights, weights))

    bins = np.linspace(float(np.min(m2_values)), float(np.max(m2_values)), 65)
    neighbor_overlap: list[float] = []
    for slot in range(1, len(counts)):
        left, _ = np.histogram(m2_values[slots == slot], bins=bins)
        right, _ = np.histogram(m2_values[slots == slot + 1], bins=bins)
        neighbor_overlap.append(float(np.minimum(left / left.sum(), right / right.sum()).sum()))
    hist, edges = np.histogram(m2_values, bins=bins, weights=weights)
    widths = np.diff(edges)
    density = hist / widths
    positive = density > 0
    free_profile = np.full_like(density, np.nan, dtype=float)
    free_profile[positive] = -np.log(density[positive])
    free_profile[positive] -= np.nanmin(free_profile)
    return {
        "mean_M2": mean_m2, "mean_M4": mean_m4, "binder": binder,
        "effective_sample_size": ess, "mbar_iterations": iterations,
        "free_energies": free.tolist(), "neighbor_overlap": neighbor_overlap,
        "profile_centers": (0.5 * (edges[:-1] + edges[1:])).tolist(),
        "profile_free_energy": free_profile.tolist(),
    }


def block_bootstrap(metadata: dict[str, str], arrays: dict[str, np.ndarray], draws: int,
                    block_size: int, seed: int, bins: int) -> dict[str, float]:
    samples = int(metadata["samples_per_window"])
    replicas = int(metadata["umbrella_replicas"])
    if draws == 0:
        return {}
    block_size = min(block_size, samples)
    starts = np.arange(0, samples - block_size + 1, block_size)
    if starts.size == 0:
        starts = np.asarray([0])
    blocks_needed = math.ceil(samples / block_size)
    rng = np.random.default_rng(seed)
    estimates = []
    # Rows are emitted time-major, one row per slot. Resample synchronized time
    # blocks so exchange-induced correlations between windows are retained.
    row_grid = np.arange(samples * replicas).reshape(samples, replicas)
    for _ in range(draws):
        chosen = rng.choice(starts, size=blocks_needed, replace=True)
        times = np.concatenate([np.arange(start, start + block_size) for start in chosen])[:samples]
        indices = row_grid[times].reshape(-1)
        sample_arrays = {key: values[indices] for key, values in arrays.items()}
        result = estimate(sample_arrays, bins)
        estimates.append((result["mean_M2"], result["binder"]))
    values = np.asarray(estimates)
    return {
        "mean_M2_error": float(np.std(values[:, 0], ddof=1)),
        "binder_error": float(np.std(values[:, 1], ddof=1)),
        "bootstrap_draws": draws, "bootstrap_block_size": block_size,
    }


def reference_estimate(path: Path, draws: int, block_size: int, seed: int) -> dict[str, float]:
    run = read_stats(path)
    mean_m2 = float(np.mean(run.M2))
    binder = float(1.0 - np.mean(run.M4) / (3.0 * mean_m2**2))
    if draws == 0:
        return {"reference_mean_M2": mean_m2, "reference_binder": binder}
    starts = np.arange(0, run.size, block_size)
    blocks_needed = math.ceil(run.size / block_size)
    rng = np.random.default_rng(seed)
    estimates = []
    for _ in range(draws):
        chosen = rng.choice(starts, size=blocks_needed, replace=True)
        indices = np.concatenate([
            np.arange(start, min(start + block_size, run.size)) for start in chosen
        ])[:run.size]
        sample_m2 = float(np.mean(run.M2[indices]))
        sample_binder = float(
            1.0 - np.mean(run.M4[indices]) / (3.0 * sample_m2**2)
        )
        estimates.append((sample_m2, sample_binder))
    errors = np.std(np.asarray(estimates), axis=0, ddof=1)
    return {
        "reference_mean_M2": mean_m2,
        "reference_mean_M2_error": float(errors[0]),
        "reference_binder": binder,
        "reference_binder_error": float(errors[1]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("statistics", type=Path)
    parser.add_argument("--bootstrap", type=int, default=200)
    parser.add_argument("--block-size", type=int, default=10)
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--bins", type=int, default=512,
                        help="occupied-bin WHAM resolution; 0 selects exact unbinned MBAR")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--profile-output", type=Path)
    parser.add_argument("--reference", type=Path,
                        help="unbiased collector CSV at the same physical point")
    args = parser.parse_args()
    if args.bootstrap < 0 or args.block_size < 1 or args.bins < 0:
        parser.error("bootstrap/bins must be non-negative and block size positive")
    metadata, arrays = read_umbrella(args.statistics)
    result = estimate(arrays, args.bins)
    result.update(block_bootstrap(metadata, arrays, args.bootstrap, args.block_size,
                                  args.seed, args.bins))
    if args.reference:
        reference = reference_estimate(
            args.reference, args.bootstrap, args.block_size, args.seed + 1
        )
        result.update(reference)
        if args.bootstrap:
            for observable in ("mean_M2", "binder"):
                difference = result[observable] - reference[f"reference_{observable}"]
                error = math.hypot(
                    result[f"{observable}_error"],
                    reference[f"reference_{observable}_error"],
                )
                result[f"{observable}_reference_z"] = difference / error
    result.update({
        "L": int(metadata["L"]), "Z": float(metadata["Z"]),
        "m2": float(metadata["m2"]), "umbrella_replicas": int(metadata["umbrella_replicas"]),
        "wham_bins": args.bins,
        "source": str(args.statistics.resolve()),
    })
    profile_centers = result.pop("profile_centers")
    profile_free_energy = result.pop("profile_free_energy")
    text = json.dumps(result, indent=2, sort_keys=True, allow_nan=True) + "\n"
    print(text, end="")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    if args.profile_output:
        args.profile_output.parent.mkdir(parents=True, exist_ok=True)
        with args.profile_output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(("M2", "free_energy"))
            writer.writerows(zip(profile_centers, profile_free_energy))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
