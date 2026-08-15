import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from analyze_umbrella import estimate, read_umbrella  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
