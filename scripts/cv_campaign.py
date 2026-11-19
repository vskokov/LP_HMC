#!/usr/bin/env python3
"""GPU campaign driver for the quadratic-CV umbrella runs (scripts/cv_umbrella.jl).

Stages (each a manifest under runs/cv_umbrella/<stage>/manifest.csv):

  s2_zm2       symmetric->lamellar coexistence at Z=-2 (period p=6), L=18,24,30;
               shell CV on khat^2=1, ladder and kappa scaled from the L=12/18 pilots.
  s2_zm1172    Z=-8 sin^2(pi/8) (p=8): mass pilots at L=16, then production
               (add masses with --m2 once the pilot coexistence point is known).
  lro          unbiased lamellar-phase runs for S(q*) vs L (kappa=0, independent
               replicas, lamellar start, no transport gate): Z=-2 (p=6) and Z=-4 (p=4).
  s2_zm1172_prod  p=8 production, L=16/24/32, two masses per L around the pilot
               transition m2 ~ -2.5 (L=16).
  uline        uniform-line gap fill near the termination (M^2 CV): Z=-0.80..-0.95,
               L=24/32, 3 masses x ordered/disordered starts (gate G1).
  validate     cluster acceptance run: the local reference s2 point (Z=-2, L=12,
               m2=-1.73) with a new seed; compare with reports/cv_umbrella/s2/Zm2/L12.

Backends: ``--backend tsp`` (local A6000, task-spooler) or ``--backend slurm``
(scripts/slurm_backend.py, config configs/hpc/hazel.json; default when ``sbatch``
is on PATH).  Slurm jobs run <=2 h, checkpoint (exit 75) and resubmit themselves.
Set LP_HMC_RUNS to put run directories on cluster scratch/project storage.

Scaling rules (reference: L=12, eps=0.039, nlf=26, kappa=2e4, 72 windows):
  eps ~ L^-3/4 (HMC volume scaling), nlf keeps tau ~ 1;  kappa ~ V (fixed relative
  stiffness of an intensive CV);  windows ~ L^{3/2} (window width ~ V^-1/2).

Usage:
  python3 scripts/cv_campaign.py prepare
  python3 scripts/cv_campaign.py submit [--stage s2_zm2 ...] [--dry-run]
  python3 scripts/cv_campaign.py status
"""

from __future__ import annotations

import argparse
import math
import os
import shutil
from pathlib import Path

import slurm_backend
from tsp_campaign import ROOT, julia_command, read_manifest, status_rows, submit_rows, tag, write_manifest

BASE = Path(os.environ.get("LP_HMC_RUNS", ROOT / "runs")) / "cv_umbrella"
SCRIPT = ROOT / "scripts" / "cv_umbrella.jl"
Z_P8 = -8 * math.sin(math.pi / 8) ** 2           # -1.171573
Q_P8 = 4 * math.sin(math.pi / 8) ** 2            # 0.585786


def hmc(L: int) -> dict:
    eps = 0.039 * (12 / L) ** 0.75
    return {"CVU_EPS": f"{eps:.4f}", "CVU_NLF": str(max(10, round(1.0 / eps)))}


def ladder(L: int) -> dict:
    return {"CVU_WINDOWS": str(int(round(72 * (L / 12) ** 1.5 / 4) * 4)),
            "CVU_KAPPA": f"{2e4 * (L / 12) ** 3:.0f}"}


def umbrella_row(stage, Z, q, L, m2, seed, smax=0.5, min_rt=0.3, max_therm=None, samples=4000,
                 kind="shell", init="umbrella", therm=16000):
    suffix = "" if init == "umbrella" else f"_{init}"
    out = BASE / stage / f"Z{tag(round(Z, 4))}" / f"L{L}" / f"m2{tag(m2)}_s{seed}{suffix}"
    row = {"stage": stage, "L": L, "Z": f"{Z:.6f}", "m2": m2, "seed": seed, "out": str(out),
           "CVU_L": L, "CVU_Z": f"{Z:.6f}", "CVU_M2": m2, "CVU_KIND": kind, "CVU_INIT": init,
           "CVU_SHELL_Q": f"{q:.6f}", "CVU_SMIN": 0.0, "CVU_SMAX": smax, "CVU_POWER": 1.3,
           "CVU_THERM": therm, "CVU_MAX_THERM": max_therm or int(4000 * L ** 1.5 / 3),
           "CVU_MIN_RT": min_rt, "CVU_MIN_SWAP": 0.2, "CVU_SAMPLES": samples, "CVU_SKIP": 2,
           "CVU_CHECK_EVERY": 1000, "CVU_SEED": seed, "CVU_OUT": str(out)}
    row.update(hmc(L))
    row.update(ladder(L))
    return row


