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
  s2_zm2_ext   Z=-2: L=36 (two masses) + second seeds at L=24/30.
  p9_pilot     p=9 (Z=-0.9358) shell-CV pilots at L=18, four masses (meeting region).
  p9_mixed     p=9 pilots on the mixed coordinate s = M^2 - 2 P_shell (L=18, four
               masses): the shell ladder could not cross the uniform(P~0)/modulated gap
               at m2 <= -2.5 (checkpoint diagnostic 2026-11-20).
  p8_shift     r5: p=8 shell CV at L=24/32 at the corrected (lower) masses.
  p8_mixed     r5: p=8 mixed CV (L=16/24, m2=-2.6..-3.0): uniform vs lamellar vs symmetric.
  p9_L27       r5: p=9 mixed CV at L=27 (second size for the L=18 coexistence).
  b8, b13      r8: band-CV symmetric->lamellar umbrellas at Z=-1.1716 (band 0.36-0.62) and
               Z=-1.3 (band 0.37-0.70), L=20/28/32, bands from the measured S(k) peak.
  bline        r10: re-placed b8/b13 masses (L20/28/32 near m2 = -2.34..-2.40).
  b8_mixed     r8: mixedband s = M^2 - 2 P_band at Z=-1.1716, L=20/28: uniform vs lamellar.
  uline_ext    r8: M^2 CV at Z=-1.0, -1.05 (renormalized moat closes), L=24/32.
  zeff2        r8: deeper unbiased S(k) points at Z=-1.5, -1.3, -1.1716 (L=48).
  zeff         r7: unbiased symmetric-phase S(k) (scripts/sk_symmetric.jl) on a (Z, m2) grid
               approaching the transitions, L=48 (+32/64 near m2_c): Z_eff(Z, m2), k2*.
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
SK_SCRIPT = ROOT / "scripts" / "sk_symmetric.jl"
SCRIPT_OF = {"zeff": SK_SCRIPT, "zeff2": SK_SCRIPT, "ulam": SK_SCRIPT, "ulam2": SK_SCRIPT, "zeff3": SK_SCRIPT, "zeff4": SK_SCRIPT,
             "zeff5": SK_SCRIPT, "zeff6": SK_SCRIPT, "ulam3": SK_SCRIPT, "zeff8": SK_SCRIPT, "ulam4": SK_SCRIPT, "zeff9": SK_SCRIPT, "ulam5": SK_SCRIPT,
             "zeffL": SK_SCRIPT, "ulamL": SK_SCRIPT}          # stages not driven by cv_umbrella.jl
Z_P8 = -8 * math.sin(math.pi / 8) ** 2           # -1.171573
Q_P8 = 4 * math.sin(math.pi / 8) ** 2            # 0.585786
Z_P9 = -8 * math.sin(math.pi / 9) ** 2           # -0.935822 (meeting region)
Q_P9 = 4 * math.sin(math.pi / 9) ** 2            # 0.467911


def hmc(L: int) -> dict:
    eps = 0.039 * (12 / L) ** 0.75
    return {"CVU_EPS": f"{eps:.4f}", "CVU_NLF": str(max(10, round(1.0 / eps)))}


def sk_row(stage, Z, L, m2, seed, samples=4000, skip=5, therm=20000, reps=8, kmax=3.0, init=None):
    out = BASE / stage / f"Z{tag(round(Z, 4))}" / f"L{L}" / f"m2{tag(m2)}_s{seed}"
    eps = 0.039 * (12 / L) ** 0.75
    return {"stage": stage, "L": L, "Z": f"{Z:.6f}", "m2": m2, "seed": seed, "out": str(out),
            "SK_L": L, "SK_Z": f"{Z:.6f}", "SK_M2": m2, "SK_REPS": reps, "SK_EPS": f"{eps:.4f}",
            "SK_NLF": max(10, round(1.0 / eps)), "SK_THERM": therm, "SK_SAMPLES": samples,
            "SK_SKIP": skip, "SK_KMAX": kmax, "SK_SEED": seed, "SK_OUT": str(out), "SK_GPU": "true",
            **({"SK_INIT": init[0], "SK_INIT_N": init[1]} if init else {})}


def ladder(L: int) -> dict:
    return {"CVU_WINDOWS": str(int(round(72 * (L / 12) ** 1.5 / 4) * 4)),
            "CVU_KAPPA": f"{2e4 * (L / 12) ** 3:.0f}"}


