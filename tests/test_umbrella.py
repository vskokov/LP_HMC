import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from analyze_umbrella import estimate, read_umbrella, solve_binned_wham  # noqa: E402


class UmbrellaTests(unittest.TestCase):
    def test_zero_bias_mbar_recovers_direct_moments(self):
        base_m2 = np.asarray([0.01, 0.04, 0.09, 0.16])
        replicas = 3
        m2 = np.tile(base_m2, replicas)
        arrays = {
            "slot": np.repeat(np.arange(1, replicas + 1), len(base_m2)).astype(float),
            "M2": m2,
            "M4": m2**2,
            "umbrella_center": np.repeat([0.0, 0.1, 0.2], len(base_m2)),
            "umbrella_kappa": np.zeros(replicas * len(base_m2)),
        }
        result = estimate(arrays)
        expected_m2 = float(np.mean(base_m2))
        expected_binder = 1.0 - np.mean(base_m2**2) / (3.0 * expected_m2**2)
        self.assertAlmostEqual(result["mean_M2"], expected_m2)
        self.assertAlmostEqual(result["binder"], expected_binder)
        self.assertTrue(all(abs(value) < 1e-12 for value in result["free_energies"]))

    def test_binned_wham_converges_for_long_overlapping_ladder(self):
        rng = np.random.default_rng(1729)
        replicas = 81
        samples = 80
        centers = np.linspace(0.0, 0.4, replicas)
        kappas = np.full(replicas, 20_000.0)
        counts = np.full(replicas, samples, dtype=float)
        values = np.concatenate([
            rng.normal(center, 1.0 / np.sqrt(kappa), samples)
            for center, kappa in zip(centers, kappas)
        ])
        free, denominator, iterations = solve_binned_wham(
            values, centers, kappas, counts, bins=256
        )
        self.assertTrue(np.all(np.isfinite(free)))
        self.assertTrue(np.all(np.isfinite(denominator)))
        self.assertLess(iterations, 100)

    def test_schema_reader_rejects_missing_window(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            path.write_text(
                "# schema_version=3\n# sampler=umbrella_exchange\n"
                "# umbrella_replicas=2\n# samples_per_window=1\n"
                + ",".join(("trajectory", "slot", "walker_id", "umbrella_center",
                            "umbrella_kappa", "M", "M2", "M4", "Q", "G",
                            "acceptance_rate")) + "\n"
                "1,1,1,0,10,0,0,0,1,1,1\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "incomplete umbrella slots"):
                read_umbrella(path)

    def test_tsp_dry_run_manifest_contains_umbrella_parameters(self):
        with tempfile.TemporaryDirectory() as directory:
            command = [
                sys.executable, str(ROOT / "scripts/submit_umbrella_tsp.py"),
                "--L=4", "--point=1,-2", "--eps=.03", "--n-lf=4",
                "--startup-eps=.02", "--startup-n-lf=4", "--startup-sweeps=4",
                "--max-thermalization-sweeps=128",
                "--min-round-trip-fraction=.25",
                "--min-swap-acceptance=.2",
                "--umbrella-windows=5", "--umbrella-max=.4",
                "--umbrella-kappa=80", "--samples=10",
                f"--run-root={directory}", "--run-name=test", "--dry-run",
            ]
            subprocess.run(command, check=True, text=True, capture_output=True)
            with (Path(directory) / "test/manifest.csv").open(newline="") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["umbrella_replicas"], "5")
            self.assertEqual(float(row["umbrella_max"]), 0.4)
            self.assertEqual(float(row["umbrella_kappa"]), 80.0)
            self.assertEqual(int(row["production_sweeps"]), 64)
            self.assertEqual(int(row["max_production_sweeps"]), 128)
            self.assertEqual(float(row["min_round_trip_fraction"]), 0.25)
            self.assertEqual(float(row["min_swap_acceptance"]), 0.2)
            worker = subprocess.run(
                [sys.executable, str(ROOT / "scripts/run_umbrella_task.py"),
                 "--manifest", str(Path(directory) / "test/manifest.csv"),
                 "--task-id=0", "--dry-run"],
                check=True, text=True, capture_output=True,
            )
            self.assertIn("umbrella_worker event=started", worker.stdout)
            self.assertIn("task_id=0", worker.stdout)
            self.assertIn("checkpoint_exists=False", worker.stdout)
            self.assertIn("umbrella_worker event=thermalization_started", worker.stdout)

    def test_prepare_only_writes_manifest_without_enqueueing_tsp(self):
        with tempfile.TemporaryDirectory() as directory:
            command = [
                sys.executable, str(ROOT / "scripts/submit_umbrella_tsp.py"),
                "--L=4", "--point=1,-2", "--eps=.03", "--n-lf=4",
                "--startup-eps=.02", "--startup-n-lf=4", "--startup-sweeps=4",
                "--max-thermalization-sweeps=128",
                "--min-round-trip-fraction=.25",
                "--min-swap-acceptance=.2",
                "--umbrella-windows=5", "--umbrella-max=.4",
                "--umbrella-kappa=80", "--samples=10",
                f"--run-root={directory}", "--run-name=prep", "--prepare-only",
            ]
            result = subprocess.run(command, check=True, text=True, capture_output=True)
            self.assertTrue((Path(directory) / "prep/manifest.csv").is_file())
            self.assertIn("manifest:", result.stdout)

    def test_lsf_memory_request_is_in_gigabytes(self):
        with tempfile.TemporaryDirectory() as directory:
            command = [
                sys.executable, str(ROOT / "scripts/submit_umbrella_bsub.py"),
                "--L=4", "--point=1,-2", "--eps=.03", "--n-lf=4",
                "--startup-eps=.02", "--startup-n-lf=4", "--startup-sweeps=4",
                "--umbrella-windows=5", "--umbrella-max=.4",
                "--umbrella-kappa=80", "--samples=10", "--mem-gb=24",
                "--exclude-host=gpu31",
                f"--run-root={directory}", "--run-name=lsf_memory", "--dry-run",
            ]
            subprocess.run(command, check=True, text=True, capture_output=True)
            script = (Path(directory) / "lsf_memory/lsf_job.sh").read_text()
            self.assertIn(
                '#BSUB -R "select[(h200 || h100 || l40s) && hname!=\'gpu31\'] '
                'rusage[mem=24]"', script,
            )
            self.assertNotIn("rusage[mem=24000]", script)
            self.assertIn("export PYTHONUNBUFFERED=1", script)
            self.assertIn("module load cuda/13.2", script)
            self.assertIn("module load julia/1.12.6", script)
            self.assertIn(
                'export JULIA_DEPOT_PATH="/usr/local/usrapps/$GROUP/$USER/julia_depot"',
                script,
            )


if __name__ == "__main__":
    unittest.main()