def lro_row(Z, q, L, m2, s0, seed, replicas=4, samples=3000, skip=5):
    out = BASE / "lro" / f"Z{tag(round(Z, 4))}" / f"L{L}" / f"m2{tag(m2)}_s{seed}"
    row = {"stage": "lro", "L": L, "Z": f"{Z:.6f}", "m2": m2, "seed": seed, "out": str(out),
           "CVU_L": L, "CVU_Z": f"{Z:.6f}", "CVU_M2": m2, "CVU_KIND": "shell",
           "CVU_SHELL_Q": f"{q:.6f}", "CVU_WINDOWS": replicas, "CVU_SMIN": s0, "CVU_SMAX": s0,
           "CVU_KAPPA": 0, "CVU_POWER": 1.0, "CVU_INIT": "umbrella",
           "CVU_THERM": 20000, "CVU_MAX_THERM": 20000, "CVU_MIN_RT": 0, "CVU_MIN_SWAP": 0,
           "CVU_SAMPLES": samples, "CVU_SKIP": skip, "CVU_CHECK_EVERY": 1000,
           "CVU_SEED": seed, "CVU_OUT": str(out)}
    row.update(hmc(L))
    return row


def stage_rows(stage: str) -> list[dict]:
    if stage == "s2_zm2":
        # m_eq(L): -1.730 (L12), -1.835 (L18); reweighting covers +-0.3 around m2.
        return [umbrella_row(stage, -2.0, 1.0, 18, -1.83, 31, max_therm=250000),
                umbrella_row(stage, -2.0, 1.0, 24, -1.88, 32, max_therm=400000),
                umbrella_row(stage, -2.0, 1.0, 30, -1.90, 33, max_therm=600000)]
    if stage == "s2_zm1172":
        # Pilot masses bracket the expected line (Hartree -1.62 shifted by the
        # Z=-2 lattice offset ~ -0.4); uniform order competes here, M is recorded.
        return [umbrella_row(stage, Z_P8, Q_P8, 16, m2, 40 + i, smax=0.4, max_therm=150000)
                for i, m2 in enumerate((-1.8, -2.1, -2.4))]
    if stage == "lro":
        rows = []
        # Z=-2: m2=-3 (MF single-mode A^2/2 = 0.67); Z=-4: m2=0 (A^2/2 = 0.67).
        for L in (12, 18, 24, 30, 36):
            rows.append(lro_row(-2.0, 1.0, L, -3.0, 0.6, 50 + L))
        for L in (12, 16, 20, 24, 32, 40):
            rows.append(lro_row(-4.0, 2.0, L, 0.0, 0.6, 60 + L))
        return rows
    if stage == "s2_zm1172_prod":
        # From the L=16 pilots: chi_s peaks at m2 ~ -2.46..-2.52 (twopeak there, ordered
        # peak d_eff ~ 1.6, no uniform order).  The line moves down with L (Z=-2: -1.73 ->
        # -1.835 for L 12 -> 18), so two masses per L bracket the expected m_eq(L).
        rows = []
        for L, masses, mt in ((16, (-2.47, -2.53), 300000), (24, (-2.49, -2.55), 500000),
                              (32, (-2.51, -2.57), 800000)):
            for k, m2 in enumerate(masses):
                rows.append(umbrella_row(stage, Z_P8, Q_P8, L, m2, 800 + 10 * k + L,
                                         smax=0.45, max_therm=mt))
        return rows
    if stage == "uline":
        # Uniform-line gap fill (G1): M^2 umbrella, 3 masses around the extrapolated
        # chi_max location x 2 starts (ordered/disordered), L=24 and 32.  Profile from
        # the termination campaign (smax 0.55, kappa ~ V, windows ~ L^1.5), more samples.
        # Convert for analyze_transition_order.py with scripts/cv_to_schema3.py.
        rows = []
        for Z, mc in ULINE_CENTERS.items():
            for L in (24, 32):
                for k, dm in enumerate((-0.02, 0.0, 0.02)):
                    m2 = round(mc[L] + dm, 4)
                    for init in ("disordered", "ordered"):
                        r = umbrella_row(stage, Z, 0.0, L, m2, 700 + 10 * k + (init == "ordered"),
                                         smax=0.55, min_rt=0.3, max_therm=600000,
                                         samples=8000, kind="M2", init=init, therm=20000)
                        r.pop("CVU_SHELL_Q")
                        r["CVU_WINDOWS"] = str(int(round(int(r["CVU_WINDOWS"]) * 1.1 / 4) * 4))
                        rows.append(r)
        return rows
    if stage == "validate":
        # Same parameters as the local reference run s2/Zm2/L12/m2m1p73_s21, new seed.
        return [umbrella_row(stage, -2.0, 1.0, 12, -1.73, 121)]
    raise SystemExit(f"unknown stage {stage}")


