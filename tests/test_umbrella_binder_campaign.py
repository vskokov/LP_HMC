import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "scripts/umbrella_binder_campaign.py"
sys.path.insert(0, str(ROOT / "scripts"))
from umbrella_binder_campaign import combined_row, scan_t  # noqa: E402
from umbrella_profiles import CANONICAL_Z_MAX  # noqa: E402


class UmbrellaBinderCampaignTests(unittest.TestCase):
    def test_submit_dry_run_uses_validated_l12_profile_and_five_masses(self):
        with tempfile.TemporaryDirectory() as directory:
            campaign_dir = Path(directory) / "runs"
            result = subprocess.run(
                [
                    sys.executable, str(CAMPAIGN), "submit", "12",
                    "--dry-run",
                    "--campaign-dir", str(campaign_dir),
                    "--julia", "julia",
                ],
                check=True, text=True, capture_output=True, cwd=ROOT,
            )
        self.assertIn("--n-lf=26", result.stdout)
        self.assertIn("--umbrella-windows=58", result.stdout)
        self.assertIn("--umbrella-kappa=20000", result.stdout)
        self.assertIn("--init-schedule=split", result.stdout)
        self.assertIn("--replicas=2", result.stdout)
        self.assertIn("reweight_sources_Zm0p6.csv", result.stdout)
        self.assertIn("--run-name=L12", result.stdout)
        self.assertIn("--samples=4000", result.stdout)
        self.assertIn("run_umbrella_task.py", result.stdout)
        self.assertIn("--task-id", result.stdout)

    def test_submit_missing_profile_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    sys.executable, str(CAMPAIGN), "submit", "12",
                    "--dry-run",
                    "--profile-dir", directory,
                    "--campaign-dir", directory,
                    "--julia", "julia",
                ],
                text=True, capture_output=True, cwd=ROOT,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(result.stderr)

    def test_submit_wider_umbrella_scales_windows_and_thermalization(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    sys.executable, str(CAMPAIGN), "submit", "12",
                    "--dry-run",
                    "--campaign-dir", directory,
                    "--julia", "julia",
                    "--umbrella-max", "0.55",
                ],
                check=True, text=True, capture_output=True, cwd=ROOT,
            )
        self.assertIn("--umbrella-windows=79", result.stdout)
        self.assertIn("--umbrella-max=0.55", result.stdout)
        self.assertIn("--thermalization-sweeps=45630", result.stdout)
        self.assertIn("--max-thermalization-sweeps=228150", result.stdout)

    def test_submit_unvalidated_profile_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            profile_dir = Path(directory) / "profiles"
            profile_dir.mkdir()
            payload = json.loads((ROOT / "configs/umbrella_profiles/L12.json").read_text())
            payload["validated"] = False
            (profile_dir / "L12.json").write_text(json.dumps(payload))
            result = subprocess.run(
                [
                    sys.executable, str(CAMPAIGN), "submit", "12",
                    "--dry-run",
                    "--profile-dir", str(profile_dir),
                    "--campaign-dir", directory,
                    "--julia", "julia",
                ],
                text=True, capture_output=True, cwd=ROOT,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("validated", result.stderr.lower() + result.stdout.lower())

    def test_plot_csv_columns_and_canonical_gate(self):
        ok = combined_row(12, -0.6, -1.86421, [0.62, 0.625], [0.0, 0.0], bootstrap=1)
        bad = combined_row(12, -0.6, -1.86421, [0.62, 0.70], [0.0, 0.0], bootstrap=1)
        for row in (ok, bad):
            self.assertEqual(
                set(row),
                {
                    "t", "Z", "m2", "L", "U4", "uncertainty", "warning_status",
                    "source_U4_min", "source_U4_max", "canonical_combined_z",
                },
            )
        self.assertEqual(ok["warning_status"], "ok")
        self.assertEqual(bad["warning_status"], "source_disagreement")
        self.assertGreater(bad["canonical_combined_z"], CANONICAL_Z_MAX)
        self.assertAlmostEqual(ok["t"], scan_t(-1.86421))
        self.assertAlmostEqual(ok["uncertainty"], 0.0025)

    def test_analyze_two_replica_statistics(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        from umbrella_binder_campaign import analyze_run_dir

        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "L6"
            stats = run_dir / "statistics"
            stats.mkdir(parents=True)
            write_tiny_umbrella_csv(stats / "r0.csv", binder_shift=0.0)
            write_tiny_umbrella_csv(stats / "r1.csv", binder_shift=0.0)
            report_dir = Path(directory) / "reports"
            rows = analyze_run_dir(run_dir, report_dir, bootstrap=1, dry_run=False)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["L"], 6)
            self.assertEqual(rows[0]["warning_status"], "ok")
            self.assertTrue((report_dir / "r0.json").is_file())

    def test_extend_disagreement_doubles_target_and_clears_marker(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        from umbrella_binder_campaign import (
            disagreement_masses, extend_row, mass_key, write_manifest,
        )
        import csv as csvlib

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "L12"
            for name in ("complete", "progress"):
                (run_dir / name).mkdir(parents=True)
            analysis = root / "binder.csv"
            analysis.write_text(
                "t,Z,m2,L,U4,uncertainty,warning_status\n"
                "0,-0.6,-1.95,12,0.66,0,ok\n"
                "1,-0.6,-1.75,12,0.1,0,source_disagreement\n",
                encoding="utf-8",
            )
            self.assertEqual(disagreement_masses(analysis, 12), {mass_key(-1.75)})
            header = (
                "task_id,L,Z,m2,replica,samples,min_samples,max_samples,"
                "collection_shard_samples,init_phase,checkpoint_path,"
                "completion_marker,progress_marker,lock_path,shard_dir,"
                "max_continuations,runtime_budget_minutes\n"
            )
            rows_text = []
            parsed = []
            for task, m2, phase in (
                (0, "-1.95", "disordered"),
                (1, "-1.75", "disordered"),
                (2, "-1.75", "ordered"),
            ):
                marker = run_dir / "complete" / f"{task}.complete"
                progress = run_dir / "progress" / f"{task}.json"
                marker.write_text('{"complete": true, "state": "complete"}\n')
                progress.write_text(json.dumps({
                    "samples": 4000, "target_samples": 4000, "decision": "complete",
                    "committed_shards": [], "checkpoint": str(run_dir / f"{task}.jld2"),
                }))
                line = (
                    f"{task},12,-0.6,{m2},0,4000,4000,4000,500,{phase},"
                    f"{run_dir / f'{task}.jld2'},{marker},{progress},"
                    f"{run_dir / f'{task}.lock'},{run_dir / 'shards' / str(task)},20,360\n"
                )
                rows_text.append(line)
            (run_dir / "manifest.csv").write_text(header + "".join(rows_text), encoding="utf-8")
            with (run_dir / "manifest.csv").open() as handle:
                parsed = list(csvlib.DictReader(handle))
            masses = disagreement_masses(analysis, 12)
            for row in parsed:
                if mass_key(row["m2"]) in masses:
                    self.assertEqual(extend_row(row, 0, dry_run=False), 8000)
            write_manifest(run_dir / "manifest.csv", parsed)
            keep = json.loads((run_dir / "progress" / "0.json").read_text())
            self.assertEqual(keep["target_samples"], 4000)
            self.assertTrue((run_dir / "complete" / "0.complete").is_file())
            bumped = json.loads((run_dir / "progress" / "1.json").read_text())
            self.assertEqual(bumped["target_samples"], 8000)
            self.assertEqual(bumped["decision"], "collecting")
            self.assertFalse((run_dir / "complete" / "1.complete").is_file())
            self.assertFalse((run_dir / "complete" / "2.complete").is_file())
            with (run_dir / "manifest.csv").open() as handle:
                manifest_rows = list(csvlib.DictReader(handle))
            self.assertEqual(manifest_rows[0]["min_samples"], "4000")
            self.assertEqual(manifest_rows[1]["min_samples"], "8000")
            self.assertEqual(manifest_rows[2]["max_samples"], "8000")

    def test_plot_umbrella_pm2_writes_normalized_density(self):
        with tempfile.TemporaryDirectory() as directory:
            campaign = Path(directory)
            stats = campaign / "L6" / "statistics"
            stats.mkdir(parents=True)
            write_tiny_umbrella_csv(stats / "r0_disordered.csv", binder_shift=0.0)
            text = (stats / "r0_disordered.csv").read_text()
            (stats / "r0_disordered.csv").write_text(
                text.replace("# sampler=umbrella_exchange\n",
                             "# sampler=umbrella_exchange\n# init_phase=disordered\n"),
            )
            output = campaign / "pm2.png"
            result = subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts/plot_umbrella_pm2.py"),
                    "--L", "6", "--Z", "-0.6", "--m2", "-1.86421",
                    "--campaign-dir", str(campaign),
                    "--output", str(output),
                ],
                check=True, text=True, capture_output=True, cwd=ROOT,
            )
            self.assertTrue(output.is_file())
            csv_path = output.with_suffix(".csv")
            self.assertTrue(csv_path.is_file())
            rows = list(__import__("csv").DictReader(csv_path.open()))
            self.assertGreater(len(rows), 1)
            self.assertIn("P", rows[0])
            self.assertIn("MP", rows[0])
            self.assertIn("M2P", rows[0])
            self.assertTrue(output.with_name(output.stem + "_MP.png").is_file())
            self.assertTrue(output.with_name(output.stem + "_M2P.png").is_file())
            self.assertIn("wrote", result.stdout)


def write_tiny_umbrella_csv(path: Path, *, binder_shift: float) -> None:
    samples = 8
    replicas = 2
    centers = (0.08, 0.12)
    kappa = 50.0
    lines = [
        "# schema_version=3",
        "# sampler=umbrella_exchange",
        "# L=6",
        "# Z=-0.6",
        "# m2=-1.86421",
        f"# samples_per_window={samples}",
        f"# umbrella_replicas={replicas}",
        "trajectory,slot,walker_id,umbrella_center,umbrella_kappa,M,M2,M4,Q,G,acceptance_rate",
    ]
    for time in range(samples):
        for slot, center in enumerate(centers, start=1):
            m2 = center + 0.002 * (time - 3.5) + binder_shift
            m = m2 ** 0.5
            m4 = m2 ** 2
            lines.append(
                f"{time},{slot},{slot},{center},{kappa},{m},{m2},{m4},1,1,0.8"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
