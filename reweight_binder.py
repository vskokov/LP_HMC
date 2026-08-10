#!/usr/bin/env python3
"""Single-source or MBAR reweighting of Binder cumulants."""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np


SCHEMA_VERSIONS = {1, 2}
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
    sampler: str = "hmc"
    tempering_replicas: int = 1
    mass_span: float = 0.0
    swap_every: int = 1

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


@dataclass(frozen=True)
class MbarModel:
    """Solved multistate Bennett model for one lattice size."""

    groups: tuple[SourceGroup, ...]
    M2: np.ndarray
    M4: np.ndarray
    Q: np.ndarray
    G: np.ndarray
    source_index: np.ndarray
    source_counts: np.ndarray
    free_energies: np.ndarray
    log_denominator: np.ndarray
    iterations: int


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
        schema_version = _parse_metadata_value(
            metadata["schema_version"], int, "schema_version"
        )
        if schema_version not in SCHEMA_VERSIONS:
            raise ValueError(f"{path}: unsupported schema_version={metadata['schema_version']}")
        replica_metadata = {"sampler", "tempering_replicas", "mass_span", "swap_every"}
        if schema_version == 2:
            missing_replica = replica_metadata - metadata.keys()
            if missing_replica:
                raise ValueError(
                    f"{path}: missing replica metadata: {', '.join(sorted(missing_replica))}"
                )

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

    tempering_replicas = _parse_metadata_value(
        metadata.get("tempering_replicas", "1"), int, "tempering_replicas"
    )
    mass_span = _parse_metadata_value(metadata.get("mass_span", "0"), float, "mass_span")
    swap_every = _parse_metadata_value(metadata.get("swap_every", "1"), int, "swap_every")
    if tempering_replicas != 1 and (tempering_replicas < 3 or tempering_replicas % 2 == 0):
        raise ValueError(f"{path}: invalid tempering_replicas={tempering_replicas}")
    if tempering_replicas > 1 and (not math.isfinite(mass_span) or mass_span <= 0):
        raise ValueError(f"{path}: replica exchange requires a positive finite mass_span")
    if swap_every < 1:
        raise ValueError(f"{path}: swap_every must be positive")

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
        sampler=metadata.get("sampler", "hmc"),
        tempering_replicas=tempering_replicas,
        mass_span=mass_span,
        swap_every=swap_every,
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
                elif not stats_path.is_file():
                    relocated = manifest.parent / "statistics" / stats_path.name
                    if relocated.is_file():
                        stats_path = relocated
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


def select_fixed_source(
    groups: Sequence[SourceGroup], Z: float, m2: float, *, atol: float = 1e-12
) -> SourceGroup:
    """Select one exact source coordinate and reject ambiguous/missing matches."""
    matches = [
        group for group in groups
        if math.isclose(group.Z, Z, rel_tol=0.0, abs_tol=atol)
        and math.isclose(group.m2, m2, rel_tol=0.0, abs_tol=atol)
    ]
    if len(matches) != 1:
        available = ", ".join(f"({group.Z:g}, {group.m2:g})" for group in groups)
        raise ValueError(
            f"fixed source ({Z:g}, {m2:g}) has {len(matches)} matches; "
            f"available sources: {available}"
        )
    return matches[0]


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


def logsumexp(values: np.ndarray, axis: int | None = None) -> np.ndarray:
    """Numerically stable log(sum(exp(values))) without a SciPy dependency."""
    array = np.asarray(values, dtype=float)
    maximum = np.max(array, axis=axis, keepdims=True)
    if not np.all(np.isfinite(maximum)):
        raise ValueError("non-finite log-sum-exp input")
    result = maximum + np.log(np.sum(np.exp(array - maximum), axis=axis, keepdims=True))
    return np.squeeze(result, axis=axis)


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


