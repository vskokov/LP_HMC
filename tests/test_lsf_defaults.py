"""Tests for lsf_defaults.py."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lsf_defaults import bsub_command_for_script, submit_bsub_script  # noqa: E402


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

    def test_submit_bsub_script_invokes_parsed_command(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "lsf_job.sh"
            script.write_text(
                "#!/usr/bin/env bash\n#BSUB -J test\ntrue\n", encoding="utf-8"
            )
            with patch("lsf_defaults.subprocess.run") as run:
                submit_bsub_script(script, dry_run=False)
            run.assert_called_once_with(
                bsub_command_for_script(script), check=True
            )

    def test_submit_bsub_script_dry_run_does_not_invoke_bsub(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "lsf_job.sh"
            script.write_text("#!/usr/bin/env bash\n#BSUB -J test\ntrue\n", encoding="utf-8")
            with patch("lsf_defaults.subprocess.run") as run:
                submit_bsub_script(script, dry_run=True)
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