def umbrella_row(stage, Z, q, L, m2, seed, smax=0.5, min_rt=0.3, max_therm=None, samples=4000,
                 kind="shell", init="umbrella", therm=16000, min_swap=0.2):
    suffix = "" if init == "umbrella" else f"_{init}"
    out = BASE / stage / f"Z{tag(round(Z, 4))}" / f"L{L}" / f"m2{tag(m2)}_s{seed}{suffix}"
    row = {"stage": stage, "L": L, "Z": f"{Z:.6f}", "m2": m2, "seed": seed, "out": str(out),
           "CVU_L": L, "CVU_Z": f"{Z:.6f}", "CVU_M2": m2, "CVU_KIND": kind, "CVU_INIT": init,
           "CVU_SHELL_Q": f"{q:.6f}", "CVU_SMIN": 0.0, "CVU_SMAX": smax, "CVU_POWER": 1.3,
           "CVU_THERM": therm, "CVU_MAX_THERM": max_therm or int(4000 * L ** 1.5 / 3),
           "CVU_MIN_RT": min_rt, "CVU_MIN_SWAP": min_swap, "CVU_SAMPLES": samples, "CVU_SKIP": 2,
           "CVU_CHECK_EVERY": 1000, "CVU_SEED": seed, "CVU_OUT": str(out)}
    row.update(hmc(L))
    row.update(ladder(L))
    return row


