import csv
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from explore_umbrella_nlf import summarize  # noqa: E402


class UmbrellaNlfExplorerTests(unittest.TestCase):
    def test_summary_uses_worst_phase_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks = []
            for n_lf, phase, diffusion in (
                (4, "disordered", 0.0010),
                (4, "ordered", 0.0012),
                (16, "disordered", 0.0025),
                (16, "ordered", 0.0020),
            ):
                output = root / f"{phase}_{n_lf}.csv"
                row = {
                    "checkpoint": str(root / f"{phase}.jld2"),
                    "init_phase": phase,
                    "n_lf": n_lf,
                    "trajectory_length": 0.02 * n_lf,
                    "hmc_acceptance": 0.78,
                    "diffusion_per_lf_step": diffusion,
                    "diffusion_per_second": 0.1 * diffusion,
                }
                with output.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=list(row))
                    writer.writeheader()
                    writer.writerow(row)
                tasks.append({
                    "source_task_id": 0 if phase == "disordered" else 1,
                    "source_replica": 0 if phase == "disordered" else 1,
                    "checkpoint": row["checkpoint"], "output": output,
                })
            manifest = root / "sweep_manifest.csv"
            with manifest.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(tasks[0]))
                writer.writeheader()
                writer.writerows(tasks)

            self.assertEqual(summarize(manifest, 0.65, 0.90), 0)
            with (root / "recommendations.csv").open(newline="", encoding="utf-8") as handle:
                recommendation = next(csv.DictReader(handle))
            self.assertEqual(int(recommendation["n_lf"]), 16)
            self.assertEqual(int(recommendation["rank"]), 1)


if __name__ == "__main__":
    unittest.main()
