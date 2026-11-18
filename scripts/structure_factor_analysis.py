#!/usr/bin/env python3
"""Statistics for shell-resolved structure-factor umbrella measurements."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    from analyze_umbrella import prepare_umbrella_model, sample_log_denominator
except ModuleNotFoundError:  # package-style import from repository root
    from .analyze_umbrella import prepare_umbrella_model, sample_log_denominator


@dataclass(frozen=True)
class ShellTable:
    metadata: dict[str, str]
    columns: tuple[str, ...]
    arrays: dict[str, np.ndarray]
    q: np.ndarray
    degeneracy: np.ndarray


RANK_METRICS = (
    "rank_lambda1", "rank_lambda2", "rank_lambda3",
    "rank_effective_dimension", "rank_background_per_mode",
    "rank_raw_power", "rank_raw_excess_power", "rank_excess_power",
)


def read_numeric_csv(path: Path) -> tuple[dict[str, str], tuple[str, ...], np.ndarray]:
    metadata: dict[str, str] = {}
    header_line = -1
    columns: tuple[str, ...] = ()
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle):
            if line.startswith("#"):
                key, separator, value = line[1:].strip().partition("=")
                if not separator:
                    raise ValueError(f"{path}: malformed metadata")
                metadata[key.strip()] = value.strip()
                continue
            columns = tuple(line.rstrip("\r\n").split(","))
            header_line = line_number
            break
    if header_line < 0 or not columns:
        raise ValueError(f"{path}: missing header")
    try:
        table = np.loadtxt(path, delimiter=",", skiprows=header_line + 1, dtype=float)
    except ValueError as error:
        raise ValueError(f"{path}: non-numeric row") from error
    table = np.atleast_2d(table)
    if table.shape[0] == 0 or table.shape[1] != len(columns):
        raise ValueError(f"{path}: empty data or column mismatch")
    if not np.all(np.isfinite(table)):
        raise ValueError(f"{path}: non-finite data")
    return metadata, columns, table


def read_shell_table(path: Path) -> ShellTable:
    metadata, columns, table = read_numeric_csv(path)
    arrays = {column: table[:, index] for index, column in enumerate(columns)}
    shell_columns = tuple(column for column in columns if column.startswith("P_q"))
    if not shell_columns:
        raise ValueError(f"{path}: no shell powers")
    q_key = "shell_q" if "shell_q" in metadata else "stored_shell_q"
    d_key = "shell_degeneracy" if "shell_degeneracy" in metadata else "stored_shell_degeneracy"
    q = np.asarray([float(value) for value in metadata[q_key].split(";")], dtype=float)
    degeneracy = np.asarray([int(value) for value in metadata[d_key].split(";")], dtype=int)
    if len(q) != len(shell_columns) or len(degeneracy) != len(q):
        raise ValueError(f"{path}: shell metadata length mismatch")
    return ShellTable(metadata, columns, arrays, q, degeneracy)


def normalized_weights(log_denominator: np.ndarray, Q: np.ndarray | None = None,
                       G: np.ndarray | None = None, delta_m2: float = 0.0,
                       delta_Z: float = 0.0, temperature: float = 1.0) -> np.ndarray:
    logw = -np.asarray(log_denominator, dtype=float)
    if delta_m2:
        if Q is None:
            raise ValueError("mass reweighting requires Q")
        logw = logw - 0.5 * delta_m2 * np.asarray(Q) / temperature
    if delta_Z:
        if G is None:
            raise ValueError("Z reweighting requires G")
        logw = logw - 0.5 * delta_Z * np.asarray(G) / temperature
    logw -= np.max(logw)
    weights = np.exp(logw)
    total = float(weights.sum())
    if not math.isfinite(total) or total <= 0:
        raise ValueError("reweighting produced zero/non-finite total weight")
    return weights / total


def census_weights(census: ShellTable, production_arrays: dict[str, np.ndarray],
                   bins: int = 128) -> np.ndarray:
    model = prepare_umbrella_model(production_arrays, bins=bins)
    denominator = sample_log_denominator(
        census.arrays["M2"], model.centers, model.kappas, model.counts,
        model.free_energies,
    )
    return normalized_weights(denominator)


def canonical_weights(table: ShellTable, delta_m2: float = 0.0,
                      delta_Z: float = 0.0, bins: int = 128) -> np.ndarray:
    arrays = table.arrays
    model = prepare_umbrella_model({
        "slot": arrays["slot"], "umbrella_center": arrays["umbrella_center"],
        "umbrella_kappa": arrays["umbrella_kappa"], "M2": arrays["M2"],
        "M4": arrays["M4"], "Q": arrays["Q"],
    }, bins=bins)
    return normalized_weights(
        model.log_denominator, arrays["Q"], arrays["G"],
        delta_m2=delta_m2, delta_Z=delta_Z,
        temperature=float(table.metadata.get("temperature", "1")),
    )


def canonical_weights_with_fallback(table: ShellTable, delta_m2: float = 0.0,
                                    delta_Z: float = 0.0, bins: int = 128) -> np.ndarray:
    """Coarsen sparse pilot/bootstrap histograms if the Newton WHAM solve stalls."""
    last_error: RuntimeError | None = None
    for candidate in dict.fromkeys((bins, 64, 32)):
        try:
            return canonical_weights(table, delta_m2=delta_m2, delta_Z=delta_Z,
                                     bins=candidate)
        except RuntimeError as error:
            last_error = error
    raise RuntimeError(f"canonical WHAM failed for bins={tuple(dict.fromkeys((bins, 64, 32)))}: {last_error}")


def shell_summary(table: ShellTable, weights: np.ndarray) -> list[dict[str, float]]:
    volume = float(int(table.metadata["L"]) ** 3)
    shell_columns = [column for column in table.columns if column.startswith("P_q")]
    rows = []
    for column, q, degeneracy in zip(shell_columns, table.q, table.degeneracy):
        mean_power = float(np.dot(weights, table.arrays[column]))
        rows.append({
            "q": float(q), "degeneracy": int(degeneracy),
            "mean_power": mean_power,
            "S_per_mode": volume * mean_power / int(degeneracy),
        })
    return rows


def observable_summary(table: ShellTable, weights: np.ndarray) -> dict[str, float]:
    volume = float(int(table.metadata["L"]) ** 3)
    p = table.arrays["P_selected"]
    mean_p = float(np.dot(weights, p))
    mean_p2 = float(np.dot(weights, p * p))
    mean_amp = float(np.dot(weights, np.sqrt(np.maximum(p, 0.0))))
    degeneracy = int(table.metadata["selected_degeneracy"])
    binder = 1.0 - degeneracy * mean_p2 / ((degeneracy + 2.0) * mean_p**2)
    ess = 1.0 / float(np.dot(weights, weights))
    result = {
        "mean_power": mean_p,
        "S_per_mode": volume * mean_p / degeneracy,
        "susceptibility": volume * (mean_p - mean_amp**2),
        "binder": binder,
        "mean_energy_density": float(np.dot(weights, table.arrays["H"])) / volume,
        "orientation_max_fraction": float(np.dot(weights, table.arrays["orientation_max_fraction"])),
        "orientation_participation": float(np.dot(weights, table.arrays["orientation_participation"])),
        "ess": ess, "ess_fraction": ess / len(weights),
        "max_weight": float(np.max(weights)),
    }
    if all(metric in table.arrays for metric in RANK_METRICS):
        result.update({metric: float(np.dot(weights, table.arrays[metric]))
                       for metric in RANK_METRICS})
        background_total = (result["rank_background_per_mode"] *
                            int(table.metadata["selected_degeneracy"]))
        result["rank_signal_to_background"] = (
            result["rank_raw_excess_power"] / max(background_total, np.finfo(float).tiny)
        )
    return result


def rank_from_eigenvalues(lambda2: float, lambda3: float,
                          eigenvalue_threshold: float = 0.15,
                          lambda1: float | None = None) -> int:
    """Classify the dimension of an already background-subtracted tensor."""
    if lambda1 is not None:
        trace = lambda1 + lambda2 + lambda3
        if trace > 0:
            lambda2 /= trace
            lambda3 /= trace
    if lambda2 < eigenvalue_threshold:
        return 1
    if lambda3 < eigenvalue_threshold:
        return 2
    return 3


def rank_label(summary: dict[str, float], confidence: float = 0.90,
               modulation_confidence: float = 0.95) -> str:
    """Turn bootstrap support into a conservative morphology label."""
    support = float(summary.get("modulation_support", math.nan))
    if not math.isfinite(support):
        return "not_measured"
    if support <= 1.0 - modulation_confidence:
        return "unmodulated"
    probabilities = [float(summary.get(f"rank{rank}_probability", 0.0))
                     for rank in (1, 2, 3)]
    best = int(np.argmax(probabilities)) + 1
    if support >= modulation_confidence and probabilities[best - 1] >= confidence:
        return f"rank{best}"
    return "mixed/undetermined"


def subset_table(table: ShellTable, indices: np.ndarray) -> ShellTable:
    """Return a row-resampled table while preserving shell metadata."""
    indices = np.asarray(indices, dtype=int)
    return ShellTable(
        table.metadata, table.columns,
        {name: values[indices] for name, values in table.arrays.items()},
        table.q, table.degeneracy,
    )


def trajectory_block_indices(trajectories: np.ndarray, rng: np.random.Generator,
                             block_length: int) -> np.ndarray:
    """Moving-block resample of trajectories, keeping all umbrella slots together."""
    trajectories = np.asarray(trajectories)
    unique = np.unique(trajectories)
    if len(unique) < 2:
        return np.arange(len(trajectories), dtype=int)
    block_length = max(1, min(int(block_length), len(unique)))
    selected: list[float] = []
    while len(selected) < len(unique):
        start = int(rng.integers(0, len(unique)))
        selected.extend(unique[(start + np.arange(block_length)) % len(unique)].tolist())
    selected = selected[:len(unique)]
    rows_by_trajectory = {value: np.flatnonzero(trajectories == value) for value in unique}
    return np.concatenate([rows_by_trajectory[value] for value in selected])


def bootstrap_observables(table: ShellTable, draws: int = 200, block_length: int = 5,
                          bins: int = 128, seed: int = 1729) -> dict[str, float]:
    """Blocked bootstrap including a fresh umbrella reconstruction in every draw."""
    if draws < 2:
        return {}
    rng = np.random.default_rng(seed)
    metrics = ["S_per_mode", "susceptibility", "binder", "mean_energy_density",
               "orientation_max_fraction", "orientation_participation"]
    has_rank = all(metric in table.arrays for metric in RANK_METRICS)
    if has_rank:
        metrics.extend(RANK_METRICS)
    samples = {metric: [] for metric in metrics}
    rank_draws: list[int] = []
    modulated_draws = 0
    for _ in range(draws):
        indices = trajectory_block_indices(table.arrays["trajectory"], rng, block_length)
        replica = subset_table(table, indices)
        summary = observable_summary(replica, canonical_weights_with_fallback(replica, bins=bins))
        for metric in metrics:
            samples[metric].append(summary[metric])
        if has_rank and summary["rank_raw_excess_power"] > 0:
            modulated_draws += 1
            rank_draws.append(rank_from_eigenvalues(summary["rank_lambda2"],
                                                     summary["rank_lambda3"],
                                                     lambda1=summary["rank_lambda1"]))
    result: dict[str, float] = {}
    for metric, values in samples.items():
        array = np.asarray(values, dtype=float)
        result[metric + "_mcse"] = float(np.std(array, ddof=1))
        result[metric + "_ci_low"] = float(np.quantile(array, 0.025))
        result[metric + "_ci_high"] = float(np.quantile(array, 0.975))
    if has_rank:
        result["modulation_support"] = modulated_draws / draws
        for rank in (1, 2, 3):
            result[f"rank{rank}_probability"] = (
                rank_draws.count(rank) / len(rank_draws) if rank_draws else 0.0
            )
        result["rank_label"] = rank_label(result)
    return result


def detect_bimodality(values: np.ndarray, weights: np.ndarray,
                      bins: int | None = None) -> dict[str, float | bool]:
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    if bins is None:
        q25, q75 = np.quantile(values, [0.25, 0.75])
        width = 2.0 * (q75 - q25) / max(len(values), 2) ** (1 / 3)
        bins = 50 if width <= 0 else int(np.clip(math.ceil(np.ptp(values) / width), 30, 100))
    histogram, edges = np.histogram(values, bins=bins, weights=weights, density=True)
    smooth = np.convolve(histogram, np.asarray([0.25, 0.5, 0.25]), mode="same")
    peaks = [i for i in range(1, len(smooth) - 1)
             if smooth[i] > smooth[i - 1] and smooth[i] >= smooth[i + 1]]
    if len(peaks) < 2:
        return {"resolved": False, "bins": bins}
    strongest = sorted(peaks, key=lambda i: smooth[i], reverse=True)[:2]
    left, right = sorted(strongest)
    if right - left < 2:
        return {"resolved": False, "bins": bins}
    valley = left + int(np.argmin(smooth[left:right + 1]))
    threshold = 0.8 * min(smooth[left], smooth[right])
    if smooth[valley] >= threshold:
        return {"resolved": False, "bins": bins}
    positive = smooth[smooth > 0]
    valley_density = float(smooth[valley])
    if valley_density <= 0:
        valley_density = 0.5 * float(np.min(positive))
    barrier = math.log(math.sqrt(smooth[left] * smooth[right]) / valley_density)
    split = edges[valley + 1]
    low_weight = float(weights[values < split].sum())
    return {
        "resolved": True, "bins": bins, "split": float(split),
        "barrier": barrier, "low_weight": low_weight,
        "peak_low": float(0.5 * (edges[left] + edges[left + 1])),
        "peak_high": float(0.5 * (edges[right] + edges[right + 1])),
    }


def bimodality_stable(values: np.ndarray, weights: np.ndarray) -> dict[str, float | bool]:
    base = detect_bimodality(values, weights)
    if not base.get("resolved"):
        return base
    bins = int(base["bins"])
    alternatives = [detect_bimodality(values, weights, max(30, bins // 2)),
                    detect_bimodality(values, weights, min(100, bins * 2))]
    base["stable"] = all(result.get("resolved") for result in alternatives)
    return base


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0])
    known = set(fields)
    for row in rows[1:]:
        for field in row:
            if field not in known:
                fields.append(field); known.add(field)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
