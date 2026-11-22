# Hazel campaign status

Generated 2026-11-22 23:09 UTC by `scripts/hpc_status_report.py` on the cluster (branch `hazel-ops`). Run data are not in git; copy completed stages with rsync (docs/HPC.md §4).

## Operator notes

- **Hardware:** chains use `gpu_partners`/`short_gpu` with GPU types L40S, H100, H200 and RTX PRO 6000. They're picked per (re)submission. The `gpu` partition gave 2 four-hour H100 cycles, then nothing for 7 h. All rows are back on `short_gpu`. Throughput is about 8 sweeps/s at L=32 and 20–45 sweeps/s at L=24, per GPU.
- **`p9_mixed` (not yet in the run plan; approved by the user on Hazel 2026-11-20):** `p9_pilot` m²=−2.50/−2.65 cannot cross the gap between the uniform branch (P_shell≈0, |M|≈0.7) and the modulated branch (P_shell≳0.02) with the shell ladder. Both stopped with `exit=3` and 0 round trips; the checkpoint diagnostic is in the journal. `p9_mixed` redoes all four masses on s = M² − 2·P_shell over s∈[−0.95, 0.60] with 240 windows, MIN_SWAP 0.1. All four masses transport through the gap; see the round-trip counts below. Gate: −2.20/−2.35 need 30% round-trip walkers with a 1.5M cap; −2.50/−2.65 need 15% (36 walkers) with a 2.5M cap (user-approved 2026-11-21), because they transport more slowly across the uniform↔modulated switch.
- **`p9_pilot` m²=−2.20/−2.35** completed normally on the shell coordinate. The −2.50/−2.65 rows are superseded by `p9_mixed`, and their checkpoints are kept.
- **Run plan r5 (2026-11-22):** `s2_zm1172_prod` L32 rows are cancelled (checkpoints kept, not resubmitted). New stages `p8_mixed` (6), `p8_shift` (5) and `p9_L27` (2) were prepared and submitted on 2026-11-22 around 03:00 EST; the `p8_mixed` L16 rows run on Intel GPUs only.
- **Run plan r6 (2026-11-22):** `p8_shift` and `p8_mixed` are on HOLD. Their chains were cancelled around 13:30 EST, with no resubmit; all 11 checkpoints and data are kept. A one-off checkpoint push of `p9_mixed` and `s2_zm1172_prod` (115 MB) went to `checkpoints/` on the share. `uline`, `s2_zm2_ext` and `p9_L27` continue on the new `cv_umbrella.jl`.
- **Run plan r7 (2026-11-22):** new stage `zeff`, 171 unbiased S(k) runs (`sk_symmetric.jl`, plain HMC, 8 replicas, no umbrella), submitted around 14:00 EST. Their HMC columns show collect-phase acceptance; swap and round-trip columns don't apply.

## Summary

| stage | complete | queued/running | idle |
|---|---|---|---|
| `p8_mixed` | 0/6 | 0 | 6 |
| `p8_shift` | 0/5 | 0 | 5 |
| `p9_L27` | 0/2 | 2 | 0 |
| `p9_mixed` | 4/4 | 0 | 0 |
| `p9_pilot` | 2/4 | 0 | 2 |
| `s2_zm1172_prod` | 4/6 | 0 | 2 |
| `s2_zm2_ext` | 2/4 | 2 | 0 |
| `uline` | 33/48 | 15 | 0 |
| `validate` | 1/1 | 0 | 0 |
| `zeff` | 113/171 | 58 | 0 |

Running GPUs: h100 1, rtx_6000_pro 2

During thermalization the HMC columns show the last check interval (ε adapts per window); for completed/collecting rows they show the whole collect phase. Round-trip walkers reset when collection starts.

## Runs

### `p8_mixed` (0/6 complete)

| run | state | phase | sweeps | collected | HMC acc (mean / min window) | min swap | round-trip walkers | ε median | cont |
|---|---|---|---|---|---|---|---|---|---|
| Zm1p1716/L16/m2m2p6_s1016 | IDLE | therm | 637205 | 0 | 0.802 / 0.732 | 0.159 | 21 | 0.03017 | 3 |
| Zm1p1716/L16/m2m2p8_s1026 | IDLE | therm | 543000 | 0 | 0.800 / 0.786 | 0.176 | 1 | 0.03017 | 2 |
| Zm1p1716/L16/m2m3_s1036 | IDLE | therm | 547000 | 0 | 0.800 / 0.783 | 0.173 | 0 | 0.03017 | 2 |
| Zm1p1716/L24/m2m2p6_s1024 | IDLE | therm | 94802 | 0 | 0.800 / 0.778 | 0.135 | 0 | 0.02229 | 2 |
| Zm1p1716/L24/m2m2p8_s1034 | IDLE | therm | 152250 | 0 | 0.800 / 0.740 | 0.201 | 0 | 0.02229 | 3 |
| Zm1p1716/L24/m2m3_s1044 | IDLE | therm | 188000 | 0 | 0.800 / 0.782 | 0.177 | 0 | 0.02229 | 3 |

### `p8_shift` (0/5 complete)

