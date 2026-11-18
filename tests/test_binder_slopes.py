import math
import csv
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from analyze_binder_slopes import (  # noqa: E402
    Campaign,
    bisection_root,
    campaign_status,
    linear_crossing,
)


class BinderSlopeTests(unittest.TestCase):
    def test_linear_crossing_selects_highest_binder(self):
        left = [(-2.0, 0.60), (-1.9, 0.40), (-1.8, 0.55), (-1.7, 0.20)]
        right = [(-2.0, 0.50), (-1.9, 0.45), (-1.8, 0.45), (-1.7, 0.30)]
        crossing = linear_crossing(left, right, 12, 16)
        self.assertIsNotNone(crossing)
        assert crossing is not None
        self.assertGreater(crossing.linear_U4, 0.45)
        self.assertEqual(crossing.pair, "12x16")

    def test_bisection_root(self):
        root = bisection_root(lambda value: value**3 - 2.0, 1.0, 2.0)
        self.assertAlmostEqual(root, 2.0 ** (1.0 / 3.0), places=12)

    def test_bisection_rejects_missing_bracket(self):
        with self.assertRaisesRegex(ValueError, "do not bracket"):
            bisection_root(lambda value: value**2 + 1.0, -1.0, 1.0)

    def test_partial_campaign_accepts_two_common_paired_masses(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for L in (12, 16, 20, 24):
                run_dir = root / f"L{L}"
                run_dir.mkdir()
                rows = []
                for task_id, (mass, replica) in enumerate(
                    ((-2.1, 0), (-2.1, 1), (-2.0, 0), (-2.0, 1))
                ):
                    stats = run_dir / f"stats_{task_id}.csv"
                    stats.touch()
                    rows.append({
                        "task_id": task_id, "m2": mass, "replica": replica,
                        "stats_path": stats, "completion_marker": run_dir / f"missing_{task_id}",
                    })
                with (run_dir / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=rows[0])
                    writer.writeheader(); writer.writerows(rows)
            campaign = Campaign(-1.0, root, root / "binder.csv")
            strict_ready, _ = campaign_status(campaign, (12, 16, 20, 24))
            partial_ready, details = campaign_status(
                campaign, (12, 16, 20, 24), allow_partial=True,
            )
            self.assertFalse(strict_ready)
            self.assertTrue(partial_ready)
            self.assertIn("common_paired_masses=2", details)


if __name__ == "__main__":
    unittest.main()