# m2 at chi_max, extrapolated from L=12-24 (reports/transition_order/summary.csv).
ULINE_CENTERS = {-0.80: {24: -2.195, 32: -2.200}, -0.85: {24: -2.290, 32: -2.297},
                 -0.90: {24: -2.384, 32: -2.388}, -0.95: {24: -2.487, 32: -2.490}}

STAGES = ("s2_zm2", "s2_zm1172", "lro")
ALL_STAGES = STAGES + ("validate", "uline", "s2_zm1172_prod")


def manifest(stage: str) -> Path:
    return BASE / stage / "manifest.csv"


def env_of(row: dict) -> dict:
    env = {k: v for k, v in row.items() if k.startswith("CVU_") and v != ""}
    env["CVU_GPU"] = "true"
    return env


def is_complete(row: dict) -> bool:
    return (Path(row["out"]) / "complete.json").is_file()


def label(row: dict) -> str:
    return f"cvu_{row['stage']}_Z{tag(round(float(row['Z']), 4))}_L{row['L']}_m2{tag(float(row['m2']))}_s{row['seed']}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=("tsp", "slurm"),
                    default="slurm" if shutil.which("sbatch") else "tsp")
    ap.add_argument("--config", type=Path, help="Slurm JSON config (default configs/hpc/hazel.json)")
    ap.add_argument("--gpu", help="Slurm GPU type, e.g. l40s, a100, h100, rtx_6000_pro")
    ap.add_argument("--runtime-minutes", type=int, help="simulation budget per Slurm job")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare"); p.add_argument("--stage", nargs="+", default=list(STAGES))
    s = sub.add_parser("submit"); s.add_argument("--stage", nargs="+", default=list(STAGES))
    s.add_argument("--dry-run", action="store_true")
    t = sub.add_parser("status"); t.add_argument("--stage", nargs="+", default=list(STAGES))
    args = ap.parse_args()
    cfg = slurm_backend.load_config(args.config, {"gpu_type": args.gpu,
                                                  "runtime_minutes": args.runtime_minutes})
    done_of = lambda r: Path(r["out"]) / "complete.json"
    for stage in args.stage:
        if stage not in ALL_STAGES:
            raise SystemExit(f"unknown stage {stage}")
        if args.cmd == "prepare":
            write_manifest(manifest(stage), stage_rows(stage))
            print(f"{stage}: wrote {manifest(stage)}")
            continue
        rows = read_manifest(manifest(stage))
        print(stage, end=": ")
        if args.backend == "slurm":
            if args.cmd == "submit":
                n = slurm_backend.submit_rows_slurm(
                    rows, env_of=env_of, workdir_of=lambda r: Path(r["out"]), done_of=done_of,
                    command=[cfg["julia"], "--startup-file=no", f"--project={ROOT}", str(SCRIPT)],
                    label=label, cfg=cfg, dry_run=args.dry_run)
                print(f"{n} job chains started")
            else:
                slurm_backend.status_rows_slurm(rows, done_of=done_of, label=label)
        elif args.cmd == "submit":
            submit_rows(rows, command=lambda r: julia_command(SCRIPT, env=env_of(r)),
                        is_complete=is_complete, label=label, dry_run=args.dry_run)
        else:
            status_rows(rows, is_complete=is_complete, label=label)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