| run | state | phase | sweeps | collected | HMC acc (mean / min window) | min swap | round-trip walkers | ε median | cont |
|---|---|---|---|---|---|---|---|---|---|
| Zm1p1716/L24/m2m2p75_s884 | IDLE | therm | 208000 | 0 | 0.799 / 0.784 | 0.397 | 19 | 0.02229 | 3 |
| Zm1p1716/L24/m2m2p85_s894 | IDLE | therm | 194384 | 0 | 0.800 / 0.763 | 0.393 | 3 | 0.02229 | 3 |
| Zm1p1716/L32/m2m2p78_s892 | IDLE | therm | 44000 | 0 | 0.800 / 0.784 | 0.386 | 0 | 0.01797 | 1 |
| Zm1p1716/L32/m2m2p86_s902 | IDLE | therm | 73000 | 0 | 0.800 / 0.782 | 0.385 | 0 | 0.01797 | 2 |
| Zm1p1716/L32/m2m2p94_s912 | IDLE | therm | 100000 | 0 | 0.801 / 0.784 | 0.379 | 0 | 0.01797 | 2 |

### `p9_L27` (0/2 complete)

| run | state | phase | sweeps | collected | HMC acc (mean / min window) | min swap | round-trip walkers | ε median | cont |
|---|---|---|---|---|---|---|---|---|---|
| Zm0p9358/L27/m2m2p42_s1100 | PD rtx_6000_pro | therm | 182930 | 0 | 0.800 / 0.783 | 0.213 | 0 | 0.02037 | 4 |
| Zm0p9358/L27/m2m2p47_s1101 | PD rtx_6000_pro | therm | 194058 | 0 | 0.798 / 0.569 | 0.178 | 0 | 0.02037 | 4 |

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
| Zm2/L36/m2m1p92_s134 | PD h200 | therm | 234651 | 0 | 0.800 / 0.780 | 0.400 | 0 | 0.01745 | 13 |
| Zm2/L36/m2m1p96_s135 | R rtx_6000_pro | therm | 245000 | 0 | 0.800 / 0.786 | 0.400 | 0 | 0.0178 | 10 |

### `uline` (33/48 complete)

