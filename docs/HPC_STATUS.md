# Hazel campaign status

Generated 2026-11-22 14:06 UTC by `scripts/hpc_status_report.py` on the cluster (branch `hazel-ops`). Run data are not in git; copy completed stages with rsync (docs/HPC.md §4).

## Operator notes

- **Hardware:** chains use `gpu_partners`/`short_gpu` with GPU types L40S, H100, H200 and RTX PRO 6000. They're picked per (re)submission. The `gpu` partition gave 2 four-hour H100 cycles, then nothing for 7 h. All rows are back on `short_gpu`. Throughput is about 8 sweeps/s at L=32 and 20–45 sweeps/s at L=24, per GPU.
- **`p9_mixed` (not yet in the run plan; approved by the user on Hazel 2026-11-20):** `p9_pilot` m²=−2.50/−2.65 cannot cross the gap between the uniform branch (P_shell≈0, |M|≈0.7) and the modulated branch (P_shell≳0.02) with the shell ladder. Both stopped with `exit=3` and 0 round trips; the checkpoint diagnostic is in the journal. `p9_mixed` redoes all four masses on s = M² − 2·P_shell over s∈[−0.95, 0.60] with 240 windows, MIN_SWAP 0.1. All four masses transport through the gap; see the round-trip counts below. Gate: −2.20/−2.35 need 30% round-trip walkers with a 1.5M cap; −2.50/−2.65 need 15% (36 walkers) with a 2.5M cap (user-approved 2026-11-21), because they transport more slowly across the uniform↔modulated switch.
- **`p9_pilot` m²=−2.20/−2.35** completed normally on the shell coordinate. The −2.50/−2.65 rows are superseded by `p9_mixed`, and their checkpoints are kept.
- **Run plan r5 (2026-11-22):** `s2_zm1172_prod` L32 rows are cancelled (checkpoints kept, not resubmitted). New stages `p8_mixed` (6), `p8_shift` (5) and `p9_L27` (2) were prepared and submitted on 2026-11-22 around 03:00 EST; the `p8_mixed` L16 rows run on Intel GPUs only.

## Summary

| stage | complete | queued/running | idle |
|---|---|---|---|
| `p8_mixed` | 0/6 | 6 | 0 |
| `p8_shift` | 0/5 | 5 | 0 |
| `p9_L27` | 0/2 | 2 | 0 |
| `p9_mixed` | 4/4 | 0 | 0 |
| `p9_pilot` | 2/4 | 0 | 2 |
| `s2_zm1172_prod` | 4/6 | 0 | 2 |
| `s2_zm2_ext` | 2/4 | 2 | 0 |
| `uline` | 26/48 | 21 | 1 |
| `validate` | 1/1 | 0 | 0 |

Running GPUs: h100 2, h200 2, l40s 4, rtx_6000_pro 8

During thermalization the HMC columns show the last check interval (ε adapts per window); for completed/collecting rows they show the whole collect phase. Round-trip walkers reset when collection starts.

## Runs

### `p8_mixed` (0/6 complete)

| run | state | phase | sweeps | collected | HMC acc (mean / min window) | min swap | round-trip walkers | ε median | cont |
|---|---|---|---|---|---|---|---|---|---|
| Zm1p1716/L16/m2m2p6_s1016 | PD l40s | therm | 419859 | 0 | 0.800 / 0.786 | 0.160 | 4 | 0.03017 | 2 |
| Zm1p1716/L16/m2m2p8_s1026 | R h100 | therm | 291000 | 0 | 0.800 / 0.781 | 0.177 | 0 | 0.03017 | 1 |
| Zm1p1716/L16/m2m3_s1036 | PD l40s | therm | 212219 | 0 | 0.799 / 0.721 | 0.168 | 0 | 0.03017 | 1 |
| Zm1p1716/L24/m2m2p6_s1024 | R h200 | therm | 30000 | 0 | 0.800 / 0.783 | 0.155 | 0 | 0.02229 | 0 |
| Zm1p1716/L24/m2m2p8_s1034 | PD rtx_6000_pro | therm | 104384 | 0 | 0.799 / 0.760 | 0.203 | 0 | 0.02229 | 2 |
| Zm1p1716/L24/m2m3_s1044 | PD rtx_6000_pro | therm | 104037 | 0 | 0.804 / 0.568 | 0.179 | 0 | 0.02229 | 2 |