def lro_row(Z, q, L, m2, s0, seed, replicas=4, samples=3000, skip=5, stage="lro"):
    out = BASE / stage / f"Z{tag(round(Z, 4))}" / f"L{L}" / f"m2{tag(m2)}_s{seed}"
    row = {"stage": stage, "L": L, "Z": f"{Z:.6f}", "m2": m2, "seed": seed, "out": str(out),
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
                umbrella_row(stage, -2.0, 1.0, 24, -1.88, 32, max_therm=700000),
                umbrella_row(stage, -2.0, 1.0, 30, -1.90, 33, max_therm=900000)]
        # max_therm raised 400k/600k -> 700k/900k (2026-11-20): with the fixed step the
        # L24/L30 chains were frozen; they resume with eps adaptation and reset transport.
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
    if stage == "lro2":
        # Reruns of the lro points with L >= 24: with the fixed CVU_EPS their HMC
        # acceptance was 0 (L >= 30) or 0.2 (L = 24), i.e. the fields never left the
        # initial lamellae.  New seeds; eps adapts during thermalisation.  L <= 20 lro
        # runs (acceptance 0.80-0.85) remain valid.
        return ([lro_row(-2.0, 1.0, L, -3.0, 0.6, 150 + L, stage=stage) for L in (24, 30, 36)] +
                [lro_row(-4.0, 2.0, L, 0.0, 0.6, 160 + L, stage=stage) for L in (24, 32, 40)])
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
    if stage == "s2_zm2_ext":
        # Z=-2 barrier scaling beyond the local L=18/24/30: L=36, plus independent second
        # seeds at L=24/30 (combined with the local runs in the analysis).
        return [umbrella_row(stage, -2.0, 1.0, 24, -1.88, 132, max_therm=500000),
                umbrella_row(stage, -2.0, 1.0, 30, -1.90, 133, max_therm=800000),
                umbrella_row(stage, -2.0, 1.0, 36, -1.92, 134, max_therm=1200000),
                umbrella_row(stage, -2.0, 1.0, 36, -1.96, 135, max_therm=1200000)]
    if stage == "p9_pilot":
        # Meeting region on the commensurate p=9 lattice (Z=-0.9358): shell-CV pilots
        # bracketing the region where the uniform line (m2 ~ -2.47 at L=24) and the
        # lamellar line meet; the M^2 coordinate (uniform order) is recorded as well.
        return [umbrella_row(stage, Z_P9, Q_P9, 18, m2, 900 + i, smax=0.45, max_therm=300000)
                for i, m2 in enumerate((-2.2, -2.35, -2.5, -2.65))]
    if stage == "p9_mixed":
        # Mixed CV s = M^2 - c P_shell, c = 2: monotone along the measured uniform ->
        # modulated(+offset) -> lamellar path at m2 = -2.65 (M^2 0.53 -> 0, P 0 -> 0.44),
        # so the ladder interpolates the gap the shell ladder skipped.  Uniform spacing,
        # kappa as p9_pilot (window width ~0.004), ~2 widths per window -> 240 windows.
        rows = []
        for i, m2 in enumerate((-2.2, -2.35, -2.5, -2.65)):
            r = umbrella_row(stage, Z_P9, Q_P9, 18, m2, 950 + i, smax=0.60, max_therm=600000,
                             kind="mixed", therm=50000)
            r.update({"CVU_MIX": 2.0, "CVU_SMIN": -0.95, "CVU_POWER": 1.0, "CVU_WINDOWS": 240})
            rows.append(r)
        return rows
    if stage == "p8_shift":
        # Run plan r5.  Workstation analysis of s2_zm1172(+_prod): m_eq = -2.65(2) at L=16
        # but < -2.70 at L=24 (disordered still ahead by ~9 kT at -2.70), so the L=24/32
        # prod masses (-2.49..-2.57) miss the transition.  Shell CV as s2_zm1172_prod.
        rows = []
        for L, masses, mt in ((24, (-2.75, -2.85), 750000), (32, (-2.78, -2.86, -2.94), 1200000)):
            for k, m2 in enumerate(masses):
                rows.append(umbrella_row(stage, Z_P8, Q_P8, L, m2, 860 + 10 * k + L,
                                         smax=0.5, max_therm=mt))
        return rows
    if stage == "p8_mixed":
        # Run plan r5.  Mixed CV s = M^2 - 2 P_shell at p=8: does uniform order (extrapolated
        # line m2 ~ -2.9..-3.0 at this Z) pre-empt the lamellar phase?  Window spacing as
        # p9_mixed in units of the window width (spacing ~ L^-1.5); gate as approved for
        # the deep p9_mixed rows (15% round-trip walkers, min swap 0.1).
        rows = []
        for L, mt in ((16, 1500000), (24, 3000000)):
            nwin = int(round(1.95 / (0.0065 * (18 / L) ** 1.5) / 4) * 4)
            for i, m2 in enumerate((-2.6, -2.8, -3.0)):
                r = umbrella_row(stage, Z_P8, Q_P8, L, m2, 1000 + 10 * i + L, smax=0.75,
                                 max_therm=mt, kind="mixed", therm=50000, min_rt=0.15,
                                 min_swap=0.1)
                r.update({"CVU_MIX": 2.0, "CVU_SMIN": -1.2, "CVU_POWER": 1.0, "CVU_WINDOWS": nwin})
                rows.append(r)
        return rows
    if stage == "p9_L27":
        # Run plan r5.  Second size for the p=9 symmetric->uniform coexistence
        # (L=18: m_eq = -2.449(2), barrier 5.1(2) kT, lamellar >= 15 kT higher).
        # Mixed CV on a reduced range (lamellar side down to s = -0.6).
        rows = []
        nwin = int(round(1.2 / (0.0065 * (18 / 27) ** 1.5) / 4) * 4)
        for i, m2 in enumerate((-2.42, -2.47)):
            r = umbrella_row(stage, Z_P9, Q_P9, 27, m2, 1100 + i, smax=0.60, max_therm=3000000,
                             kind="mixed", therm=50000, min_rt=0.15, min_swap=0.1)
            r.update({"CVU_MIX": 2.0, "CVU_SMIN": -0.6, "CVU_POWER": 1.0, "CVU_WINDOWS": nwin})
            rows.append(r)
        return rows
    if stage == "zeff":
        # Renormalized dispersion G^-1(k) = 1/S(k) in the symmetric phase, approached from
        # above.  m2_c estimates: uniform line (reports/transition_order, Z >= -0.95),
        # lamellar line (Z=-2: -1.861; p=8 symmetric windows order near -2.0..-2.1);
        # unknown in between, so the -1.1..-1.0 grid is wide.  Points that order (from the
        # disordered start) are flagged by the analysis and mark the ordering onset.
        mc = {-2.0: -1.86, -1.75: -1.90, -1.5: -1.95, -1.3: -2.0, -1.171573: -2.05,
              -0.95: -2.485, -0.9: -2.383, -0.8: -2.194, -0.6: -1.872, -0.4: -1.61, 0.0: -1.216}
        grid = {Z: [round(m + d, 3) for d in (0.75, 0.6, 0.45, 0.3, 0.2, 0.12, 0.06, 0.02)]
                for Z, m in mc.items()}
        for Z in (-1.1, -1.05, -1.0):
            grid[Z] = [round(-1.8 - 0.1 * i, 3) for i in range(9)]      # -1.8 .. -2.6
        rows, seed = [], 6000
        for Z in sorted(grid):
            ms = grid[Z]
            for i, m2 in enumerate(ms):
                Ls = [48]
                if i >= len(ms) - 3:
                    Ls += [64]
                if i == len(ms) - 3:
                    Ls += [32]
                for L in Ls:
                    seed += 1
                    rows.append(sk_row(stage, Z, L, m2, seed))
        return rows
    if stage in ("b8", "b13"):
        # Run plan r8.  Band CV: total power of all modes with khat^2 in [lo, hi] (any
        # orientation), so the (111)-vs-axis lamella ambiguity of the p=8 shell CV is gone.
        # Bands bracket the renormalized S(k) peak (reports/sk_symmetric: Z8 0.43-0.48,
        # Z=-1.3 0.51-0.58, drifting down toward the transition).  L chosen for dense
        # shells inside the band and an axis mode in it for the lamellar start fields.
        # Masses: two per L around the expected line (Z8 L16 chi_s peak -2.46..-2.52,
        # line moves down with L; Z=-1.3 interpolated towards Z=-2).
        Z, band, q0, base = ((Z_P8, (0.36, 0.62), 0.44, -2.50) if stage == "b8"
                             else (-1.3, (0.37, 0.70), 0.50, -2.39))
        rows = []
        for j, (L, dm, mt) in enumerate(((20, 0.0, 400000), (28, -0.05, 900000),
                                         (32, -0.08, 1300000))):
            for k, off in enumerate((0.0, -0.10)):
                m2 = round(base + dm + off, 3)
                r = umbrella_row(stage, Z, q0, L, m2, (1200 if stage == "b8" else 1300) + 10 * k + L,
                                 smax=0.5, max_therm=mt, kind="band")
                r.update({"CVU_BAND_LO": band[0], "CVU_BAND_HI": band[1]})
                rows.append(r)
        return rows
    if stage == "bline2":
        # Run plan r11 (answers QUESTION_bline_masses_2026-11-26).  bline Z8 L20 gives
        # m_eq = -2.301(6), above the r10 L28/L32 masses; at Z=-2 m_eq moved down by 0.024
        # from L18 to L30, so L28/32 is expected near -2.32..-2.34.  The Z8 -2.40 rows are
        # cancelled and replaced by -2.30, so -2.30/-2.34 bracket the line.  Same CV/caps.
        caps = {28: 900000, 32: 1300000}
        rows = []
        for L in (28, 32):
            r = umbrella_row(stage, Z_P8, 0.44, L, -2.30, 1800 + L, smax=0.5,
                             max_therm=caps[L], kind="band")
            r.update({"CVU_BAND_LO": 0.36, "CVU_BAND_HI": 0.62})
            rows.append(r)
        return rows
    if stage == "bline":
        # Run plan r10.  The r8 b8/b13 masses were placed from the p=8 axis-shell estimate
        # (L16 m_eq -2.65), which forced the wrong wave vector.  Band-CV L20 results put the
        # line near m2 = -2.34 at both Z (b13 L20 m_eq -2.342(3); b8 L20 chi_s peak ~-2.34,
        # at the edge of the reweighting range), and unbiased L48 chains at Z8 nucleate
        # lamellae between -2.35 (1/8) and -2.45 (8/8).  New rows bracket -2.34..-2.40;
        # same CV, band and caps as b8/b13.  Results combine with b8/b13 per (Z, L).
        spec = {"b8": (Z_P8, (0.36, 0.62), 0.44, 1600, ((20, -2.36), (28, -2.34), (28, -2.40),
                                                       (32, -2.34), (32, -2.40))),
                "b13": (-1.3, (0.37, 0.70), 0.50, 1700, ((28, -2.36), (32, -2.34), (32, -2.40)))}
        caps = {20: 400000, 28: 900000, 32: 1300000}
        rows = []
        for Z, band, q0, s0, pts in spec.values():
            for i, (L, m2) in enumerate(pts):
                r = umbrella_row(stage, Z, q0, L, m2, s0 + 10 * i + L, smax=0.5,
                                 max_therm=caps[L], kind="band")
                r.update({"CVU_BAND_LO": band[0], "CVU_BAND_HI": band[1]})
                rows.append(r)
        return rows
    if stage == "b8_mixed":
        # Run plan r8, replaces p8_mixed: s = M^2 - 2 P_band, uniform vs lamellar deep in
        # the ordered region at Z8.  Window spacing as p8_mixed.
        rows = []
        for L, mt in ((20, 2000000), (28, 3500000)):
            nwin = int(round(1.95 / (0.0065 * (18 / L) ** 1.5) / 4) * 4)
            for i, m2 in enumerate((-2.7, -2.9)):
                r = umbrella_row(stage, Z_P8, 0.44, L, m2, 1400 + 10 * i + L, smax=0.75,
                                 max_therm=mt, kind="mixedband", therm=50000, min_rt=0.15,
                                 min_swap=0.1)
                r.update({"CVU_MIX": 2.0, "CVU_SMIN": -1.2, "CVU_POWER": 1.0, "CVU_WINDOWS": nwin,
                          "CVU_BAND_LO": 0.36, "CVU_BAND_HI": 0.62})
                rows.append(r)
        return rows
    if stage == "uline_ext":
        # Run plan r8.  The renormalized S(k) peak slides to k -> 0 near the transition
        # for Z >= -1.05 (Z=-1.0, m2=-2.6: m2_eff ~ 0.002 at L=48), so the uniform
        # coordinate is the relevant one there.  Profile as uline; check the window
        # states for slabs/interfaces (scripts/cv_state_profiles.jl).
        rows = []
        for iz, (Z, mc) in enumerate(((-1.0, -2.60), (-1.05, -2.68))):
            for L in (24, 32):
                for k, dm in enumerate((-0.03, 0.0, 0.03)):
                    m2 = round(mc + dm, 4)
                    for init in ("disordered", "ordered"):
                        seed = 1500 + 100 * iz + L + 10 * k + 1000 * (init == "ordered")
                        r = umbrella_row(stage, Z, 0.0, L, m2, seed,
                                         smax=0.55, min_rt=0.3, max_therm=900000,
                                         samples=8000, kind="M2", init=init, therm=20000)
                        r.pop("CVU_SHELL_Q")
                        r["CVU_WINDOWS"] = str(int(round(int(r["CVU_WINDOWS"]) * 1.1 / 4) * 4))
                        rows.append(r)
        return rows
    if stage == "ulam":
        # LOCAL exploratory (not in the Hazel run plan): uniform <-> lamellar boundary by
        # direct coexistence.  Half-uniform / half-lamellar L = 48 boxes (sk_symmetric.jl
        # SK_INIT=slab, layers parallel to the interfaces in odd replicas, perpendicular in
        # even ones); the phase that invades the box has the lower free energy.  n = number
        # of wavelengths across L, near the renormalized peak (reports/sk_symmetric).
        nwave = {-1.1: 5, -1.3: 6, -1.6: 7, -2.0: 8}
        rows, seed = [], 7000
        for m2 in (-2.7, -3.1, -3.6, -4.2):
            for Z, n in nwave.items():
                seed += 1
                rows.append(sk_row(stage, Z, 48, m2, seed, samples=4000, skip=25, therm=2000,
                                   init=("slab", n)))
        return rows
    if stage == "zeff3":
        # LOCAL: symmetric -> moat crossover (Zeff = 0, curvature of 1/S at k = 0) for
        # -0.4 < Z < 0, where the line leaves the uniform transition (Z=-0.4: Zeff changes
        # sign ~0.03 above m_c; Z=0: Zeff > 0 everywhere).  m_c interpolated from
        # reports/transition_order (Z=0 -1.216, -0.25 -1.432, -0.4 -1.61); deep-symmetric
        # masses follow the line toward Z -> 0-.
        mc = {-0.05: -1.257, -0.1: -1.30, -0.2: -1.39, -0.3: -1.49}
        grid = {Z: [round(m + d, 3) for d in (1.5, 1.0, 0.6, 0.35, 0.2, 0.1, 0.05, 0.02)]
                for Z, m in mc.items()}
        grid[0.0] = [0.0, 0.5, 1.0]
        rows, seed = [], 7200
        for Z in sorted(grid):
            for m2 in grid[Z]:
                seed += 1
                rows.append(sk_row(stage, Z, 48, m2, seed))
        return rows
    if stage == "zeff4":
        # LOCAL: resolve the moat crossover next to the uniform line for Z <= -0.6, where the
        # zeff/zeff2 scans still have Zeff < 0 at m_c + 0.02.  L = 64 (lowest shell
        # khat^2 = 0.0096) at 0.005-0.015 above m_c (zeff grid: Z=-0.6 -1.872, Z=-0.8 -2.194).
        mc = {-0.6: -1.872, -0.8: -2.194}
        rows, seed = [], 7300
        for Z, m in mc.items():
            for d in (0.015, 0.01, 0.005):
                seed += 1
                rows.append(sk_row(stage, Z, 64, round(m + d, 3), seed))
        return rows
    if stage == "zeff5":
        # LOCAL: follow the moat line up to the top of the phase-diagram figures.  Near Z = 0
        # the crossover sits where Zeff(Z=0, m2) - 0 = -Z (the shift Zeff - Z is nearly
        # Z-independent: it reproduces the Z=-0.05/-0.1 crossings).  (a) direct crossings
        # for Z = -0.03, -0.02, -0.01 (expected m2 ~ -0.7, -0.55, -0.1); (b) high-statistics
        # Z = 0 shift at the figure borders m2 = 0.25 (prelim) and 2.5 (theory), plus 1.0.
        grid = {-0.03: ((-0.55, -0.7, -0.85), 4000), -0.02: ((-0.35, -0.5, -0.65), 4000),
                -0.01: ((0.25, -0.1, -0.35), 8000), 0.0: ((0.25, 1.0, 2.5), 16000)}
        rows, seed = [], 7400
        for Z, (ms, ns) in grid.items():
            for m2 in ms:
                seed += 1
                rows.append(sk_row(stage, Z, 48, m2, seed, samples=ns))
        return rows
    if stage == "zeff6":
        # LOCAL: volume dependence of the moat line away from the uniform line: L=64 at the
        # Z=-0.2/-0.3 crossings (L=48 only so far), L=32 at Z=-0.4 (L=48/64 exist).  The
        # large-L rows next to the transition run on Hazel (stage zeffL, r12).
        grid = [(-0.4, 32, (-1.59, -1.55)), (-0.3, 64, (-1.41, -1.44)), (-0.2, 64, (-1.25, -1.29))]
        rows, seed = [], 7500
        for Z, L, ms in grid:
            for m2 in ms:
                seed += 1
                rows.append(sk_row(stage, Z, L, m2, seed))
        return rows
    if stage == "zeffL":
        # HAZEL (run plan r12): moat crossover next to the uniform line at large L.  Near the
        # crossover xi ~ 25 at L=64 (m2_eff ~ 0.002), so L=96/128 test the volume dependence;
        # L=64 at Z=-0.9/-0.95 extends the Z=-0.6/-0.8 series toward Z*.  m_c: L=32 chi_max
        # (Z=-0.6 -1.872, -0.8 -2.194, -0.9 -2.388, -0.95 -2.490).
        grid = [(-0.6, 96, (-1.857, -1.862, -1.867)), (-0.8, 96, (-2.189, -2.192)),
                (-0.9, 64, (-2.373, -2.378, -2.383)), (-0.95, 64, (-2.475, -2.480, -2.485)),
                (-0.9, 96, (-2.378, -2.383)), (-0.95, 96, (-2.480, -2.485)),
                (-0.6, 128, (-1.857, -1.862))]
        rows, seed = [], 7800
        for Z, L, ms in grid:
            for m2 in ms:
                seed += 1
                rows.append(sk_row(stage, Z, L, m2, seed))
        return rows
    if stage == "ulamL":
        # HAZEL (run plan r12): second box size for the uniform <-> lamellar slab runs (local
        # ulam/ulam2 at L=48).  L=64 with the same wavevector where commensurate (n=8 for
        # khat^2=0.586 at Z=-1.3/-1.45; n=7, khat^2=0.462, for the L=48 n=5 at Z=-1.0/-1.1).
        # Masses bracket the L=48 line: Z=-1.0 above -2.7, -1.1 (-2.9,-2.8), -1.3 (-3.6,-3.4),
        # -1.45 below -4.0.
        grid = {-1.0: (7, (-2.6, -2.7, -2.85)), -1.1: (7, (-2.8, -2.9, -3.0)),
                -1.3: (8, (-3.4, -3.5, -3.6)), -1.45: (8, (-3.7, -4.0, -4.3))}
        rows, seed = [], 7900
        for Z, (n, ms) in grid.items():
            for m2 in ms:
                seed += 1
                rows.append(sk_row(stage, Z, 64, m2, seed, samples=4000, skip=25, therm=2000,
                                   init=("slab", n)))
        return rows
    if stage == "zeff8":
        # LOCAL: volume dependence of the moat line far from the uniform line: L=64 bracketing
        # the L=48 crossings at Z=-0.05 (m2=-0.872) and Z=-0.1 (-1.055).
        grid = [(-0.05, 64, (-0.85, -0.90)), (-0.1, 64, (-1.03, -1.08))]
        rows, seed = [], 8000
        for Z, L, ms in grid:
            for m2 in ms:
                seed += 1
                rows.append(sk_row(stage, Z, L, m2, seed))
        return rows
    if stage == "zeff9":
        # LOCAL: statistics for the moat zeros next to Z=0 (zeff5: Z_eff within +-0.003 of zero
        # over a wide m2 range, zero sensitive to the fit weights).  New masses interleaved
        # with zeff5, 16000 samples each.
        grid = [(-0.03, (-0.5, -0.65, -0.8)), (-0.02, (-0.45, -0.55, -0.75)), (-0.01, (0.05, -0.2, -0.45))]
        rows, seed = [], 8200
        for Z, ms in grid:
            for m2 in ms:
                seed += 1
                rows.append(sk_row(stage, Z, 48, m2, seed, samples=16000))
        return rows
    if stage == "ulam5":
        # LOCAL: follow the plunge of the uniform <-> lamellar line (ulam4: Z=-1.45 (-4.45,-4.15),
        # Z=-1.5 above -4.7, Z=-1.6 (-6.0,-5.5), Z=-2 below -7.0).  Close Z=-1.5; add Z=-1.7/-1.8.
        grid = {-1.5: (7, (-4.3, -4.5)), -1.7: (7, (-6.5, -7.5)), -1.8: (8, (-7.0, -8.0))}
        rows, seed = [], 8300
        for Z, (n, ms) in grid.items():
            for m2 in ms:
                seed += 1
                rows.append(sk_row(stage, Z, 48, m2, seed, samples=4000, skip=25, therm=2000,
                                   init=("slab", n)))
        return rows
    if stage == "ulam4":
        # LOCAL: uniform <-> lamellar line where it steepens (ulam3, perpendicular slabs: Z=-1.45
        # between -4.6 and -4.0, mixed at -4.3; lamellar wins at Z=-1.6 down to -5.0 and at
        # Z=-2.0 down to -6.0; MF multi-harmonic line -5.09 at Z=-1.6, none at Z=-2).
        grid = {-1.45: (6, (-4.15, -4.45)), -1.5: (7, (-4.7, -5.1)), -1.6: (7, (-5.5, -6.0, -6.5)),
                -2.0: (8, (-7.0, -8.0))}
        rows, seed = [], 8100
        for Z, (n, ms) in grid.items():
            for m2 in ms:
                seed += 1
                rows.append(sk_row(stage, Z, 48, m2, seed, samples=4000, skip=25, therm=2000,
                                   init=("slab", n)))
        return rows
    if stage == "ulam3":
        # LOCAL: uniform <-> lamellar line deeper in m2 for Z <= -1.45 (ulam/ulam2: lamellar
        # wins at Z=-1.45 down to -4.0, Z=-1.6/-2.0 down to -4.2).  Same slab protocol.
        grid = {-1.45: (6, (-4.3, -4.6)), -1.6: (7, (-4.6, -5.0)), -2.0: (8, (-5.0, -5.5, -6.0))}
        rows, seed = [], 7700
        for Z, (n, ms) in grid.items():
            for m2 in ms:
                seed += 1
                rows.append(sk_row(stage, Z, 48, m2, seed, samples=4000, skip=25, therm=2000,
                                   init=("slab", n)))
        return rows
    if stage == "ulam2":
        # LOCAL refinement of ulam (first pass: Z=-1.1 line in (-3.1,-2.7), Z=-1.3 in
        # (-3.6,-3.1), Z<=-1.6 lamellar down to -3.6); same slab protocol.
        grid = {-1.0: (5, (-2.7, -2.85, -3.0)), -1.1: (5, (-2.8, -2.9, -3.0)),
                -1.3: (6, (-3.25, -3.4)), -1.45: (6, (-3.4, -3.7, -4.0))}
        rows, seed = [], 7100
        for Z, (n, ms) in grid.items():
            for m2 in ms:
                seed += 1
                rows.append(sk_row(stage, Z, 48, m2, seed, samples=4000, skip=25, therm=2000,
                                   init=("slab", n)))
        return rows
    if stage == "zeff2":
        # Run plan r8.  The zeff m2_c guesses for -1.5 <= Z <= -1.17 were too high (the
        # deepest points still have m2_eff 0.2-0.45); follow the peak down to ordering.
        grid = {-1.5: (-2.05, -2.15, -2.25), -1.3: (-2.1, -2.2, -2.3, -2.4),
                Z_P8: (-2.15, -2.25, -2.35, -2.45)}
        rows, seed = [], 6500
        for Z, ms in grid.items():
            for m2 in ms:
                seed += 1
                rows.append(sk_row(stage, Z, 48, m2, seed))
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