| run | state | phase | sweeps | collected | HMC acc (mean / min window) | min swap | round-trip walkers | ε median | cont |
|---|---|---|---|---|---|---|---|---|---|
| Zm0p8/L24/m2m2p215_s700_disordered | complete | collect | 249000 | 8000 | 0.799 / 0.692 | 0.391 | 0 | 0.02185 | 2 |
| Zm0p8/L24/m2m2p215_s701_ordered | complete | collect | 247000 | 8000 | 0.800 / 0.720 | 0.379 | 0 | 0.02185 | 1 |
| Zm0p8/L24/m2m2p195_s710_disordered | complete | collect | 218000 | 8000 | 0.798 / 0.707 | 0.385 | 0 | 0.02185 | 0 |
| Zm0p8/L24/m2m2p195_s711_ordered | complete | collect | 237000 | 8000 | 0.798 / 0.687 | 0.380 | 0 | 0.02185 | 2 |
| Zm0p8/L24/m2m2p175_s720_disordered | complete | collect | 210000 | 8000 | 0.800 / 0.703 | 0.389 | 0 | 0.02185 | 1 |
| Zm0p8/L24/m2m2p175_s721_ordered | complete | collect | 272000 | 8000 | 0.807 / 0.708 | 0.387 | 0 | 0.02142 | 3 |
| Zm0p8/L32/m2m2p22_s700_disordered | complete | collect | 561000 | 8000 | 0.800 / 0.689 | 0.390 | 0 | 0.01761 | 11 |
| Zm0p8/L32/m2m2p22_s701_ordered | complete | collect | 635000 | 8000 | 0.800 / 0.703 | 0.384 | 0 | 0.01761 | 13 |
| Zm0p8/L32/m2m2p2_s710_disordered | PD rtx_6000_pro | therm | 508301 | 0 | 0.799 / 0.748 | 0.396 | 82 | 0.01761 | 12 |
| Zm0p8/L32/m2m2p2_s711_ordered | complete | collect | 549000 | 8000 | 0.801 / 0.713 | 0.386 | 0 | 0.01761 | 11 |
| Zm0p8/L32/m2m2p18_s720_disordered | PD rtx_6000_pro | therm | 499992 | 0 | 0.800 / 0.788 | 0.395 | 85 | 0.01761 | 11 |
| Zm0p8/L32/m2m2p18_s721_ordered | complete | collect | 544000 | 8000 | 0.801 / 0.719 | 0.385 | 0 | 0.01761 | 10 |
| Zm0p85/L24/m2m2p31_s700_disordered | complete | collect | 286000 | 8000 | 0.800 / 0.738 | 0.381 | 0 | 0.02185 | 1 |
| Zm0p85/L24/m2m2p31_s701_ordered | complete | collect | 267000 | 8000 | 0.802 / 0.700 | 0.374 | 0 | 0.02185 | 2 |
| Zm0p85/L24/m2m2p29_s710_disordered | complete | collect | 247000 | 8000 | 0.802 / 0.726 | 0.380 | 0 | 0.02185 | 1 |
| Zm0p85/L24/m2m2p29_s711_ordered | complete | collect | 272000 | 8000 | 0.800 / 0.708 | 0.377 | 0 | 0.02185 | 1 |
| Zm0p85/L24/m2m2p27_s720_disordered | complete | collect | 251000 | 8000 | 0.801 / 0.710 | 0.387 | 0 | 0.02185 | 1 |
| Zm0p85/L24/m2m2p27_s721_ordered | complete | collect | 235000 | 8000 | 0.799 / 0.695 | 0.382 | 0 | 0.02185 | 1 |
| Zm0p85/L32/m2m2p317_s700_disordered | PD h200 | therm | 600000 | 0 | 0.800 / 0.784 | 0.386 | 101 | 0.01761 | 13 |
| Zm0p85/L32/m2m2p317_s701_ordered | PD h200 | therm | 600000 | 0 | 0.800 / 0.786 | 0.384 | 80 | 0.01761 | 12 |
| Zm0p85/L32/m2m2p297_s710_disordered | complete | collect | 620000 | 8000 | 0.800 / 0.698 | 0.385 | 0 | 0.01761 | 12 |
| Zm0p85/L32/m2m2p297_s711_ordered | complete | collect | 609000 | 8000 | 0.799 / 0.713 | 0.378 | 0 | 0.01761 | 12 |
| Zm0p85/L32/m2m2p277_s720_disordered | complete | collect | 613000 | 8000 | 0.799 / 0.715 | 0.385 | 0 | 0.01797 | 12 |
| Zm0p85/L32/m2m2p277_s721_ordered | complete | collect | 575000 | 8000 | 0.801 / 0.698 | 0.385 | 0 | 0.01761 | 12 |
| Zm0p9/L24/m2m2p404_s700_disordered | complete | collect | 295000 | 8000 | 0.797 / 0.676 | 0.367 | 0 | 0.02229 | 1 |
| Zm0p9/L24/m2m2p404_s701_ordered | complete | collect | 300000 | 8000 | 0.800 / 0.700 | 0.366 | 0 | 0.02185 | 1 |
| Zm0p9/L24/m2m2p384_s710_disordered | complete | collect | 272000 | 8000 | 0.807 / 0.731 | 0.373 | 0 | 0.02142 | 1 |
| Zm0p9/L24/m2m2p384_s711_ordered | complete | collect | 297000 | 8000 | 0.798 / 0.691 | 0.374 | 0 | 0.02185 | 1 |
| Zm0p9/L24/m2m2p364_s720_disordered | complete | collect | 280000 | 8000 | 0.799 / 0.708 | 0.370 | 0 | 0.02207 | 1 |
| Zm0p9/L24/m2m2p364_s721_ordered | complete | collect | 265000 | 8000 | 0.798 / 0.719 | 0.377 | 0 | 0.02207 | 1 |
| Zm0p9/L32/m2m2p408_s700_disordered | PD h200 | therm | 600000 | 0 | 0.800 / 0.781 | 0.376 | 63 | 0.01761 | 12 |
| Zm0p9/L32/m2m2p408_s701_ordered | complete | collect | 719000 | 8000 | 0.802 / 0.671 | 0.367 | 0 | 0.01761 | 13 |
| Zm0p9/L32/m2m2p388_s710_disordered | PD rtx_6000_pro | therm | 527460 | 0 | 0.800 / 0.774 | 0.379 | 71 | 0.01761 | 12 |
| Zm0p9/L32/m2m2p388_s711_ordered | PD h100 | therm | 571551 | 0 | 0.799 / 0.771 | 0.380 | 71 | 0.01761 | 12 |
| Zm0p9/L32/m2m2p368_s720_disordered | PD rtx_6000_pro | therm | 653167 | 0 | 0.797 / 0.719 | 0.383 | 98 | 0.01761 | 14 |
| Zm0p9/L32/m2m2p368_s721_ordered | PD rtx_6000_pro | collect | 652090 | 3045 | 0.801 / 0.679 | 0.373 | 0 | 0.01761 | 13 |
| Zm0p95/L24/m2m2p507_s700_disordered | complete | collect | 407000 | 8000 | 0.802 / 0.686 | 0.354 | 0 | 0.02185 | 2 |
| Zm0p95/L24/m2m2p507_s701_ordered | complete | collect | 365000 | 8000 | 0.802 / 0.719 | 0.353 | 0 | 0.02185 | 2 |
| Zm0p95/L24/m2m2p487_s710_disordered | complete | collect | 328000 | 8000 | 0.797 / 0.677 | 0.364 | 0 | 0.02185 | 1 |
| Zm0p95/L24/m2m2p487_s711_ordered | complete | collect | 342000 | 8000 | 0.801 / 0.724 | 0.355 | 0 | 0.02185 | 1 |
| Zm0p95/L24/m2m2p467_s720_disordered | complete | collect | 271000 | 8000 | 0.800 / 0.729 | 0.358 | 0 | 0.02229 | 1 |
| Zm0p95/L24/m2m2p467_s721_ordered | complete | collect | 311000 | 8000 | 0.803 / 0.703 | 0.368 | 0 | 0.02185 | 2 |
| Zm0p95/L32/m2m2p51_s700_disordered | R rtx_6000_pro | therm | 622000 | 0 | 0.800 / 0.782 | 0.365 | 61 | 0.01761 | 12 |
| Zm0p95/L32/m2m2p51_s701_ordered | PD rtx_6000_pro | therm | 600000 | 0 | 0.800 / 0.784 | 0.365 | 47 | 0.01797 | 12 |
| Zm0p95/L32/m2m2p49_s710_disordered | PD h200 | therm | 518620 | 0 | 0.799 / 0.776 | 0.367 | 45 | 0.01761 | 11 |
| Zm0p95/L32/m2m2p49_s711_ordered | PD l40s | therm | 653015 | 0 | 0.794 / 0.333 | 0.367 | 76 | 0.01761 | 13 |
| Zm0p95/L32/m2m2p47_s720_disordered | PD rtx_6000_pro | therm | 631686 | 0 | 0.800 / 0.773 | 0.372 | 77 | 0.01761 | 13 |
| Zm0p95/L32/m2m2p47_s721_ordered | PD rtx_6000_pro | therm | 646940 | 0 | 0.800 / 0.787 | 0.371 | 93 | 0.01797 | 13 |

### `validate` (1/1 complete)

