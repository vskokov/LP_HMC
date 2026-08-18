"""Tests for lsf_defaults.py."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lsf_defaults import submit_bsub_script  # noqa: E402


class LsfDefaultsTests(unittest.TestCase):
    def test_submit_bsub_script_uses_shared_filesystem_path(self):
        script = Path("/share/project/runs/L16/lsf_job.sh")
        with patch("lsf_defaults.subprocess.run") as run:
            submit_bsub_script(script, dry_run=False)
        run.assert_called_once_with(["bsub", "-Zs", str(script.resolve())], check=True)

    def test_submit_bsub_script_dry_run_does_not_invoke_bsub(self):
        script = Path("/share/project/runs/L16/lsf_job.sh")
        with patch("lsf_defaults.subprocess.run") as run:
            submit_bsub_script(script, dry_run=True)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