### `p8_shift` (0/5 complete)

| run | state | phase | sweeps | collected | HMC acc (mean / min window) | min swap | round-trip walkers | ε median | cont |
|---|---|---|---|---|---|---|---|---|---|
| Zm1p1716/L24/m2m2p75_s884 | PD h100 | therm | 134012 | 0 | 0.802 / 0.500 | 0.398 | 6 | 0.02229 | 2 |
| Zm1p1716/L24/m2m2p85_s894 | PD rtx_6000_pro | therm | 132589 | 0 | 0.801 / 0.778 | 0.392 | 0 | 0.02229 | 2 |
| Zm1p1716/L32/m2m2p78_s892 | R h200 | therm | 16000 | 0 | 0.800 / 0.783 | 0.383 | 0 | 0.01797 | 0 |
| Zm1p1716/L32/m2m2p86_s902 | R l40s | therm | 56000 | 0 | 0.799 / 0.787 | 0.384 | 0 | 0.01779 | 1 |
| Zm1p1716/L32/m2m2p94_s912 | R l40s | therm | 37098 | 0 | 0.802 / 0.694 | 0.376 | 0 | 0.01797 | 1 |

### `p9_L27` (0/2 complete)

| run | state | phase | sweeps | collected | HMC acc (mean / min window) | min swap | round-trip walkers | ε median | cont |
|---|---|---|---|---|---|---|---|---|---|
| Zm0p9358/L27/m2m2p42_s1100 | R rtx_6000_pro | therm | 80000 | 0 | 0.800 / 0.782 | 0.214 | 0 | 0.02037 | 1 |
| Zm0p9358/L27/m2m2p47_s1101 | R rtx_6000_pro | therm | 68000 | 0 | 0.800 / 0.784 | 0.188 | 0 | 0.02037 | 1 |

### `p9_mixed` (4/4 complete)

| run | state | phase | sweeps | collected | HMC acc (mean / min window) | min swap | round-trip walkers | ε median | cont |
|---|---|---|---|---|---|---|---|---|---|
| Zm0p9358/L18/m2m2p2_s950 | complete | collect | 816000 | 4000 | 0.798 / 0.720 | 0.213 | 0 | 0.02767 | 3 |
| Zm0p9358/L18/m2m2p35_s951 | complete | collect | 783000 | 4000 | 0.803 / 0.728 | 0.193 | 0 | 0.02712 | 3 |
| Zm0p9358/L18/m2m2p5_s952 | complete | collect | 1088000 | 4000 | 0.797 / 0.721 | 0.178 | 0 | 0.02767 | 5 |
| Zm0p9358/L18/m2m2p65_s953 | complete | collect | 1340000 | 4000 | 0.802 / 0.697 | 0.099 | 0 | 0.02712 | 6 |

### `p9_pilot` (2/4 complete)

| run | state | phase | sweeps | collected | HMC acc (mean / min window) | min swap | round-trip walkers | ε median | cont |
|---|---|---|---|---|---|---|---|---|---|
| Zm0p9358/L18/m2m2p2_s900 | complete | collect | 201000 | 4000 | 0.777 / 0.763 | 0.438 | 0 | | 0 |
| Zm0p9358/L18/m2m2p35_s901 | complete | collect | 108000 | 4000 | 0.771 / 0.343 | 0.380 | 0 | | 1 |
| Zm0p9358/L18/m2m2p5_s902 | IDLE | therm | 450000 | 0 | 0.800 / 0.789 | 0.358 | 0 | 0.02767 | 0 |
| Zm0p9358/L18/m2m2p65_s903 | IDLE | therm | 300000 | 0 | 0.739 / 0.624 | 0.395 | 0 | | 0 |

### `s2_zm1172_prod` (4/6 complete)

