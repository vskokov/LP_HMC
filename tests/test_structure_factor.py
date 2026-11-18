import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from structure_factor_analysis import (  # noqa: E402
    bimodality_stable,
    detect_bimodality,
    normalized_weights,
    rank_from_eigenvalues,
    rank_label,
    trajectory_block_indices,
)
from structure_factor_campaign import longest_dense_core  # noqa: E402


class StructureFactorAnalysisTests(unittest.TestCase):
    def test_two_parameter_reweighting(self):
        denominator = np.zeros(4)
        Q = np.array([0.0, 1.0, 2.0, 3.0])
        G = np.array([3.0, 2.0, 1.0, 0.0])
        weights = normalized_weights(denominator, Q, G, delta_m2=0.2, delta_Z=-0.1)
        expected = np.exp(-0.5 * (0.2 * Q - 0.1 * G))
        expected /= expected.sum()
        np.testing.assert_allclose(weights, expected)

    def test_dense_core(self):
        masses = [-2.4, -2.3, -2.15, -2.13, -2.12, -2.11, -2.1, -1.9]
        self.assertEqual(longest_dense_core(masses), [-2.15, -2.13, -2.12, -2.11, -2.1])

    def test_bimodal_detection_and_unimodal_rejection(self):
        rng = np.random.default_rng(71)
        bimodal = np.concatenate((rng.normal(0.2, 0.015, 4000), rng.normal(0.7, 0.02, 4000)))
        weights = np.full(len(bimodal), 1.0 / len(bimodal))
        result = bimodality_stable(bimodal, weights)
        self.assertTrue(result["resolved"])
        self.assertTrue(result["stable"])
        self.assertGreater(result["barrier"], 1.0)

        unimodal = rng.normal(0.4, 0.08, 8000)
        weights = np.full(len(unimodal), 1.0 / len(unimodal))
        self.assertFalse(detect_bimodality(unimodal, weights)["resolved"])

    def test_block_resampling_keeps_complete_umbrella_trajectories(self):
        trajectories = np.repeat(np.arange(12), 5)
        indices = trajectory_block_indices(trajectories, np.random.default_rng(9), 3)
        self.assertEqual(len(indices), len(trajectories))
        selected = trajectories[indices]
        counts = np.unique(selected, return_counts=True)[1]
        self.assertTrue(np.all(counts % 5 == 0))

    def test_rank_classification_is_conservative(self):
        self.assertEqual(rank_from_eigenvalues(0.02, 0.01), 1)
        self.assertEqual(rank_from_eigenvalues(0.45, 0.02), 2)
        self.assertEqual(rank_from_eigenvalues(0.34, 0.31), 3)
        self.assertEqual(rank_label({"modulation_support": 0.99,
                                     "rank1_probability": 0.94,
                                     "rank2_probability": 0.04,
                                     "rank3_probability": 0.02}), "rank1")
        self.assertEqual(rank_label({"modulation_support": 0.70,
                                     "rank1_probability": 0.95,
                                     "rank2_probability": 0.05,
                                     "rank3_probability": 0.0}), "mixed/undetermined")
        self.assertEqual(rank_label({"modulation_support": 0.01,
                                     "rank1_probability": 0.0,
                                     "rank2_probability": 0.0,
                                     "rank3_probability": 0.0}), "unmodulated")


if __name__ == "__main__":
    unittest.main()