| run | state | phase | sweeps | collected | HMC acc (mean / min window) | min swap | round-trip walkers | ε median | cont |
|---|---|---|---|---|---|---|---|---|---|
| Zm2/L12/m2m1p73_s121 | complete | collect | 24000 | 4000 | 0.811 / 0.798 | 0.393 | 9 | | 0 |

### `zeff` (113/171 complete)

| run | state | phase | sweeps | collected | HMC acc (mean / min window) | min swap | round-trip walkers | ε median | cont |
|---|---|---|---|---|---|---|---|---|---|
| Zm2/L48/m2m1p11_s6001 | complete | collect | 40000 | 4000 | 0.783 / 0.709 | nan |  | 0.01495 | 0 |
| Zm2/L48/m2m1p26_s6002 | complete | collect | 40000 | 4000 | 0.799 / 0.760 | nan |  | 0.01465 | 0 |
| Zm2/L48/m2m1p41_s6003 | complete | collect | 40000 | 4000 | 0.783 / 0.681 | nan |  | 0.01451 | 0 |
| Zm2/L48/m2m1p56_s6004 | complete | collect | 40000 | 4000 | 0.810 / 0.744 | nan |  | 0.01394 | 0 |
| Zm2/L48/m2m1p66_s6005 | complete | collect | 40000 | 4000 | 0.787 / 0.744 | nan |  | 0.01451 | 0 |
| Zm2/L48/m2m1p74_s6006 | complete | collect | 40000 | 4000 | 0.782 / 0.717 | nan |  | 0.01514 | 0 |
| Zm2/L64/m2m1p74_s6007 | complete | collect | 40000 | 4000 | 0.822 / 0.782 | nan |  | 0.01088 | 0 |
| Zm2/L32/m2m1p74_s6008 | complete | collect | 40000 | 4000 | 0.799 / 0.771 | nan |  | 0.01946 | 0 |
| Zm2/L48/m2m1p8_s6009 | complete | collect | 40000 | 4000 | 0.786 / 0.738 | nan |  | 0.01465 | 0 |
| Zm2/L64/m2m1p8_s6010 | complete | collect | 40000 | 4000 | 0.787 / 0.717 | nan |  | 0.01192 | 0 |
| Zm2/L48/m2m1p84_s6011 | complete | collect | 40000 | 4000 | 0.799 / 0.696 | nan |  | 0.01422 | 0 |
| Zm2/L64/m2m1p84_s6012 | complete | collect | 40000 | 4000 | 0.794 / 0.736 | nan |  | 0.01202 | 0 |
| Zm1p75/L48/m2m1p15_s6013 | complete | collect | 40000 | 4000 | 0.789 / 0.751 | nan |  | 0.0148 | 0 |
| Zm1p75/L48/m2m1p3_s6014 | complete | collect | 40000 | 4000 | 0.800 / 0.750 | nan |  | 0.01408 | 0 |
| Zm1p75/L48/m2m1p45_s6015 | complete | collect | 40000 | 4000 | 0.793 / 0.754 | nan |  | 0.01436 | 0 |
| Zm1p75/L48/m2m1p6_s6016 | complete | collect | 40000 | 4000 | 0.801 / 0.752 | nan |  | 0.01422 | 0 |
| Zm1p75/L48/m2m1p7_s6017 | complete | collect | 40000 | 4000 | 0.778 / 0.727 | nan |  | 0.01466 | 0 |
| Zm1p75/L48/m2m1p78_s6018 | complete | collect | 40000 | 4000 | 0.797 / 0.757 | nan |  | 0.01423 | 0 |
| Zm1p75/L64/m2m1p78_s6019 | complete | collect | 40000 | 4000 | 0.800 / 0.743 | nan |  | 0.0111 | 0 |
| Zm1p75/L32/m2m1p78_s6020 | complete | collect | 40000 | 4000 | 0.828 / 0.777 | nan |  | 0.0178 | 0 |
| Zm1p75/L48/m2m1p84_s6021 | PD h200 | not started | | | | | | | 0 |
| Zm1p75/L64/m2m1p84_s6022 | complete | collect | 40000 | 4000 | 0.789 / 0.754 | nan |  | 0.01179 | 0 |
| Zm1p75/L48/m2m1p88_s6023 | complete | collect | 40000 | 4000 | 0.792 / 0.752 | nan |  | 0.01436 | 0 |
| Zm1p75/L64/m2m1p88_s6024 | complete | collect | 40000 | 4000 | 0.786 / 0.730 | nan |  | 0.01167 | 0 |
| Zm1p5/L48/m2m1p2_s6025 | complete | collect | 40000 | 4000 | 0.811 / 0.748 | nan |  | 0.01339 | 0 |
| Zm1p5/L48/m2m1p35_s6026 | complete | collect | 40000 | 4000 | 0.810 / 0.758 | nan |  | 0.01366 | 0 |
| Zm1p5/L48/m2m1p5_s6027 | complete | collect | 40000 | 4000 | 0.805 / 0.767 | nan |  | 0.01366 | 0 |
| Zm1p5/L48/m2m1p65_s6028 | complete | collect | 40000 | 4000 | 0.797 / 0.758 | nan |  | 0.0138 | 0 |
| Zm1p5/L48/m2m1p75_s6029 | PD h200 | not started | | | | | | | 0 |
| Zm1p5/L48/m2m1p83_s6030 | complete | collect | 40000 | 4000 | 0.792 / 0.742 | nan |  | 0.01423 | 0 |
| Zm1p5/L64/m2m1p83_s6031 | complete | collect | 40000 | 4000 | 0.796 / 0.750 | nan |  | 0.01156 | 0 |
| Zm1p5/L32/m2m1p83_s6032 | complete | collect | 40000 | 4000 | 0.794 / 0.744 | nan |  | 0.01908 | 0 |
| Zm1p5/L48/m2m1p89_s6033 | complete | collect | 40000 | 4000 | 0.781 / 0.733 | nan |  | 0.01437 | 0 |
| Zm1p5/L64/m2m1p89_s6034 | complete | collect | 40000 | 4000 | 0.802 / 0.774 | nan |  | 0.01121 | 0 |
| Zm1p5/L48/m2m1p93_s6035 | complete | collect | 40000 | 4000 | 0.781 / 0.739 | nan |  | 0.01408 | 0 |
| Zm1p5/L64/m2m1p93_s6036 | complete | collect | 40000 | 4000 | 0.784 / 0.744 | nan |  | 0.01144 | 0 |
| Zm1p3/L48/m2m1p25_s6037 | PD h200 | not started | | | | | | | 0 |
| Zm1p3/L48/m2m1p4_s6038 | complete | collect | 40000 | 4000 | 0.797 / 0.745 | nan |  | 0.01394 | 0 |
| Zm1p3/L48/m2m1p55_s6039 | complete | collect | 40000 | 4000 | 0.810 / 0.781 | nan |  | 0.01394 | 0 |
| Zm1p3/L48/m2m1p7_s6040 | complete | collect | 40000 | 4000 | 0.771 / 0.728 | nan |  | 0.01525 | 0 |
| Zm1p3/L48/m2m1p8_s6041 | complete | collect | 40000 | 4000 | 0.781 / 0.758 | nan |  | 0.01408 | 0 |
| Zm1p3/L48/m2m1p88_s6042 | complete | collect | 40000 | 4000 | 0.814 / 0.782 | nan |  | 0.01326 | 0 |
| Zm1p3/L64/m2m1p88_s6043 | complete | collect | 40000 | 4000 | 0.817 / 0.778 | nan |  | 0.01046 | 0 |
| Zm1p3/L32/m2m1p88_s6044 | R h100 | collect | 21500 | 300 | 0.783 / 0.745 | nan |  | 0.01851 | 0 |
| Zm1p3/L48/m2m1p94_s6045 | PD h200 | not started | | | | | | | 0 |
| Zm1p3/L64/m2m1p94_s6046 | complete | collect | 40000 | 4000 | 0.797 / 0.754 | nan |  | 0.01133 | 0 |
| Zm1p3/L48/m2m1p98_s6047 | complete | collect | 40000 | 4000 | 0.811 / 0.775 | nan |  | 0.0134 | 0 |
| Zm1p3/L64/m2m1p98_s6048 | complete | collect | 40000 | 4000 | 0.793 / 0.720 | nan |  | 0.0111 | 0 |
| Zm1p1716/L48/m2m1p3_s6049 | complete | collect | 40000 | 4000 | 0.814 / 0.765 | nan |  | 0.01274 | 0 |
| Zm1p1716/L48/m2m1p45_s6050 | complete | collect | 40000 | 4000 | 0.830 / 0.785 | nan |  | 0.01262 | 0 |
| Zm1p1716/L48/m2m1p6_s6051 | complete | collect | 40000 | 4000 | 0.797 / 0.751 | nan |  | 0.01408 | 0 |
| Zm1p1716/L48/m2m1p75_s6052 | PD h100 | not started | | | | | | | 0 |
| Zm1p1716/L48/m2m1p85_s6053 | PD h200 | not started | | | | | | | 0 |
| Zm1p1716/L48/m2m1p93_s6054 | complete | collect | 40000 | 4000 | 0.769 / 0.730 | nan |  | 0.0151 | 0 |
| Zm1p1716/L64/m2m1p93_s6055 | complete | collect | 40000 | 4000 | 0.799 / 0.762 | nan |  | 0.01088 | 0 |
| Zm1p1716/L32/m2m1p93_s6056 | complete | collect | 40000 | 4000 | 0.835 / 0.789 | nan |  | 0.01675 | 0 |
| Zm1p1716/L48/m2m1p99_s6057 | complete | collect | 40000 | 4000 | 0.787 / 0.751 | nan |  | 0.01408 | 0 |
| Zm1p1716/L64/m2m1p99_s6058 | complete | collect | 40000 | 4000 | 0.803 / 0.756 | nan |  | 0.01056 | 0 |
| Zm1p1716/L48/m2m2p03_s6059 | complete | collect | 40000 | 4000 | 0.823 / 0.778 | nan |  | 0.01261 | 0 |
| Zm1p1716/L64/m2m2p03_s6060 | PD h100 | not started | | | | | | | 0 |
| Zm1p1/L48/m2m1p8_s6061 | PD h200 | not started | | | | | | | 0 |
| Zm1p1/L48/m2m1p9_s6062 | complete | collect | 40000 | 4000 | 0.776 / 0.733 | nan |  | 0.01423 | 0 |
| Zm1p1/L48/m2m2_s6063 | complete | collect | 40000 | 4000 | 0.778 / 0.715 | nan |  | 0.01424 | 0 |
| Zm1p1/L48/m2m2p1_s6064 | complete | collect | 40000 | 4000 | 0.813 / 0.709 | nan |  | 0.01212 | 0 |
| Zm1p1/L48/m2m2p2_s6065 | complete | collect | 40000 | 4000 | 0.785 / 0.739 | nan |  | 0.01366 | 0 |
| Zm1p1/L48/m2m2p3_s6066 | complete | collect | 40000 | 4000 | 0.807 / 0.758 | nan |  | 0.013 | 0 |
| Zm1p1/L48/m2m2p4_s6067 | complete | collect | 40000 | 4000 | 0.803 / 0.775 | nan |  | 0.01353 | 0 |
| Zm1p1/L64/m2m2p4_s6068 | PD h100 | not started | | | | | | | 0 |
| Zm1p1/L32/m2m2p4_s6069 | PD h200 | not started | | | | | | | 0 |
| Zm1p1/L48/m2m2p5_s6070 | complete | collect | 40000 | 4000 | 0.798 / 0.746 | nan |  | 0.01326 | 0 |
| Zm1p1/L64/m2m2p5_s6071 | complete | collect | 40000 | 4000 | 0.793 / 0.721 | nan |  | 0.01088 | 0 |
| Zm1p1/L48/m2m2p6_s6072 | complete | collect | 40000 | 4000 | 0.791 / 0.768 | nan |  | 0.0138 | 0 |
| Zm1p1/L64/m2m2p6_s6073 | complete | collect | 40000 | 4000 | 0.808 / 0.711 | nan |  | 0.009956 | 0 |
| Zm1p05/L48/m2m1p8_s6074 | complete | collect | 40000 | 4000 | 0.806 / 0.758 | nan |  | 0.01341 | 0 |
| Zm1p05/L48/m2m1p9_s6075 | complete | collect | 40000 | 4000 | 0.769 / 0.715 | nan |  | 0.01495 | 0 |
| Zm1p05/L48/m2m2_s6076 | PD h100 | not started | | | | | | | 0 |
| Zm1p05/L48/m2m2p1_s6077 | PD h200 | not started | | | | | | | 0 |
| Zm1p05/L48/m2m2p2_s6078 | complete | collect | 40000 | 4000 | 0.786 / 0.751 | nan |  | 0.01367 | 0 |
| Zm1p05/L48/m2m2p3_s6079 | complete | collect | 40000 | 4000 | 0.816 / 0.781 | nan |  | 0.01287 | 0 |
| Zm1p05/L48/m2m2p4_s6080 | complete | collect | 40000 | 4000 | 0.813 / 0.752 | nan |  | 0.01287 | 0 |
| Zm1p05/L64/m2m2p4_s6081 | complete | collect | 40000 | 4000 | 0.801 / 0.745 | nan |  | 0.01077 | 0 |
| Zm1p05/L32/m2m2p4_s6082 | complete | collect | 40000 | 4000 | 0.820 / 0.773 | nan |  | 0.01659 | 0 |
| Zm1p05/L48/m2m2p5_s6083 | PD l40s | not started | | | | | | | 0 |
| Zm1p05/L64/m2m2p5_s6084 | PD h100 | not started | | | | | | | 0 |
| Zm1p05/L48/m2m2p6_s6085 | PD h200 | not started | | | | | | | 0 |
| Zm1p05/L64/m2m2p6_s6086 | complete | collect | 40000 | 4000 | 0.804 / 0.770 | nan |  | 0.01056 | 0 |
| Zm1/L48/m2m1p8_s6087 | complete | collect | 40000 | 4000 | 0.791 / 0.764 | nan |  | 0.01366 | 0 |
| Zm1/L48/m2m1p9_s6088 | PD l40s | not started | | | | | | | 0 |
| Zm1/L48/m2m2_s6089 | complete | collect | 40000 | 4000 | 0.791 / 0.757 | nan |  | 0.01381 | 0 |
| Zm1/L48/m2m2p1_s6090 | complete | collect | 40000 | 4000 | 0.795 / 0.757 | nan |  | 0.01353 | 0 |
| Zm1/L48/m2m2p2_s6091 | PD l40s | not started | | | | | | | 0 |
| Zm1/L48/m2m2p3_s6092 | PD h100 | not started | | | | | | | 0 |
| Zm1/L48/m2m2p4_s6093 | PD h200 | not started | | | | | | | 0 |
| Zm1/L64/m2m2p4_s6094 | complete | collect | 40000 | 4000 | 0.785 / 0.736 | nan |  | 0.0111 | 0 |
| Zm1/L32/m2m2p4_s6095 | complete | collect | 40000 | 4000 | 0.792 / 0.741 | nan |  | 0.01833 | 0 |
| Zm1/L48/m2m2p5_s6096 | PD l40s | not started | | | | | | | 0 |
| Zm1/L64/m2m2p5_s6097 | complete | collect | 40000 | 4000 | 0.811 / 0.783 | nan |  | 0.01046 | 0 |
| Zm1/L48/m2m2p6_s6098 | complete | collect | 40000 | 4000 | 0.796 / 0.747 | nan |  | 0.01339 | 0 |
| Zm1/L64/m2m2p6_s6099 | PD l40s | not started | | | | | | | 0 |
| Zm0p95/L48/m2m1p735_s6100 | PD h100 | not started | | | | | | | 0 |
| Zm0p95/L48/m2m1p885_s6101 | PD h200 | not started | | | | | | | 0 |
| Zm0p95/L48/m2m2p035_s6102 | complete | collect | 40000 | 4000 | 0.787 / 0.728 | nan |  | 0.01394 | 0 |
| Zm0p95/L48/m2m2p185_s6103 | complete | collect | 40000 | 4000 | 0.779 / 0.734 | nan |  | 0.01394 | 0 |
| Zm0p95/L48/m2m2p285_s6104 | PD l40s | not started | | | | | | | 0 |
| Zm0p95/L48/m2m2p365_s6105 | complete | collect | 40000 | 4000 | 0.811 / 0.788 | nan |  | 0.01261 | 0 |
| Zm0p95/L64/m2m2p365_s6106 | complete | collect | 40000 | 4000 | 0.793 / 0.748 | nan |  | 0.01067 | 0 |
| Zm0p95/L32/m2m2p365_s6107 | PD l40s | not started | | | | | | | 0 |
| Zm0p95/L48/m2m2p425_s6108 | PD h100 | not started | | | | | | | 0 |
| Zm0p95/L64/m2m2p425_s6109 | PD h200 | not started | | | | | | | 0 |
| Zm0p95/L48/m2m2p465_s6110 | complete | collect | 40000 | 4000 | 0.795 / 0.765 | nan |  | 0.01326 | 0 |
| Zm0p95/L64/m2m2p465_s6111 | complete | collect | 40000 | 4000 | 0.787 / 0.739 | nan |  | 0.01099 | 0 |
| Zm0p9/L48/m2m1p633_s6112 | PD l40s | not started | | | | | | | 0 |
| Zm0p9/L48/m2m1p783_s6113 | complete | collect | 40000 | 4000 | 0.803 / 0.761 | nan |  | 0.01326 | 0 |
| Zm0p9/L48/m2m1p933_s6114 | complete | collect | 40000 | 4000 | 0.795 / 0.762 | nan |  | 0.01353 | 0 |
| Zm0p9/L48/m2m2p083_s6115 | PD l40s | not started | | | | | | | 0 |
| Zm0p9/L48/m2m2p183_s6116 | PD h100 | not started | | | | | | | 0 |
| Zm0p9/L48/m2m2p263_s6117 | PD h200 | not started | | | | | | | 0 |
| Zm0p9/L64/m2m2p263_s6118 | complete | collect | 40000 | 4000 | 0.786 / 0.753 | nan |  | 0.01099 | 0 |
| Zm0p9/L32/m2m2p263_s6119 | complete | collect | 40000 | 4000 | 0.793 / 0.758 | nan |  | 0.01833 | 0 |
| Zm0p9/L48/m2m2p323_s6120 | PD l40s | not started | | | | | | | 0 |
| Zm0p9/L64/m2m2p323_s6121 | complete | collect | 40000 | 4000 | 0.820 / 0.710 | nan |  | 0.009747 | 0 |
| Zm0p9/L48/m2m2p363_s6122 | complete | collect | 40000 | 4000 | 0.781 / 0.735 | nan |  | 0.01353 | 0 |
| Zm0p9/L64/m2m2p363_s6123 | PD l40s | not started | | | | | | | 0 |
| Zm0p8/L48/m2m1p444_s6124 | PD h100 | not started | | | | | | | 0 |
| Zm0p8/L48/m2m1p594_s6125 | PD h200 | not started | | | | | | | 0 |
| Zm0p8/L48/m2m1p744_s6126 | complete | collect | 40000 | 4000 | 0.773 / 0.750 | nan |  | 0.01436 | 0 |
| Zm0p8/L48/m2m1p894_s6127 | complete | collect | 40000 | 4000 | 0.801 / 0.729 | nan |  | 0.01249 | 0 |
| Zm0p8/L48/m2m1p994_s6128 | PD l40s | not started | | | | | | | 0 |
| Zm0p8/L48/m2m2p074_s6129 | complete | collect | 40000 | 4000 | 0.807 / 0.755 | nan |  | 0.013 | 0 |
| Zm0p8/L64/m2m2p074_s6130 | complete | collect | 40000 | 4000 | 0.794 / 0.751 | nan |  | 0.01066 | 0 |
| Zm0p8/L32/m2m2p074_s6131 | PD l40s | not started | | | | | | | 0 |
| Zm0p8/L48/m2m2p134_s6132 | PD h100 | not started | | | | | | | 0 |
| Zm0p8/L64/m2m2p134_s6133 | PD h200 | not started | | | | | | | 0 |
| Zm0p8/L48/m2m2p174_s6134 | complete | collect | 40000 | 4000 | 0.797 / 0.703 | nan |  | 0.01274 | 0 |
| Zm0p8/L64/m2m2p174_s6135 | complete | collect | 40000 | 4000 | 0.801 / 0.760 | nan |  | 0.01045 | 0 |
| Zm0p6/L48/m2m1p122_s6136 | PD l40s | not started | | | | | | | 0 |
| Zm0p6/L48/m2m1p272_s6137 | complete | collect | 40000 | 4000 | 0.813 / 0.760 | nan |  | 0.01236 | 0 |
| Zm0p6/L48/m2m1p422_s6138 | complete | collect | 40000 | 4000 | 0.804 / 0.772 | nan |  | 0.013 | 0 |
| Zm0p6/L48/m2m1p572_s6139 | PD l40s | not started | | | | | | | 0 |
| Zm0p6/L48/m2m1p672_s6140 | PD h100 | not started | | | | | | | 0 |
| Zm0p6/L48/m2m1p752_s6141 | PD h200 | not started | | | | | | | 0 |
| Zm0p6/L64/m2m1p752_s6142 | complete | collect | 40000 | 4000 | 0.812 / 0.782 | nan |  | 0.01025 | 0 |
| Zm0p6/L32/m2m1p752_s6143 | complete | collect | 40000 | 4000 | 0.792 / 0.753 | nan |  | 0.01797 | 0 |
| Zm0p6/L48/m2m1p812_s6144 | PD l40s | not started | | | | | | | 0 |
| Zm0p6/L64/m2m1p812_s6145 | complete | collect | 40000 | 4000 | 0.810 / 0.777 | nan |  | 0.01025 | 0 |
| Zm0p6/L48/m2m1p852_s6146 | complete | collect | 40000 | 4000 | 0.819 / 0.789 | nan |  | 0.01262 | 0 |
| Zm0p6/L64/m2m1p852_s6147 | PD l40s | not started | | | | | | | 0 |
| Zm0p4/L48/m2m0p86_s6148 | PD h100 | not started | | | | | | | 0 |
| Zm0p4/L48/m2m1p01_s6149 | PD h200 | not started | | | | | | | 0 |
| Zm0p4/L48/m2m1p16_s6150 | complete | collect | 40000 | 4000 | 0.808 / 0.769 | nan |  | 0.013 | 0 |
| Zm0p4/L48/m2m1p31_s6151 | complete | collect | 40000 | 4000 | 0.812 / 0.788 | nan |  | 0.01274 | 0 |
| Zm0p4/L48/m2m1p41_s6152 | PD l40s | not started | | | | | | | 0 |
| Zm0p4/L48/m2m1p49_s6153 | complete | collect | 40000 | 4000 | 0.766 / 0.736 | nan |  | 0.01408 | 0 |
| Zm0p4/L64/m2m1p49_s6154 | complete | collect | 40000 | 4000 | 0.779 / 0.720 | nan |  | 0.01102 | 0 |
| Zm0p4/L32/m2m1p49_s6155 | PD l40s | not started | | | | | | | 0 |
| Zm0p4/L48/m2m1p55_s6156 | PD h100 | not started | | | | | | | 0 |
| Zm0p4/L64/m2m1p55_s6157 | PD h200 | not started | | | | | | | 0 |
| Zm0p4/L48/m2m1p59_s6158 | complete | collect | 40000 | 4000 | 0.798 / 0.694 | nan |  | 0.01261 | 0 |
| Zm0p4/L64/m2m1p59_s6159 | complete | collect | 40000 | 4000 | 0.787 / 0.736 | nan |  | 0.01088 | 0 |
| Z0/L48/m2m0p466_s6160 | PD l40s | not started | | | | | | | 0 |
| Z0/L48/m2m0p616_s6161 | complete | collect | 40000 | 4000 | 0.805 / 0.779 | nan |  | 0.01224 | 0 |
| Z0/L48/m2m0p766_s6162 | complete | collect | 40000 | 4000 | 0.790 / 0.742 | nan |  | 0.01353 | 0 |
| Z0/L48/m2m0p916_s6163 | PD l40s | not started | | | | | | | 0 |
| Z0/L48/m2m1p016_s6164 | PD h100 | not started | | | | | | | 0 |
| Z0/L48/m2m1p096_s6165 | PD h200 | not started | | | | | | | 0 |
| Z0/L64/m2m1p096_s6166 | complete | collect | 40000 | 4000 | 0.800 / 0.751 | nan |  | 0.009944 | 0 |
| Z0/L32/m2m1p096_s6167 | complete | collect | 40000 | 4000 | 0.808 / 0.770 | nan |  | 0.01709 | 0 |
| Z0/L48/m2m1p156_s6168 | PD l40s | not started | | | | | | | 0 |
| Z0/L64/m2m1p156_s6169 | complete | collect | 40000 | 4000 | 0.811 / 0.782 | nan |  | 0.01005 | 0 |
| Z0/L48/m2m1p196_s6170 | complete | collect | 40000 | 4000 | 0.819 / 0.782 | nan |  | 0.012 | 0 |
| Z0/L64/m2m1p196_s6171 | PD l40s | not started | | | | | | | 0 |