| run | state | phase | sweeps | collected | HMC acc (mean / min window) | min swap | round-trip walkers | ε median | cont |
|---|---|---|---|---|---|---|---|---|---|
| Zm1p1716/L16/m2m2p47_s816 | complete | collect | 62000 | 4000 | 0.784 / 0.772 | 0.438 | 0 | | 0 |
| Zm1p1716/L16/m2m2p53_s826 | complete | collect | 75000 | 4000 | 0.784 / 0.767 | 0.444 | 0 | | 0 |
| Zm1p1716/L24/m2m2p49_s824 | complete | collect | 256000 | 4000 | 0.802 / 0.709 | 0.438 | 0 | 0.02229 | 4 |
| Zm1p1716/L24/m2m2p55_s834 | complete | collect | 350000 | 4000 | 0.794 / 0.713 | 0.430 | 0 | 0.02274 | 4 |
| Zm1p1716/L32/m2m2p51_s832 | IDLE | therm | 227220 | 0 | 0.798 / 0.732 | 0.443 | 4 | 0.01797 | 9 |
| Zm1p1716/L32/m2m2p57_s842 | IDLE | therm | 270723 | 0 | 0.800 / 0.775 | 0.442 | 8 | 0.01833 | 9 |

### `s2_zm2_ext` (2/4 complete)

| run | state | phase | sweeps | collected | HMC acc (mean / min window) | min swap | round-trip walkers | ε median | cont |
|---|---|---|---|---|---|---|---|---|---|
| Zm2/L24/m2m1p88_s132 | complete | collect | 160000 | 4000 | 0.796 / 0.713 | 0.388 | 0 | 0.02415 | 4 |
| Zm2/L30/m2m1p9_s133 | complete | collect | 355000 | 4000 | 0.799 / 0.710 | 0.372 | 0 | 0.02 | 11 |
| Zm2/L36/m2m1p92_s134 | PD l40s | therm | 217794 | 0 | 0.800 / 0.780 | 0.399 | 0 | 0.01745 | 12 |
| Zm2/L36/m2m1p96_s135 | PD l40s | therm | 193978 | 0 | 0.801 / 0.782 | 0.400 | 0 | 0.0178 | 8 |

### `uline` (26/48 complete)

