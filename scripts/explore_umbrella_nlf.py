#!/usr/bin/env python3
"""Compare umbrella walker transport across HMC leapfrog counts.

The source checkpoints are loaded read-only. By default, GPU probes are queued
serially through task-spooler and a final queued task builds combined/ranked CSVs.
Use `--scheduler=local` to run the same sweep synchronously.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shlex
import shutil
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from runtime_preflight import run as run_preflight


REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT = REPO_ROOT / "scripts/audit_umbrella_transport.jl"
LOCAL_JULIA = Path(
    "/home/vskokov/.julia/juliaup/julia-1.12.6+0.x64.linux.gnu/bin/julia"
)


def comma_ints(text: str) -> list[int]:
    try:
        values = [int(value.strip()) for value in text.split(",")]
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected comma-separated integers") from error
    if not values or any(value < 1 for value in values) or len(values) != len(set(values)):
        raise argparse.ArgumentTypeError("values must be unique positive integers")
    return values


def comma_floats(text: str) -> list[float]:
    try:
        values = [float(value.strip()) for value in text.split(",")]
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected comma-separated numbers") from error
    if not values or any(not math.isfinite(value) or value <= 0 for value in values):
        raise argparse.ArgumentTypeError("trajectory lengths must be finite and positive")
    return values


def local_checkpoint(run_dir: Path, manifest_value: str) -> Path:
    supplied = Path(manifest_value)
    candidate = run_dir / "checkpoints" / supplied.name
    if candidate.is_file():
        return candidate.resolve()
    if supplied.is_file():
        return supplied.resolve()
    raise FileNotFoundError(f"checkpoint not found locally: {supplied.name}")


def probe_command(args, row: dict[str, str], checkpoint: Path, output: Path,
                  n_lf: int) -> list[str]:
    command = [
        "env",
        f"UMBRELLA_CHECKPOINT={checkpoint}",
        f"UMBRELLA_PROBE_SWEEPS={args.probe_sweeps}",
        f"UMBRELLA_PROBE_LAGS={','.join(map(str, args.lags))}",
        args.julia,
        "--startup-file=no",
        f"--project={REPO_ROOT}",
        str(AUDIT),
        row["L"],
        f"--mass={row['m2']}",
        f"--Z={row['Z']}",
        f"--eps={row['eps']}",
        f"--n_lf={n_lf}",
        f"--rng={row['seed']}",
        f"--umbrella-replicas={row['umbrella_replicas']}",
        f"--umbrella-min={row['umbrella_min']}",
        f"--umbrella-max={row['umbrella_max']}",
        f"--umbrella-kappa={row['umbrella_kappa']}",
        f"--umbrella-power={row['umbrella_power']}",
        f"--swap-every={row['swap_every']}",
        f"--diagnostics={output}",
    ]
    args.fp64 and command.append("--fp64")
    args.cpu and command.append("--cpu")
    return command


def read_single_row(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 1:
        raise ValueError(f"expected one result row in {path}, found {len(rows)}")
    return rows[0]


def geometric_mean(values: list[float]) -> float:
    if any(value <= 0 for value in values):
        return 0.0
    return math.exp(sum(math.log(value) for value in values) / len(values))


def summarize(manifest: Path, minimum_acceptance: float,
              maximum_acceptance: float) -> int:
    with manifest.open(newline="", encoding="utf-8") as handle:
        tasks = list(csv.DictReader(handle))
    if not tasks:
        raise ValueError(f"empty sweep manifest: {manifest}")

    rows: list[dict[str, str]] = []
    missing: list[Path] = []
    for task in tasks:
        output = Path(task["output"])
        if not output.is_file():
            missing.append(output)
            continue
        row = read_single_row(output)
        row["source_task_id"] = task["source_task_id"]
        row["source_replica"] = task["source_replica"]
        rows.append(row)
    rows.sort(key=lambda row: (int(row["n_lf"]), row["init_phase"], row["checkpoint"]))
    output_dir = manifest.parent
    combined = output_dir / "results.csv"
    if rows:
        fields = list(rows[0])
        with combined.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    expected_checkpoints = len({task["checkpoint"] for task in tasks})
    grouped: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[int(row["n_lf"])].append(row)
    rankings: list[dict[str, object]] = []
    for n_lf, group in grouped.items():
        acceptances = [float(row["hmc_acceptance"]) for row in group]
        per_lf = [float(row["diffusion_per_lf_step"]) for row in group]
        per_second = [float(row["diffusion_per_second"]) for row in group]
        edge_swaps = [float(row.get("minimum_edge_swap_acceptance", 1.0)) for row in group]
        complete = len(group) == expected_checkpoints
        in_band = (
            complete and all(value > 0 for value in per_lf) and
            all(minimum_acceptance <= value <= maximum_acceptance
                for value in acceptances) and min(edge_swaps) >= 0.25
        )
        rankings.append({
            "n_lf": n_lf,
            "trajectory_length": statistics.mean(
                float(row["trajectory_length"]) for row in group
            ),
            "completed_checkpoints": len(group),
            "expected_checkpoints": expected_checkpoints,
            "minimum_hmc_acceptance": min(acceptances),
            "maximum_hmc_acceptance": max(acceptances),
            "minimum_edge_swap_acceptance": min(edge_swaps),
            "minimum_diffusion_per_lf_step": min(per_lf),
            "geomean_diffusion_per_lf_step": geometric_mean(per_lf),
            "minimum_diffusion_per_second": min(per_second),
            "geomean_diffusion_per_second": geometric_mean(per_second),
            "eligible": in_band,
        })
    rankings.sort(key=lambda row: (
        not bool(row["eligible"]), -float(row["minimum_diffusion_per_second"]),
        -float(row["minimum_diffusion_per_lf_step"])
    ))
    for rank, row in enumerate(rankings, 1):
        row["rank"] = rank if row["eligible"] else ""
    recommendations = output_dir / "recommendations.csv"
    if rankings:
        fields = ["rank", *[field for field in rankings[0] if field != "rank"]]
        with recommendations.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rankings)

    print(f"completed_results={len(rows)}/{len(tasks)}")
    print(f"results={combined}")
    print(f"recommendations={recommendations}")
    if missing:
        print(f"missing_results={len(missing)}")
    eligible = [row for row in rankings if row["eligible"]]
    if eligible:
        best = eligible[0]
        print(
            "recommended_n_lf=" + str(best["n_lf"]) +
            " criterion=maximize worst-phase diffusion per second then per leapfrog step"
        )
        return 0 if not missing else 2
    print("recommended_n_lf=none reason=incomplete_or_acceptance_out_of_band")
    return 2


def write_sweep_manifest(path: Path, tasks: list[dict[str, object]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(tasks[0]))
        writer.writeheader()
        for task in tasks:
            row = dict(task)
            for key in ("checkpoint", "output"):
                if key in row:
                    row[key] = str(row[key])
            writer.writerows([row])
    temporary.replace(path)


def read_sweep_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def run_single_probe(args, manifest: Path, probe_id: int) -> int:
    tasks = read_sweep_manifest(manifest)
    if probe_id < 0 or probe_id >= len(tasks):
        raise SystemExit(f"probe_id out of range: {probe_id}")
    task = tasks[probe_id]
    output = Path(task["output"])
    if output.is_file() and not args.force:
        print(f"probe {probe_id} already complete: {output}")
        return 0
    source_manifest = args.run_dir / "manifest.csv"
    with source_manifest.open(newline="", encoding="utf-8") as handle:
        source_rows = {row["task_id"]: row for row in csv.DictReader(handle)}
    source = source_rows[task["source_task_id"]]
    checkpoint = Path(task["checkpoint"])
    command = probe_command(args, source, checkpoint, output, int(task["n_lf"]))
    print("+", shlex.join(command))
    subprocess.run(command, cwd=REPO_ROOT, check=True)
    return 0


def lsf_probe_script(args, manifest: Path, count: int, logs: Path,
                     run_name: str) -> str:
    runner = Path(__file__).resolve()
    base = [
        shlex.quote(sys.executable),
        shlex.quote(str(runner)),
        f"--run-probe-id=$PROBE_ID",
        f"--sweep-manifest={shlex.quote(str(manifest.resolve()))}",
        f"--run-dir={shlex.quote(str(args.run_dir.resolve()))}",
        f"--julia={shlex.quote(args.julia)}",
    ]
    if args.fp64:
        base.append("--fp64")
    if args.cpu:
        base.append("--cpu")
    if args.force:
        base.append("--force")
    command = " ".join(base)
    lines = [
        "#!/usr/bin/env bash",
        f'#BSUB -J "{run_name}[1-{count}]"',
        f"#BSUB -q {args.queue}",
        f"#BSUB -W {args.walltime}",
        f"#BSUB -n {args.cpus}",
        f'#BSUB -gpu "{args.gpu_request}"',
        f"#BSUB -o {logs.resolve()}/%J_%I.out",
        f"#BSUB -e {logs.resolve()}/%J_%I.err",
        "",
        "set -euo pipefail",
        "export PYTHONUNBUFFERED=1",
        'PROBE_ID="$((LSB_JOBINDEX - 1))"',
        command,
        "",
    ]
    return "\n".join(lines)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    result.add_argument("--run-dir", type=Path, default=REPO_ROOT / "runs/umbrella_L24_w161")
    result.add_argument("--n-lfs", type=comma_ints,
                        help="explicit candidates; otherwise derive them from trajectory lengths")
    result.add_argument("--trajectory-lengths", type=comma_floats,
                        default=comma_floats("0.25,0.5,0.75,1,1.25,1.5,2"))
    result.add_argument("--probe-sweeps", type=int, default=5000)
    result.add_argument("--lags", type=comma_ints, default=comma_ints("1,10,100,500,1000"))
    result.add_argument("--scheduler", choices=("tsp", "local", "lsf"), default="tsp")
    result.add_argument("--slots", type=int, default=1,
                        help="TSP concurrency; use 1 for one GPU")
    result.add_argument("--prepare-only", action="store_true",
                        help="write sweep manifest and LSF script without submitting")
    result.add_argument("--queue", default="short_gpu")
    result.add_argument("--walltime", default="120")
    result.add_argument("--cpus", type=int, default=1)
    result.add_argument("--gpu-request", default="num=1:mode=shared:mps=no")
    result.add_argument("--run-probe-id", type=int, help=argparse.SUPPRESS)
    result.add_argument("--sweep-manifest", type=Path, help=argparse.SUPPRESS)
    result.add_argument("--output-dir", type=Path)
    result.add_argument("--julia")
    result.add_argument("--tsp", default="tsp")
    result.add_argument("--fp64", action="store_true")
    result.add_argument("--cpu", action="store_true")
    result.add_argument("--force", action="store_true",
                        help="rerun probes whose result CSV already exists")
    result.add_argument("--dry-run", action="store_true")
    result.add_argument("--minimum-acceptance", type=float, default=0.65)
    result.add_argument("--maximum-acceptance", type=float, default=0.90)
    result.add_argument("--summarize-manifest", type=Path, help=argparse.SUPPRESS)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.summarize_manifest:
        return summarize(args.summarize_manifest.resolve(), args.minimum_acceptance,
                         args.maximum_acceptance)
    if args.run_probe_id is not None:
        if args.sweep_manifest is None:
            raise SystemExit("--run-probe-id requires --sweep-manifest")
        args.sweep_manifest = args.sweep_manifest.resolve()
        args.run_dir = args.run_dir.resolve()
        if args.julia is None:
            args.julia = str(LOCAL_JULIA) if LOCAL_JULIA.is_file() else "julia"
        return run_single_probe(args, args.sweep_manifest, args.run_probe_id)
    if args.probe_sweeps < 1 or args.slots < 1:
        raise SystemExit("--probe-sweeps and --slots must be positive")
    if args.scheduler == "tsp" and args.slots != 1:
        raise SystemExit("use --slots=1 so the summary task waits for every one-GPU probe")
    if args.scheduler == "lsf" and args.slots != 1:
        raise SystemExit("LSF nlf probes use one GPU per array task; keep --slots=1")
    if max(args.lags) > args.probe_sweeps:
        raise SystemExit("all --lags must be no larger than --probe-sweeps")
    if not 0 <= args.minimum_acceptance < args.maximum_acceptance <= 1:
        raise SystemExit("invalid acceptance band")
    args.run_dir = args.run_dir.resolve()
    source_manifest = args.run_dir / "manifest.csv"
    if not source_manifest.is_file():
        raise SystemExit(f"missing source manifest: {source_manifest}")
    args.output_dir = (args.output_dir or
                       REPO_ROOT / "reports" / f"nlf_sweep_{args.run_dir.name}").resolve()
    if args.julia is None:
        args.julia = str(LOCAL_JULIA) if LOCAL_JULIA.is_file() else "julia"

    with source_manifest.open(newline="", encoding="utf-8") as handle:
        source_rows = list(csv.DictReader(handle))
    required = {
        "task_id", "L", "Z", "m2", "replica", "seed", "eps",
        "umbrella_replicas", "umbrella_min", "umbrella_max", "umbrella_kappa",
        "umbrella_power", "swap_every", "init_phase", "checkpoint_path",
    }
    if not source_rows or not required.issubset(source_rows[0]):
        raise SystemExit("source manifest is empty or lacks umbrella fields")
    if args.n_lfs is None:
        epsilons = {float(row["eps"]) for row in source_rows}
        if len(epsilons) != 1:
            raise SystemExit("trajectory-derived n_lf candidates require one epsilon")
        epsilon = epsilons.pop()
        args.n_lfs = sorted({max(1, round(length / epsilon))
                             for length in args.trajectory_lengths})

    tasks: list[dict[str, object]] = []
    commands: list[list[str]] = []
    for source in source_rows:
        try:
            checkpoint = local_checkpoint(args.run_dir, source["checkpoint_path"])
        except FileNotFoundError as error:
            raise SystemExit(str(error)) from error
        phase = source["init_phase"].replace("/", "_")
        for n_lf in args.n_lfs:
            output = args.output_dir / "raw" / (
                f"task_{int(source['task_id']):04d}_{phase}_nlf{n_lf:03d}.csv"
            )
            tasks.append({
                "probe_id": len(tasks), "source_task_id": source["task_id"],
                "source_replica": source["replica"], "init_phase": source["init_phase"],
                "checkpoint": checkpoint, "n_lf": n_lf,
                "probe_sweeps": args.probe_sweeps, "output": output,
            })
            if args.force or not output.is_file():
                commands.append(probe_command(args, source, checkpoint, output, n_lf))

    sweep_manifest = args.output_dir / "sweep_manifest.csv"
    summary_command = [
        sys.executable, str(Path(__file__).resolve()),
        f"--summarize-manifest={sweep_manifest}",
        f"--minimum-acceptance={args.minimum_acceptance}",
        f"--maximum-acceptance={args.maximum_acceptance}",
    ]
    print(f"source_manifest: {source_manifest}")
    print(f"sweep_manifest: {sweep_manifest}")
    print(f"tasks: {len(tasks)} ({len(commands)} pending)")
    print(f"n_lf candidates: {','.join(map(str, args.n_lfs))}")
    print(f"probe sweeps: {args.probe_sweeps}; lags: {','.join(map(str, args.lags))}")
    for command in commands:
        prefix = [args.tsp] if args.scheduler == "tsp" else []
        print("+", shlex.join([*prefix, *command]))
    if args.scheduler == "tsp":
        print("+", shlex.join(([args.tsp] if args.scheduler == "tsp" else []) + summary_command))
    if args.dry_run:
        print("dry-run: no files were written and no tasks were enqueued")
        return 0

    if args.scheduler == "tsp" and shutil.which(args.tsp) is None:
        raise SystemExit(f"task-spooler executable not found: {args.tsp}")
    try:
        run_preflight(args.julia, REPO_ROOT)
    except RuntimeError as error:
        raise SystemExit(str(error)) from error
    (args.output_dir / "raw").mkdir(parents=True, exist_ok=True)
    write_sweep_manifest(sweep_manifest, tasks)
    if args.scheduler == "local":
        for command in commands:
            subprocess.run(command, cwd=REPO_ROOT, check=True)
        return summarize(sweep_manifest, args.minimum_acceptance,
                         args.maximum_acceptance)

    if args.scheduler == "lsf":
        run_name = f"nlf_{args.run_dir.name}"
        logs = args.output_dir / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        script = lsf_probe_script(args, sweep_manifest, len(tasks), logs, run_name)
        script_path = args.output_dir / "lsf_job.sh"
        script_path.write_text(script, encoding="utf-8")
        submission = {
            "run_name": run_name, "queue": args.queue, "walltime": args.walltime,
            "cpus": args.cpus, "gpu_request": args.gpu_request, "task_count": len(tasks),
            "pending_probes": len(commands),
        }
        (args.output_dir / "submission.json").write_text(
            json.dumps(submission, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(script)
        print(f"lsf_script: {script_path}")
        if args.prepare_only:
            return 0
        subprocess.run(["bsub"], input=script, text=True, check=True)
        print(f"enqueued {len(tasks)} nlf probe array tasks")
        return 0

    subprocess.run([args.tsp, "-S", str(args.slots)], check=True)
    for command in commands:
        subprocess.run([args.tsp, *command], cwd=REPO_ROOT, check=True)
    subprocess.run([args.tsp, *summary_command], cwd=REPO_ROOT, check=True)
    print(f"enqueued {len(commands)} probes plus one summary task; inspect with `{args.tsp}`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
