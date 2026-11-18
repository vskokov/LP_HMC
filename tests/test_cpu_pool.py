import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cpu_pool  # noqa: E402


class CpuPoolTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "pool"

    def tearDown(self):
        self.tmp.cleanup()

    def _state(self, name):
        return json.loads((self.root / "state" / f"{name}.json").read_text())["state"]

    def test_runs_tasks_respects_markers_and_failures(self):
        out = Path(self.tmp.name)
        for i in range(5):
            m = out / f"ok{i}.done"
            cpu_pool.submit_task(f"ok{i}", [sys.executable, "-c",
                                 f"import os,pathlib;assert os.environ['OMP_NUM_THREADS']=='1';"
                                 f"pathlib.Path(r'{m}').write_text('x')"],
                                 root=self.root, done_marker=m, group="g")
        pre = out / "pre.done"
        pre.write_text("x")
        cpu_pool.submit_task("pre", [sys.executable, "-c", "raise SystemExit(3)"],
                             root=self.root, done_marker=pre)
        cpu_pool.submit_task("bad", [sys.executable, "-c", "raise SystemExit(4)"], root=self.root)
        cpu_pool.submit_task("nomarker", [sys.executable, "-c", "pass"], root=self.root,
                             done_marker=out / "never")
        rc = cpu_pool.Pool(self.root, workers=3, reserve_gb=0.0, poll=0.05).run(exit_when_empty=True)
        self.assertEqual(rc, 0)
        for i in range(5):
            self.assertEqual(self._state(f"ok{i}"), "done")
        self.assertEqual(self._state("pre"), "done")       # never launched: marker existed
        self.assertFalse((self.root / "logs" / "pre.log").exists())
        self.assertEqual(self._state("bad"), "failed")
        self.assertEqual(self._state("nomarker"), "failed")  # rc 0 but marker missing

    def test_retry_and_priority(self):
        order = Path(self.tmp.name) / "order.txt"
        for name, prio in (("low", 0), ("high", 5)):
            cpu_pool.submit_task(name, [sys.executable, "-c",
                                 f"open(r'{order}','a').write('{name}\\n')"],
                                 root=self.root, priority=prio)
        flag = Path(self.tmp.name) / "flag"
        cpu_pool.submit_task("flaky", [sys.executable, "-c",
                             f"import pathlib,sys;p=pathlib.Path(r'{flag}');"
                             f"sys.exit(0) if p.exists() else (p.write_text('1'), sys.exit(1))"],
                             root=self.root, max_retries=1, priority=-1)
        cpu_pool.Pool(self.root, workers=1, reserve_gb=0.0, poll=0.05).run(exit_when_empty=True)
        self.assertEqual(order.read_text().split(), ["high", "low"])
        self.assertEqual(self._state("flaky"), "done")

    def test_dependencies(self):
        log = Path(self.tmp.name) / "dep.txt"
        cpu_pool.submit_task("child", [sys.executable, "-c", f"open(r'{log}','a').write('child\\n')"],
                             root=self.root, priority=10, after=["parent"])
        cpu_pool.submit_task("parent", [sys.executable, "-c",
                             f"import time;time.sleep(0.2);open(r'{log}','a').write('parent\\n')"],
                             root=self.root)
        cpu_pool.submit_task("orphan", ["true"], root=self.root, after=["bad"])
        cpu_pool.submit_task("bad", ["false"], root=self.root)
        cpu_pool.Pool(self.root, workers=4, reserve_gb=0.0, poll=0.05).run(exit_when_empty=True)
        self.assertEqual(log.read_text().split(), ["parent", "child"])
        self.assertEqual(self._state("orphan"), "failed")

    def test_resubmit_is_idempotent(self):
        p1 = cpu_pool.submit_task("a", ["true"], root=self.root, priority=1)
        t1 = json.loads(p1.read_text())["submitted"]
        time.sleep(0.01)
        cpu_pool.submit_task("a", ["false"], root=self.root, priority=9)
        payload = json.loads(p1.read_text())
        self.assertEqual(payload["cmd"], ["true"])
        self.assertEqual(payload["submitted"], t1)
        with self.assertRaises(ValueError):
            cpu_pool.submit_task("bad name/", ["true"], root=self.root)


if __name__ == "__main__":
    unittest.main()