## Operations journal (last 60 lines of `$LP_HMC_RUNS/OPS_JOURNAL.md`)

## 2026-11-22 22:28 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/zeff/Zm0p4/L48/m2m1p59_s6158

## 2026-11-22 22:28 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/zeff/Zm0p6/L32/m2m1p752_s6143

## 2026-11-22 22:28 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/zeff/Zm0p6/L48/m2m1p852_s6146

## 2026-11-22 22:28 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/zeff/Zm0p6/L64/m2m1p752_s6142

## 2026-11-22 22:28 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/zeff/Zm0p6/L64/m2m1p812_s6145

## 2026-11-22 22:28 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/zeff/Zm0p8/L64/m2m2p174_s6135

## 2026-11-22 22:28 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/zeff/Zm1p05/L48/m2m1p9_s6075

## 2026-11-22 22:28 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/zeff/Zm1p1/L48/m2m2p6_s6072

## 2026-11-22 22:28 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/zeff/Zm1p5/L48/m2m1p65_s6028

## 2026-11-22 22:39 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/zeff/Z0/L32/m2m1p096_s6167

## 2026-11-22 22:39 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/zeff/Z0/L48/m2m0p616_s6161

## 2026-11-22 22:39 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/zeff/Z0/L48/m2m0p766_s6162

## 2026-11-22 22:39 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/zeff/Zm0p4/L64/m2m1p49_s6154

## 2026-11-22 22:58 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/zeff/Z0/L48/m2m1p196_s6170

## 2026-11-22 22:58 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/zeff/Z0/L64/m2m1p096_s6166

## 2026-11-22 22:58 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/zeff/Z0/L64/m2m1p156_s6169

## 2026-11-22 22:58 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/zeff/Zm0p4/L64/m2m1p59_s6159

## 2026-11-22 22:58 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/zeff/Zm1p05/L48/m2m2p4_s6080

## 2026-11-22 22:58 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/zeff/Zm1p5/L64/m2m1p93_s6036

## 2026-11-22 23:09 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/uline/Zm0p9/L32/m2m2p408_s701_ordered

