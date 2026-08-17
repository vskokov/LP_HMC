import csv
import json
import multiprocessing
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_umbrella_task import merge_shards  # noqa: E402
from umbrella_profiles import proposed_profile  # noqa: E402
from umbrella_runtime import claim_continuation, deterministic_seed, exclusive_task_lock  # noqa: E402


def try_lock(path: str, queue: multiprocessing.Queue) -> None:
    try:
        with exclusive_task_lock(Path(path)):
            queue.put(True)
    except RuntimeError:
        queue.put(False)


class UmbrellaCampaignTests(unittest.TestCase):
    def test_scaling_profiles_and_l20_interpolation(self):
        profiles = [proposed_profile(L) for L in (6, 8, 12, 16, 18, 20, 24, 32)]
        self.assertEqual([p["umbrella_windows"] for p in profiles],
                         [21, 32, 58, 88, 105, 123, 161, 247])
        self.assertTrue(profiles[6]["validated"])
        self.assertFalse(profiles[5]["validated"])
        self.assertGreater(profiles[5]["epsilon"], profiles[6]["epsilon"])
        self.assertLess(profiles[5]["epsilon"], profiles[4]["epsilon"])

    def test_block_seeds_are_stable_and_stage_separated(self):
        values = [deterministic_seed(17, 2, "collection", i) for i in range(4)]
        self.assertEqual(values, [deterministic_seed(17, 2, "collection", i) for i in range(4)])
        self.assertEqual(len(set(values)), 4)
        self.assertNotEqual(values[0], deterministic_seed(17, 2, "thermalization", 0))

    def test_continuation_claim_is_unique_and_caps_total_allocations(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "progress.json"
            self.assertTrue(claim_continuation(state, 0, 3))
            self.assertFalse(claim_continuation(state, 0, 3))
            self.assertTrue(claim_continuation(state, 1, 3))
            self.assertFalse(claim_continuation(state, 2, 3))

    def test_task_lock_rejects_concurrent_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "task.lock"
            queue = multiprocessing.Queue()
            with exclusive_task_lock(path):
                process = multiprocessing.Process(target=try_lock, args=(str(path), queue))
                process.start(); process.join(5)
                self.assertFalse(queue.get(timeout=1))
            with exclusive_task_lock(path):
                pass

    def test_merge_uses_only_committed_shards_with_exact_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); shard_dir = root / "shards"; shard_dir.mkdir()
            header = "trajectory,slot,walker_id,umbrella_center,umbrella_kappa,M,M2,M4,Q,G,acceptance_rate\n"
            diag_header = "trajectory,round_trips_total,walkers_with_round_trip,min_hmc_acceptance,min_swap_acceptance,swap_acceptance_1_2\n"
            committed = []
            for index in range(2):
                stats = shard_dir / f"s{index}.csv"; diag = shard_dir / f"d{index}.csv"
                stats.write_text(header + f"{index},1,1,0,1,0,0,0,0,0,1\n", encoding="utf-8")
                diag.write_text(diag_header + f"{index},0,0,1,1,1\n", encoding="utf-8")
                committed.append({"statistics": str(stats), "diagnostics": str(diag)})
            (shard_dir / "uncommitted.csv").write_text(header + "999,1,1,0,1,0,0,0,0,0,1\n")
            row = {"stats_path": str(root / "final.csv"), "diagnostics_path": str(root / "diag.csv"),
                   "L": "2", "Z": "-0.6", "m2": "-1", "eps": ".1", "n_lf": "2",
                   "seed": "3", "skip": "1", "warmup": "0", "umbrella_replicas": "2",
                   "umbrella_min": "0", "umbrella_max": ".4", "umbrella_kappa": "1",
                   "production_sweeps": "2", "umbrella_power": "1", "swap_every": "1", "init_phase": "ordered",
                   "collection_shard_samples": "1"}
            merge_shards(row, {"samples": 2, "committed_shards": committed})
            text = (root / "final.csv").read_text()
            self.assertNotIn("999,", text)
            self.assertEqual(sum(not line.startswith("#") for line in text.splitlines()), 3)
            self.assertEqual(len((root / "diag.csv").read_text().splitlines()), 3)

    def test_all_l_dry_run_and_l24_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/umbrella_campaign.py"), "prepare",
                 "--campaign-dir", str(root), "--profile-dir", str(root / "profiles")],
                text=True, capture_output=True, check=True)
            self.assertIn("production_blocked_unvalidated_L=6,8,12,16,18,20,32", result.stdout)
            index = json.loads((root / "campaign.json").read_text())
            self.assertEqual(len(index["sizes"]), 8)
            for item in index["sizes"]:
                with Path(item["manifest"]).open(newline="") as handle:
                    rows = list(csv.DictReader(handle))
                self.assertEqual(len(rows), 4)
            with (root / "L24/manifest.csv").open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([r["init_phase"] for r in rows],
                             ["disordered", "ordered", "disordered", "ordered"])
            self.assertIn("umbrella_L24_w161_nlf48_lsf", rows[0]["checkpoint_path"])
            self.assertTrue((root / "L24/L24_migration.json").is_file())
            script = (root / "L24/lsf_job.sh").read_text()
            self.assertIn("#BSUB -W 120", script)
            self.assertIn("hname!='gpu31'", script)
            self.assertIn('--task-id "${TASK_ID}"', script)

    def test_status_and_repair_advance_all_four_synchronously(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run([
                sys.executable, str(ROOT / "scripts/submit_umbrella_bsub.py"),
                "--L=4", "--point=-.6,-1", "--eps=.03", "--n-lf=4",
                "--startup-eps=.02", "--startup-n-lf=2", "--startup-sweeps=0",
                "--thermalization-sweeps=10", "--max-thermalization-sweeps=20",
                "--umbrella-windows=5", "--umbrella-kappa=10", "--replicas=4",
                "--init-schedule=split", "--samples=10000", "--min-samples=10000",
                "--max-samples=40000", "--sample-increment=5000", "--dry-run",
                f"--run-root={root}", "--run-name=cohort"], check=True,
                text=True, capture_output=True)
            manifest = root / "cohort/manifest.csv"
            with manifest.open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            for row in rows:
                path = Path(row["progress_marker"]); path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"decision": "awaiting_cohort", "samples": 10000,
                                            "target_samples": 10000, "committed_shards": []}))
            evaluation = root / "evaluation.json"
            evaluation.write_text(json.dumps({"binder_mcse": .006, "minimum_overlap": .4,
                                               "maximum_bin_shift": .0001,
                                               "phase_difference": .01,
                                               "phase_combined_error": .01}))
            repaired = subprocess.run([
                sys.executable, str(ROOT / "scripts/umbrella_campaign.py"), "repair",
                "--manifest", str(manifest), "--evaluation-json", str(evaluation),
                "--dry-run", "--bjobs", "definitely-not-a-command"],
                check=True, text=True, capture_output=True)
            self.assertEqual(repaired.stdout.count("UMBRELLA_TASK_ID="), 4)
            for row in rows:
                progress = json.loads(Path(row["progress_marker"]).read_text())
                self.assertEqual(progress["decision"], "collecting")
                self.assertEqual(progress["target_samples"], 15000)
            shown = subprocess.run([
                sys.executable, str(ROOT / "scripts/umbrella_campaign.py"), "status",
                "--manifest", str(manifest), "--bjobs", "definitely-not-a-command"],
                check=True, text=True, capture_output=True)
            payload = json.loads(shown.stdout)
            self.assertEqual({task["samples"] for task in payload["tasks"]}, {10000})

    def test_adaptive_submit_requires_validated_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([
                sys.executable, str(ROOT / "scripts/submit_umbrella_bsub.py"),
                "--L=4", "--point=-.6,-1", "--eps=.03", "--n-lf=4",
                "--startup-eps=.02", "--startup-n-lf=2", "--startup-sweeps=0",
                "--umbrella-windows=5", "--umbrella-kappa=10",
                "--min-samples=10000", f"--run-root={directory}"],
                text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("validated evidence", result.stderr)


if __name__ == "__main__":
    unittest.main()
