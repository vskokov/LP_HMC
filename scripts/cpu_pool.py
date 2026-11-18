#!/usr/bin/env python3
"""File-backed CPU job scheduler for single-threaded simulation and analysis tasks.

Every task is a JSON file in ``<root>/tasks``.  A single ``run`` daemon launches
pending tasks on up to ``--workers`` CPU slots, subject to a free-memory admission
rule, and records state in ``<root>/state``.  Submissions made while the daemon is
running are picked up on the next scan, so campaign drivers can keep feeding it.

Typical use::

    python3 scripts/cpu_pool.py submit --name hartree_Zm1 --group hartree \
        -- python3 scripts/hartree_lattice.py --Z=-1
    nohup python3 scripts/cpu_pool.py run --workers 60 > runs/_cpu_pool/daemon.log 2>&1 &
    python3 scripts/cpu_pool.py status

Campaign drivers should call :func:`submit_task` directly.  Tasks are expected to
be resume-safe; a task whose ``done_marker`` already exists is never launched.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POOL = Path(os.environ.get("CPU_POOL_ROOT", ROOT / "runs" / "_cpu_pool"))
SINGLE_THREAD_ENV = {
    "JULIA_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "OMP_NUM_THREADS": "1",
    "FFTW_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
}
NAME_RE = re.compile(r"^[A-Za-z0-9_.+-]{1,160}$")
TERMINAL = {"done", "failed", "cancelled"}

sys.path.insert(0, str(Path(__file__).resolve().parent))
from umbrella_runtime import atomic_json  # noqa: E402


# --------------------------------------------------------------------------- paths
def _dirs(root: Path) -> dict[str, Path]:
    d = {k: root / k for k in ("tasks", "state", "logs")}
    for p in d.values():
        p.mkdir(parents=True, exist_ok=True)
    return d


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


# --------------------------------------------------------------------------- submit
def submit_task(
    name: str,
    cmd: list[str],
    *,
    root: Path = DEFAULT_POOL,
    env: dict[str, str] | None = None,
    cwd: str | Path | None = None,
    done_marker: str | Path | None = None,
    mem_gb: float = 0.5,
    priority: int = 0,
    group: str = "default",
    max_retries: int = 0,
    replace: bool = False,
    after: Iterable[str] = (),
) -> Path:
    """Register one task; returns its JSON path.  Existing tasks are kept unless replace."""
    if not NAME_RE.match(name):
        raise ValueError(f"invalid task name {name!r}")
    if not cmd:
        raise ValueError("empty command")
    d = _dirs(root)
    path = d["tasks"] / f"{name}.json"
    if path.exists() and not replace:
        return path
    payload = {
        "name": name,
        "cmd": [str(c) for c in cmd],
        "env": {str(k): str(v) for k, v in (env or {}).items()},
        "cwd": str(cwd or ROOT),
        "done_marker": str(done_marker) if done_marker else None,
        "mem_gb": float(mem_gb),
        "priority": int(priority),
        "group": group,
        "max_retries": int(max_retries),
        "after": [str(a) for a in after],
        "submitted": time.time(),
    }
    atomic_json(path, payload)
    if replace:
        with contextlib.suppress(FileNotFoundError):
            (d["state"] / f"{name}.json").unlink()
    return path


def load_tasks(root: Path) -> list[dict]:
    d = _dirs(root)
    tasks = []
    for p in sorted(d["tasks"].glob("*.json")):
        t = _read_json(p)
        if t is None:
            continue
        t["_state"] = _read_json(d["state"] / p.name) or {"state": "pending", "attempts": 0}
        tasks.append(t)
    return tasks


def _set_state(root: Path, name: str, **fields) -> dict:
    path = _dirs(root)["state"] / f"{name}.json"
    state = _read_json(path) or {"state": "pending", "attempts": 0}
    state.update(fields)
    atomic_json(path, state)
    return state


# --------------------------------------------------------------------------- memory
def mem_available_gb() -> float:
    with open("/proc/meminfo", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / 1024**2
    return float("inf")


def mem_total_gb() -> float:
    with open("/proc/meminfo", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) / 1024**2
    return float("inf")


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # Treat zombies as dead.
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
            return fh.read().split()[2] != "Z"
    except FileNotFoundError:
        return False


def _is_done(task: dict) -> bool:
    marker = task.get("done_marker")
    return bool(marker) and Path(marker).exists()


# --------------------------------------------------------------------------- daemon
class Pool:
    def __init__(self, root: Path, workers: int, reserve_gb: float, poll: float):
        self.root = root
        self.workers = workers
        self.reserve_gb = reserve_gb
        self.poll = poll
        self.running: dict[str, tuple[subprocess.Popen | None, int, float]] = {}
        self.stopping = False

    def log(self, msg: str) -> None:
        print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)

    # Adopt tasks left 'running' by a previous daemon.
    def recover(self) -> None:
        for t in load_tasks(self.root):
            st = t["_state"]
            if st.get("state") != "running":
                continue
            pid = st.get("pid")
            if _pid_alive(pid):
                self.running[t["name"]] = (None, pid, t["mem_gb"])
                self.log(f"adopted live task {t['name']} pid={pid}")
            else:
                new = "done" if _is_done(t) else "pending"
                _set_state(self.root, t["name"], state=new, pid=None, note="recovered")
                self.log(f"recovered stale task {t['name']} -> {new}")

    def reap(self) -> None:
        tasks = {t["name"]: t for t in load_tasks(self.root)}
        for name, (proc, pid, _) in list(self.running.items()):
            if proc is not None:
                rc = proc.poll()
                if rc is None:
                    continue
            else:
                if _pid_alive(pid):
                    continue
                rc = 0 if _is_done(tasks.get(name, {})) else -1
            del self.running[name]
            task = tasks.get(name, {})
            st = task.get("_state", {})
            if st.get("state") == "cancelled":
                continue
            ok = rc == 0 and (not task.get("done_marker") or _is_done(task))
            if ok:
                _set_state(self.root, name, state="done", rc=rc, end=time.time(), pid=None)
                self.log(f"done   {name}")
            elif st.get("attempts", 1) <= task.get("max_retries", 0):
                _set_state(self.root, name, state="pending", rc=rc, end=time.time(), pid=None)
                self.log(f"retry  {name} rc={rc}")
            else:
                _set_state(self.root, name, state="failed", rc=rc, end=time.time(), pid=None)
                self.log(f"FAILED {name} rc={rc}")

    def pending(self) -> list[dict]:
        out = []
        tasks = load_tasks(self.root)
        states = {t["name"]: t["_state"].get("state", "pending") for t in tasks}
        for t in tasks:
            st = states[t["name"]]
            if st != "pending" or t["name"] in self.running:
                continue
            if _is_done(t):
                _set_state(self.root, t["name"], state="done", note="marker present")
                continue
            deps = [states.get(a, "missing") for a in t.get("after", [])]
            if any(d in ("failed", "cancelled", "missing") for d in deps):
                _set_state(self.root, t["name"], state="failed", note="dependency failed")
                self.log(f"FAILED {t['name']} (dependency failed)")
                continue
            if any(d != "done" for d in deps):
                continue
            out.append(t)
        out.sort(key=lambda t: (-t.get("priority", 0), t.get("submitted", 0), t["name"]))
        return out

    def launch(self, task: dict) -> None:
        d = _dirs(self.root)
        env = os.environ.copy()
        env.update(SINGLE_THREAD_ENV)
        env.update(task.get("env", {}))
        log_path = d["logs"] / f"{task['name']}.log"
        attempts = task["_state"].get("attempts", 0) + 1
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"\n=== attempt {attempts} {time.ctime()} :: {' '.join(task['cmd'])}\n")
        fh = log_path.open("a", encoding="utf-8")
        proc = subprocess.Popen(
            task["cmd"], cwd=task.get("cwd") or ROOT, env=env, stdout=fh,
            stderr=subprocess.STDOUT, start_new_session=True,
        )
        fh.close()
        self.running[task["name"]] = (proc, proc.pid, task.get("mem_gb", 0.5))
        _set_state(self.root, task["name"], state="running", pid=proc.pid,
                   start=time.time(), attempts=attempts, log=str(log_path))
        self.log(f"start  {task['name']} pid={proc.pid}")

    def admit(self, task: dict) -> bool:
        need = task.get("mem_gb", 0.5)
        committed = sum(m for _, _, m in self.running.values())
        if committed + need > mem_total_gb() - self.reserve_gb:
            return False
        return mem_available_gb() - need >= self.reserve_gb

    def shutdown(self, *_):
        self.stopping = True

    def run(self, exit_when_empty: bool) -> int:
        signal.signal(signal.SIGTERM, self.shutdown)
        signal.signal(signal.SIGINT, self.shutdown)
        self.recover()
        self.log(f"pool root={self.root} workers={self.workers} reserve={self.reserve_gb}GB")
        while not self.stopping:
            self.reap()
            for t in self.pending():
                if len(self.running) >= self.workers or not self.admit(t):
                    break
                self.launch(t)
            if exit_when_empty and not self.running and not self.pending() and \
                    not any(t["_state"].get("state", "pending") == "pending"
                            for t in load_tasks(self.root)):
                break
            time.sleep(self.poll)
        if self.stopping:
            self.log("stopping: terminating running tasks and requeueing them")
            for name, (proc, pid, _) in self.running.items():
                with contextlib.suppress(ProcessLookupError, PermissionError):
                    os.killpg(pid, signal.SIGTERM)
                _set_state(self.root, name, state="pending", pid=None, note="daemon stopped")
            deadline = time.time() + 30
            for proc, pid, _ in self.running.values():
                while _pid_alive(pid) and time.time() < deadline:
                    time.sleep(0.2)
                if _pid_alive(pid):
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(pid, signal.SIGKILL)
                if proc is not None:
                    proc.poll()
        return 0


# --------------------------------------------------------------------------- CLI
def _select(tasks: Iterable[dict], names: list[str], group: str | None) -> list[dict]:
    out = []
    for t in tasks:
        if names and t["name"] not in names:
            continue
        if group and t.get("group") != group:
            continue
        out.append(t)
    return out


def cmd_status(args) -> int:
    tasks = _select(load_tasks(args.root), [], args.group)
    counts: dict[str, int] = {}
    for t in tasks:
        s = t["_state"].get("state", "pending")
        counts[s] = counts.get(s, 0) + 1
    by_group: dict[str, dict[str, int]] = {}
    for t in tasks:
        g = by_group.setdefault(t.get("group", "default"), {})
        s = t["_state"].get("state", "pending")
        g[s] = g.get(s, 0) + 1
    print(f"root={args.root}  total={len(tasks)}  " +
          "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    for g, c in sorted(by_group.items()):
        print(f"  [{g}] " + "  ".join(f"{k}={v}" for k, v in sorted(c.items())))
    if args.verbose:
        for t in tasks:
            st = t["_state"]
            if st.get("state") in ("running", "failed"):
                el = time.time() - st.get("start", time.time())
                print(f"  {st['state']:8s} {t['name']}  pid={st.get('pid')}  "
                      f"rc={st.get('rc')}  elapsed={el/60:.1f}min")
    return 0


def cmd_submit(args) -> int:
    env = dict(kv.split("=", 1) for kv in args.env)
    cmd = args.cmd[1:] if args.cmd and args.cmd[0] == "--" else args.cmd
    p = submit_task(args.name, cmd, root=args.root, env=env, cwd=args.cwd,
                    done_marker=args.done_marker, mem_gb=args.mem_gb,
                    priority=args.priority, group=args.group,
                    max_retries=args.max_retries, replace=args.replace,
                    after=args.after)
    print(p)
    return 0


def cmd_cancel(args) -> int:
    for t in _select(load_tasks(args.root), args.names, args.group):
        st = t["_state"]
        if st.get("state") in TERMINAL - {"failed"}:
            continue
        if st.get("state") == "running" and _pid_alive(st.get("pid")):
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(st["pid"], signal.SIGTERM)
        _set_state(args.root, t["name"], state="cancelled")
        print("cancelled", t["name"])
    return 0


def cmd_retry(args) -> int:
    for t in _select(load_tasks(args.root), args.names, args.group):
        if t["_state"].get("state") in ("failed", "cancelled"):
            _set_state(args.root, t["name"], state="pending", attempts=0)
            print("requeued", t["name"])
    return 0


def cmd_run(args) -> int:
    lock = args.root / "daemon.lock"
    _dirs(args.root)
    with lock.open("a+") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(f"another cpu_pool daemon owns {lock}", file=sys.stderr)
            return 2
        fh.seek(0); fh.truncate(); fh.write(f"pid={os.getpid()}\n"); fh.flush()
        return Pool(args.root, args.workers, args.reserve_gb, args.poll).run(args.exit_when_empty)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=DEFAULT_POOL)
    sub = ap.add_subparsers(dest="command", required=True)

    s = sub.add_parser("submit")
    s.add_argument("--name", required=True)
    s.add_argument("--group", default="default")
    s.add_argument("--env", action="append", default=[], metavar="K=V")
    s.add_argument("--cwd")
    s.add_argument("--done-marker")
    s.add_argument("--mem-gb", type=float, default=0.5)
    s.add_argument("--priority", type=int, default=0)
    s.add_argument("--max-retries", type=int, default=0)
    s.add_argument("--replace", action="store_true")
    s.add_argument("--after", action="append", default=[], metavar="TASK")
    s.add_argument("cmd", nargs=argparse.REMAINDER)
    s.set_defaults(func=cmd_submit)

    r = sub.add_parser("run")
    r.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 4))
    r.add_argument("--reserve-gb", type=float, default=6.0)
    r.add_argument("--poll", type=float, default=3.0)
    r.add_argument("--exit-when-empty", action="store_true")
    r.set_defaults(func=cmd_run)

    st = sub.add_parser("status")
    st.add_argument("--group")
    st.add_argument("-v", "--verbose", action="store_true")
    st.set_defaults(func=cmd_status)

    for nm, fn in (("cancel", cmd_cancel), ("retry", cmd_retry)):
        c = sub.add_parser(nm)
        c.add_argument("names", nargs="*")
        c.add_argument("--group")
        c.set_defaults(func=fn)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
