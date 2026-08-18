"""Tests for lsf_defaults.py."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lsf_defaults import (  # noqa: E402
    bsub_command_for_script,
    expand_lsf_index_spec,
    submit_bsub_script,
)


class LsfDefaultsTests(unittest.TestCase):
    def test_bsub_command_for_script_parses_directives(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "lsf_job.sh"
            script.write_text(
                """#!/usr/bin/env bash
#BSUB -J "pilot[1-2]"
#BSUB -q short_gpu
#BSUB -W 120
#BSUB -R "select[h100] rusage[mem=24]"
set -euo pipefail
echo hello
""",
                encoding="utf-8",
            )
            command = bsub_command_for_script(script)
            self.assertEqual(command[0], "bsub")
            self.assertIn("-J", command)
            self.assertEqual(command[command.index("-J") + 1], "pilot[1-2]")
            self.assertIn("-q", command)
            self.assertEqual(command[command.index("-q") + 1], "short_gpu")
            self.assertEqual(command[-2:], ["bash", str(script.resolve())])

    def test_bsub_command_can_override_job_name_for_sparse_array(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "lsf_job.sh"
            script.write_text(
                "#!/usr/bin/env bash\n#BSUB -J \"nlf_run[1-8]\"\ntrue\n",
                encoding="utf-8",
            )
            command = bsub_command_for_script(script, job_name="nlf_run[2,5]")
            self.assertEqual(command[command.index("-J") + 1], "nlf_run[2,5]")

    def test_expand_lsf_index_spec_handles_ranges_and_lists(self):
        self.assertEqual(expand_lsf_index_spec("1-2"), [1, 2])
        self.assertEqual(expand_lsf_index_spec("1,4,7"), [1, 4, 7])
        self.assertEqual(expand_lsf_index_spec("1-2%4"), [1, 2])

    def test_submit_bsub_script_expands_array_into_scalar_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "lsf_job.sh"
            script.write_text(
                "#!/usr/bin/env bash\n#BSUB -J \"pilot[1-2]\"\ntrue\n",
                encoding="utf-8",
            )
            with patch("lsf_defaults.subprocess.run") as run:
                submit_bsub_script(script, dry_run=False)
            self.assertEqual(run.call_count, 2)
            names = [call.args[0][call.args[0].index("-J") + 1] for call in run.call_args_list]
            self.assertEqual(names, ["pilot_t0", "pilot_t1"])
            for call in run.call_args_list:
                job_name = call.args[0][call.args[0].index("-J") + 1]
                self.assertNotIn("[", job_name)
                env_spec = call.args[0][call.args[0].index("-env") + 1]
                self.assertIn("UMBRELLA_TASK_ID=", env_spec)
                self.assertIn("PROBE_ID=", env_spec)

    def test_submit_bsub_script_invokes_parsed_command(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "lsf_job.sh"
            script.write_text(
                "#!/usr/bin/env bash\n#BSUB -J test\ntrue\n", encoding="utf-8"
            )
            with patch("lsf_defaults.subprocess.run") as run:
                submit_bsub_script(script, dry_run=False)
            self.assertEqual(run.call_count, 1)
            called = run.call_args
            self.assertEqual(called.kwargs.get("check"), True)
            env = called.kwargs["env"]
            self.assertTrue(env["HOME"].endswith("lsf_home"))
            self.assertEqual(env["LSB_JOB_SPOOLDIR"], str(Path(env["HOME"]) / ".lsbatch"))
            command = called.args[0]
            self.assertEqual(command[0], "bsub")
            self.assertEqual(command[1], "-env")
            self.assertIn("HOME=", command[2])
            self.assertIn("LSB_JOB_SPOOLDIR=", command[2])
            self.assertEqual(command[-2:], ["bash", str(script.resolve())])
            self.assertTrue((Path(env["HOME"]) / ".lsbatch").is_dir())

    def test_submit_bsub_script_dry_run_does_not_invoke_bsub(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "lsf_job.sh"
            script.write_text("#!/usr/bin/env bash\n#BSUB -J test\ntrue\n", encoding="utf-8")
            with patch("lsf_defaults.subprocess.run") as run:
                submit_bsub_script(script, dry_run=True)
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
