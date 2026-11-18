#!/usr/bin/env python3
"""CPU structure-factor census, production preparation, collection, and analysis."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-lp-hmc")

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from structure_factor_analysis import (  # noqa: E402
    bimodality_stable,
    bootstrap_observables,
    canonical_weights_with_fallback,
    census_weights,
    observable_summary,
    RANK_METRICS,
    rank_label,
    read_shell_table,
    shell_summary,
    write_rows,
)

JULIA_112 = Path("/home/vskokov/.julia/juliaup/julia-1.12.6+0.x64.linux.gnu/bin/julia")
DEFAULT_JULIA = str(JULIA_112 if JULIA_112.is_file() else "julia")
DEFAULT_DEPOT = "/tmp/lp_hmc_julia_depot:/home/vskokov/.julia"

CAMPAIGNS = {
    -1.0: "runs/umbrella_binder_Zm1",
    -0.75: "runs/umbrella_binder_Zm0p75",
    -0.5: "runs/umbrella_binder_Zm0p5",
    0.0: "runs/umbrella_binder_Z0",
    0.5: "runs/umbrella_binder_Z0p5",
}
SIZES = (12, 16, 20, 24)


def label(value: float) -> str:
    return str(value).replace("-", "m").replace(".", "p")


def latest_checkpoint(row: dict[str, str]) -> Path | None:
    progress = Path(row.get("progress_marker", ""))
    if progress.is_file():
        try:
            payload = json.loads(progress.read_text(encoding="utf-8"))
            candidate = Path(str(payload.get("checkpoint", "")))
            if candidate.is_file():
                return candidate
        except (json.JSONDecodeError, OSError):
            pass
    candidate = Path(row["checkpoint_path"])
    return candidate if candidate.is_file() else None


def source_rows(
    campaigns: dict[float, str | Path] | None = None,
    sizes: tuple[int, ...] = SIZES,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    selected = CAMPAIGNS if campaigns is None else campaigns
    for Z, relative in selected.items():
        campaign_root = Path(relative)
        if not campaign_root.is_absolute():
            campaign_root = REPO_ROOT / campaign_root
        for L in sizes:
            manifest = campaign_root / f"L{L}" / "manifest.csv"
            if not manifest.is_file():
                continue
            with manifest.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    checkpoint = latest_checkpoint(row)
                    stats = Path(row["stats_path"])
                    if checkpoint is None or not stats.is_file():
                        continue
                    rows.append({
                        **row, "Z": repr(Z), "L": str(L),
                        "source_manifest": str(manifest.resolve()),
                        "source_checkpoint": str(checkpoint.resolve()),
                        "source_stats": str(stats.resolve()),
                    })
    return rows


def _run_census(task: dict[str, str]) -> tuple[int, str]:
    command = [
        task["julia"], f"--project={REPO_ROOT}",
        str(REPO_ROOT / "scripts/census_structure_factor.jl"),
        task["source_checkpoint"], task["census_path"],
    ]
    environment = dict(os.environ)
    environment.update({"JULIA_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
                        "JULIA_NUM_PRECOMPILE_TASKS": "1",
                        "JULIA_DEPOT_PATH": environment.get("JULIA_DEPOT_PATH", DEFAULT_DEPOT)})
    result = subprocess.run(command, cwd=REPO_ROOT, env=environment,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return result.returncode, result.stdout


def census(args: argparse.Namespace) -> int:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    tasks = []
    campaigns = (
        {float(Z): path for Z, path in args.campaign}
        if args.campaign else CAMPAIGNS
    )
    for row in source_rows(campaigns, tuple(args.sizes)):
        path = output / f"Z{label(float(row['Z']))}" / f"L{row['L']}" / f"task_{int(row['task_id']):06d}.csv"
        task = {**row, "census_path": str(path), "julia": args.julia}
        if args.resume and path.is_file():
            tasks.append(task)
            continue
        tasks.append(task)
    if args.max_tasks:
        tasks = tasks[:args.max_tasks]
    pending = [task for task in tasks if not (args.resume and Path(task["census_path"]).is_file())]
    failures = 0
    with ProcessPoolExecutor(max_workers=min(args.workers, max(1, len(pending)))) as pool:
        futures = {pool.submit(_run_census, task): task for task in pending}
        for complete, future in enumerate(as_completed(futures), start=1):
            task = futures[future]
            code, log = future.result()
            if code:
                failures += 1
                print(f"census failed task={task['task_id']} Z={task['Z']} L={task['L']}\n{log}", file=sys.stderr)
            elif complete == 1 or complete % 20 == 0 or complete == len(pending):
                print(f"census {complete}/{len(pending)}", flush=True)
    completed = [task for task in tasks if Path(task["census_path"]).is_file()]
    index_fields = list(completed[0]) if completed else []
    if completed:
        with (output / "census_index.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=index_fields)
            writer.writeheader(); writer.writerows(completed)
    print(f"census_index={output / 'census_index.csv'} failures={failures}")
    return 1 if failures else 0


def longest_dense_core(masses: list[float], max_gap: float = 0.021) -> list[float]:
    ordered = sorted(set(masses))
    runs: list[list[float]] = []
    current: list[float] = []
    for mass in ordered:
        if current and mass - current[-1] > max_gap + 1e-12:
            runs.append(current); current = []
        current.append(mass)
    current and runs.append(current)
    return max(runs, key=lambda run: (len(run), -np.ptp(run))) if runs else []


def _load_index(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def plot_preparation(output: Path, summaries: list[dict[str, object]],
                     frozen: list[dict[str, object]]) -> None:
    if not frozen:
        return
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figures = output / "figures"; figures.mkdir(exist_ok=True)
    fig, axis = plt.subplots(figsize=(6.8, 4.5))
    for L in sorted({int(row["L"]) for row in frozen}):
        series = sorted((row for row in frozen if int(row["L"]) == L),
                        key=lambda row: float(row["Z"]))
        axis.plot([float(row["Z"]) for row in series],
                  [float(row["selected_q"]) for row in series], marker="o", label=f"L={L}")
    z_grid = np.linspace(min(float(row["Z"]) for row in frozen),
                         max(float(row["Z"]) for row in frozen), 200)
    axis.plot(z_grid, np.maximum(0.0, -z_grid / 2.0), "k--", lw=1,
              label=r"mean field $\max(0,-Z/2)$")
    axis.set(xlabel=r"$Z$", ylabel=r"frozen measured $q_*$")
    axis.grid(alpha=0.25); axis.legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(figures / "selected_shell_vs_Z.png", dpi=180); plt.close(fig)

    for frozen_row in frozen:
        Z, L = float(frozen_row["Z"]), int(frozen_row["L"])
        group = [row for row in summaries
                 if math.isclose(float(row["Z"]), Z) and int(row["L"]) == L]
        masses = sorted({float(row["m2"]) for row in group})
        if not masses:
            continue
        fig, axis = plt.subplots(figsize=(6.8, 4.5))
        for mass in (masses[0], masses[-1]):
            q_values = sorted({float(row["q"]) for row in group
                               if math.isclose(float(row["m2"]), mass)})
            spectrum = [np.mean([float(row["S_per_mode"]) for row in group
                                 if math.isclose(float(row["m2"]), mass)
                                 and math.isclose(float(row["q"]), q)]) for q in q_values]
            axis.plot(q_values, spectrum, marker=".", ms=3, label=fr"$m^2={mass:g}$")
        axis.axvline(float(frozen_row["selected_q"]), color="C3", ls="--", lw=1, label=r"frozen $q_*$")
        axis.axvline(max(0.0, -Z / 2.0), color="k", ls=":", lw=1, label="mean field")
        axis.set(xlim=(0, 2.0), xlabel=r"lattice $q(k)$", ylabel=r"$S(q)$ per mode",
                 title=f"Z={Z:g}, L={L}")
        axis.grid(alpha=0.25); axis.legend(frameon=False, fontsize=8)
        fig.tight_layout(); fig.savefig(figures / f"spectrum_Z{label(Z)}_L{L}.png", dpi=180); plt.close(fig)


def _prepare_census_row(payload: tuple[dict[str, str], int]) -> list[dict[str, object]]:
    row, wham_bins = payload
    census_table = read_shell_table(Path(row["census_path"]))
    # The census only freezes a shell; one 500-trajectory/window shard gives a
    # stable pilot WHAM model without rereading every 4,000-sample production file.
    shards = sorted(Path(row["shard_dir"]).glob("statistics_*.csv"))[:1]
    production = read_umbrella_bias_columns_many(shards or [Path(row["source_stats"])])
    used_bins = wham_bins
    last_error: RuntimeError | None = None
    for candidate_bins in dict.fromkeys((wham_bins, 64, 32)):
        try:
            weights = census_weights(census_table, production, bins=candidate_bins)
            used_bins = candidate_bins
            break
        except RuntimeError as error:
            last_error = error
    else:
        if shards:
            production = read_umbrella_bias_columns(Path(row["source_stats"]))
            for candidate_bins in (64, 32):
                try:
                    weights = census_weights(census_table, production, bins=candidate_bins)
                    used_bins = candidate_bins
                    break
                except RuntimeError as error:
                    last_error = error
            else:
                raise RuntimeError(f"pilot WHAM failed for task {row['task_id']}: {last_error}")
        else:
            raise RuntimeError(f"pilot WHAM failed for task {row['task_id']}: {last_error}")
    base = {
        "Z": float(row["Z"]), "L": int(row["L"]), "m2": float(row["m2"]),
        "phase": row["init_phase"], "task_id": int(row["task_id"]),
        "source_checkpoint": row["source_checkpoint"], "source_stats": row["source_stats"],
        "pilot_wham_bins": used_bins,
        "pilot_samples_per_window": int(len(production["M2"]) /
                                         len(np.unique(production["slot"]))),
    }
    return [{**base, **spectrum} for spectrum in shell_summary(census_table, weights)]


def read_umbrella_bias_columns(path: Path) -> dict[str, np.ndarray]:
    """Read only the four columns needed to solve the pilot WHAM model."""
    header_line = -1
    selected_columns: tuple[int, ...] | None = None
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle):
            if not line.startswith("#"):
                columns = tuple(line.rstrip("\r\n").split(","))
                required = ("slot", "umbrella_center", "umbrella_kappa", "M2")
                if not all(name in columns for name in required):
                    raise ValueError(f"{path}: missing umbrella bias columns")
                selected_columns = tuple(columns.index(name) for name in required)
                header_line = line_number
                break
    if header_line < 0:
        raise ValueError(f"{path}: missing umbrella header")
    table = np.loadtxt(path, delimiter=",", skiprows=header_line + 1,
                       usecols=selected_columns, dtype=float)
    table = np.atleast_2d(table)
    if table.shape[0] == 0 or not np.all(np.isfinite(table)):
        raise ValueError(f"{path}: empty or non-finite umbrella data")
    zeros = np.zeros(table.shape[0], dtype=float)
    return {"slot": table[:, 0], "umbrella_center": table[:, 1],
            "umbrella_kappa": table[:, 2], "M2": table[:, 3],
            "M4": zeros, "Q": zeros}


def read_umbrella_bias_columns_many(paths: list[Path]) -> dict[str, np.ndarray]:
    parts = [read_umbrella_bias_columns(path) for path in paths]
    return {name: np.concatenate([part[name] for part in parts]) for name in parts[0]}


def prepare(args: argparse.Namespace) -> int:
    rows = _load_index(args.index.resolve())
    summaries: list[dict[str, object]] = []
    by_group: dict[tuple[float, int], list[dict[str, object]]] = defaultdict(list)
    with ProcessPoolExecutor(max_workers=min(args.workers, max(1, len(rows)))) as pool:
        futures = [pool.submit(_prepare_census_row, (row, args.wham_bins)) for row in rows]
        for number, future in enumerate(as_completed(futures), start=1):
            records = future.result()
            for record in records:
                summaries.append(record)
                by_group[(float(record["Z"]), int(record["L"]))].append(record)
            if number == 1 or number % 20 == 0 or number == len(rows):
                print(f"prepared census weights {number}/{len(rows)}", flush=True)
    summaries.sort(key=lambda item: (float(item["Z"]), int(item["L"]),
                                      float(item["m2"]), str(item["phase"]), float(item["q"])))

    frozen: list[dict[str, object]] = []
    selected_tasks: list[dict[str, str]] = []
    for (Z, L), group in sorted(by_group.items()):
        core = longest_dense_core([float(item["m2"]) for item in group])
        if len(core) < 3:
            continue
        qvalues = sorted({float(item["q"]) for item in group
                          if float(item["q"]) <= args.q_cut + 1e-12})
        baseline_mass = max(core)
        ordered_masses = set(sorted(core)[:2])
        scores = []
        for q in qvalues:
            baseline = [float(item["S_per_mode"]) for item in group
                        if math.isclose(float(item["m2"]), baseline_mass) and math.isclose(float(item["q"]), q)]
            ordered = [float(item["S_per_mode"]) for item in group
                       if float(item["m2"]) in ordered_masses and math.isclose(float(item["q"]), q)]
            if baseline and ordered and np.mean(baseline) > 0:
                ordered_mean = float(np.mean(ordered))
                growth = ordered_mean / float(np.mean(baseline))
                # Freeze the measured dominant shell.  Growth is recorded as a
                # diagnostic but is not allowed to promote a tiny UV fluctuation.
                scores.append((ordered_mean, growth, -q, q))
        if not scores:
            continue
        _, score, _, selected_q = max(scores)
        mass_power = []
        for mass in core:
            values = [float(item["mean_power"]) for item in group
                      if math.isclose(float(item["m2"]), mass) and math.isclose(float(item["q"]), selected_q)]
            mass_power.append((mass, float(np.mean(values))))
        x = np.asarray([item[0] for item in mass_power])
        y = np.asarray([item[1] for item in mass_power])
        center = float(x[int(np.argmax(np.abs(np.gradient(y, x))))])
        chosen_masses = sorted(core, key=lambda value: abs(value - center))[:3]
        chosen_masses.sort()
        candidates = sorted(qvalues)
        interior = selected_q > 1e-12 and selected_q not in (candidates[0], candidates[-1])
        frozen.append({
            "Z": Z, "L": L, "selected_q": selected_q,
            "mean_field_q": max(0.0, -Z / 2.0), "growth_score": score,
            "interior_peak_candidate": interior, "dense_mass_min": min(core),
            "dense_mass_max": max(core), "center_mass": center,
            "production_masses": ";".join(repr(value) for value in chosen_masses),
        })
        for row in rows:
            if (math.isclose(float(row["Z"]), Z) and int(row["L"]) == L and
                    any(math.isclose(float(row["m2"]), mass) for mass in chosen_masses)):
                root = args.production_root.resolve()
                task_id = len(selected_tasks)
                task_dir = root / f"Z{label(Z)}" / f"L{L}" / f"task_{task_id:06d}"
                selected_tasks.append({
                    **row, "structure_task_id": str(task_id), "selected_q": repr(selected_q),
                    "q_cut": repr(args.q_cut), "source_checkpoint": row["source_checkpoint"],
                    "task_dir": str(task_dir), "progress_path": str(task_dir / "progress.json"),
                    "merged_path": str(task_dir / "statistics.csv"),
                })

    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    write_rows(output / "census_summary.csv", summaries)
    write_rows(output / "frozen_shells.csv", frozen)
    write_rows(output / "production_manifest.csv", selected_tasks)
    plot_preparation(output, summaries, frozen)
    print(f"frozen_shells={output / 'frozen_shells.csv'} tasks={len(selected_tasks)}")
    return 0


def _common_arguments(row: dict[str, str], seed: int) -> list[str]:
    return [
        row["L"], f"--Z={row['Z']}", f"--mass={row['m2']}", f"--eps={row['eps']}",
        f"--n_lf={row['n_lf']}", f"--rng={seed}", "--cpu",
        f"--umbrella-replicas={row['umbrella_replicas']}",
        f"--umbrella-min={row['umbrella_min']}", f"--umbrella-max={row['umbrella_max']}",
        f"--umbrella-kappa={row['umbrella_kappa']}", f"--umbrella-power={row['umbrella_power']}",
        f"--swap-every={row['swap_every']}", f"--init-phase={row['init_phase']}",
    ]


def merge_shards(task_dir: Path, destination: Path) -> None:
    shards = sorted((task_dir / "shards").glob("statistics_*.csv"))
    if not shards:
        return
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    expected_header: str | None = None
    with temporary.open("w", encoding="utf-8") as output:
        wrote_header = False
        for shard in shards:
            with shard.open(encoding="utf-8") as source:
                for line in source:
                    if line.startswith("#"):
                        if not wrote_header:
                            output.write(line)
                        continue
                    if not wrote_header:
                        output.write(line); wrote_header = True; expected_header = line
                    elif line.startswith("trajectory,"):
                        if line != expected_header:
                            temporary.unlink(missing_ok=True)
                            raise ValueError(
                                f"{task_dir}: shard schemas differ; start a fresh rank-production directory"
                            )
                    else:
                        output.write(line)
    os.replace(temporary, destination)


def _run_production_task(payload: tuple[dict[str, str], str, int, int]) -> tuple[int, str]:
    row, julia, target_samples, shard_samples = payload
    task_dir = Path(row["task_dir"]); shards = task_dir / "shards"
    task_dir.mkdir(parents=True, exist_ok=True); shards.mkdir(exist_ok=True)
    progress_path = Path(row["progress_path"])
    if progress_path.is_file():
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
    else:
        progress = {"samples": 0, "checkpoint": row["source_checkpoint"], "shards": []}
    environment = dict(os.environ)
    environment.update({
        "JULIA_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "FFTW_NUM_THREADS": "1",
        "JULIA_NUM_PRECOMPILE_TASKS": "1",
        "JULIA_DEPOT_PATH": environment.get("JULIA_DEPOT_PATH", DEFAULT_DEPOT),
        "STRUCTURE_SELECTED_Q": row["selected_q"], "STRUCTURE_Q_CUT": row["q_cut"],
    })
    logs = []
    while int(progress["samples"]) < target_samples:
        index = len(progress["shards"])
        count = min(shard_samples, target_samples - int(progress["samples"]))
        environment["STRUCTURE_EXPECTED_COLLECTED"] = str(progress["samples"])
        statistics = shards / f"statistics_{index:06d}.csv"
        diagnostics = shards / f"diagnostics_{index:06d}.csv"
        checkpoint = shards / f"checkpoint_{(index + 1) % 2}.jld2"
        seed = int(row["seed"]) + 104729 * (index + 1)
        command = [
            julia, f"--project={REPO_ROOT}", str(REPO_ROOT / "scripts/collect_structure_factor_shard.jl"),
            *_common_arguments(row, seed), f"--init={progress['checkpoint']}",
            f"--samples={count}", f"--skip={row['skip']}", f"--block-index={index}",
            f"--output={statistics}", f"--diagnostics={diagnostics}",
            f"--collection-checkpoint={checkpoint}",
        ]
        result = subprocess.run(command, cwd=REPO_ROOT, env=environment,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        logs.append(result.stdout)
        if result.returncode:
            return result.returncode, "".join(logs)
        progress["samples"] = int(progress["samples"]) + count
        progress["checkpoint"] = str(checkpoint)
        progress["shards"].append(str(statistics))
        temporary = progress_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(progress, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, progress_path)
    merge_shards(task_dir, Path(row["merged_path"]))
    return 0, "".join(logs)


def run(args: argparse.Namespace) -> int:
    rows = _load_index(args.manifest.resolve())
    allowed = None
    if args.only_flagged:
        flagged = _load_index(args.only_flagged.resolve())
        allowed = {int(row["structure_task_id"]) for row in flagged if row.get("extend", "").lower() == "true"}
    tasks = [row for row in rows if allowed is None or int(row["structure_task_id"]) in allowed]
    failures = 0
    payloads = [(row, args.julia, args.target_samples, args.shard_samples) for row in tasks]
    with ProcessPoolExecutor(max_workers=min(args.workers, max(1, len(tasks)))) as pool:
        futures = {pool.submit(_run_production_task, payload): payload[0] for payload in payloads}
        for complete, future in enumerate(as_completed(futures), start=1):
            row = futures[future]; code, log = future.result()
            if code:
                failures += 1
                print(f"production failed task={row['structure_task_id']}\n{log}", file=sys.stderr)
            elif complete == 1 or complete % 10 == 0 or complete == len(tasks):
                print(f"production {complete}/{len(tasks)}", flush=True)
    return 1 if failures else 0


def plot_analysis(output: Path, combined: list[dict[str, object]],
                  reweight_rows: list[dict[str, object]]) -> None:
    """Write compact diagnostic figures; CSV files remain the source of truth."""
    if not combined:
        return
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figures = output / "figures"; figures.mkdir(exist_ok=True)
    for Z in sorted({float(row["Z"]) for row in combined}):
        subset = [row for row in combined if math.isclose(float(row["Z"]), Z)]
        fig, axes = plt.subplots(2, 2, figsize=(9.0, 6.8), sharex=True)
        specifications = (("S_per_mode", r"$S(q_*)$ per mode"),
                          ("susceptibility", r"$\chi_{q_*}$"),
                          ("binder", r"$U_{q_*}$"),
                          ("orientation_participation", "orientation participation"))
        for L in sorted({int(row["L"]) for row in subset}):
            series = sorted((row for row in subset if int(row["L"]) == L),
                            key=lambda row: float(row["m2"]))
            for axis, (metric, ylabel) in zip(axes.flat, specifications):
                x = [float(row["m2"]) for row in series]
                y = [float(row[metric]) for row in series]
                error = [float(row.get(metric + "_mcse", math.nan)) for row in series]
                axis.errorbar(x, y, yerr=error, marker="o", ms=3, capsize=2, label=f"L={L}")
                axis.set_ylabel(ylabel); axis.grid(alpha=0.25)
        for axis in axes[-1]:
            axis.set_xlabel(r"$m^2$")
        axes[0, 0].legend(frameon=False, fontsize=8)
        fig.suptitle(f"Finite-wavevector diagnostics, Z={Z:g}")
        fig.tight_layout()
        fig.savefig(figures / f"finite_q_Z{label(Z)}.png", dpi=180)
        plt.close(fig)

    valid = [row for row in reweight_rows if float(row["ess_fraction"]) >= 0.05]
    if valid:
        fig, axis = plt.subplots(figsize=(6.5, 4.5))
        axis.scatter([float(row["m2_target"]) for row in valid],
                     [float(row["Z_target"]) for row in valid],
                     c=[float(row["ess_fraction"]) for row in valid], s=10, cmap="viridis")
        axis.set(xlabel=r"target $m^2$", ylabel=r"target $Z$",
                 title="Locally supported two-parameter reweighting")
        fig.tight_layout(); fig.savefig(figures / "reweight_overlap.png", dpi=180); plt.close(fig)

    ranked = [row for row in combined
              if math.isfinite(float(row.get("rank_effective_dimension", math.nan)))]
    if ranked:
        fig, axis = plt.subplots(figsize=(7.0, 5.0))
        labels = sorted({str(row.get("rank_label", "not_measured")) for row in ranked})
        markers = {"rank1": "o", "rank2": "s", "rank3": "^",
                   "mixed/undetermined": "X", "unmodulated": "x", "not_measured": "."}
        for classification in labels:
            subset = [row for row in ranked if str(row.get("rank_label")) == classification]
            points = axis.scatter(
                [float(row["m2"]) for row in subset], [float(row["Z"]) for row in subset],
                c=[float(row["rank_effective_dimension"]) for row in subset],
                vmin=1.0, vmax=3.0, cmap="viridis", marker=markers.get(classification, "o"),
                s=55, edgecolors="black", linewidths=0.4, label=classification,
            )
        axis.set(xlabel=r"$m^2$", ylabel=r"$Z$", title="Modulation spatial rank")
        axis.grid(alpha=0.2); axis.legend(frameon=False, fontsize=8)
        fig.colorbar(points, ax=axis, label=r"$d_{\rm eff}$")
        fig.tight_layout(); fig.savefig(figures / "modulation_dimension_map.png", dpi=190); plt.close(fig)

        for L in sorted({int(row["L"]) for row in ranked}):
            subset = [row for row in ranked if int(row["L"]) == L]
            fig, axis = plt.subplots(figsize=(6.8, 4.6))
            for eigenvalue, color in zip(("rank_lambda1", "rank_lambda2", "rank_lambda3"),
                                         ("C0", "C1", "C2")):
                axis.scatter([float(row["rank_effective_dimension"]) for row in subset],
                             [float(row[eigenvalue]) for row in subset], s=24,
                             color=color, label=eigenvalue.replace("rank_", ""))
            axis.axhline(0.15, color="k", ls=":", lw=1, label="rank threshold")
            axis.set(xlabel=r"$d_{\rm eff}$", ylabel="tensor eigenvalue",
                     title=f"Orientation-tensor spectrum, L={L}")
            axis.grid(alpha=0.2); axis.legend(frameon=False, fontsize=8)
            fig.tight_layout(); fig.savefig(figures / f"rank_eigenvalues_L{L}.png", dpi=190); plt.close(fig)


def adaptive_rank_refinements(combined: list[dict[str, object]],
                              min_delta_z: float = 0.0625,
                              min_delta_m2: float = 0.05) -> list[dict[str, object]]:
    """Suggest midpoint anchors where morphology changes or is unresolved."""
    ranked = [row for row in combined if "rank_effective_dimension" in row]
    suggestions: list[dict[str, object]] = []
    seen: set[tuple[int, float, float]] = set()

    def inspect_pair(left: dict[str, object], right: dict[str, object], direction: str) -> None:
        dz = abs(float(right["Z"]) - float(left["Z"]))
        dm = abs(float(right["m2"]) - float(left["m2"]))
        labels = {str(left.get("rank_label")), str(right.get("rank_label"))}
        uncertain = "mixed/undetermined" in labels or "not_measured" in labels
        changed = len(labels) > 1 or abs(float(right["rank_effective_dimension"]) -
                                         float(left["rank_effective_dimension"])) > 0.25
        resolvable = (direction == "Z" and dz > min_delta_z + 1e-12) or (
            direction == "m2" and dm > min_delta_m2 + 1e-12)
        if not (resolvable and (uncertain or changed)):
            return
        key = (int(left["L"]), round((float(left["Z"]) + float(right["Z"])) / 2, 12),
               round((float(left["m2"]) + float(right["m2"])) / 2, 12))
        if key in seen:
            return
        seen.add(key)
        suggestions.append({
            "L": key[0], "Z_target": key[1], "m2_target": key[2], "direction": direction,
            "left_label": left.get("rank_label"), "right_label": right.get("rank_label"),
            "left_deff": left["rank_effective_dimension"],
            "right_deff": right["rank_effective_dimension"],
            "reason": "uncertain" if uncertain else "rank_or_deff_change",
        })

    for L in sorted({int(row["L"]) for row in ranked}):
        volume = [row for row in ranked if int(row["L"]) == L]
        for Z in sorted({float(row["Z"]) for row in volume}):
            series = sorted((row for row in volume if math.isclose(float(row["Z"]), Z)),
                            key=lambda row: float(row["m2"]))
            for left, right in zip(series, series[1:]):
                inspect_pair(left, right, "m2")
        z_values = sorted({float(row["Z"]) for row in volume})
        for z0, z1 in zip(z_values, z_values[1:]):
            lefts = [row for row in volume if math.isclose(float(row["Z"]), z0)]
            rights = [row for row in volume if math.isclose(float(row["Z"]), z1)]
            if lefts and rights:
                pair = min(((left, right) for left in lefts for right in rights),
                           key=lambda item: abs(float(item[0]["m2"]) - float(item[1]["m2"])))
                inspect_pair(*pair, "Z")
    return suggestions


def _analyze_completed_task(payload: tuple[dict[str, str], dict[str, object]]) -> tuple[dict[str, object], list[dict[str, object]]]:
    row, settings = payload
    table = read_shell_table(Path(row["merged_path"]))
    wham_bins = int(settings["wham_bins"])
    weights = canonical_weights_with_fallback(table, bins=wham_bins)
    summary = observable_summary(table, weights)
    uncertainty = bootstrap_observables(
        table, draws=int(settings["bootstrap"]), block_length=int(settings["block_length"]),
        bins=wham_bins, seed=1729 + int(row["structure_task_id"]),
    )
    samples_collected = len(np.unique(table.arrays["trajectory"]))
    task_row = {
        "structure_task_id": int(row["structure_task_id"]), "Z": float(row["Z"]),
        "L": int(row["L"]), "m2": float(row["m2"]), "phase": row["init_phase"],
        "selected_q": float(row["selected_q"]), "samples_collected": samples_collected,
        **summary, **uncertainty,
    }
    if all(metric in summary for metric in RANK_METRICS):
        task_row["rank_label"] = rank_label(task_row)

    reweighted: list[dict[str, object]] = []
    q_values = table.arrays["Q"]
    g_values = table.arrays["G"]
    temperature = float(table.metadata.get("temperature", "1"))
    log_base = np.log(np.maximum(weights, np.finfo(float).tiny))
    for delta_m2 in np.linspace(-float(settings["mass_reweight_width"]),
                                float(settings["mass_reweight_width"]), 9):
        for delta_Z in np.linspace(-float(settings["z_reweight_width"]),
                                   float(settings["z_reweight_width"]), 9):
            logw = log_base - 0.5 * (delta_m2 * q_values + delta_Z * g_values) / temperature
            logw -= np.max(logw)
            local = np.exp(logw); local /= local.sum()
            ess = 1.0 / float(np.dot(local, local))
            local_summary = observable_summary(table, local)
            amp_test = bimodality_stable(np.sqrt(np.maximum(table.arrays["P_selected"], 0.0)), local)
            target_energy = (table.arrays["H"] + 0.5 * delta_m2 * q_values
                             + 0.5 * delta_Z * g_values) / int(row["L"]) ** 3
            energy_test = bimodality_stable(target_energy, local)
            reweighted.append({
                "structure_task_id": int(row["structure_task_id"]), "Z_source": float(row["Z"]),
                "L": int(row["L"]), "m2_source": float(row["m2"]),
                "Z_target": float(row["Z"]) + float(delta_Z),
                "m2_target": float(row["m2"]) + float(delta_m2),
                "ess": ess, "ess_fraction": ess / len(local),
                "S_per_mode": local_summary["S_per_mode"],
                "susceptibility": local_summary["susceptibility"],
                "binder": local_summary["binder"],
                "mean_energy_density": float(np.dot(local, target_energy)),
                "orientation_max_fraction": local_summary["orientation_max_fraction"],
                "orientation_participation": local_summary["orientation_participation"],
                "amplitude_bimodal": bool(amp_test.get("resolved", False)),
                "amplitude_bimodal_stable": bool(amp_test.get("stable", False)),
                "amplitude_low_weight": amp_test.get("low_weight", math.nan),
                "amplitude_barrier": amp_test.get("barrier", math.nan),
                "energy_bimodal": bool(energy_test.get("resolved", False)),
                "energy_bimodal_stable": bool(energy_test.get("stable", False)),
                "energy_low_weight": energy_test.get("low_weight", math.nan),
                "energy_barrier": energy_test.get("barrier", math.nan),
            })
    return task_row, reweighted


def analyze(args: argparse.Namespace) -> int:
    rows = [row for row in _load_index(args.manifest.resolve())
            if Path(row["merged_path"]).is_file()]
    task_rows: list[dict[str, object]] = []
    reweight_rows: list[dict[str, object]] = []
    settings = {
        "wham_bins": args.wham_bins, "bootstrap": args.bootstrap,
        "block_length": args.block_length,
        "mass_reweight_width": args.mass_reweight_width,
        "z_reweight_width": args.z_reweight_width,
    }
    with ProcessPoolExecutor(max_workers=min(args.workers, max(1, len(rows)))) as pool:
        futures = [pool.submit(_analyze_completed_task, (row, settings)) for row in rows]
        for number, future in enumerate(as_completed(futures), start=1):
            task_row, local_reweight = future.result()
            task_rows.append(task_row); reweight_rows.extend(local_reweight)
            if number == 1 or number % 10 == 0 or number == len(rows):
                print(f"analyzed {number}/{len(rows)}", flush=True)
    task_rows.sort(key=lambda item: int(item["structure_task_id"]))
    reweight_rows.sort(key=lambda item: (int(item["structure_task_id"]),
                                         float(item["m2_target"]), float(item["Z_target"])))
    combined: list[dict[str, object]] = []
    grouped: dict[tuple[float, int, float], list[dict[str, object]]] = defaultdict(list)
    for row in task_rows:
        grouped[(float(row["Z"]), int(row["L"]), float(row["m2"]))].append(row)
    base_metrics = ["S_per_mode", "susceptibility", "binder", "mean_energy_density",
                    "orientation_max_fraction", "orientation_participation"]
    for (Z, L, mass), group in sorted(grouped.items()):
        record: dict[str, object] = {"Z": Z, "L": L, "m2": mass,
                                     "selected_q": float(group[0]["selected_q"]),
                                     "phase_sources": len(group)}
        metrics = list(base_metrics)
        if all(all(metric in item for metric in RANK_METRICS) for item in group):
            metrics.extend(RANK_METRICS)
        for metric in metrics:
            values = [float(item[metric]) for item in group]
            record[metric] = float(np.mean(values))
            record[metric + "_source_spread"] = float(np.ptp(values))
            errors = [float(item.get(metric + "_mcse", math.nan)) for item in group]
            finite_errors = [value for value in errors if math.isfinite(value)]
            record[metric + "_mcse"] = (float(math.sqrt(sum(value * value for value in finite_errors)) /
                                                    max(1, len(finite_errors)))
                                                if finite_errors else math.nan)
        record["min_ess_fraction"] = min(float(item["ess_fraction"]) for item in group)
        if all("modulation_support" in item for item in group):
            record["modulation_support"] = float(np.mean(
                [float(item["modulation_support"]) for item in group]))
            for rank in (1, 2, 3):
                record[f"rank{rank}_probability"] = float(np.mean(
                    [float(item[f"rank{rank}_probability"]) for item in group]))
            record["rank_label"] = rank_label(record)
        combined.append(record)
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    write_rows(output / "task_observables.csv", task_rows)
    write_rows(output / "combined_observables.csv", combined)
    write_rows(output / "reweight_grid.csv", reweight_rows)
    write_rows(output / "rank_refinement_suggestions.csv",
               adaptive_rank_refinements(combined))

    precision: list[dict[str, object]] = []
    group_lookup = {(float(row["Z"]), int(row["L"]), float(row["m2"])): row for row in combined}
    for row in task_rows:
        failed = []
        if float(row["ess_fraction"]) < args.min_ess_fraction:
            failed.append("low_ess")
        if float(row.get("S_per_mode_mcse", math.inf)) > args.s_rel_mcse * max(abs(float(row["S_per_mode"])), 1e-15):
            failed.append("S_mcse")
        if float(row.get("susceptibility_mcse", math.inf)) > args.chi_rel_mcse * max(abs(float(row["susceptibility"])), 1e-15):
            failed.append("chi_mcse")
        if float(row.get("binder_mcse", math.inf)) > args.binder_mcse:
            failed.append("binder_mcse")
        aggregate = group_lookup[(float(row["Z"]), int(row["L"]), float(row["m2"]))]
        source_scale = 2.0 * math.sqrt(2.0) * max(float(row.get("S_per_mode_mcse", math.inf)), 1e-15)
        if float(aggregate["S_per_mode_source_spread"]) > source_scale:
            failed.append("source_disagreement")
        samples = int(row["samples_collected"])
        precision.append({
            "structure_task_id": row["structure_task_id"], "Z": row["Z"], "L": row["L"],
            "m2": row["m2"], "samples_collected": samples,
            "extend": bool(failed and samples < args.max_samples),
            "target_samples": min(args.max_samples, samples + args.sample_increment),
            "precision_pass": not failed, "reasons": ";".join(failed),
        })
    write_rows(output / "precision_status.csv", precision)

    refinement = []
    for task_id in sorted({int(row["structure_task_id"]) for row in reweight_rows}):
        unsupported = [row for row in reweight_rows
                       if int(row["structure_task_id"]) == task_id
                       and float(row["ess_fraction"]) < args.min_ess_fraction]
        if unsupported:
            nearest = min(unsupported, key=lambda row:
                          (float(row["m2_target"]) - float(row["m2_source"])) ** 2
                          + (float(row["Z_target"]) - float(row["Z_source"])) ** 2)
            refinement.append({
                "structure_task_id": task_id, "Z_source": nearest["Z_source"],
                "L": nearest["L"], "m2_source": nearest["m2_source"],
                "m2_target": nearest["m2_target"], "Z_target": nearest["Z_target"],
                "ess_fraction": nearest["ess_fraction"],
                "reason": "local_reweighting_low_ess",
                "suggestion": "new simulation point if this direction is needed",
            })
    write_rows(output / "refinement_suggestions.csv", refinement)
    equal_weight = []
    for task_id in sorted({int(row["structure_task_id"]) for row in reweight_rows}):
        candidates = [row for row in reweight_rows
                      if int(row["structure_task_id"]) == task_id
                      and bool(row["amplitude_bimodal_stable"])
                      and float(row["ess_fraction"]) >= args.min_ess_fraction]
        if candidates:
            best = min(candidates, key=lambda row: abs(float(row["amplitude_low_weight"]) - 0.5))
            equal_weight.append(best)
    write_rows(output / "equal_weight_candidates.csv", equal_weight)
    plot_analysis(output, combined, reweight_rows)
    print(f"analysis={output} completed_tasks={len(task_rows)}")
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    census_parser = sub.add_parser("census")
    census_parser.add_argument("--output", type=Path, default=REPO_ROOT / "reports/structure_factor_cpu/census")
    census_parser.add_argument("--workers", type=int, default=32)
    census_parser.add_argument("--julia", default=DEFAULT_JULIA)
    census_parser.add_argument("--resume", action="store_true")
    census_parser.add_argument("--max-tasks", type=int, default=0)
    census_parser.add_argument(
        "--campaign", nargs=2, action="append", metavar=("Z", "RUN_DIR"),
        help="repeat to replace the default campaign registry",
    )
    census_parser.add_argument("--sizes", type=int, nargs="+", default=list(SIZES))
    census_parser.set_defaults(function=census)

    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--index", type=Path, default=REPO_ROOT / "reports/structure_factor_cpu/census/census_index.csv")
    prepare_parser.add_argument("--output", type=Path, default=REPO_ROOT / "reports/structure_factor_cpu/preparation")
    prepare_parser.add_argument("--production-root", type=Path, default=REPO_ROOT / "runs/structure_factor_cpu")
    prepare_parser.add_argument("--q-cut", type=float, default=2.0)
    prepare_parser.add_argument("--wham-bins", type=int, default=128)
    prepare_parser.add_argument("--workers", type=int, default=32)
    prepare_parser.set_defaults(function=prepare)

    run_parser = sub.add_parser("run")
    run_parser.add_argument("--manifest", type=Path, default=REPO_ROOT / "reports/structure_factor_cpu/preparation/production_manifest.csv")
    run_parser.add_argument("--workers", type=int, default=32)
    run_parser.add_argument("--julia", default=DEFAULT_JULIA)
    run_parser.add_argument("--target-samples", type=int, default=200)
    run_parser.add_argument("--shard-samples", type=int, default=20,
                            help="atomic restart unit within each 200-sample analysis stage")
    run_parser.add_argument("--only-flagged", type=Path)
    run_parser.set_defaults(function=run)

    analyze_parser = sub.add_parser("analyze")
    analyze_parser.add_argument("--manifest", type=Path, default=REPO_ROOT / "reports/structure_factor_cpu/preparation/production_manifest.csv")
    analyze_parser.add_argument("--output", type=Path, default=REPO_ROOT / "reports/structure_factor_cpu/analysis")
    analyze_parser.add_argument("--wham-bins", type=int, default=128)
    analyze_parser.add_argument("--workers", type=int, default=32)
    analyze_parser.add_argument("--bootstrap", type=int, default=200)
    analyze_parser.add_argument("--block-length", type=int, default=5)
    analyze_parser.add_argument("--mass-reweight-width", type=float, default=0.03)
    analyze_parser.add_argument("--z-reweight-width", type=float, default=0.05)
    analyze_parser.add_argument("--min-ess-fraction", type=float, default=0.05)
    analyze_parser.add_argument("--s-rel-mcse", type=float, default=0.05)
    analyze_parser.add_argument("--chi-rel-mcse", type=float, default=0.10)
    analyze_parser.add_argument("--binder-mcse", type=float, default=0.02)
    analyze_parser.add_argument("--sample-increment", type=int, default=200)
    analyze_parser.add_argument("--max-samples", type=int, default=1000)
    analyze_parser.set_defaults(function=analyze)
    return root


def main() -> int:
    args = parser().parse_args()
    if hasattr(args, "workers") and args.workers < 1:
        raise SystemExit("workers must be positive")
    return args.function(args)


if __name__ == "__main__":
    raise SystemExit(main())
