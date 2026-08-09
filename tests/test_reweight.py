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
            self.assertIn("diagnostics/task_000000.csv", row["diagnostics_path"])
            self.assertIn("thermalize_replicas.jl", result.stdout)
            self.assertIn("collect_reweight_stats_replicas.jl", result.stdout)
            self.assertIn("--tempering-replicas=5", result.stdout)

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
