"""Tests for umbrella_tuning_campaign.py."""

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from umbrella_tuning_campaign import (  # noqa: E402
    initial_state,
    nlf_all_probes_done,
    pilot_is_complete,
    ranked_nlf_candidates,
)


class UmbrellaTuningCampaignTests(unittest.TestCase):
    def test_initial_state_starts_at_pilot(self):
        state = initial_state(16)
        self.assertEqual(state["stage"], "pilot")
        self.assertIsNone(state["pilot_manifest"])

    def test_prepare_writes_campaign_tree_dry_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/umbrella_tuning_campaign.py"),
                 "prepare", "--sizes", "6,12", "--dry-run",
                 "--campaign-dir", str(root / "campaign"),
                 "--profile-dir", str(root / "profiles"),
                 "--report-dir", str(root / "reports")],
                text=True, capture_output=True, check=True,
            )
            self.assertIn("campaign_index=", result.stdout)
            index = json.loads((root / "campaign" / "campaign.json").read_text())
            self.assertEqual(len(index["sizes"]), 2)
            for L in (6, 12):
                state_path = root / "campaign" / f"L{L}" / "state.json"
                self.assertTrue(state_path.is_file())
                state = json.loads(state_path.read_text())
                self.assertEqual(state["stage"], "pilot")
                manifest = Path(state["pilot_manifest"])
                self.assertTrue(manifest.is_file())
                self.assertTrue((manifest.parent / "lsf_job.sh").is_file())

    def test_repair_advances_completed_pilot_to_nlf_dry_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = root / "campaign"
            reports = root / "reports"
            subprocess.run(
                [sys.executable, str(ROOT / "scripts/umbrella_tuning_campaign.py"),
                 "prepare", "--sizes", "6",
                 "--campaign-dir", str(campaign),
                 "--profile-dir", str(root / "profiles"),
                 "--report-dir", str(reports)],
                check=True, capture_output=True, text=True,
            )
            state_path = campaign / "L6" / "state.json"
            state = json.loads(state_path.read_text())
            pilot_dir = Path(state["pilot_manifest"]).parent
            with (pilot_dir / "manifest.csv").open(newline="", encoding="utf-8") as handle:
                manifest_rows = list(csv.DictReader(handle))
            (pilot_dir / "checkpoints").mkdir(exist_ok=True)
            for row in manifest_rows:
                checkpoint = Path(row["checkpoint_path"])
                checkpoint.parent.mkdir(parents=True, exist_ok=True)
                checkpoint.write_bytes(b"stub")
            for sub in ("complete", "statistics"):
                (pilot_dir / sub).mkdir(exist_ok=True)
            for index in range(2):
                name = f"r{index}"
                (pilot_dir / "statistics" / f"{name}.csv").write_text("data\n")
                (pilot_dir / "complete" / f"{name}.complete").write_text(
                    json.dumps({"complete": True}), encoding="utf-8"
                )
            self.assertTrue(pilot_is_complete(pilot_dir))
            subprocess.run(
                [sys.executable, str(ROOT / "scripts/umbrella_tuning_campaign.py"),
                 "repair", "--campaign-dir", str(campaign),
                 "--profile-dir", str(root / "profiles"),
                 "--report-dir", str(reports), "--L", "6"],
                check=True, capture_output=True, text=True,
            )
            state = json.loads(state_path.read_text())
            self.assertEqual(state["stage"], "nlf")
            nlf_dir = reports / "L6_nlf"
            self.assertTrue((nlf_dir / "sweep_manifest.csv").is_file())
            self.assertTrue((nlf_dir / "lsf_job.sh").is_file())

    def test_ranked_nlf_candidates_reads_eligible_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            (output_dir / "recommendations.csv").write_text(
                "rank,n_lf,eligible\n1,26,True\n2,32,True\n3,19,False\n",
                encoding="utf-8",
            )
            self.assertEqual(ranked_nlf_candidates(output_dir), [26, 32])

    def test_nlf_all_probes_done_requires_every_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            raw = output_dir / "raw"
            raw.mkdir()
            manifest = output_dir / "sweep_manifest.csv"
            manifest.write_text(
                "probe_id,output\n0," + str(raw / "a.csv") + "\n1," + str(raw / "b.csv") + "\n",
                encoding="utf-8",
            )
            self.assertFalse(nlf_all_probes_done(output_dir))
            (raw / "a.csv").write_text("x\n")
            self.assertFalse(nlf_all_probes_done(output_dir))
            (raw / "b.csv").write_text("x\n")
            self.assertTrue(nlf_all_probes_done(output_dir))


if __name__ == "__main__":
    unittest.main()
