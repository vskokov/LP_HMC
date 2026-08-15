import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUBMITTER = ROOT / "scripts" / "submit_binder_analysis_bsub.py"


class BinderAnalysisBsubTests(unittest.TestCase):
    def test_dynamic_array_size_and_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = subprocess.run(
                [
                    sys.executable, str(SUBMITTER),
                    "--data-prefix", "production_",
                    "--L", "8", "16", "24",
                    "--max-concurrent", "2",
                    "--log-dir", str(root / "logs"),
                    "--output-root", str(root / "plots"),
                    "--dry-run",
                ],
                text=True, capture_output=True, check=True,
            )
        self.assertIn("tasks: 9 (3 lattice sizes x 3 scans)", result.stdout)
        self.assertIn("reweight_binder[1-9]%2", result.stdout)
        self.assertIn("production_L*/manifest.csv", result.stdout)
        self.assertIn("9: L=24  Z=-0.9", result.stdout)

    def test_custom_scan_changes_task_count(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = subprocess.run(
                [
                    sys.executable, str(SUBMITTER),
                    "--data-prefix", "binder_lsf_",
                    "--L", "12", "32",
                    "--scan=-1.05,-2.85,-2.65,central",
                    "--log-dir", str(root / "logs"),
                    "--output-root", str(root / "plots"),
                    "--dry-run",
                ],
                text=True, capture_output=True, check=True,
            )
        self.assertIn("tasks: 2 (2 lattice sizes x 1 scans)", result.stdout)
        self.assertIn("reweight_binder[1-2]%2", result.stdout)
        self.assertIn("2: L=32  Z=-1.05", result.stdout)


if __name__ == "__main__":
    unittest.main()