STAGES = ("s2_zm2", "s2_zm1172", "lro", "lro2")
ALL_STAGES = STAGES + ("validate", "uline", "s2_zm1172_prod", "s2_zm2_ext", "p9_pilot", "p9_mixed",
                       "p8_shift", "p8_mixed", "p9_L27", "zeff",
                       "b8", "b13", "b8_mixed", "uline_ext", "zeff2", "bline", "bline2", "ulam", "ulam2", "zeff3", "zeff4",
                       "zeff5", "zeff6", "ulam3", "zeffL", "ulamL", "zeff8", "ulam4", "zeff9", "ulam5")


def manifest(stage: str) -> Path:
    return BASE / stage / "manifest.csv"


def env_of(row: dict) -> dict:
    env = {k: v for k, v in row.items() if k.startswith(("CVU_", "SK_")) and v != ""}
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
    ap.add_argument("--gpu", help="Slurm GPU type or comma list, e.g. l40s or l40s,h100,h200")
    ap.add_argument("--runtime-minutes", type=int, help="simulation budget per Slurm job")
    ap.add_argument("--lmin", type=int, default=0, help="only rows with L >= LMIN")
    ap.add_argument("--lmax", type=int, default=10**6, help="only rows with L <= LMAX")
    ap.add_argument("--match", default="", help="only rows whose run directory contains this text")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare"); p.add_argument("--stage", nargs="+", default=list(STAGES))
    s = sub.add_parser("submit"); s.add_argument("--stage", nargs="+", default=list(STAGES))
    s.add_argument("--dry-run", action="store_true")
    t = sub.add_parser("status"); t.add_argument("--stage", nargs="+", default=list(STAGES))
    f = sub.add_parser("refresh", help="slurm: rewrite job.sh of incomplete rows from the manifest (no submit)")
    f.add_argument("--stage", nargs="+", default=list(STAGES))
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
        rows = [r for r in read_manifest(manifest(stage))
                if args.lmin <= int(r["L"]) <= args.lmax and args.match in r["out"]]
        print(stage, end=": ")
        if args.backend == "slurm":
            if args.cmd == "submit":
                n = slurm_backend.submit_rows_slurm(
                    rows, env_of=env_of, workdir_of=lambda r: Path(r["out"]), done_of=done_of,
                    command=[cfg["julia"], "--startup-file=no", f"--project={ROOT}", str(SCRIPT_OF.get(stage, SCRIPT))],
                    label=label, cfg=cfg, dry_run=args.dry_run)
                print(f"{n} job chains started")
            elif args.cmd == "refresh":
                n = slurm_backend.refresh_rows_slurm(
                    rows, env_of=env_of, workdir_of=lambda r: Path(r["out"]), done_of=done_of,
                    command=[cfg["julia"], "--startup-file=no", f"--project={ROOT}", str(SCRIPT_OF.get(stage, SCRIPT))],
                    label=label, cfg=cfg)
                print(f"{n} job scripts refreshed")
            else:
                slurm_backend.status_rows_slurm(rows, done_of=done_of, label=label)
        elif args.cmd == "submit":
            submit_rows(rows, command=lambda r: julia_command(SCRIPT_OF.get(stage, SCRIPT), env=env_of(r)),
                        is_complete=is_complete, label=label, dry_run=args.dry_run)
        else:
            status_rows(rows, is_complete=is_complete, label=label)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
