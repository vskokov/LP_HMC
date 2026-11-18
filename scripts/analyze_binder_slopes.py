#!/usr/bin/env python3
"""CPU finite-size scaling of dU4/dm2 from M2-umbrella statistics.

The script never launches simulations or TSP jobs.  It consumes only complete
campaigns, reconstructs canonical moments with the existing binned-WHAM
machinery, refines adjacent-size Binder crossings by local mass reweighting,
and propagates crossing/slope correlations with a synchronized block bootstrap.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import multiprocessing as mp
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from analyze_umbrella import (  # noqa: E402
    UmbrellaModel,
    evaluate_umbrella_model,
    prepare_umbrella_model,
    read_umbrella,
)
from reweight_binder import integrated_autocorrelation_time  # noqa: E402
from umbrella_binder_campaign import analyze_run_dir  # noqa: E402


DEFAULT_CAMPAIGNS = (
    (-0.5, "runs/umbrella_binder_Zm0p5", "plots/umbrella_binder_mZm0p5.csv"),
    (-0.25, "runs/umbrella_binder_Zm0p25", "plots/umbrella_binder_mZm0p25.csv"),
    (0.0, "runs/umbrella_binder_Z0", "plots/umbrella_binder_mZ0.csv"),
    (0.5, "runs/umbrella_binder_Z0p5", "plots/umbrella_binder_mZ0p5.csv"),
    (1.0, "runs/umbrella_binder_Z1", "plots/umbrella_binder_mZ1.csv"),
    (1.25, "runs/umbrella_binder_Z1p25", "plots/umbrella_binder_mZ1p25.csv"),
    (2.0, "runs/umbrella_binder_Z2", "plots/umbrella_binder_mZ2.csv"),
    (-0.75, "runs/umbrella_binder_Zm0p75", "plots/umbrella_binder_mZm0p75.csv"),
    (-1.0, "runs/umbrella_binder_Zm1", "plots/umbrella_binder_mZm1.csv"),
)
SOURCE_BINDER_TOLERANCE = 0.01


@dataclass(frozen=True)
class Campaign:
    Z: float
    run_dir: Path
    binder_csv: Path


@dataclass
class Source:
    key: tuple[int, float, str]
    path: Path
    L: int
    source_m2: float
    phase: str
    temperature: float
    samples: int
    replicas: int
    arrays: dict[str, np.ndarray]
    model: UmbrellaModel
    wham_bins: int
    block_size: int


@dataclass(frozen=True)
class CrossingSpec:
    pair: str
    L: int
    sL: int
    left_m2: float
    right_m2: float
    linear_m2: float
    linear_U4: float


def metadata_only(path: Path) -> dict[str, str]:
    metadata: dict[str, str] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.startswith("#"):
                break
            key, separator, value = line[1:].strip().partition("=")
            if separator:
                metadata[key.strip()] = value.strip()
    return metadata


def completion_counts(manifest: Path) -> tuple[int, int]:
    with manifest.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    complete = 0
    for row in rows:
        marker = Path(row["completion_marker"])
        if not marker.is_file():
            continue
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        complete += payload.get("complete") is True
    return complete, len(rows)


def paired_statistics_masses(manifest: Path) -> set[float]:
    """Return source masses having both independent statistics files."""
    replicas: dict[float, set[str]] = defaultdict(set)
    with manifest.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if not Path(row["stats_path"]).is_file():
                continue
            replicas[float(row["m2"])].add(row.get("replica", row.get("init_phase", "")))
    return {mass for mass, sources in replicas.items() if len(sources) >= 2}


def campaign_status(
    campaign: Campaign, sizes: Iterable[int], allow_partial: bool = False,
) -> tuple[bool, str]:
    descriptions = []
    ready = True
    paired_by_size: list[set[float]] = []
    for L in sizes:
        manifest = campaign.run_dir / f"L{L}" / "manifest.csv"
        if not manifest.is_file():
            ready = False
            descriptions.append(f"L{L}=missing")
            paired_by_size.append(set())
            continue
        complete, expected = completion_counts(manifest)
        paired = paired_statistics_masses(manifest)
        paired_by_size.append(paired)
        descriptions.append(f"L{L}={complete}/{expected},paired={len(paired)}")
        if not allow_partial:
            ready &= expected > 0 and complete == expected
    if allow_partial:
        common = set.intersection(*paired_by_size) if paired_by_size else set()
        ready = len(common) >= 2
        descriptions.append(f"common_paired_masses={len(common)}")
    descriptions.append(
        "binder_csv=present" if campaign.binder_csv.is_file()
        else "binder_csv=will_generate"
    )
    return ready, " ".join(descriptions)


def load_binder_curve(path: Path, sizes: set[int]) -> dict[int, list[tuple[float, float]]]:
    curves: dict[int, list[tuple[float, float]]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            L = int(float(row["L"]))
            if L in sizes:
                curves[L].append((float(row["m2"]), float(row["U4"])))
    for curve in curves.values():
        curve.sort()
    return curves


def generate_binder_curve(
    campaign: Campaign, sizes: set[int], output: Path,
) -> dict[int, list[tuple[float, float]]]:
    """Generate the source-mass curve when a completed new campaign lacks one."""
    rows: list[dict[str, object]] = []
    report_root = output / "generated_central_reports" / f"Z{campaign.Z:g}"
    for L in sorted(sizes):
        rows.extend(analyze_run_dir(
            campaign.run_dir / f"L{L}", report_root / f"L{L}",
            bootstrap=1, dry_run=False, reuse_existing=True,
        ))
    csv_path = output / f"generated_binder_Z{campaign.Z:g}.csv"
    write_rows(csv_path, rows)
    curves: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for row in rows:
        curves[int(row["L"])].append((float(row["m2"]), float(row["U4"])))
    for curve in curves.values():
        curve.sort()
    return curves


def linear_crossing(
    left: list[tuple[float, float]], right: list[tuple[float, float]],
    L: int, sL: int,
) -> CrossingSpec | None:
    first, second = dict(left), dict(right)
    common = sorted(set(first) & set(second))
    found: list[CrossingSpec] = []
    for m0, m1 in zip(common, common[1:]):
        d0 = first[m0] - second[m0]
        d1 = first[m1] - second[m1]
        if d0 == 0.0:
            found.append(CrossingSpec(
                f"{L}x{sL}", L, sL, m0, m1, m0, first[m0],
            ))
        elif d0 * d1 < 0.0:
            fraction = d0 / (d0 - d1)
            mass = m0 + fraction * (m1 - m0)
            binder = first[m0] + fraction * (first[m1] - first[m0])
            found.append(CrossingSpec(
                f"{L}x{sL}", L, sL, m0, m1, mass, binder,
            ))
    return max(found, key=lambda item: item.linear_U4) if found else None


def source_index(campaign: Campaign, sizes: set[int]) -> dict[tuple[int, float], list[Path]]:
    indexed: dict[tuple[int, float], list[Path]] = defaultdict(list)
    for L in sorted(sizes):
        for path in sorted((campaign.run_dir / f"L{L}" / "statistics").glob("*.csv")):
            metadata = metadata_only(path)
            if int(metadata.get("L", -1)) != L:
                continue
            indexed[(L, round(float(metadata["m2"]), 12))].append(path)
    return indexed


def automatic_block_size(arrays: dict[str, np.ndarray], samples: int, replicas: int) -> int:
    maximum = 0.5
    for name in ("M2", "Q"):
        time_series = arrays[name].reshape(samples, replicas).mean(axis=1)
        maximum = max(maximum, integrated_autocorrelation_time(time_series))
    return min(max(1, int(math.ceil(2.0 * maximum))), max(1, samples // 4))


def prepare_with_fallback(
    arrays: dict[str, np.ndarray], initial_free: np.ndarray | None = None,
    preferred: int | None = None,
) -> tuple[UmbrellaModel, int]:
    schedule = (preferred,) if preferred is not None else (512, 256, 128)
    last: RuntimeError | None = None
    for bins in schedule:
        try:
            return prepare_umbrella_model(arrays, bins, initial_free=initial_free), bins
        except RuntimeError as error:
            last = error
    if last is None:
        raise RuntimeError("empty WHAM bin schedule")
    raise last


def load_sources(
    campaign: Campaign, specs: list[CrossingSpec], sizes: set[int],
    block_size: str, requested_bins: int,
) -> dict[tuple[int, float, str], Source]:
    indexed = source_index(campaign, sizes)
    needed: set[tuple[int, float]] = set()
    for spec in specs:
        for L in (spec.L, spec.sL):
            needed.add((L, round(spec.left_m2, 12)))
            needed.add((L, round(spec.right_m2, 12)))
    result: dict[tuple[int, float, str], Source] = {}
    for L, mass in sorted(needed):
        paths = indexed.get((L, mass), [])
        if len(paths) != 2:
            raise RuntimeError(f"Z={campaign.Z:g} L={L} m2={mass:g}: expected two sources, found {len(paths)}")
        for path in paths:
            started = time.monotonic()
            metadata, full_arrays = read_umbrella(path)
            # The generic reader exposes the full schema for existing callers;
            # slope FSS needs only these six columns.  Copies release the large
            # 11-column backing table before the process pool is forked.
            arrays = {
                name: np.ascontiguousarray(full_arrays[name])
                for name in (
                    "slot", "umbrella_center", "umbrella_kappa",
                    "M2", "M4", "Q",
                )
            }
            del full_arrays
            phase = metadata.get("init_phase", path.stem)
            model, bins = prepare_with_fallback(
                arrays, preferred=requested_bins if requested_bins > 0 else None,
            )
            temperature = float(metadata.get("temperature", "1"))
            analytic = evaluate_umbrella_model(model, temperature=temperature)
            derivative_step = 1e-5
            upper = evaluate_umbrella_model(
                model, delta_m2=derivative_step, temperature=temperature,
            )["binder"]
            lower = evaluate_umbrella_model(
                model, delta_m2=-derivative_step, temperature=temperature,
            )["binder"]
            finite_difference = (upper - lower) / (2.0 * derivative_step)
            derivative_scale = max(abs(analytic["binder_slope_m2"]), 1e-10)
            if abs(finite_difference - analytic["binder_slope_m2"]) / derivative_scale > 1e-5:
                raise RuntimeError(
                    f"{path}: analytic Binder slope failed finite-difference check"
                )
            samples = int(metadata["samples_per_window"])
            replicas = int(metadata["umbrella_replicas"])
            chosen_block = (
                automatic_block_size(arrays, samples, replicas)
                if block_size == "auto" else min(int(block_size), samples)
            )
            key = (L, mass, phase)
            result[key] = Source(
                key=key, path=path, L=L, source_m2=float(metadata["m2"]),
                phase=phase, temperature=temperature,
                samples=samples, replicas=replicas, arrays=arrays, model=model,
                wham_bins=bins, block_size=chosen_block,
            )
            print(
                f"  prepared L={L} m2={mass:g} phase={phase} bins={bins} "
                f"block={chosen_block} elapsed={time.monotonic() - started:.1f}s",
                flush=True,
            )
    return result


def sources_for(
    sources: dict[tuple[int, float, str], Source], spec: CrossingSpec, L: int,
) -> list[Source]:
    masses = {round(spec.left_m2, 12), round(spec.right_m2, 12)}
    selected = [source for key, source in sources.items() if key[0] == L and key[1] in masses]
    if len(selected) != 4:
        raise RuntimeError(
            f"{spec.pair} L={L}: expected four independent endpoint/phase sources, "
            f"found {len(selected)}"
        )
    return sorted(selected, key=lambda source: (source.source_m2, source.phase))


def combined_evaluation(selected: list[Source], target_m2: float) -> dict[str, float]:
    estimates = [
        evaluate_umbrella_model(
            source.model, delta_m2=target_m2 - source.source_m2,
            temperature=source.temperature,
        )
        for source in selected
    ]
    result = {
        name: float(np.mean([estimate[name] for estimate in estimates]))
        for name in ("binder", "binder_slope_m2")
    }
    result.update({
        "min_ess": min(item["effective_sample_size"] for item in estimates),
        "min_ess_fraction": min(item["ess_fraction"] for item in estimates),
        "max_weight": max(item["max_normalized_weight"] for item in estimates),
        "max_top1_abs_m2q_fraction": max(item["top1_abs_m2q_fraction"] for item in estimates),
        "max_top1_abs_m4q_fraction": max(item["top1_abs_m4q_fraction"] for item in estimates),
        "min_m2q_ess_fraction": min(item["m2q_contribution_ess_fraction"] for item in estimates),
        "min_m4q_ess_fraction": min(item["m4q_contribution_ess_fraction"] for item in estimates),
        "source_binder_spread": max(item["binder"] for item in estimates) - min(item["binder"] for item in estimates),
        "source_slope_min": min(item["binder_slope_m2"] for item in estimates),
        "source_slope_max": max(item["binder_slope_m2"] for item in estimates),
    })
    return result


def bisection_root(function, left: float, right: float, iterations: int = 50) -> float:
    f_left = float(function(left))
    f_right = float(function(right))
    if f_left == 0.0:
        return left
    if f_right == 0.0:
        return right
    if not (math.isfinite(f_left) and math.isfinite(f_right)) or f_left * f_right > 0.0:
        raise ValueError("reweighted curves do not bracket a crossing")
    for _ in range(iterations):
        middle = 0.5 * (left + right)
        f_middle = float(function(middle))
        if f_left * f_middle <= 0.0:
            right, f_right = middle, f_middle
        else:
            left, f_left = middle, f_middle
    return 0.5 * (left + right)


def refined_crossing(
    low_sources: list[Source], high_sources: list[Source], spec: CrossingSpec,
    max_iterations: int = 12,
) -> float:
    """Safeguarded Newton solve using the already-available analytic slopes."""
    left, right = spec.left_m2, spec.right_m2
    left_low = combined_evaluation(low_sources, left)
    left_high = combined_evaluation(high_sources, left)
    right_low = combined_evaluation(low_sources, right)
    right_high = combined_evaluation(high_sources, right)
    f_left = left_low["binder"] - left_high["binder"]
    f_right = right_low["binder"] - right_high["binder"]
    if f_left == 0.0:
        return left
    if f_right == 0.0:
        return right
    if f_left * f_right > 0.0:
        raise ValueError("reweighted curves do not bracket a crossing")
    mass = min(max(spec.linear_m2, left), right)
    for _ in range(max_iterations):
        low = combined_evaluation(low_sources, mass)
        high = combined_evaluation(high_sources, mass)
        difference = low["binder"] - high["binder"]
        if abs(difference) < 1e-11 or right - left < 1e-11:
            return mass
        if f_left * difference <= 0.0:
            right, f_right = mass, difference
        else:
            left, f_left = mass, difference
        derivative = low["binder_slope_m2"] - high["binder_slope_m2"]
        candidate = mass - difference / derivative if derivative != 0.0 else math.nan
        if not math.isfinite(candidate) or candidate <= left or candidate >= right:
            candidate = 0.5 * (left + right)
        mass = candidate
    return mass


def evaluate_spec(sources: dict[tuple[int, float, str], Source], spec: CrossingSpec) -> dict[str, float]:
    left_sources = sources_for(sources, spec, spec.L)
    right_sources = sources_for(sources, spec, spec.sL)

    refined = refined_crossing(left_sources, right_sources, spec)
    rows: dict[str, float] = {}
    for method, mass in (("reweighted", refined), ("linear", spec.linear_m2)):
        low = combined_evaluation(left_sources, mass)
        high = combined_evaluation(right_sources, mass)
        slope_low = low["binder_slope_m2"]
        slope_high = high["binder_slope_m2"]
        exponent = math.log(abs(slope_high / slope_low)) / math.log(spec.sL / spec.L)
        prefix = method + "_"
        rows.update({
            prefix + "m2_c": mass,
            prefix + "U4_low": low["binder"],
            prefix + "U4_high": high["binder"],
            prefix + "slope_low": slope_low,
            prefix + "slope_high": slope_high,
            prefix + "y_eff": exponent,
        })
        if method == "reweighted":
            rows.update({
                "min_ess": min(low["min_ess"], high["min_ess"]),
                "min_ess_fraction": min(low["min_ess_fraction"], high["min_ess_fraction"]),
                "max_weight": max(low["max_weight"], high["max_weight"]),
                "max_top1_abs_m2q_fraction": max(low["max_top1_abs_m2q_fraction"], high["max_top1_abs_m2q_fraction"]),
                "max_top1_abs_m4q_fraction": max(low["max_top1_abs_m4q_fraction"], high["max_top1_abs_m4q_fraction"]),
                "min_m2q_ess_fraction": min(low["min_m2q_ess_fraction"], high["min_m2q_ess_fraction"]),
                "min_m4q_ess_fraction": min(low["min_m4q_ess_fraction"], high["min_m4q_ess_fraction"]),
                "source_binder_spread": max(low["source_binder_spread"], high["source_binder_spread"]),
                "source_slope_spread": max(low["source_slope_max"] - low["source_slope_min"], high["source_slope_max"] - high["source_slope_min"]),
            })
    return rows


def circular_times(samples: int, block: int, rng: np.random.Generator) -> np.ndarray:
    blocks = math.ceil(samples / block)
    starts = rng.integers(0, samples, size=blocks)
    offsets = np.arange(block)
    return ((starts[:, None] + offsets) % samples).reshape(-1)[:samples]


def resample_source(source: Source, rng: np.random.Generator) -> Source:
    times = circular_times(source.samples, source.block_size, rng)
    row_grid = np.arange(source.samples * source.replicas).reshape(source.samples, source.replicas)
    indices = row_grid[times].reshape(-1)
    names = ("slot", "umbrella_center", "umbrella_kappa", "M2", "M4", "Q")
    arrays = {name: source.arrays[name][indices] for name in names}
    model, _ = prepare_with_fallback(
        arrays, initial_free=source.model.free_energies, preferred=source.wham_bins,
    )
    return Source(
        key=source.key, path=source.path, L=source.L,
        source_m2=source.source_m2, phase=source.phase,
        temperature=source.temperature, samples=source.samples,
        replicas=source.replicas, arrays=arrays, model=model,
        wham_bins=source.wham_bins, block_size=source.block_size,
    )


_BOOT_SOURCES: dict[tuple[int, float, str], Source] = {}
_BOOT_SPECS: list[CrossingSpec] = []


def initialize_bootstrap(sources, specs) -> None:
    global _BOOT_SOURCES, _BOOT_SPECS
    _BOOT_SOURCES = sources
    _BOOT_SPECS = specs


def bootstrap_draw(task: tuple[int, int]) -> tuple[int, list[dict[str, object]]]:
    draw, seed = task
    rng = np.random.default_rng(seed)
    sampled_sources: dict[tuple[int, float, str], Source] = {}
    for key, source in _BOOT_SOURCES.items():
        sampled = resample_source(source, rng)
        # The solved model owns sorted M2/M4/Q and its denominator. The raw
        # resampled slot/center/kappa arrays are no longer needed for crossing
        # evaluation and otherwise nearly double each worker's resident set.
        sampled.arrays = {}
        sampled_sources[key] = sampled

    rows: list[dict[str, object]] = []
    for spec in _BOOT_SPECS:
        try:
            result = evaluate_spec(sampled_sources, spec)
            for method in ("reweighted", "linear"):
                rows.append({
                    "draw": draw, "pair": spec.pair, "method": method,
                    "m2_c": result[method + "_m2_c"],
                    "U4_low": result[method + "_U4_low"],
                    "U4_high": result[method + "_U4_high"],
                    "slope_low": result[method + "_slope_low"],
                    "slope_high": result[method + "_slope_high"],
                    "y_eff": result[method + "_y_eff"],
                })
        except (RuntimeError, ValueError, FloatingPointError):
            for method in ("reweighted", "linear"):
                rows.append({
                    "draw": draw, "pair": spec.pair, "method": method,
                    "m2_c": math.nan, "U4_low": math.nan, "U4_high": math.nan,
                    "slope_low": math.nan, "slope_high": math.nan, "y_eff": math.nan,
                })
    return draw, rows


def run_bootstrap(sources, specs, draws: int, jobs: int, seed: int) -> list[dict[str, object]]:
    if draws < 1:
        return []
    rng = np.random.default_rng(seed)
    seeds = rng.integers(0, np.iinfo(np.uint64).max, size=draws, dtype=np.uint64)
    tasks = [(draw, int(seeds[draw])) for draw in range(draws)]
    rows: list[dict[str, object]] = []
    started = time.monotonic()
    report_every = max(1, draws // 20)
    methods = mp.get_all_start_methods()
    context = mp.get_context("fork" if "fork" in methods else methods[0])
    processes = min(jobs, draws)
    with context.Pool(
        processes=processes, initializer=initialize_bootstrap,
        initargs=(sources, specs),
    ) as pool:
        results = pool.imap_unordered(bootstrap_draw, tasks, chunksize=1)
        for complete, (_, draw_rows) in enumerate(results, start=1):
            rows.extend(draw_rows)
            if complete == 1 or complete == draws or complete % report_every == 0:
                elapsed = time.monotonic() - started
                rate = complete / elapsed
                eta = (draws - complete) / rate if rate > 0 else math.inf
                print(
                    f"bootstrap {complete}/{draws} elapsed={elapsed/60:.1f}m ETA={eta/60:.1f}m workers={processes}",
                    file=sys.stderr, flush=True,
                )
    rows.sort(key=lambda row: (int(row["draw"]), str(row["pair"]), str(row["method"])))
    return rows


def percentile_summary(values: list[float]) -> tuple[float, float, float, int]:
    finite = np.asarray([value for value in values if math.isfinite(value)], dtype=float)
    if finite.size == 0:
        return math.nan, math.nan, math.nan, 0
    low, median, high = np.percentile(finite, [2.5, 50.0, 97.5])
    return float(low), float(median), float(high), int(finite.size)


def warning_status(row: dict[str, object], success_fraction: float) -> str:
    if success_fraction < 0.80:
        return "unstable_crossing"
    if float(row["min_ess"]) < 50 or float(row["min_ess_fraction"]) < 0.01:
        return "low_ess"
    if float(row["source_binder_spread"]) > SOURCE_BINDER_TOLERANCE:
        return "source_disagreement"
    if max(float(row["max_top1_abs_m2q_fraction"]), float(row["max_top1_abs_m4q_fraction"])) > 0.5:
        return "heavy_mixed_tail"
    if min(float(row["min_m2q_ess_fraction"]), float(row["min_m4q_ess_fraction"])) < 0.01:
        return "low_mixed_ess"
    if success_fraction < 0.95:
        return "bootstrap_root_warning"
    return "ok"


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def slope_curve_rows(
    Z: float, sources: dict[tuple[int, float, str], Source], specs: list[CrossingSpec],
    points: int = 81,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for spec in specs:
        for L in (spec.L, spec.sL):
            selected = sources_for(sources, spec, L)
            for mass in np.linspace(spec.left_m2, spec.right_m2, points):
                estimate = combined_evaluation(selected, float(mass))
                rows.append({
                    "Z": Z, "pair": spec.pair, "L": L, "m2": float(mass),
                    "U4": estimate["binder"],
                    "dU4_dm2": estimate["binder_slope_m2"],
                    "abs_dU4_dm2": abs(estimate["binder_slope_m2"]),
                })
    return rows


def plot_outputs(output: Path, slopes: list[dict[str, object]], summaries: list[dict[str, object]]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    by_Z: dict[float, list[dict[str, object]]] = defaultdict(list)
    for row in slopes:
        by_Z[float(row["Z"])].append(row)
    for Z, rows in by_Z.items():
        fig, axes = plt.subplots(2, 1, figsize=(7.0, 7.0), sharex=True)
        for L in sorted({int(row["L"]) for row in rows}):
            subset = [row for row in rows if int(row["L"]) == L]
            subset.sort(key=lambda row: float(row["m2"]))
            axes[0].plot([row["m2"] for row in subset], [row["U4"] for row in subset], label=f"L={L}")
            axes[1].plot([row["m2"] for row in subset], [row["abs_dU4_dm2"] for row in subset], label=f"L={L}")
        axes[0].set_ylabel(r"$U_4$")
        axes[1].set_ylabel(r"$|\partial U_4/\partial m^2|$")
        axes[1].set_xlabel(r"$m^2$")
        axes[1].set_yscale("log")
        axes[0].legend(frameon=False, ncol=2)
        for axis in axes:
            axis.grid(alpha=0.25)
        fig.suptitle(f"Binder and mass derivative at Z={Z:g}")
        fig.tight_layout()
        label = str(Z).replace("-", "m").replace(".", "p")
        fig.savefig(output / f"slope_curves_Z{label}.png", dpi=180)
        plt.close(fig)

    valid = [row for row in summaries if row["method"] == "reweighted"]
    fig, axis = plt.subplots(figsize=(7.2, 4.8))
    for pair, marker in (("12x16", "o"), ("16x20", "s"), ("20x24", "^")):
        subset = sorted((row for row in valid if row["pair"] == pair), key=lambda row: float(row["Z"]))
        if not subset:
            continue
        z = np.asarray([float(row["Z"]) for row in subset])
        central = np.asarray([float(row["y_eff"]) for row in subset])
        lo = np.asarray([float(row["y_eff_low"]) for row in subset])
        hi = np.asarray([float(row["y_eff_high"]) for row in subset])
        axis.plot(z, central, marker=marker, label=pair)
        bracketed = np.isfinite(lo) & np.isfinite(hi) & (lo <= central) & (central <= hi)
        if np.any(bracketed):
            axis.errorbar(
                z[bracketed], central[bracketed],
                yerr=np.vstack((central[bracketed] - lo[bracketed], hi[bracketed] - central[bracketed])),
                fmt="none", capsize=3,
            )
    for value, label, style in ((1 / 0.6298, "3D Ising", "--"), (2.0, "tricritical MF", ":"), (3.0, "first order", "-.")):
        axis.axhline(value, color="0.35", linestyle=style, linewidth=1.0, label=label)
    axis.set_xlabel(r"$Z$")
    axis.set_ylabel(r"$y_{\rm eff}$")
    axis.grid(alpha=0.25)
    axis.legend(frameon=False, ncol=2)
    fig.tight_layout()
    fig.savefig(output / "effective_exponents_vs_Z.png", dpi=180)
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(6.4, 4.8))
    for pair, marker in (("12x16", "o"), ("16x20", "s"), ("20x24", "^")):
        subset = sorted((row for row in summaries if row["pair"] == pair and row["method"] == "reweighted"), key=lambda row: float(row["Z"]))
        axis.plot([row["Z"] for row in subset], [float(row["m2_c"]) - float(row["linear_m2_c"]) for row in subset], marker=marker, label=pair)
    axis.axhline(0.0, color="0.35", linewidth=1.0)
    axis.set_xlabel(r"$Z$")
    axis.set_ylabel(r"$m^2_{c,\,reweighted}-m^2_{c,\,linear}$")
    axis.grid(alpha=0.25)
    axis.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(output / "crossing_method_shift.png", dpi=180)
    plt.close(fig)


def interpretation(output: Path, summaries: list[dict[str, object]], status_rows: list[dict[str, object]]) -> None:
    lines = [
        "# Binder mass-derivative finite-size scaling", "",
        "The reweighted crossing is primary; the legacy linear crossing is retained as a systematic check.",
        "Reference exponents are conventional benchmarks only and are not imposed on the modified theory.", "",
        "## Campaign status", "",
    ]
    for row in status_rows:
        lines.append(f"- Z={float(row['Z']):g}: {row['status']} ({row['details']})")
    lines.extend(["", "## Largest-size-pair readout", ""])
    primary = [row for row in summaries if row["method"] == "reweighted"]
    largest = []
    for z_value in sorted({float(row["Z"]) for row in primary}):
        candidates = [row for row in primary if math.isclose(float(row["Z"]), z_value)]
        largest.append(max(candidates, key=lambda row: int(row["sL"])))
    for row in largest:
        low, high = float(row["y_eff_low"]), float(row["y_eff_high"])
        compatible = []
        for value, name in ((1 / 0.6298, "3D-Ising"), (2.0, "conventional-tricritical"), (3.0, "first-order")):
            if low <= value <= high:
                compatible.append(name)
        reference = ", ".join(compatible) if compatible else "none of the three exact benchmark values"
        lines.append(
            f"- Z={float(row['Z']):g}, pair={row['pair']}: central y_eff={float(row['y_eff']):.3f}, bootstrap "
            f"[{low:.3f}, {high:.3f}], warning={row['warning_status']}; interval contains {reference}."
        )
    lines.extend([
        "", "A benchmark match is not a singularity classification. Drift across the available size pairs,",
        "mixed-moment tails, source agreement, and the possible failure of uniform M in the modulated regime",
        "must be considered together. First-order identification additionally requires coexistence/barrier evidence.", "",
    ])
    (output / "interpretation.md").write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--campaign", nargs=3, action="append", metavar=("Z", "RUN_DIR", "BINDER_CSV"),
        help="repeat to replace the default campaign registry",
    )
    parser.add_argument("--sizes", type=int, nargs="+", default=[12, 16, 20, 24])
    parser.add_argument("--bootstrap", type=int, default=200)
    parser.add_argument(
        "--jobs", type=int, default=min(2, os.cpu_count() or 1),
        help="bootstrap workers; two is the measured memory-bandwidth optimum on this host",
    )
    parser.add_argument("--block-size", default="auto")
    parser.add_argument(
        "--bins", type=int, choices=(0, 128, 256, 512), default=0,
        help="WHAM bins; 0 uses the production 512,256,128 fallback",
    )
    parser.add_argument("--seed", type=int, default=314159)
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "reports/binder_slope_fss/exploratory")
    parser.add_argument("--Z", type=float, action="append", dest="z_filter")
    parser.add_argument(
        "--allow-partial", action="store_true",
        help="analyze campaigns with at least two common masses having both source files",
    )
    args = parser.parse_args()
    if args.bootstrap < 1 or args.jobs < 1:
        parser.error("bootstrap and jobs must be positive")
    if args.block_size != "auto" and int(args.block_size) < 1:
        parser.error("block size must be positive or auto")
    args.sizes = sorted(set(args.sizes))
    if len(args.sizes) < 2 or any(size < 2 for size in args.sizes):
        parser.error("at least two valid lattice sizes are required")
    return args


def main() -> int:
    args = parse_args()
    raw = args.campaign or DEFAULT_CAMPAIGNS
    campaigns = [
        Campaign(float(item[0]), (REPO_ROOT / item[1]).resolve(), (REPO_ROOT / item[2]).resolve())
        for item in raw
    ]
    if args.z_filter:
        campaigns = [campaign for campaign in campaigns if any(math.isclose(campaign.Z, value, abs_tol=1e-12) for value in args.z_filter)]
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    status_rows: list[dict[str, object]] = []
    slope_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    bootstrap_rows: list[dict[str, object]] = []
    size_set = set(args.sizes)
    pair_sizes = tuple(zip(args.sizes, args.sizes[1:]))

    for campaign_index, campaign in enumerate(campaigns):
        ready, details = campaign_status(campaign, args.sizes, args.allow_partial)
        status_rows.append({"Z": campaign.Z, "status": "ready" if ready else "skipped", "details": details})
        print(f"Z={campaign.Z:g} {'ready' if ready else 'skipped'} {details}", flush=True)
        if not ready:
            continue
        curves = (
            load_binder_curve(campaign.binder_csv, size_set)
            if campaign.binder_csv.is_file()
            else generate_binder_curve(campaign, size_set, output)
        )
        specs = []
        for L, sL in pair_sizes:
            spec = linear_crossing(curves[L], curves[sL], L, sL)
            if spec is None:
                print(f"Z={campaign.Z:g} {L}x{sL}: no linear crossing", file=sys.stderr)
                continue
            specs.append(spec)
        if not specs:
            continue
        print(f"Z={campaign.Z:g}: loading {len(specs)} crossing neighborhoods", flush=True)
        sources = load_sources(
            campaign, specs, size_set, args.block_size, args.bins,
        )
        central: dict[str, dict[str, float]] = {}
        for spec in specs:
            try:
                central[spec.pair] = evaluate_spec(sources, spec)
            except ValueError as error:
                print(f"Z={campaign.Z:g} {spec.pair}: {error}", file=sys.stderr)
        usable_specs = [spec for spec in specs if spec.pair in central]
        if not usable_specs:
            continue
        slope_rows.extend(slope_curve_rows(campaign.Z, sources, usable_specs))
        draws = run_bootstrap(
            sources, usable_specs, args.bootstrap, args.jobs,
            args.seed + 1009 * campaign_index,
        )
        for row in draws:
            bootstrap_rows.append({"Z": campaign.Z, **row})
        grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
        for row in draws:
            grouped[(str(row["pair"]), str(row["method"]))].append(row)
        for spec in usable_specs:
            values = central[spec.pair]
            for method in ("reweighted", "linear"):
                samples = grouped[(spec.pair, method)]
                y_low, y_median, y_high, successes = percentile_summary([float(row["y_eff"]) for row in samples])
                m_low, m_median, m_high, _ = percentile_summary([float(row["m2_c"]) for row in samples])
                success_fraction = successes / args.bootstrap
                base = {
                    "Z": campaign.Z, "pair": spec.pair, "L": spec.L, "sL": spec.sL,
                    "method": method,
                    "m2_c": values[method + "_m2_c"],
                    "m2_c_low": m_low, "m2_c_median": m_median, "m2_c_high": m_high,
                    "U4_low_size": values[method + "_U4_low"],
                    "U4_high_size": values[method + "_U4_high"],
                    "slope_low": values[method + "_slope_low"],
                    "slope_high": values[method + "_slope_high"],
                    "y_eff": values[method + "_y_eff"],
                    "y_eff_low": y_low, "y_eff_median": y_median, "y_eff_high": y_high,
                    "bootstrap_success_fraction": success_fraction,
                    "linear_m2_c": spec.linear_m2,
                }
                if method == "reweighted":
                    base.update({name: values[name] for name in (
                        "min_ess", "min_ess_fraction", "max_weight",
                        "max_top1_abs_m2q_fraction", "max_top1_abs_m4q_fraction",
                        "min_m2q_ess_fraction", "min_m4q_ess_fraction",
                        "source_binder_spread", "source_slope_spread",
                    )})
                    base["warning_status"] = warning_status(base, success_fraction)
                else:
                    base.update({
                        "min_ess": "", "min_ess_fraction": "", "max_weight": "",
                        "max_top1_abs_m2q_fraction": "", "max_top1_abs_m4q_fraction": "",
                        "min_m2q_ess_fraction": "", "min_m4q_ess_fraction": "",
                        "source_binder_spread": "", "source_slope_spread": "",
                        "warning_status": "comparison_only",
                    })
                summary_rows.append(base)

        # Long bootstrap campaigns are checkpointed at each completed Z so an
        # outage cannot discard every earlier campaign in the same invocation.
        write_rows(output / "campaign_status.csv", status_rows)
        write_rows(output / "slope_curves.csv", slope_rows)
        write_rows(output / "crossing_exponents.csv", summary_rows)
        write_rows(output / "bootstrap_draws.csv", bootstrap_rows)
        interpretation(output, summary_rows, status_rows)
        print(f"checkpointed Z={campaign.Z:g} in {output}", flush=True)

    write_rows(output / "campaign_status.csv", status_rows)
    write_rows(output / "slope_curves.csv", slope_rows)
    write_rows(output / "crossing_exponents.csv", summary_rows)
    write_rows(output / "bootstrap_draws.csv", bootstrap_rows)
    if summary_rows:
        plot_outputs(output, slope_rows, summary_rows)
    interpretation(output, summary_rows, status_rows)
    print(f"output_dir={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
