"""Tests for umbrella_profiles.py."""

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from umbrella_profiles import (  # noqa: E402
    binder_canonical_combined_z,
    proposed_profile,
    validate_profile_evidence,
)


class UmbrellaProfileTests(unittest.TestCase):
    def test_binder_canonical_combined_z_uses_fixed_tolerance(self):
        self.assertAlmostEqual(binder_canonical_combined_z([0.63, 0.61]), 2.0)

    def test_validate_profile_evidence_requires_canonical_agreement_for_large_l(self):
        profile = proposed_profile(24)
        profile["validated"] = True
        profile["n_lf"] = 40
        profile["validation"] = {
            "provenance": "/tmp/confirm",
            "worst_phase_hmc_acceptance": 0.75,
            "minimum_edge_swap_acceptance": 0.30,
            "minimum_histogram_overlap": 0.50,
            "both_endpoints_visited": True,
            "stable_diffusion_both_phases": True,
            "confirmed_candidates": 2,
            "canonical_combined_z": 2.5,
        }
        with self.assertRaisesRegex(ValueError, "ordered/disordered Binder agreement"):
            validate_profile_evidence(24, profile["validation"])

    def test_validate_profile_evidence_accepts_small_canonical_split(self):
        validation = {
            "provenance": "/tmp/confirm",
            "worst_phase_hmc_acceptance": 0.75,
            "minimum_edge_swap_acceptance": 0.30,
            "minimum_histogram_overlap": 0.50,
            "both_endpoints_visited": True,
            "stable_diffusion_both_phases": True,
            "confirmed_candidates": 2,
            "canonical_combined_z": 1.5,
        }
        validate_profile_evidence(16, validation)

    def test_load_profile_rejects_missing_canonical_field(self):
        from umbrella_profiles import load_profile

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "L16.json"
            profile = proposed_profile(16)
            profile["validated"] = True
            profile["n_lf"] = 40
            profile["validation"] = {
                "provenance": "/tmp/confirm",
                "worst_phase_hmc_acceptance": 0.75,
                "minimum_edge_swap_acceptance": 0.30,
                "minimum_histogram_overlap": 0.50,
                "both_endpoints_visited": True,
                "stable_diffusion_both_phases": True,
                "confirmed_candidates": 2,
            }
            path.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "required transport/canonical evidence"):
                load_profile(path, 16, require_validated=True)


if __name__ == "__main__":
    unittest.main()