| run | state | phase | sweeps | collected | HMC acc (mean / min window) | min swap | round-trip walkers | ε median | cont |
|---|---|---|---|---|---|---|---|---|---|
| Zm0p8/L24/m2m2p215_s700_disordered | complete | collect | 249000 | 8000 | 0.799 / 0.692 | 0.391 | 0 | 0.02185 | 2 |
| Zm0p8/L24/m2m2p215_s701_ordered | complete | collect | 247000 | 8000 | 0.800 / 0.720 | 0.379 | 0 | 0.02185 | 1 |
| Zm0p8/L24/m2m2p195_s710_disordered | complete | collect | 218000 | 8000 | 0.798 / 0.707 | 0.385 | 0 | 0.02185 | 0 |
| Zm0p8/L24/m2m2p195_s711_ordered | complete | collect | 237000 | 8000 | 0.798 / 0.687 | 0.380 | 0 | 0.02185 | 2 |
| Zm0p8/L24/m2m2p175_s720_disordered | complete | collect | 210000 | 8000 | 0.800 / 0.703 | 0.389 | 0 | 0.02185 | 1 |
| Zm0p8/L24/m2m2p175_s721_ordered | complete | collect | 272000 | 8000 | 0.807 / 0.708 | 0.387 | 0 | 0.02142 | 3 |
| Zm0p8/L32/m2m2p22_s700_disordered | complete | collect | 561000 | 8000 | 0.800 / 0.689 | 0.390 | 0 | 0.01761 | 11 |
| Zm0p8/L32/m2m2p22_s701_ordered | IDLE | therm | 600000 | 0 | 0.800 / 0.783 | 0.397 | 99 | 0.01761 | 12 |
| Zm0p8/L32/m2m2p2_s710_disordered | PD rtx_6000_pro | therm | 404474 | 0 | 0.800 / 0.770 | 0.396 | 56 | 0.01797 | 10 |
| Zm0p8/L32/m2m2p2_s711_ordered | R rtx_6000_pro | therm | 474000 | 0 | 0.800 / 0.782 | 0.396 | 80 | 0.01761 | 10 |
| Zm0p8/L32/m2m2p18_s720_disordered | PD h200 | therm | 414959 | 0 | 0.800 / 0.785 | 0.395 | 51 | 0.01761 | 9 |
| Zm0p8/L32/m2m2p18_s721_ordered | complete | collect | 544000 | 8000 | 0.801 / 0.719 | 0.385 | 0 | 0.01761 | 10 |
| Zm0p85/L24/m2m2p31_s700_disordered | complete | collect | 286000 | 8000 | 0.800 / 0.738 | 0.381 | 0 | 0.02185 | 1 |
| Zm0p85/L24/m2m2p31_s701_ordered | complete | collect | 267000 | 8000 | 0.802 / 0.700 | 0.374 | 0 | 0.02185 | 2 |
| Zm0p85/L24/m2m2p29_s710_disordered | complete | collect | 247000 | 8000 | 0.802 / 0.726 | 0.380 | 0 | 0.02185 | 1 |
| Zm0p85/L24/m2m2p29_s711_ordered | complete | collect | 272000 | 8000 | 0.800 / 0.708 | 0.377 | 0 | 0.02185 | 1 |
| Zm0p85/L24/m2m2p27_s720_disordered | complete | collect | 251000 | 8000 | 0.801 / 0.710 | 0.387 | 0 | 0.02185 | 1 |
| Zm0p85/L24/m2m2p27_s721_ordered | complete | collect | 235000 | 8000 | 0.799 / 0.695 | 0.382 | 0 | 0.02185 | 1 |
| Zm0p85/L32/m2m2p317_s700_disordered | R h100 | therm | 592000 | 0 | 0.800 / 0.753 | 0.386 | 98 | 0.01761 | 13 |
| Zm0p85/L32/m2m2p317_s701_ordered | PD h200 | therm | 573501 | 0 | 0.800 / 0.762 | 0.384 | 71 | 0.01761 | 12 |
| Zm0p85/L32/m2m2p297_s710_disordered | R rtx_6000_pro | therm | 557000 | 0 | 0.800 / 0.782 | 0.389 | 86 | 0.01761 | 12 |
| Zm0p85/L32/m2m2p297_s711_ordered | PD l40s | therm | 589271 | 0 | 0.802 / 0.749 | 0.389 | 103 | 0.01761 | 12 |
| Zm0p85/L32/m2m2p277_s720_disordered | R rtx_6000_pro | therm | 587000 | 0 | 0.800 / 0.783 | 0.393 | 101 | 0.01761 | 12 |
| Zm0p85/L32/m2m2p277_s721_ordered | R rtx_6000_pro | collect | 560900 | 950 | 0.802 / 0.698 | 0.361 | 0 | 0.01761 | 11 |
| Zm0p9/L24/m2m2p404_s700_disordered | complete | collect | 295000 | 8000 | 0.797 / 0.676 | 0.367 | 0 | 0.02229 | 1 |
| Zm0p9/L24/m2m2p404_s701_ordered | complete | collect | 300000 | 8000 | 0.800 / 0.700 | 0.366 | 0 | 0.02185 | 1 |
| Zm0p9/L24/m2m2p384_s710_disordered | complete | collect | 272000 | 8000 | 0.807 / 0.731 | 0.373 | 0 | 0.02142 | 1 |
| Zm0p9/L24/m2m2p384_s711_ordered | complete | collect | 297000 | 8000 | 0.798 / 0.691 | 0.374 | 0 | 0.02185 | 1 |
| Zm0p9/L24/m2m2p364_s720_disordered | complete | collect | 280000 | 8000 | 0.799 / 0.708 | 0.370 | 0 | 0.02207 | 1 |
| Zm0p9/L24/m2m2p364_s721_ordered | complete | collect | 265000 | 8000 | 0.798 / 0.719 | 0.377 | 0 | 0.02207 | 1 |
| Zm0p9/L32/m2m2p408_s700_disordered | PD rtx_6000_pro | therm | 585016 | 0 | 0.806 / 0.438 | 0.376 | 60 | 0.01761 | 12 |
| Zm0p9/L32/m2m2p408_s701_ordered | PD rtx_6000_pro | therm | 600000 | 0 | 0.800 / 0.785 | 0.376 | 72 | 0.01779 | 11 |
| Zm0p9/L32/m2m2p388_s710_disordered | R l40s | therm | 450000 | 0 | 0.800 / 0.785 | 0.379 | 44 | 0.01761 | 10 |
| Zm0p9/L32/m2m2p388_s711_ordered | PD rtx_6000_pro | therm | 465737 | 0 | 0.800 / 0.782 | 0.379 | 35 | 0.01761 | 10 |
| Zm0p9/L32/m2m2p368_s720_disordered | PD rtx_6000_pro | therm | 538127 | 0 | 0.799 / 0.717 | 0.383 | 66 | 0.01761 | 12 |
| Zm0p9/L32/m2m2p368_s721_ordered | R rtx_6000_pro | therm | 518000 | 0 | 0.800 / 0.782 | 0.381 | 66 | 0.01761 | 11 |
| Zm0p95/L24/m2m2p507_s700_disordered | complete | collect | 407000 | 8000 | 0.802 / 0.686 | 0.354 | 0 | 0.02185 | 2 |
| Zm0p95/L24/m2m2p507_s701_ordered | complete | collect | 365000 | 8000 | 0.802 / 0.719 | 0.353 | 0 | 0.02185 | 2 |
| Zm0p95/L24/m2m2p487_s710_disordered | complete | collect | 328000 | 8000 | 0.797 / 0.677 | 0.364 | 0 | 0.02185 | 1 |
| Zm0p95/L24/m2m2p487_s711_ordered | complete | collect | 342000 | 8000 | 0.801 / 0.724 | 0.355 | 0 | 0.02185 | 1 |
| Zm0p95/L24/m2m2p467_s720_disordered | complete | collect | 271000 | 8000 | 0.800 / 0.729 | 0.358 | 0 | 0.02229 | 1 |
| Zm0p95/L24/m2m2p467_s721_ordered | complete | collect | 311000 | 8000 | 0.803 / 0.703 | 0.368 | 0 | 0.02185 | 2 |
| Zm0p95/L32/m2m2p51_s700_disordered | R l40s | therm | 514000 | 0 | 0.800 / 0.785 | 0.364 | 34 | 0.01761 | 10 |
| Zm0p95/L32/m2m2p51_s701_ordered | PD h100 | therm | 518609 | 0 | 0.800 / 0.777 | 0.365 | 33 | 0.01761 | 11 |
| Zm0p95/L32/m2m2p49_s710_disordered | PD h200 | therm | 518620 | 0 | 0.799 / 0.776 | 0.367 | 45 | 0.01761 | 11 |
| Zm0p95/L32/m2m2p49_s711_ordered | R rtx_6000_pro | therm | 547000 | 0 | 0.800 / 0.784 | 0.368 | 53 | 0.01761 | 11 |
| Zm0p95/L32/m2m2p47_s720_disordered | PD l40s | therm | 533741 | 0 | 0.800 / 0.777 | 0.371 | 53 | 0.01797 | 11 |
| Zm0p95/L32/m2m2p47_s721_ordered | PD rtx_6000_pro | therm | 538554 | 0 | 0.800 / 0.773 | 0.371 | 60 | 0.01797 | 11 |