def prepare_mbar(
    groups: Sequence[SourceGroup], *, tolerance: float = 1e-10,
    max_iterations: int = 10_000,
) -> MbarModel:
    """Solve the MBAR self-consistency equations for a set of source ensembles."""
    if not groups:
        raise ValueError("MBAR requires at least one source group")
    if tolerance <= 0 or not math.isfinite(tolerance):
        raise ValueError("MBAR tolerance must be finite and positive")
    if max_iterations < 1:
        raise ValueError("MBAR max iterations must be positive")

    ordered = tuple(sorted(groups, key=lambda group: group.first_order))
    source_counts = np.asarray([group.size for group in ordered], dtype=float)
    M2 = np.concatenate([run.M2 for group in ordered for run in group.runs])
    M4 = np.concatenate([run.M4 for group in ordered for run in group.runs])
    Q = np.concatenate([run.Q for group in ordered for run in group.runs])
    G = np.concatenate([run.G for group in ordered for run in group.runs])
    source_index = np.concatenate([
        np.full(group.size, index, dtype=int) for index, group in enumerate(ordered)
    ])
    source_Z = np.asarray([group.Z for group in ordered], dtype=float)
    source_m2 = np.asarray([group.m2 for group in ordered], dtype=float)
    # The quartic and other fixed action terms are common to every source and
    # cancel from the MBAR denominator, leaving only the Z and m2 couplings.
    reduced_potential = 0.5 * (
        source_m2[:, None] * Q[None, :] + source_Z[:, None] * G[None, :]
    )
    log_counts = np.log(source_counts)
    free_energies = np.zeros(len(ordered), dtype=float)

    for iteration in range(1, max_iterations + 1):
        log_denominator = logsumexp(
            log_counts[:, None] + free_energies[:, None] - reduced_potential,
            axis=0,
        )
        updated = -logsumexp(-reduced_potential - log_denominator[None, :], axis=1)
        updated -= updated[0]
        if np.max(np.abs(updated - free_energies)) < tolerance:
            free_energies = updated
            break
        free_energies = updated
    else:
        raise RuntimeError(
            f"MBAR did not converge in {max_iterations} iterations; "
            "the source ensembles may have inadequate overlap"
        )

    log_denominator = logsumexp(
        log_counts[:, None] + free_energies[:, None] - reduced_potential,
        axis=0,
    )
    return MbarModel(
        groups=ordered, M2=M2, M4=M4, Q=Q, G=G,
        source_index=source_index, source_counts=source_counts,
        free_energies=free_energies, log_denominator=log_denominator,
        iterations=iteration,
    )


def mbar_weights(model: MbarModel, target_Z: float, target_m2: float) -> np.ndarray:
    with np.errstate(over="ignore", invalid="ignore"):
        logw = -0.5 * (target_m2 * model.Q + target_Z * model.G)
        logw -= model.log_denominator
    return normalize_logweights(logw)


def evaluate_mbar(model: MbarModel, target_Z: float, target_m2: float):
    weights = mbar_weights(model, target_Z, target_m2)
    binder = binder_from_weights(model.M2, model.M4, weights)
    ess = 1.0 / float(np.dot(weights, weights))
    contributions = np.bincount(
        model.source_index, weights=weights, minlength=len(model.groups)
    )
    return binder, ess, float(np.max(weights)), weights, contributions


def fourth_moment_diagnostics(M4: np.ndarray, weights: np.ndarray) -> tuple[float, float]:
    """Return contribution ESS and the share supplied by the largest 1% of terms."""
    contributions = np.asarray(M4, dtype=float) * np.asarray(weights, dtype=float)
    total = float(np.sum(contributions))
    if total <= 0 or not math.isfinite(total):
        return 0.0, 1.0
    squared = float(np.dot(contributions, contributions))
    contribution_ess = total**2 / squared if squared > 0 else float(len(contributions))
    count = max(1, int(math.ceil(0.01 * len(contributions))))
    top_share = float(np.partition(contributions, -count)[-count:].sum() / total)
    return contribution_ess, top_share


def source_consistency(
    groups: Sequence[SourceGroup], target_Z: float, target_m2: float,
    min_ess: float, min_ess_fraction: float,
) -> tuple[int, float, float, float]:
    """Compare usable independent single-source estimates at one target."""
    estimates: list[float] = []
    fractions: list[float] = []
    for group in groups:
        binder, ess, _, _ = evaluate_group(group, target_Z, target_m2)
        fraction = ess / group.size
        if ess >= min_ess and fraction >= min_ess_fraction:
            estimates.append(binder)
            fractions.append(fraction)
    if not estimates:
        return 0, math.nan, math.nan, math.nan
    return (
        len(estimates), min(estimates), max(estimates),
        min(fractions),
    )


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


