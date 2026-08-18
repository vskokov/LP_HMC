"""Tests for tune_umbrella_profile.py."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from tune_umbrella_profile import (  # noqa: E402
    canonical_gate_passes,
    confirm_is_complete,
    confirmation_attempts,
    manifest_only_flags,
    nlf_candidates,
    resolve_pilot_n_lf,
)


class TuneUmbrellaProfileTests(unittest.TestCase):
    def test_pilot_stage_dry_run_uses_measured_hmc_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            profile_dir = Path(directory) / "profiles"
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/tune_umbrella_profile.py"),
                 "--L=6", "--stage=pilot", "--dry-run",
                 f"--profile-dir={profile_dir}", f"--run-root={directory}/runs"],
                check=True, text=True, capture_output=True,
            )
            self.assertIn("--n-lf=32", result.stdout)
            self.assertIn("--eps=0.06558992039", result.stdout)
            self.assertIn("--dry-run", result.stdout)
            self.assertIn("tune_L6_pilot", result.stdout)

    def test_nlf_candidates_includes_ranked_alternates_for_l12(self):
        from argparse import Namespace

        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            nlf_dir = report_dir / "L12_nlf"
            nlf_dir.mkdir()
            (nlf_dir / "recommendations.csv").write_text(
                "rank,n_lf,eligible\n1,26,True\n2,32,True\n3,19,True\n",
                encoding="utf-8",
            )
            args = Namespace(
                L=12, report_dir=report_dir, try_alternate_nlf=True, n_lf=None,
            )
            self.assertEqual(nlf_candidates(args, 26), [26, 32, 19])

    def test_confirmation_attempts_escalate_samples_and_thermalization(self):
        from argparse import Namespace

        args = Namespace(
            confirm_sample_schedule="",
            confirm_samples=1000,
            confirm_attempts=3,
            confirm_samples_max=10000,
            confirm_thermalization_escalation=True,
        )
        self.assertEqual(
            confirmation_attempts(args),
            [(1000, 1.0), (2000, 1.5), (4000, 2.0)],
        )

    def test_canonical_gate_passes_within_two_sigma(self):
        self.assertTrue(canonical_gate_passes({"canonical_combined_z": 1.9}))
        self.assertFalse(canonical_gate_passes({"canonical_combined_z": 2.1}))
        self.assertFalse(canonical_gate_passes({}))
        from argparse import Namespace

        args = Namespace(dry_run=False)
        self.assertEqual(manifest_only_flags(args), ["--prepare-only"])
        args.dry_run = True
        self.assertEqual(manifest_only_flags(args), ["--dry-run"])

    def test_confirm_is_complete_requires_two_finished_replicas(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "complete").mkdir()
            (run_dir / "statistics").mkdir()
            self.assertFalse(confirm_is_complete(run_dir))
            for index in range(2):
                name = f"r{index}"
                (run_dir / "statistics" / f"{name}.csv").write_text("data\n", encoding="utf-8")
                (run_dir / "complete" / f"{name}.complete").write_text(
                    json.dumps({"complete": True}), encoding="utf-8"
                )
            self.assertTrue(confirm_is_complete(run_dir))

    def test_resolve_pilot_n_lf_scales_with_window_count(self):
        profile = {
            "startup_n_lf": 11,
            "umbrella_windows": 58,
        }
        self.assertEqual(resolve_pilot_n_lf(profile, 6), 29)

    def test_pilot_stage_dry_run_uses_transport_scaled_n_lf_for_l12(self):
        with tempfile.TemporaryDirectory() as directory:
            profile_dir = Path(directory) / "profiles"
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/tune_umbrella_profile.py"),
                 "--L=12", "--stage=pilot", "--dry-run",
                 f"--profile-dir={profile_dir}", f"--run-root={directory}/runs"],
                check=True, text=True, capture_output=True,
            )
            self.assertIn("--n-lf=29", result.stdout)
            self.assertIn("--max-thermalization-sweeps=81225", result.stdout)

    def test_pilot_stage_dry_run_uses_bsub_submitter_for_lsf(self):
        with tempfile.TemporaryDirectory() as directory:
            profile_dir = Path(directory) / "profiles"
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/tune_umbrella_profile.py"),
                 "--L=6", "--stage=pilot", "--dry-run", "--scheduler=lsf",
                 f"--profile-dir={profile_dir}", f"--run-root={directory}/runs"],
                check=True, text=True, capture_output=True,
            )
            self.assertIn("submit_umbrella_bsub.py", result.stdout)
            self.assertIn("--self-resubmit", result.stdout)
            self.assertIn("--runtime-budget-minutes=60.0", result.stdout)
            self.assertNotIn("submit_umbrella_tsp.py", result.stdout)


    def test_pilot_stage_uses_measured_n_lf_not_validated_profile_n_lf(self):
        from umbrella_profiles import proposed_profile

        with tempfile.TemporaryDirectory() as directory:
            profile_dir = Path(directory) / "profiles"
            profile_dir.mkdir()
            profile = proposed_profile(6)
            profile["n_lf"] = 8
            profile["validated"] = True
            (profile_dir / "L6.json").write_text(
                json.dumps(profile, indent=2) + "\n", encoding="utf-8"
            )
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/tune_umbrella_profile.py"),
                 "--L=6", "--stage=pilot", "--dry-run",
                 f"--profile-dir={profile_dir}", f"--run-root={directory}/runs"],
                check=True, text=True, capture_output=True,
            )
            self.assertIn("--n-lf=32", result.stdout)
            self.assertIn("--thermalization-sweeps=5000", result.stdout)


if __name__ == "__main__":
    unittest.main()