### `validate` (1/1 complete)

| run | state | phase | sweeps | collected | HMC acc (mean / min window) | min swap | round-trip walkers | ε median | cont |
|---|---|---|---|---|---|---|---|---|---|
| Zm2/L12/m2m1p73_s121 | complete | collect | 24000 | 4000 | 0.811 / 0.798 | 0.393 | 9 | | 0 |

## Operations journal (last 60 lines of `$LP_HMC_RUNS/OPS_JOURNAL.md`)

- RTX slots idle (13 free) because continuations resubmit from their submit-time script snapshot (type list without rtx). Retyped 8 pending L>=30 jobs to rtx_6000_pro; later continuations use the refreshed job.sh with rtx in the list.

## 2026-11-21 11:01 UTC
- gpu-partition trial: s2_zm2_ext L36 s135 started on gpu17 H100 after ~2 h (kept on gpu partition); uline Zm0p95 L32 s710 (l40) pending ~3.5 h -> reverted to short_gpu (default config) per r3.
- s2_zm2_ext Zm2/L24/m2m1p88_s132 passed gate, collecting.

## 2026-11-21 11:20 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/s2_zm1172_prod/Zm1p1716/L24/m2m2p49_s824

## 2026-11-21 11:20 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/s2_zm2_ext/Zm2/L24/m2m1p88_s132

