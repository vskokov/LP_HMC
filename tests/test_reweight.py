import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reweight_binder import (  # noqa: E402
    RunData,
    analyze,
    binder_from_weights,
    bootstrap_mbar_errors,
    evaluate_group,
    group_sources,
    normalize_logweights,
    read_stats,
    select_source,
)


def run_data(*, order=0, L=8, Z=1.0, m2=-2.0, seed=1,
             M2=None, Q=None, G=None):
    M2 = np.asarray(M2 if M2 is not None else [1.0, 4.0, 9.0, 16.0])
    return RunData(
        path=Path(f"run-{seed}.csv"), L=L, Z=Z, m2=m2, seed=seed,
        epsilon=0.1, n_lf=10, order=order, M2=M2, M4=M2**2,
        Q=np.asarray(Q if Q is not None else np.arange(len(M2)), dtype=float),
        G=np.asarray(G if G is not None else np.arange(len(M2)), dtype=float),
    )


class ReweightTests(unittest.TestCase):
    def test_binder_crossing_script_interpolates_all_crossings(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "binder.csv"
            output_path = Path(directory) / "crossings.csv"
            input_path.write_text(
                "t,Z,m2,L,U4,uncertainty\n"
                "0.0,-0.6,-1.8,8,0.2,0.01\n"
                "0.5,-0.7,-2.0,8,0.6,0.01\n"
                "1.0,-0.8,-2.2,8,0.3,0.01\n"
                "0.0,-0.6,-1.8,12,0.465,0.01\n"
                "1.0,-0.8,-2.2,12,0.5,0.01\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/find_binder_crossings.py"),
                 str(input_path), "--output", str(output_path)],
                text=True, capture_output=True, check=True,
            )
            rows = list(csv.DictReader(result.stdout.splitlines()))
            self.assertEqual(len(rows), 5)
            one_third = [row for row in rows if row["level"].startswith("0.333")]
            self.assertEqual(len(one_third), 2)
            self.assertAlmostEqual(float(one_third[0]["t"]), 1.0 / 6.0)
            levels_0465 = [row for row in rows if float(row["level"]) == 0.465]
            self.assertEqual(len(levels_0465), 3)
            exact = next(row for row in levels_0465 if row["L"] == "12")
            self.assertEqual(exact["kind"], "exact")
            self.assertEqual(output_path.read_text(), result.stdout)

    def test_parallel_mbar_bootstrap_matches_serial(self):
        rng = np.random.default_rng(22)
        runs = []
        for order, (Z, m2) in enumerate(((0.0, -2.2), (0.2, -2.0))):
            values = rng.normal(size=32)
            runs.append(run_data(
                order=order, Z=Z, m2=m2, seed=order + 1,
                M2=0.5 + values**2,
                Q=2.0 + values**2,
                G=3.0 + (values - 0.2 * order)**2,
            ))
        groups = group_sources(runs)[8]
        block_sizes = {(group.L, group.Z, group.m2): 4 for group in groups}
        targets = [(0.05, -2.15), (0.15, -2.05)]
        serial = bootstrap_mbar_errors(
            groups, targets, block_sizes, 4, np.random.default_rng(123),
            tolerance=1e-10, max_iterations=10_000, jobs=1,
        )
        parallel = bootstrap_mbar_errors(
            groups, targets, block_sizes, 4, np.random.default_rng(123),
            tolerance=1e-10, max_iterations=10_000, jobs=2,
        )
        np.testing.assert_allclose(parallel, serial, rtol=0.0, atol=0.0)

    def test_stable_extreme_weights_and_collapsed_ess(self):
        weights = normalize_logweights(np.array([1000.0, -1000.0]))
        np.testing.assert_allclose(weights, [1.0, 0.0])
        run = run_data(M2=[1.0, 2.0], Q=[0.0, 2000.0], G=[0.0, 0.0])
        group = group_sources([run])[8][0]
        _, ess, max_weight, _ = evaluate_group(group, 1.0, -1.0)
        self.assertAlmostEqual(ess, 1.0)
        self.assertAlmostEqual(max_weight, 1.0)
        rows = analyze([run], (1.0, -1.0), (1.0, -1.0), 2, 4, "1", 50, 0.01, 9)
        self.assertTrue(all(row["warning_status"] == "low_ess" for row in rows))

    def test_exact_source_is_uniform_and_direct_binder(self):
        first = run_data(seed=1, M2=[1.0, 4.0])
        second = run_data(seed=2, order=1, M2=[9.0, 16.0])
        group = group_sources([first, second])[8][0]
        binder, ess, max_weight, weights = evaluate_group(group, 1.0, -2.0)
        all_m2 = np.concatenate([first.M2, second.M2])
        expected = 1.0 - np.mean(all_m2**2) / (3.0 * np.mean(all_m2) ** 2)
        np.testing.assert_allclose(weights, np.full(4, 0.25))
        self.assertAlmostEqual(binder, expected)
        self.assertAlmostEqual(ess, 4.0)
        self.assertAlmostEqual(max_weight, 0.25)

    def test_nearest_source_ties_and_line_endpoints(self):
        left = run_data(order=0, Z=0.0, seed=1, M2=[1.0] * 4)
        right_short = run_data(order=1, Z=2.0, seed=2, M2=[2.0] * 4)
        right_long = run_data(order=2, Z=2.0, seed=3, M2=[2.0] * 4)
        groups = group_sources([left, right_short, right_long])[8]
        self.assertEqual(select_source(groups, 1.0, -2.0).Z, 2.0)
        rows1 = analyze([left, right_short, right_long], (0.0, -2.0), (2.0, -2.0),
                        3, 8, "1", 0, 0, 123)
        rows2 = analyze([left, right_short, right_long], (0.0, -2.0), (2.0, -2.0),
                        3, 8, "1", 0, 0, 123)
        self.assertEqual([row["t"] for row in rows1], [0.0, 0.5, 1.0])
        self.assertEqual(rows1, rows2)

    def test_zero_binder_denominator(self):
        with self.assertRaisesRegex(ValueError, "numerically zero"):
            binder_from_weights(np.zeros(2), np.zeros(2), np.full(2, 0.5))

    def test_malformed_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            path.write_text("# L=8\ntrajectory,M,M2,M4,Q,G,acceptance_rate\n1,0,0,0,0,0,1\n")
            with self.assertRaisesRegex(ValueError, "missing metadata"):
                read_stats(path)

    def test_replica_exchange_statistics_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tempered.csv"
            path.write_text(
                "# schema_version=2\n# sampler=replica_exchange\n# L=8\n# Z=1\n"
                "# m2=-2.25\n# epsilon=0.02\n# n_lf=15\n# seed=7\n# lambda=4\n"
                "# temperature=1\n# float_type=Float64\n# device=cuda\n# samples=1\n"
                "# skip=12\n# warmup=0\n# tempering_replicas=5\n# mass_span=0.4\n"
                "# swap_every=1\n# masses=-2.45;-2.35;-2.25;-2.15;-2.05\n"
                "trajectory,M,M2,M4,Q,G,acceptance_rate\n12,1,1,1,2,3,0.75\n"
            )
            run = read_stats(path)
            self.assertEqual(run.sampler, "replica_exchange")
            self.assertEqual(run.tempering_replicas, 5)
            self.assertEqual(run.mass_span, 0.4)
            self.assertEqual(run.swap_every, 1)

    def test_slurm_dry_run_manifest_mapping_and_space_paths(self):
        with tempfile.TemporaryDirectory(prefix="reweight test ") as directory:
            run_root = Path(directory) / "runs with spaces"
            points_csv = Path(directory) / "points.csv"
            points_csv.write_text("Z,m2\n0.5,-1.5\n")
            command = [
                sys.executable, str(ROOT / "scripts/submit_reweight_array.py"),
                "--L", "8", "--point=1.000,-2.00", "--points-csv", str(points_csv),
                "--eps", "0.1", "--n-lf", "5", "--samples", "4",
                "--replicas", "2", "--run-root", str(run_root),
                "--run-name", "unit", "--dry-run", "--resume",
            ]
            result = subprocess.run(command, check=True, text=True, capture_output=True)
            manifest = run_root / "unit" / "manifest.csv"
            with manifest.open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([row["task_id"] for row in rows], ["0", "1", "2", "3"])
            self.assertEqual([row["replica"] for row in rows], ["0", "1", "0", "1"])
            self.assertEqual(rows[0]["Z"], "1")
            self.assertTrue(all(int(row["seed"]) != 0 for row in rows))
            self.assertIn("set -euo pipefail", (run_root / "unit" / "array_job.sh").read_text())
            self.assertIn("dry-run: sbatch was not invoked", result.stdout)
            self.assertIn("runs with spaces/unit/manifest.csv'", result.stdout)

    def test_replica_exchange_manifest_and_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "runs"
            command = [
                sys.executable, str(ROOT / "scripts/submit_reweight_array.py"),
                "--L", "6", "--point=1,-2.25", "--eps", "0.02", "--n-lf", "4",
                "--samples", "3", "--tempering-replicas", "5", "--mass-span", "0.4",
                "--swap-every", "1", "--run-root", str(run_root), "--run-name", "tempered",
                "--dry-run",
            ]
            result = subprocess.run(command, check=True, text=True, capture_output=True)
            with (run_root / "tempered" / "manifest.csv").open(newline="") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["tempering_replicas"], "5")
            self.assertEqual(row["mass_span"], "0.4")
            self.assertEqual(row["init_phase"], "hot")
            self.assertEqual(row["phase_threshold"], "0.25")
            self.assertIn("diagnostics/task_000000.csv", row["diagnostics_path"])
            self.assertIn("thermalize_replicas.jl", result.stdout)
            self.assertIn("collect_reweight_stats_replicas.jl", result.stdout)
            self.assertIn("--tempering-replicas=5", result.stdout)
            self.assertIn("--init-phase=hot", result.stdout)
            self.assertIn("--phase-threshold=0.25", result.stdout)

    def test_split_phase_initialization_schedule(self):
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "runs"
            command = [
                sys.executable, str(ROOT / "scripts/submit_reweight_array.py"),
                "--L", "6", "--point=1,-2.25", "--eps", "0.02", "--n-lf", "4",
                "--samples", "3", "--replicas", "4", "--tempering-replicas", "5",
                "--mass-span", "0.4", "--init-schedule", "split",
                "--phase-threshold", "0.3", "--run-root", str(run_root),
                "--run-name", "split", "--dry-run",
            ]
            subprocess.run(command, check=True, text=True, capture_output=True)
            with (run_root / "split" / "manifest.csv").open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(
                [row["init_phase"] for row in rows],
                ["disordered", "disordered", "ordered", "ordered"],
            )
            self.assertTrue(all(row["phase_threshold"] == "0.3" for row in rows))

    def test_split_phase_schedule_requires_even_independent_jobs(self):
        command = [
            sys.executable, str(ROOT / "scripts/submit_reweight_array.py"),
            "--L", "6", "--point=1,-2.25", "--eps", "0.02", "--n-lf", "4",
            "--replicas", "3", "--tempering-replicas", "5", "--mass-span", "0.4",
            "--init-schedule", "split", "--dry-run",
        ]
        result = subprocess.run(command, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires an even --replicas count", result.stderr)

    def test_phase_schedule_requires_replica_exchange(self):
        command = [
            sys.executable, str(ROOT / "scripts/submit_reweight_array.py"),
            "--L", "6", "--point=1,-2.25", "--eps", "0.02", "--n-lf", "4",
            "--replicas", "4", "--init-schedule", "split", "--dry-run",
        ]
        result = subprocess.run(command, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires replica exchange", result.stderr)

    def test_tsp_dry_run_and_safe_local_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "runs"
            command = [
                sys.executable, str(ROOT / "scripts/submit_reweight_tsp.py"),
                "--L", "6", "--point=-1.05,-2.75", "--eps", "0.05",
                "--n-lf", "8", "--samples", "10", "--replicas", "4",
                "--tempering-replicas", "5", "--mass-span", "0.2",
                "--init-schedule", "split", "--run-root", str(run_root),
                "--run-name", "local-test", "--dry-run",
            ]
            result = subprocess.run(command, check=True, text=True, capture_output=True)
            manifest = run_root / "local-test" / "manifest.csv"
            self.assertFalse(manifest.exists())
            self.assertIn("--launcher none", result.stdout)
            self.assertIn("no tasks were enqueued", result.stdout)

            submit_command = [item for item in command if item != "--dry-run"]
            submit_command.extend(["--tsp", "/bin/true"])
            subprocess.run(submit_command, check=True, text=True, capture_output=True)
            with manifest.open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 4)
            self.assertEqual(
                [row["init_phase"] for row in rows],
                ["disordered", "disordered", "ordered", "ordered"],
            )
            repeated = subprocess.run(submit_command, text=True, capture_output=True)
            self.assertNotEqual(repeated.returncode, 0)
            self.assertIn("already exists", repeated.stderr)

    def test_submitters_use_measured_hmc_defaults_when_omitted(self):
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "runs"
            array_command = [
                sys.executable, str(ROOT / "scripts/submit_reweight_array.py"),
                "--L", "24", "--point=-0.6,-1.85764", "--samples", "3",
                "--run-root", str(run_root), "--run-name", "array-default",
                "--dry-run",
            ]
            result = subprocess.run(
                array_command, check=True, text=True, capture_output=True
            )
            with (run_root / "array-default" / "manifest.csv").open(newline="") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["eps"], "0.02318953874")
            self.assertEqual(row["n_lf"], "4")
            self.assertIn("measured L default", result.stdout)

            tsp_command = [
                sys.executable, str(ROOT / "scripts/submit_reweight_tsp.py"),
                "--L", "8", "--point=-0.6,-1.85764", "--samples", "3",
                "--run-root", str(run_root), "--run-name", "tsp-default",
                "--dry-run",
            ]
            result = subprocess.run(
                tsp_command, check=True, text=True, capture_output=True
            )
            self.assertIn("HMC: eps=0.05286071721 n_lf=16", result.stdout)

    def test_explicit_hmc_parameters_override_measured_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "runs"
            command = [
                sys.executable, str(ROOT / "scripts/submit_reweight_array.py"),
                "--L", "24", "--point=-0.6,-1.85764", "--eps", "0.01",
                "--n-lf", "9", "--samples", "3", "--run-root", str(run_root),
                "--run-name", "explicit", "--dry-run",
            ]
            result = subprocess.run(command, check=True, text=True, capture_output=True)
            with (run_root / "explicit" / "manifest.csv").open(newline="") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["eps"], "0.01")
            self.assertEqual(row["n_lf"], "9")
            self.assertIn("(command line)", result.stdout)

    def test_untuned_lattice_requires_explicit_hmc_parameters(self):
        command = [
            sys.executable, str(ROOT / "scripts/submit_reweight_array.py"),
            "--L", "10", "--point=-0.6,-1.85764", "--dry-run",
        ]
        result = subprocess.run(command, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no tuned HMC defaults for L=10", result.stderr)

    def test_lsf_array_uses_private_julia_and_excludes_bad_hosts(self):
        with tempfile.TemporaryDirectory(prefix="lsf reweight ") as directory:
            run_root = Path(directory) / "runs with spaces"
            command = [
                sys.executable, str(ROOT / "scripts/submit_reweight_bsub.py"),
                "--L", "24", "--point=-0.6,-1.85764", "--samples", "3",
                "--replicas", "4", "--tempering-replicas", "17",
                "--mass-span", "0.6", "--init-schedule", "split",
                "--max-concurrent", "2", "--run-root", str(run_root),
                "--run-name", "lsf-test", "--dry-run",
            ]
            result = subprocess.run(command, check=True, text=True, capture_output=True)
            run_dir = run_root / "lsf-test"
            script = (run_dir / "lsf_array_job.sh").read_text()
            with (run_dir / "manifest.csv").open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 4)
            self.assertEqual(rows[0]["eps"], "0.02318953874")
            self.assertEqual(rows[0]["n_lf"], "4")
            self.assertIn('#BSUB -J "lsf-test[1-4]%2"', script)
            self.assertIn('#BSUB -q short_gpu', script)
            self.assertIn("hname!='gpu16' && hname!='gpu33'", script)
            self.assertIn("module load cuda/12.3", script)
            self.assertNotIn("module load julia", script)
            self.assertIn(
                "export PATH=/rsstu/users/v/vskokov/gluon/juliaup/bin:", script
            )
            self.assertIn(
                "export JULIA_DEPOT_PATH=/rsstu/users/v/vskokov/gluon/jd", script
            )
            self.assertIn(
                "export JULIAUP_DEPOT_PATH=/rsstu/users/v/vskokov/gluon/.julia", script
            )
            self.assertIn('echo "julia=$(command -v julia)"', script)
            self.assertIn("julia --version", script)
            self.assertIn('echo "checking CUDA runtime and device"', script)
            self.assertIn("CUDA.functional(true)", script)
            self.assertIn("CUDA.versioninfo()", script)
            self.assertIn('TASK_ID="$((LSB_JOBINDEX - 1))"', script)
            self.assertIn('--task-id "${TASK_ID}"', script)
            self.assertIn("dry-run: bsub was not invoked", result.stdout)

    def test_cuda_runtime_is_pinned_before_lsf_precompilation(self):
        preference = (ROOT / "LocalPreferences.toml").read_text()
        self.assertIn("[CUDA_Runtime_jll]", preference)
        self.assertIn('version = "12.3"', preference)

    def test_tempering_summary_reports_phase_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stats = root / "statistics.csv"
            diagnostics = root / "diagnostics.csv"
            manifest = root / "manifest.csv"
            output = root / "blocks.csv"
            stats.write_text(
                "# init_phase=ordered\n# phase_threshold=0.25\n"
                "trajectory,M,M2,M4,Q,G,acceptance_rate\n"
                "10,0.1,0.01,0.0001,1,1,0.8\n"
                "20,0.3,0.09,0.0081,1,1,0.8\n"
                "30,0.4,0.16,0.0256,1,1,0.8\n"
                "40,0.1,0.01,0.0001,1,1,0.8\n",
                encoding="utf-8",
            )
            diagnostics.write_text(
                "trajectory,hmc_acceptance_slot_1,hmc_acceptance_slot_2,hmc_acceptance_slot_3,"
                "swap_acceptance_1_2,swap_acceptance_2_3,round_trips_total\n"
                "40,0.8,0.8,0.8,0.4,0.5,8\n",
                encoding="utf-8",
            )
            fields = [
                "task_id", "point_index", "replica", "L", "Z", "m2", "init_phase",
                "phase_threshold", "stats_path", "diagnostics_path",
            ]
            with manifest.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerow({
                    "task_id": 0, "point_index": 0, "replica": 0, "L": 6,
                    "Z": 1, "m2": -2.25, "init_phase": "ordered",
                    "phase_threshold": 0.25, "stats_path": stats,
                    "diagnostics_path": diagnostics,
                })
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/summarize_tempering.py"),
                 "--manifest", str(manifest), "--block-size", "2",
                 "--output", str(output)],
                check=True, text=True, capture_output=True,
            )
            with output.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual([row["phase_transitions"] for row in rows], ["1", "1"])
            self.assertIn("swap_bottlenecks=0", result.stdout)

    def test_even_tempering_count_is_rejected(self):
        command = [
            sys.executable, str(ROOT / "scripts/submit_reweight_array.py"),
            "--L", "6", "--point=1,-2.25", "--eps", "0.02", "--n-lf", "4",
            "--tempering-replicas", "4", "--mass-span", "0.2", "--dry-run",
        ]
        result = subprocess.run(command, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be 1 or an odd integer", result.stderr)


if __name__ == "__main__":
    unittest.main()