def resample_groups(
    groups: Sequence[SourceGroup], block_sizes: dict[tuple[int, float, float], int],
    rng: np.random.Generator,
) -> list[SourceGroup]:
    """Stratified circular-block resampling, preserving each source/run count."""
    sampled: list[SourceGroup] = []
    for group in groups:
        key = (group.L, group.Z, group.m2)
        runs: list[RunData] = []
        for run in group.runs:
            indices = _circular_block_indices(run.size, block_sizes[key], rng)
            runs.append(replace(
                run,
                M2=run.M2[indices], M4=run.M4[indices],
                Q=run.Q[indices], G=run.G[indices],
            ))
        sampled.append(SourceGroup(
            group.L, group.Z, group.m2, runs, group.first_order
        ))
    return sampled


def mbar_binders(
    model: MbarModel, targets: Sequence[tuple[float, float]], *, chunk_size: int = 32
) -> np.ndarray:
    """Evaluate Binder ratios for many targets without retaining a full weight cube."""
    result = np.empty(len(targets), dtype=float)
    target_array = np.asarray(targets, dtype=float)
    for start in range(0, len(targets), chunk_size):
        chunk = target_array[start:start + chunk_size]
        logw = -0.5 * (
            chunk[:, 1, None] * model.Q[None, :]
            + chunk[:, 0, None] * model.G[None, :]
        ) - model.log_denominator[None, :]
        logw -= np.max(logw, axis=1, keepdims=True)
        weights = np.exp(logw)
        weights /= np.sum(weights, axis=1, keepdims=True)
        mean_m2 = weights @ model.M2
        mean_m4 = weights @ model.M4
        if np.any(mean_m2 <= 16 * np.finfo(float).tiny):
            raise ValueError("weighted <M2> is numerically zero; Binder ratio is undefined")
        result[start:start + len(chunk)] = 1.0 - mean_m4 / (3.0 * mean_m2**2)
    return result


def bootstrap_mbar_errors(
    groups: Sequence[SourceGroup], targets: Sequence[tuple[float, float]],
    block_sizes: dict[tuple[int, float, float], int], draws: int,
    rng: np.random.Generator, *, tolerance: float, max_iterations: int,
) -> np.ndarray:
    """Re-solve MBAR for every stratified block-bootstrap draw."""
    estimates = np.empty((draws, len(targets)), dtype=float)
    for draw in range(draws):
        sampled = resample_groups(groups, block_sizes, rng)
        model = prepare_mbar(
            sampled, tolerance=tolerance, max_iterations=max_iterations
        )
        estimates[draw] = mbar_binders(model, targets)
    if draws == 1:
        return np.zeros(len(targets), dtype=float)
    return np.std(estimates, axis=0, ddof=1)


