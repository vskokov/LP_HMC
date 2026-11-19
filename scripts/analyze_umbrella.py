#!/usr/bin/env python3
"""Unbias an M² umbrella-exchange CSV with MBAR and report overlap diagnostics."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import dataclass
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
    header_line = -1
    with path.open(newline="", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle):
            if not line:
                raise ValueError(f"{path}: missing CSV header")
            if not line.startswith("#"):
                header_line = line_number
                if tuple(line.rstrip("\r\n").split(",")) != REQUIRED:
                    raise ValueError(f"{path}: unexpected columns")
                break
            key, separator, value = line[1:].strip().partition("=")
            if not separator:
                raise ValueError(f"{path}: malformed metadata line")
            metadata[key.strip()] = value.strip()
        else:
            raise ValueError(f"{path}: missing CSV header")
    if metadata.get("schema_version") != "3" or metadata.get("sampler") != "umbrella_exchange":
        raise ValueError(f"{path}: not an umbrella-exchange schema-3 file")
    try:
        # Loading the numeric body directly avoids retaining millions of Python
        # dictionaries.  On the largest production files this lowers peak RSS
        # by more than an order of magnitude while preserving the public return
        # shape of this reader.
        table = np.loadtxt(
            path, delimiter=",", skiprows=header_line + 1, dtype=np.float64,
        )
    except ValueError as error:
        raise ValueError(f"{path}: non-numeric statistics row") from error
    if table.size == 0:
        raise ValueError(f"{path}: no samples")
    table = np.atleast_2d(table)
    if table.shape[1] != len(REQUIRED):
        raise ValueError(f"{path}: unexpected numeric column count")
    arrays = {
        column: table[:, index] for index, column in enumerate(REQUIRED)
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


@dataclass(frozen=True)
class UmbrellaModel:
    """Solved fixed-mass umbrella model with sample-level observables."""

    M2: np.ndarray
    M4: np.ndarray
    Q: np.ndarray | None
    slots: np.ndarray
    centers: np.ndarray
    kappas: np.ndarray
    counts: np.ndarray
    free_energies: np.ndarray
    log_denominator: np.ndarray
    iterations: int
    bins: int


def prepare_umbrella_model(
    arrays: dict[str, np.ndarray], bins: int = 0,
    initial_free: np.ndarray | None = None,
) -> UmbrellaModel:
    """Solve the umbrella normalization once for repeated mass evaluation."""
    slots = arrays["slot"].astype(int)
    order = np.argsort(slots, kind="stable")
    slots = slots[order]
    m2_values = arrays["M2"][order]
    m4_values = arrays["M4"][order]
    q_values = arrays.get("Q")
    if q_values is not None:
        q_values = q_values[order]
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
            m2_values, centers, kappas, counts, bins,
            initial_free=initial_free,
        )
    else:
        reduced = 0.5 * kappas[:, None] * (
            m2_values[None, :] - centers[:, None]
        ) ** 2
        free, denominator, iterations = solve_mbar(reduced, counts)
    return UmbrellaModel(
        M2=m2_values, M4=m4_values, Q=q_values, slots=slots,
        centers=centers, kappas=kappas, counts=counts,
        free_energies=free, log_denominator=denominator,
        iterations=iterations, bins=bins,
    )


def _absolute_contribution_diagnostics(values: np.ndarray) -> tuple[float, float]:
    absolute = np.abs(np.asarray(values, dtype=float))
    total = float(np.sum(absolute))
    if not math.isfinite(total) or total <= 0.0:
        return float(len(absolute)), 0.0
    squared = float(np.dot(absolute, absolute))
    ess = total * total / squared if squared > 0.0 else float(len(absolute))
    count = max(1, int(math.ceil(0.01 * len(absolute))))
    top = float(np.partition(absolute, -count)[-count:].sum() / total)
    return ess, top


def evaluate_umbrella_model(
    model: UmbrellaModel, *, delta_m2: float = 0.0, temperature: float = 1.0,
) -> dict[str, float]:
    """Evaluate canonical moments and dU4/dm2 at a locally reweighted mass."""
    if not math.isfinite(temperature) or temperature <= 0.0:
        raise ValueError("temperature must be finite and positive")
    log_weights = -model.log_denominator
    if delta_m2 != 0.0:
        if model.Q is None:
            raise ValueError("mass reweighting requires Q=sum(phi^2)")
        log_weights = log_weights - 0.5 * delta_m2 * model.Q / temperature
    log_weights = log_weights - np.max(log_weights)
    weights = np.exp(log_weights)
    weights /= np.sum(weights)
    mean_m2 = float(np.dot(weights, model.M2))
    mean_m4 = float(np.dot(weights, model.M4))
    if mean_m2 <= 16.0 * np.finfo(float).tiny:
        raise ValueError("weighted <M2> is numerically zero")
    binder = 1.0 - mean_m4 / (3.0 * mean_m2**2)
    result = {
        "mean_M2": mean_m2,
        "mean_M4": mean_m4,
        "binder": binder,
        "effective_sample_size": 1.0 / float(np.dot(weights, weights)),
        "ess_fraction": 1.0 / (len(weights) * float(np.dot(weights, weights))),
        "max_normalized_weight": float(np.max(weights)),
    }
    if model.Q is None:
        return result
    mean_q = float(np.dot(weights, model.Q))
    centered_q = model.Q - mean_q
    centered_m2 = model.M2 - mean_m2
    centered_m4 = model.M4 - mean_m4
    cov_m2_q = float(np.dot(weights, centered_m2 * centered_q))
    cov_m4_q = float(np.dot(weights, centered_m4 * centered_q))
    slope = (
        cov_m4_q / (6.0 * temperature * mean_m2**2)
        - mean_m4 * cov_m2_q / (3.0 * temperature * mean_m2**3)
    )
    m2q_ess, top_m2q = _absolute_contribution_diagnostics(
        weights * centered_m2 * centered_q
    )
    m4q_ess, top_m4q = _absolute_contribution_diagnostics(
        weights * centered_m4 * centered_q
    )
    result.update({
        "mean_Q": mean_q,
        "cov_M2_Q": cov_m2_q,
        "cov_M4_Q": cov_m4_q,
        "binder_slope_m2": slope,
        "m2q_contribution_ess": m2q_ess,
        "m2q_contribution_ess_fraction": m2q_ess / len(weights),
        "top1_abs_m2q_fraction": top_m2q,
        "m4q_contribution_ess": m4q_ess,
        "m4q_contribution_ess_fraction": m4q_ess / len(weights),
        "top1_abs_m4q_fraction": top_m4q,
    })
    return result


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
                      tolerance: float = 1e-9,
                      max_iterations: int = 200,
                      initial_free: np.ndarray | None = None,
                      sample_denominator: bool = True,
                      ) -> tuple[np.ndarray, np.ndarray | None, int]:
    edges = np.linspace(float(np.min(m2_values)), float(np.max(m2_values)), bins + 1)
    histogram, _ = np.histogram(m2_values, bins=edges)
    occupied = histogram > 0
    positions = 0.5 * (edges[:-1] + edges[1:])
    positions = positions[occupied]
    multiplicities = histogram[occupied].astype(float)
    reduced = 0.5 * kappas[:, None] * (positions[None, :] - centers[:, None]) ** 2
    log_counts = np.log(counts)
    total_count = float(np.sum(multiplicities))
    free = (np.zeros(len(counts)) if initial_free is None
            else np.asarray(initial_free, dtype=float).copy())
    if free.shape != counts.shape or not np.all(np.isfinite(free)):
        raise ValueError("invalid initial binned-WHAM free energies")
    free -= free[0]

    def objective(candidate: np.ndarray) -> float:
        log_denominator = logsumexp(
            log_counts[:, None] + candidate[:, None] - reduced, axis=0
        )
        return float(
            (np.dot(multiplicities, log_denominator)
             - np.dot(counts, candidate)) / total_count
        )

    # The usual self-consistent WHAM iteration behaves diffusively along a long
    # window ladder: with O(10^2) windows it can have excellent local overlap yet
    # still need far more than 20,000 iterations.  Minimize the equivalent convex
    # log-likelihood with a gauge-fixed, damped Newton solve instead.  The Hessian
    # is the summed categorical covariance of the window responsibilities.
    for iteration in range(1, max_iterations + 1):
        logits = log_counts[:, None] + free[:, None] - reduced
        denominator = logsumexp(logits, axis=0)
        responsibilities = np.exp(logits - denominator[None, :])
        expected = responsibilities @ multiplicities
        gradient = (expected - counts) / total_count
        if np.max(np.abs(gradient[1:])) < tolerance:
            break

        weighted = responsibilities * multiplicities[None, :]
        hessian = (
            np.diag(expected) - weighted @ responsibilities.T
        ) / total_count
        gauge_hessian = hessian[1:, 1:]
        try:
            step = np.linalg.solve(
                gauge_hessian + 1e-8 * np.eye(len(counts) - 1),
                -gradient[1:],
            )
        except np.linalg.LinAlgError:
            step = np.linalg.lstsq(
                gauge_hessian, -gradient[1:], rcond=1e-12
            )[0]
        slope = float(np.dot(gradient[1:], step))
        if not np.isfinite(slope) or slope >= 0.0:
            step = -gradient[1:]
            slope = -float(np.dot(gradient[1:], gradient[1:]))

        current_objective = objective(free)
        scale = 1.0
        while scale >= 1e-10:
            candidate = free.copy()
            candidate[1:] += scale * step
            if objective(candidate) <= current_objective + 1e-4 * scale * slope:
                free = candidate
                break
            scale *= 0.5
        else:
            raise RuntimeError("binned umbrella WHAM line search failed")
        # Sparse occupied bins (typical when a few M² tails stretch a 512-bin
        # histogram) make the Newton Hessian ill-conditioned. The residual can
        # stall around 1e-8, just above the default 1e-9 tolerance, while the
        # line search accepts numerically zero steps.
        if scale < 1e-8:
            residual = float(np.max(np.abs(gradient[1:])))
            if residual <= max(1e-6, 1_000.0 * tolerance):
                break
            # Newton can stall on a long, tightly spaced ladder even with
            # excellent occupancy. Retry the same iteration with steepest
            # descent instead of aborting the solve.
            step = -gradient[1:]
            slope = -float(np.dot(gradient[1:], gradient[1:]))
            scale = 1.0
            while scale >= 1e-10:
                candidate = free.copy()
                candidate[1:] += scale * step
                if objective(candidate) <= current_objective + 1e-4 * scale * slope:
                    free = candidate
                    break
                scale *= 0.5
            else:
                raise RuntimeError(
                    "binned umbrella WHAM line search stalled "
                    f"(residual={residual:.3g})"
                )
            if scale < 1e-8:
                raise RuntimeError(
                    "binned umbrella WHAM line search stalled "
                    f"(residual={residual:.3g})"
                )
    else:
        raise RuntimeError("binned umbrella WHAM did not converge within the iteration limit")
    if not sample_denominator:
        return free, None, iteration
    return free, sample_log_denominator(m2_values, centers, kappas, counts, free), iteration


def estimate_with_bin_fallback(
    arrays: dict[str, np.ndarray],
    bin_schedule: tuple[int, ...] = (512, 256, 128),
    initial_free: np.ndarray | None = None,
    *, delta_m2: float = 0.0, temperature: float = 1.0,
) -> dict[str, object]:
    """Unbias with occupied-bin WHAM, coarsening the grid if Newton stalls."""
    last_error: RuntimeError | None = None
    for bins in bin_schedule:
        try:
            if delta_m2 == 0.0 and temperature == 1.0:
                result = estimate(arrays, bins, initial_free=initial_free)
            else:
                result = estimate(
                    arrays, bins, initial_free=initial_free,
                    delta_m2=delta_m2, temperature=temperature,
                )
            result["wham_bins"] = bins
            return result
        except RuntimeError as error:
            last_error = error
    if last_error is None:
        raise RuntimeError("binned umbrella WHAM bin schedule is empty")
    raise RuntimeError(
        f"binned umbrella WHAM failed for bins={bin_schedule}: {last_error}"
    ) from last_error


def estimate(arrays: dict[str, np.ndarray], bins: int = 0,
             initial_free: np.ndarray | None = None, *,
             delta_m2: float = 0.0,
             temperature: float = 1.0) -> dict[str, object]:
    model = prepare_umbrella_model(arrays, bins, initial_free=initial_free)
    evaluated = evaluate_umbrella_model(
        model, delta_m2=delta_m2, temperature=temperature,
    )
    weights_log = -model.log_denominator
    if delta_m2 != 0.0:
        if model.Q is None:
            raise ValueError("mass reweighting requires Q=sum(phi^2)")
        weights_log -= 0.5 * delta_m2 * model.Q / temperature
    weights_log -= np.max(weights_log)
    weights = np.exp(weights_log)
    weights /= np.sum(weights)

    profile_bins = np.linspace(float(np.min(model.M2)), float(np.max(model.M2)), 65)
    neighbor_overlap: list[float] = []
    for slot in range(1, len(model.counts)):
        left, _ = np.histogram(model.M2[model.slots == slot], bins=profile_bins)
        right, _ = np.histogram(model.M2[model.slots == slot + 1], bins=profile_bins)
        neighbor_overlap.append(float(np.minimum(left / left.sum(), right / right.sum()).sum()))
    hist, edges = np.histogram(model.M2, bins=profile_bins, weights=weights)
    widths = np.diff(edges)
    density = hist / widths
    positive = density > 0
    free_profile = np.full_like(density, np.nan, dtype=float)
    free_profile[positive] = -np.log(density[positive])
    free_profile[positive] -= np.nanmin(free_profile)
    return {
        **evaluated,
        "mbar_iterations": model.iterations,
        "free_energies": model.free_energies.tolist(),
        "neighbor_overlap": neighbor_overlap,
        "profile_centers": (0.5 * (edges[:-1] + edges[1:])).tolist(),
        "profile_free_energy": free_profile.tolist(),
        "profile_density": density.tolist(),
        "profile_edges": edges.tolist(),
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
    initial_free = None
    if bins > 0:
        initial_free = np.asarray(estimate(arrays, bins)["free_energies"])
    # Rows are emitted time-major, one row per slot. Resample synchronized time
    # blocks so exchange-induced correlations between windows are retained.
    row_grid = np.arange(samples * replicas).reshape(samples, replicas)
    for _ in range(draws):
        chosen = rng.choice(starts, size=blocks_needed, replace=True)
        times = np.concatenate([np.arange(start, start + block_size) for start in chosen])[:samples]
        indices = row_grid[times].reshape(-1)
        sample_arrays = {key: values[indices] for key, values in arrays.items()}
        result = estimate(sample_arrays, bins, initial_free=initial_free)
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