## 2026-11-21 13:31 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/s2_zm1172_prod/Zm1p1716/L24/m2m2p55_s834

## 2026-11-21 14:01 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/p9_mixed/Zm0p9358/L18/m2m2p35_s951

## 2026-11-21 16:12 UTC
- USER APPROVED: p9_mixed m2=-2.50 (s952) and -2.65 (s953): CVU_MIN_RT 0.3 -> 0.15, CVU_MAX_THERM 1500000 -> 2500000 (s950/s951 unchanged). Refreshed job.sh (Intel config); running jobs pick it up at their next continuation.

## 2026-11-21 16:51 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/p9_mixed/Zm0p9358/L18/m2m2p2_s950

## 2026-11-21 19:52 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/p9_mixed/Zm0p9358/L18/m2m2p5_s952

## 2026-11-21 21:52 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/p9_mixed/Zm0p9358/L18/m2m2p65_s953

## 2026-11-21 22:27 UTC
- STAGE p9_mixed COMPLETE (4/4). Analysis job 2025544 (34 min): reports/cv_umbrella/p9_mixed/Zm0p9358/L18/analysis.json committed+pushed on hazel-ops. summary: n_good 186, chi_s_max 301.8+-4.3 at m2 -2.4513+-0.0028 (not at edge), n_twopeak 27; coexistence m_eq -2.4493+-0.0024, barrier 5.07+-0.21, s_lo -0.0171, s_hi 0.4499, s_min 0.2943, latent_q 0.0514+-0.0015, deff_ordered 2.13; coexistence_fraction 1.0.

## 2026-11-21 22:54 UTC
- IDLE s2_zm2_ext Zm2/L36/m2m1p92_s134: job 2024592 exit=75 normally, self-resubmit failed 'sbatch: Socket timed out on send/recv' (transient slurmctld timeout, also seen by the heartbeat). Resubmitted (§3 first row).

## 2026-11-22 03:54 UTC
- gpu-partition: s2_zm2_ext L36 s135 pending ~7 h (Priority) after 2 completed 4-h cycles; reverted to short_gpu (default config). No rows on the gpu partition now.

## 2026-11-22 06:24 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/uline/Zm0p8/L32/m2m2p18_s721_ordered

## 2026-11-22 07:56 UTC
- pulled run plan r5 (merged into hazel-ops). Cancelled s2_zm1172_prod L32 jobs (2031630 s832, 2030084 s842) - not resubmitted, checkpoints kept; removed s2_zm1172_prod from auto-resubmit/heartbeat. Prepared p8_mixed (6), p8_shift (5), p9_L27 (2); manifest.orig.csv saved; submitted (p8_mixed L16 on Intel-only config).

## 2026-11-22 12:25 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/uline/Zm0p8/L32/m2m2p22_s700_disordered

## 2026-11-22 12:26 UTC
- exit3 rule uline/Zm0p8/L32/m2m2p22_s701_ordered: rt 68->99 rising at 600000; CVU_MAX_THERM 600000 -> 900000 (raise 1/2); resubmitted ()

## 2026-11-22 12:26 UTC
- exit3 rule applied to uline/Zm0p8/L32/m2m2p22_s701_ordered: rt 29@351k, 69@508k, 86@554k, 99@600k (needs 103) rising -> CVU_MAX_THERM 600000 -> 900000 (raise 1/2); refreshed + resubmitted (h100). Automated the same rule in ops/exit3_raise.py (<=2 raises per row, ALERT otherwise).

## 2026-11-22 12:36 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/s2_zm2_ext/Zm2/L30/m2m1p9_s133

## 2026-11-22 12:56 UTC
- exit3 rule uline/Zm0p9/L32/m2m2p408_s701_ordered: rt 40->72 rising at 600000; CVU_MAX_THERM 600000 -> 900000 (raise 1/2); resubmitted (uline: submit   cvu_uline_Zm0p9_L32_m2m2p408_s701  gpu=rtx_6000_pro)