def analyze(
    runs: Sequence[RunData], start: tuple[float, float], end: tuple[float, float],
    num: int, bootstrap: int, block_size: str, min_ess: float,
    min_ess_fraction: float, seed: int, *, source_mode: str = "nearest",
    fixed_source: tuple[float, float] | None = None,
    max_source_spread: float = math.inf,
    max_top1_m4_fraction: float = 1.0,
    mbar_tolerance: float = 1e-10, mbar_max_iterations: int = 10_000,
) -> list[dict[str, object]]:
    if num < 2:
        raise ValueError("--num must be at least 2")
    if bootstrap < 1:
        raise ValueError("--bootstrap must be positive")
    if source_mode not in {"nearest", "fixed", "mbar"}:
        raise ValueError("source_mode must be nearest, fixed, or mbar")
    if source_mode == "fixed" and fixed_source is None:
        raise ValueError("fixed source mode requires a source coordinate")
    if max_source_spread < 0 or max_top1_m4_fraction < 0:
        raise ValueError("diagnostic thresholds must be non-negative")
    by_lattice = group_sources(runs)
    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []
    block_cache: dict[tuple[int, float, float], int] = {}

    for L in sorted(by_lattice):
        groups = by_lattice[L]
        target_rows = []
        for t in np.linspace(0.0, 1.0, num):
            target_Z = start[0] + float(t) * (end[0] - start[0])
            target_m2 = start[1] + float(t) * (end[1] - start[1])
            target_rows.append((float(t), target_Z, target_m2))

        for group in groups:
            key = (group.L, group.Z, group.m2)
            if block_size == "auto":
                if key not in block_cache:
                    block_cache[key] = automatic_block_size(group)
            else:
                requested_block = int(block_size)
                if requested_block < 1:
                    raise ValueError("--block-size must be positive or 'auto'")
                block_cache[key] = min(
                    requested_block, min(run.size for run in group.runs)
                )

        mbar_model = None
        mbar_uncertainties = None
        if source_mode == "mbar":
            mbar_model = prepare_mbar(
                groups, tolerance=mbar_tolerance,
                max_iterations=mbar_max_iterations,
            )
            targets = [(target_Z, target_m2) for _, target_Z, target_m2 in target_rows]
            mbar_uncertainties = bootstrap_mbar_errors(
                groups, targets, block_cache, bootstrap, rng,
                tolerance=mbar_tolerance, max_iterations=mbar_max_iterations,
            )

        for target_index, (t, target_Z, target_m2) in enumerate(target_rows):
            if source_mode == "mbar":
                assert mbar_model is not None and mbar_uncertainties is not None
                binder, ess, max_weight, weights, contributions = evaluate_mbar(
                    mbar_model, target_Z, target_m2
                )
                sample_count = len(mbar_model.M2)
                source_Z: float | str = ""
                source_m2: float | str = ""
                chosen_block = max(
                    block_cache[(group.L, group.Z, group.m2)] for group in groups
                )
                uncertainty = float(mbar_uncertainties[target_index])
                moment_M4 = mbar_model.M4
                dominant_source_fraction = float(np.max(contributions))
                mbar_iterations = mbar_model.iterations
            else:
                group = (
                    select_fixed_source(groups, *fixed_source)
                    if source_mode == "fixed" and fixed_source is not None
                    else select_source(groups, target_Z, target_m2)
                )
                key = (group.L, group.Z, group.m2)
                chosen_block = block_cache[key]
                binder, ess, max_weight, weights = evaluate_group(
                    group, target_Z, target_m2
                )
                uncertainty = bootstrap_error(
                    group, target_Z, target_m2, chosen_block, bootstrap, rng
                )
                sample_count = group.size
                source_Z = group.Z
                source_m2 = group.m2
                moment_M4 = np.concatenate([run.M4 for run in group.runs])
                dominant_source_fraction = 1.0
                mbar_iterations = 0

            fraction = ess / sample_count
            m4_ess, top1_m4_fraction = fourth_moment_diagnostics(moment_M4, weights)
            usable_sources, source_min, source_max, source_min_fraction = source_consistency(
                groups, target_Z, target_m2, min_ess, min_ess_fraction
            )
            source_spread = (
                source_max - source_min if usable_sources else math.nan
            )
            low_ess = ess < min_ess or fraction < min_ess_fraction
            source_disagreement = (
                usable_sources >= 2 and source_spread > max_source_spread
            )
            heavy_m4_tail = top1_m4_fraction > max_top1_m4_fraction
            warning = (
                "low_ess" if low_ess else
                "source_disagreement" if source_disagreement else
                "heavy_m4_tail" if heavy_m4_tail else
                "ok"
            )
            rows.append({
                "t": float(t), "Z": target_Z, "m2": target_m2, "L": L,
                "U4": binder, "uncertainty": uncertainty,
                "source_mode": source_mode,
                "source_Z": source_Z, "source_m2": source_m2,
                "source_count": len(groups),
                "sample_count": sample_count, "kish_ess": ess,
                "ess_fraction": fraction, "max_normalized_weight": max_weight,
                "m4_contribution_ess": m4_ess,
                "m4_contribution_ess_fraction": m4_ess / sample_count,
                "top1_m4_fraction": top1_m4_fraction,
                "dominant_source_fraction": dominant_source_fraction,
                "usable_source_count": usable_sources,
                "source_U4_min": source_min, "source_U4_max": source_max,
                "source_U4_spread": source_spread,
                "source_min_ess_fraction": source_min_fraction,
                "block_size": chosen_block,
                "mbar_iterations": mbar_iterations,
                "low_ess": low_ess,
                "source_disagreement": source_disagreement,
                "heavy_m4_tail": heavy_m4_tail,
                "warning_status": warning,
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
    all_Z = np.asarray([float(row["Z"]) for row in rows])
    all_m2 = np.asarray([float(row["m2"]) for row in rows])
    if np.allclose(all_Z, all_Z[0], rtol=0.0, atol=1e-14):
        x_field, xlabel = "m2", r"target $m^2$"
    elif np.allclose(all_m2, all_m2[0], rtol=0.0, atol=1e-14):
        x_field, xlabel = "Z", r"target $Z$"
    else:
        x_field, xlabel = "t", "line parameter t"
    lattice_sizes = sorted({int(row["L"]) for row in rows})
    for L in lattice_sizes:
        selected = [row for row in rows if int(row["L"]) == L]
        x = np.asarray([float(row[x_field]) for row in selected])
        u4 = np.asarray([row["U4"] for row in selected])
        error = np.asarray([row["uncertainty"] for row in selected])
        line = axis.errorbar(x, u4, yerr=error, marker=".", capsize=2, label=f"L={L}")
        warning = np.asarray([row["warning_status"] != "ok" for row in selected])
        if np.any(warning):
            axis.scatter(x[warning], u4[warning], marker="x", s=55,
                         color=line[0].get_color(), linewidths=1.5)
    axis.set(xlabel=xlabel, ylabel=r"$U_4$",
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
    parser.add_argument(
        "--source-mode", choices=("mbar", "fixed", "nearest"), default="mbar",
        help="combine all sources with MBAR, use one explicit source, or retain legacy nearest-source selection",
    )
    parser.add_argument(
        "--source", type=float, nargs=2, metavar=("Z", "M2"),
        help="exact source coordinate required by --source-mode=fixed",
    )
    parser.add_argument(
        "--max-source-spread", type=float, default=0.25,
        help="warn when usable single-source Binder estimates span more than this",
    )
    parser.add_argument(
        "--max-top1-m4-fraction", type=float, default=0.5,
        help="warn when the largest 1%% of weighted M4 contributions exceed this share",
    )
    parser.add_argument("--mbar-tolerance", type=float, default=1e-10)
    parser.add_argument("--mbar-max-iterations", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=12345)
    args = parser.parse_args(argv)
    if args.source_mode == "fixed" and args.source is None:
        parser.error("--source-mode=fixed requires --source Z M2")
    if args.source_mode != "fixed" and args.source is not None:
        parser.error("--source is only valid with --source-mode=fixed")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    runs = read_manifests(args.manifest)
    rows = analyze(runs, tuple(args.start), tuple(args.end), args.num,
                   args.bootstrap, args.block_size, args.min_ess,
                   args.min_ess_fraction, args.seed,
                   source_mode=args.source_mode,
                   fixed_source=tuple(args.source) if args.source else None,
                   max_source_spread=args.max_source_spread,
                   max_top1_m4_fraction=args.max_top1_m4_fraction,
                   mbar_tolerance=args.mbar_tolerance,
                   mbar_max_iterations=args.mbar_max_iterations)
    csv_path = Path(str(args.output) + ".csv")
    plot_path = Path(str(args.output) + ".png")
    write_csv(rows, csv_path)
    plot_rows(rows, plot_path)
    warnings = sum(row["warning_status"] != "ok" for row in rows)
    counts = {
        status: sum(bool(row[status]) for row in rows)
        for status in ("low_ess", "source_disagreement", "heavy_m4_tail")
    }
    details = ", ".join(f"{key}={value}" for key, value in counts.items() if value)
    suffix = f" ({details})" if details else ""
    print(
        f"wrote {csv_path} and {plot_path}; source_mode={args.source_mode}; "
        f"{warnings}/{len(rows)} points have warnings{suffix}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
