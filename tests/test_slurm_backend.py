"""Slurm backend: script generation and the exit-75 self-resubmission chain (fake sbatch)."""

import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import slurm_backend as sb  # noqa: E402


class SlurmBackendTest(unittest.TestCase):
    def test_chain_until_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            bindir = tmp / "bin"; bindir.mkdir()
            log = tmp / "sbatch.log"
            fake = bindir / "sbatch"   # runs the script synchronously, like an instant scheduler
            fake.write_text(f'#!/bin/bash\necho "${{@: -1}}" >> {log}\nbash "${{@: -1}}"\n')
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
            wd = tmp / "run"; done = wd / "complete.json"
            counter = tmp / "calls"
            # fake simulation: exit 75 twice, then write the completion marker
            prog = tmp / "prog.sh"
            prog.write_text(f'n=$(( $(cat {counter} 2>/dev/null || echo 0) + 1 )); echo $n > {counter}\n'
                            f'[[ $n -lt 3 ]] && exit 75\necho ok > {done}\nexit 0\n')
            cfg = sb.load_config(Path("/nonexistent"), {"modules": [], "max_continuations": 10})
            rows = [{"out": str(wd)}]
            env = os.environ.copy(); env["PATH"] = f"{bindir}:{env['PATH']}"
            old = os.environ["PATH"]; os.environ["PATH"] = env["PATH"]
            try:
                n = sb.submit_rows_slurm(rows, env_of=lambda r: {"CVU_X": "1"}, command=["bash", str(prog)],
                                         workdir_of=lambda r: wd, done_of=lambda r: done,
                                         label=lambda r: "job", cfg=cfg)
            finally:
                os.environ["PATH"] = old
            self.assertEqual(n, 1)
            self.assertTrue(done.is_file())
            self.assertEqual(counter.read_text().strip(), "3")
            self.assertEqual((wd / "slurm" / "continuations").read_text().strip(), "2")
            self.assertEqual(len(log.read_text().splitlines()), 3)
            text = (wd / "slurm" / "job.sh").read_text()
            self.assertIn("#SBATCH --gres=gpu:l40s:1", text)
            self.assertIn("export CVU_RUNTIME=6000", text)
            # complete rows are skipped
            self.assertEqual(sb.submit_rows_slurm(rows, env_of=lambda r: {}, command=["true"],
                                                  workdir_of=lambda r: wd, done_of=lambda r: done,
                                                  label=lambda r: "job", cfg=cfg, dry_run=True), 0)

    def test_continuation_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp); bindir = tmp / "bin"; bindir.mkdir()
            fake = bindir / "sbatch"; fake.write_text('#!/bin/bash\nbash "${@: -1}"\n')
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
            wd = tmp / "run"
            cfg = sb.load_config(Path("/nonexistent"), {"modules": [], "max_continuations": 4})
            old = os.environ["PATH"]; os.environ["PATH"] = f"{bindir}:{old}"
            try:
                sb.submit_rows_slurm([{}], env_of=lambda r: {}, command=["bash", "-c", "exit 75"],
                                     workdir_of=lambda r: wd, done_of=lambda r: wd / "done",
                                     label=lambda r: "j", cfg=cfg)
            finally:
                os.environ["PATH"] = old
            self.assertEqual((wd / "slurm" / "continuations").read_text().strip(), "4")


if __name__ == "__main__":
    unittest.main()
