#!/usr/bin/env python3
"""Summarize phase mixing and block stability for replica-exchange runs."""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path

import numpy as np


def resolve_run_file(manifest: Path, raw_path: str, directory: str) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = manifest.parent / path
    if path.is_file():
        return path
    relocated = manifest.parent / directory / path.name
    if relocated.is_file():
        return relocated
    raise FileNotFoundError(path)


def read_statistics(path: Path) -> dict[str, np.ndarray]:
    metadata: dict[str, str] = {}
    data_lines: list[str] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("#"):
                key, separator, value = line[1:].strip().partition("=")
                if separator:
                    metadata[key] = value
            elif line.strip():
                data_lines.append(line)
    if not data_lines:
        raise ValueError(f"{path}: contains no statistics table")
    reader = csv.DictReader(data_lines)
    required = {"trajectory", "M", "M2", "M4"}
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise ValueError(f"{path}: missing required columns {sorted(required)}")
    rows = list(reader)
    if not rows:
        raise ValueError(f"{path}: contains no samples")
    result: dict[str, np.ndarray] = {
        key: np.asarray([float(row[key]) for row in rows], dtype=float)
        for key in required
    }
    result["metadata"] = metadata  # type: ignore[assignment]
    return result


def read_final_diagnostics(path: Path) -> tuple[dict[str, float], list[str], list[str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        last = None
        for last in reader:
            pass
    if last is None:
        raise ValueError(f"{path}: contains no diagnostic rows")
    final = {key: float(value) for key, value in last.items() if key and value != ""}
    hmc_columns = sorted(key for key in final if key.startswith("hmc_acceptance_slot_"))
    swap_columns = sorted(key for key in final if key.startswith("swap_acceptance_"))
    return final, hmc_columns, swap_columns


def binder(m2: np.ndarray, m4: np.ndarray) -> float:
    mean_m2 = float(np.mean(m2))
    return 1.0 - float(np.mean(m4)) / (3.0 * mean_m2**2)


def transition_count(ordered: np.ndarray) -> int:
    return int(np.count_nonzero(ordered[1:] != ordered[:-1])) if len(ordered) > 1 else 0


def integrated_autocorrelation_time(values: np.ndarray) -> float:
    """Initial-positive-sequence estimate, in retained samples."""
    centered = np.asarray(values, dtype=float) - float(np.mean(values))
    count = len(centered)
    if count < 2:
        return math.nan
    variance = float(np.dot(centered, centered) / count)
    if variance <= 0 or not math.isfinite(variance):
        return math.nan
    tau = 1.0
    for lag in range(1, min(count, count // 2 + 1)):
        rho = float(np.dot(centered[:-lag], centered[lag:]) / ((count - lag) * variance))
        if rho <= 0:
            break
        tau += 2.0 * rho
    return tau


def analyze_task(
    manifest: Path, row: dict[str, str], block_size: int,
    threshold_override: float | None,
) -> tuple[list[dict[str, object]], dict[str, object], dict[str, np.ndarray]]:
    stats_path = resolve_run_file(manifest, row["stats_path"], "statistics")
    diagnostics_path = resolve_run_file(manifest, row["diagnostics_path"], "diagnostics")
    stats = read_statistics(stats_path)
    final, hmc_columns, swap_columns = read_final_diagnostics(diagnostics_path)
    metadata = stats["metadata"]  # type: ignore[assignment]
    threshold = (
        threshold_override if threshold_override is not None
        else float(row.get("phase_threshold") or metadata.get("phase_threshold", "0.25"))
    )
    magnetization = stats["M"]
    ordered = np.abs(magnetization) >= threshold
    trajectories = stats["trajectory"]
    min_swap = min((final[column] for column in swap_columns), default=math.nan)
    mean_hmc = float(np.mean([final[column] for column in hmc_columns]))
    round_trips = final.get("round_trips_total", math.nan)
    last_trajectory = float(trajectories[-1])
    swap_every = int(row.get("swap_every") or metadata.get("swap_every", "1"))
    exchange_rounds = final.get(
        "exchange_rounds", math.floor(last_trajectory / swap_every)
    )
    round_trip_rate = (
        1000.0 * round_trips / exchange_rounds if exchange_rounds > 0 else math.nan
    )
    walker_rt_columns = sorted(key for key in final if key.startswith("round_trips_walker_"))
    walkers_with_round_trip = final.get(
        "walkers_with_round_trip",
        sum(final[column] > 0 for column in walker_rt_columns) if walker_rt_columns else math.nan,
    )
    replica_count = int(row.get("tempering_replicas") or len(hmc_columns))
    round_trip_walker_fraction = (
        walkers_with_round_trip / replica_count if replica_count > 1 else math.nan
    )
    orphan_tmp_files = sum(
        1 for output_path in (stats_path, diagnostics_path)
        for _ in output_path.parent.glob(output_path.name + ".tmp.*")
    )
    init_phase = row.get("init_phase") or metadata.get("init_phase", "hot")

    blocks: list[dict[str, object]] = []
    for block_index, start in enumerate(range(0, len(magnetization), block_size)):
        stop = min(start + block_size, len(magnetization))
        block_ordered = ordered[start:stop]
        blocks.append({
            "task_id": int(row["task_id"]),
            "point_index": int(row["point_index"]),
            "replica": int(row["replica"]),
            "L": int(row["L"]),
            "Z": float(row["Z"]),
            "m2": float(row["m2"]),
            "init_phase": init_phase,
            "phase_threshold": threshold,
            "block_index": block_index,
            "sample_start": start + 1,
            "sample_end": stop,
            "sample_count": stop - start,
            "U4": binder(stats["M2"][start:stop], stats["M4"][start:stop]),
            "mean_abs_M": float(np.mean(np.abs(magnetization[start:stop]))),
            "max_abs_M": float(np.max(np.abs(magnetization[start:stop]))),
            "ordered_fraction": float(np.mean(block_ordered)),
            "phase_transitions": transition_count(block_ordered),
            "mean_hmc_acceptance": mean_hmc,
            "min_swap_acceptance": min_swap,
            "round_trips_total": round_trips,
            "exchange_rounds": exchange_rounds,
            "round_trips_per_1000_exchange_rounds": round_trip_rate,
            "round_trip_walker_fraction": round_trip_walker_fraction,
        })

    summary: dict[str, object] = {
        "task_id": int(row["task_id"]), "point_index": int(row["point_index"]),
        "replica": int(row["replica"]), "L": int(row["L"]),
        "Z": float(row["Z"]), "m2": float(row["m2"]),
        "init_phase": init_phase, "samples": len(magnetization),
        "U4": binder(stats["M2"], stats["M4"]),
        "ordered_fraction": float(np.mean(ordered)),
        "phase_transitions": transition_count(ordered),
        "mean_hmc_acceptance": mean_hmc, "min_swap_acceptance": min_swap,
        "round_trips_total": round_trips, "exchange_rounds": exchange_rounds,
        "round_trips_per_1000_exchange_rounds": round_trip_rate,
        "round_trip_walker_fraction": round_trip_walker_fraction,
        "walkers_visited_low": final.get("walkers_visited_low", math.nan),
        "walkers_visited_high": final.get("walkers_visited_high", math.nan),
        "tau_int_M": integrated_autocorrelation_time(magnetization),
        "tau_int_M2": integrated_autocorrelation_time(stats["M2"]),
        "orphan_tmp_files": orphan_tmp_files,
    }
    return blocks, summary, stats


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def print_report(
    summaries: list[dict[str, object]], stats_by_task: dict[int, dict[str, np.ndarray]],
    min_swap_threshold: float,
) -> None:
    print("task point phase        samples       U4 occupancy transitions min_swap rt/1k")
    for item in summaries:
        print(
            f"{item['task_id']:4d} {item['point_index']:5d} "
            f"{str(item['init_phase']):11s} {item['samples']:7d} "
            f"{item['U4']:8.3f} {item['ordered_fraction']:9.3f} "
            f"{item['phase_transitions']:11d} {item['min_swap_acceptance']:8.3f} "
            f"{item['round_trips_per_1000_exchange_rounds']:5.1f}"
        )

    grouped: dict[tuple[int, float, float, str], list[dict[str, object]]] = defaultdict(list)
    for item in summaries:
        grouped[(int(item["L"]), float(item["Z"]), float(item["m2"]), str(item["init_phase"]))].append(item)
    print("\nphase-group comparison (moments pooled across chains)")
    print("L Z m2 phase chains pooled_U4 occupancy transitions")
    for key, items in sorted(grouped.items()):
        arrays = [stats_by_task[int(item["task_id"])] for item in items]
        all_m2 = np.concatenate([array["M2"] for array in arrays])
        all_m4 = np.concatenate([array["M4"] for array in arrays])
        occupancy = float(np.mean([float(item["ordered_fraction"]) for item in items]))
        transitions = sum(int(item["phase_transitions"]) for item in items)
        print(
            f"{key[0]} {key[1]:g} {key[2]:g} {key[3]:11s} {len(items):6d} "
            f"{binder(all_m2, all_m4):9.3f} {occupancy:9.3f} {transitions:11d}"
        )

    bottlenecks = [item for item in summaries if float(item["min_swap_acceptance"]) < min_swap_threshold]
    stuck = [item for item in summaries if int(item["phase_transitions"]) == 0]
    print(f"\nflags: swap_bottlenecks={len(bottlenecks)} zero_phase_transition_chains={len(stuck)}")
    if bottlenecks:
        print("  low-swap task ids:", ", ".join(str(item["task_id"]) for item in bottlenecks))
    if stuck:
        print("  zero-transition task ids:", ", ".join(str(item["task_id"]) for item in stuck))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--block-size", type=int, default=5000)
    parser.add_argument("--phase-threshold", type=float)
    parser.add_argument("--min-swap", type=float, default=0.2)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summary-output", type=Path)
    args = parser.parse_args()
    if args.block_size < 2:
        parser.error("--block-size must be at least 2")
    if args.phase_threshold is not None and (
        args.phase_threshold <= 0 or not math.isfinite(args.phase_threshold)
    ):
        parser.error("--phase-threshold must be finite and positive")
    if not 0 <= args.min_swap <= 1:
        parser.error("--min-swap must be between 0 and 1")

    manifest = args.manifest.resolve()
    with manifest.open(newline="", encoding="utf-8") as handle:
        manifest_rows = list(csv.DictReader(handle))
    if not manifest_rows:
        parser.error("manifest contains no tasks")

    block_rows: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    stats_by_task: dict[int, dict[str, np.ndarray]] = {}
    for row in manifest_rows:
        blocks, summary, stats = analyze_task(
            manifest, row, args.block_size, args.phase_threshold
        )
        block_rows.extend(blocks)
        summaries.append(summary)
        stats_by_task[int(row["task_id"])] = stats

    output = args.output or manifest.parent / "phase_blocks.csv"
    summary_output = args.summary_output or manifest.parent / "tempering_summary.csv"
    write_rows(output, block_rows)
    write_rows(summary_output, summaries)
    print_report(summaries, stats_by_task, args.min_swap)
    print(f"\nwrote {output}\nwrote {summary_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
