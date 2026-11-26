# Hazel campaign status

Generated 2026-11-26 03:16 UTC by `scripts/hpc_status_report.py` on the cluster (branch `hazel-ops`). Run data are not in git; copy completed stages with rsync (docs/HPC.md §4).

## Operator notes

- **Hardware:** chains use `gpu_partners`/`short_gpu` with GPU types L40S, H100, H200 and RTX PRO 6000. They're picked per (re)submission. The `gpu` partition gave 2 four-hour H100 cycles, then nothing for 7 h. All rows are back on `short_gpu`. Throughput is about 8 sweeps/s at L=32 and 20–45 sweeps/s at L=24, per GPU.
- **`p9_mixed` (not yet in the run plan; approved by the user on Hazel 2026-11-20):** `p9_pilot` m²=−2.50/−2.65 cannot cross the gap between the uniform branch (P_shell≈0, |M|≈0.7) and the modulated branch (P_shell≳0.02) with the shell ladder. Both stopped with `exit=3` and 0 round trips; the checkpoint diagnostic is in the journal. `p9_mixed` redoes all four masses on s = M² − 2·P_shell over s∈[−0.95, 0.60] with 240 windows, MIN_SWAP 0.1. All four masses transport through the gap; see the round-trip counts below. Gate: −2.20/−2.35 need 30% round-trip walkers with a 1.5M cap; −2.50/−2.65 need 15% (36 walkers) with a 2.5M cap (user-approved 2026-11-21), because they transport more slowly across the uniform↔modulated switch.
- **`p9_pilot` m²=−2.20/−2.35** completed normally on the shell coordinate. The −2.50/−2.65 rows are superseded by `p9_mixed`, and their checkpoints are kept.
- **Run plan r5 (2026-11-22):** `s2_zm1172_prod` L32 rows are cancelled (checkpoints kept, not resubmitted). New stages `p8_mixed` (6), `p8_shift` (5) and `p9_L27` (2) were prepared and submitted on 2026-11-22 around 03:00 EST; the `p8_mixed` L16 rows run on Intel GPUs only.
- **Run plan r6 (2026-11-22):** `p8_shift` and `p8_mixed` are on HOLD. Their chains were cancelled around 13:30 EST, with no resubmit; all 11 checkpoints and data are kept. A one-off checkpoint push of `p9_mixed` and `s2_zm1172_prod` (115 MB) went to `checkpoints/` on the share. `uline`, `s2_zm2_ext` and `p9_L27` continue on the new `cv_umbrella.jl`.
- **Run plan r7 (2026-11-22):** new stage `zeff`, 171 unbiased S(k) runs (`sk_symmetric.jl`, plain HMC, 8 replicas, no umbrella), submitted around 14:00 EST. Their HMC columns show collect-phase acceptance; swap and round-trip columns don't apply.

- **ETA (2026-11-24 02:40 EST):** ~1–2 weeks for all stages except `b8_mixed`, 2–3 weeks with it; queue-limited (3–5 GPUs avg). Details: `ETA_2026-11-24.md` in the sync folder.

- **ANSWERED by run plan r10 (new stage `bline`) — was OPEN QUESTION (2026-11-25):** `b8` L=20 shows no coexistence (chi peak at m² −2.375, edge of range, above both simulated masses). Add an L=20 row near −2.40 to −2.45? See `QUESTION_b8_L20_2026-11-25.md` in the sync folder.

## Summary

| stage | complete | queued/running | idle |
|---|---|---|---|
| `b13` | 2/6 | 1 | 3 |
| `b8` | 2/6 | 0 | 4 |
| `b8_mixed` | 0/4 | 2 | 2 |
| `bline` | 1/8 | 7 | 0 |
| `p8_mixed` | 0/6 | 0 | 6 |
| `p8_shift` | 0/5 | 0 | 5 |
| `p9_L27` | 0/2 | 0 | 2 |
| `p9_mixed` | 4/4 | 0 | 0 |
| `p9_pilot` | 2/4 | 0 | 2 |
| `s2_zm1172_prod` | 4/6 | 0 | 2 |
| `s2_zm2_ext` | 2/4 | 2 | 0 |
| `uline` | 44/48 | 4 | 0 |
| `uline_ext` | 8/24 | 16 | 0 |
| `validate` | 1/1 | 0 | 0 |
| `zeff` | 171/171 | 0 | 0 |
| `zeff2` | 11/11 | 0 | 0 |

Running GPUs: h100 1, h200 2, l40s 4

During thermalization the HMC columns show the last check interval (ε adapts per window); for completed/collecting rows they show the whole collect phase. Round-trip walkers reset when collection starts.

## Runs

### `b13` (2/6 complete)

| run | state | phase | sweeps | collected | HMC acc (mean / min window) | min swap | round-trip walkers | ε median | cont |
|---|---|---|---|---|---|---|---|---|---|
| Zm1p3/L20/m2m2p39_s1320 | complete | collect | 223000 | 4000 | 0.800 / 0.727 | 0.383 | 0 | 0.02607 | 0 |
| Zm1p3/L20/m2m2p49_s1330 | complete | collect | 244000 | 4000 | 0.802 / 0.723 | 0.379 | 0 | 0.02556 | 1 |
| Zm1p3/L28/m2m2p44_s1328 | PD rtx_6000_pro | therm | 119402 | 0 | 0.800 / 0.769 | 0.402 | 0 | 0.02029 | 3 |
| Zm1p3/L28/m2m2p54_s1338 | IDLE | therm | 258000 | 0 | 0.800 / 0.787 | 0.399 | 0 | 0.02029 | 5 |
| Zm1p3/L32/m2m2p47_s1332 | IDLE | therm | 102293 | 0 | 0.801 / 0.741 | 0.395 | 0 | 0.01833 | 3 |
| Zm1p3/L32/m2m2p57_s1342 | IDLE | therm | 112394 | 0 | 0.800 / 0.754 | 0.397 | 0 | 0.01833 | 4 |

### `b8` (2/6 complete)

| run | state | phase | sweeps | collected | HMC acc (mean / min window) | min swap | round-trip walkers | ε median | cont |
|---|---|---|---|---|---|---|---|---|---|
| Zm1p1716/L20/m2m2p5_s1220 | complete | collect | 201000 | 4000 | 0.798 / 0.670 | 0.395 | 0 | 0.02582 | 0 |
| Zm1p1716/L20/m2m2p6_s1230 | complete | collect | 243000 | 4000 | 0.800 / 0.682 | 0.381 | 0 | 0.02556 | 1 |
| Zm1p1716/L28/m2m2p55_s1228 | IDLE | therm | 136046 | 0 | 0.801 / 0.630 | 0.397 | 0 | 0.02029 | 3 |
| Zm1p1716/L28/m2m2p65_s1238 | IDLE | therm | 88298 | 0 | 0.799 / 0.752 | 0.398 | 0 | 0.01989 | 2 |
| Zm1p1716/L32/m2m2p58_s1232 | IDLE | therm | 78583 | 0 | 0.799 / 0.767 | 0.395 | 0 | 0.01797 | 3 |
| Zm1p1716/L32/m2m2p68_s1242 | IDLE | therm | 90721 | 0 | 0.801 / 0.781 | 0.394 | 0 | 0.01797 | 3 |

### `b8_mixed` (0/4 complete)

| run | state | phase | sweeps | collected | HMC acc (mean / min window) | min swap | round-trip walkers | ε median | cont |
|---|---|---|---|---|---|---|---|---|---|
| Zm1p1716/L20/m2m2p7_s1420 | PD rtx_6000_pro | therm | 249564 | 0 | 0.800 / 0.761 | 0.170 | 0 | 0.02556 | 2 |
| Zm1p1716/L20/m2m2p9_s1430 | PD rtx_6000_pro | therm | 149387 | 0 | 0.800 / 0.747 | 0.181 | 0 | 0.0253 | 2 |
| Zm1p1716/L28/m2m2p7_s1428 | IDLE | not started | | | | | | | 0 |
| Zm1p1716/L28/m2m2p9_s1438 | IDLE | not started | | | | | | | 0 |

### `bline` (1/8 complete)

| run | state | phase | sweeps | collected | HMC acc (mean / min window) | min swap | round-trip walkers | ε median | cont |
|---|---|---|---|---|---|---|---|---|---|
| Zm1p1716/L20/m2m2p36_s1620 | complete | collect | 180000 | 4000 | 0.802 / 0.704 | 0.393 | 0 | 0.02556 | 0 |
| Zm1p1716/L28/m2m2p34_s1638 | PD h100 | therm | 92052 | 0 | 0.801 / 0.596 | 0.403 | 0 | 0.02029 | 2 |
| Zm1p1716/L28/m2m2p4_s1648 | R l40s | therm | 91000 | 0 | 0.799 / 0.787 | 0.402 | 0 | 0.01989 | 2 |
| Zm1p1716/L32/m2m2p34_s1662 | PD l40s | therm | 26768 | 0 | 0.799 / 0.783 | 0.393 | 0 | 0.01797 | 1 |
| Zm1p1716/L32/m2m2p4_s1672 | R l40s | therm | 89000 | 0 | 0.800 / 0.787 | 0.401 | 0 | 0.01797 | 3 |
| Zm1p3/L28/m2m2p36_s1728 | PD l40s | therm | 88099 | 0 | 0.795 / 0.707 | 0.400 | 0 | 0.02029 | 2 |
| Zm1p3/L32/m2m2p34_s1742 | PD h100 | therm | 25036 | 0 | 0.803 / 0.583 | 0.394 | 0 | 0.01833 | 1 |
| Zm1p3/L32/m2m2p4_s1752 | R h200 | therm | 37000 | 0 | 0.800 / 0.787 | 0.396 | 0 | 0.01833 | 1 |

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
| Zm0p9358/L27/m2m2p42_s1100 | IDLE | therm | 255449 | 0 | 0.800 / 0.762 | 0.213 | 0 | 0.02017 | 6 |
| Zm0p9358/L27/m2m2p47_s1101 | IDLE | therm | 266530 | 0 | 0.801 / 0.772 | 0.180 | 0 | 0.01997 | 6 |

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
| Zm2/L36/m2m1p92_s134 | PD h200 | therm | 336274 | 0 | 0.801 / 0.741 | 0.400 | 4 | 0.0178 | 19 |
| Zm2/L36/m2m1p96_s135 | PD rtx_6000_pro | therm | 314632 | 0 | 0.800 / 0.775 | 0.401 | 0 | 0.01745 | 13 |

### `uline` (44/48 complete)

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
| Zm0p8/L32/m2m2p2_s710_disordered | complete | collect | 576000 | 8000 | 0.801 / 0.690 | 0.380 | 0 | 0.01761 | 13 |
| Zm0p8/L32/m2m2p2_s711_ordered | complete | collect | 549000 | 8000 | 0.801 / 0.713 | 0.386 | 0 | 0.01761 | 11 |
| Zm0p8/L32/m2m2p18_s720_disordered | complete | collect | 550000 | 8000 | 0.801 / 0.714 | 0.385 | 0 | 0.01761 | 12 |
| Zm0p8/L32/m2m2p18_s721_ordered | complete | collect | 544000 | 8000 | 0.801 / 0.719 | 0.385 | 0 | 0.01761 | 10 |
| Zm0p85/L24/m2m2p31_s700_disordered | complete | collect | 286000 | 8000 | 0.800 / 0.738 | 0.381 | 0 | 0.02185 | 1 |
| Zm0p85/L24/m2m2p31_s701_ordered | complete | collect | 267000 | 8000 | 0.802 / 0.700 | 0.374 | 0 | 0.02185 | 2 |
| Zm0p85/L24/m2m2p29_s710_disordered | complete | collect | 247000 | 8000 | 0.802 / 0.726 | 0.380 | 0 | 0.02185 | 1 |
| Zm0p85/L24/m2m2p29_s711_ordered | complete | collect | 272000 | 8000 | 0.800 / 0.708 | 0.377 | 0 | 0.02185 | 1 |
| Zm0p85/L24/m2m2p27_s720_disordered | complete | collect | 251000 | 8000 | 0.801 / 0.710 | 0.387 | 0 | 0.02185 | 1 |
| Zm0p85/L24/m2m2p27_s721_ordered | complete | collect | 235000 | 8000 | 0.799 / 0.695 | 0.382 | 0 | 0.02185 | 1 |
| Zm0p85/L32/m2m2p317_s700_disordered | complete | collect | 633000 | 8000 | 0.800 / 0.718 | 0.380 | 0 | 0.01761 | 14 |
| Zm0p85/L32/m2m2p317_s701_ordered | complete | collect | 677000 | 8000 | 0.803 / 0.705 | 0.384 | 0 | 0.01761 | 13 |
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
| Zm0p9/L32/m2m2p408_s700_disordered | PD rtx_6000_pro | collect | 737646 | 5323 | 0.801 / 0.709 | 0.375 | 0 | 0.01761 | 15 |
| Zm0p9/L32/m2m2p408_s701_ordered | complete | collect | 719000 | 8000 | 0.802 / 0.671 | 0.367 | 0 | 0.01761 | 13 |
| Zm0p9/L32/m2m2p388_s710_disordered | complete | collect | 636000 | 8000 | 0.800 / 0.685 | 0.372 | 0 | 0.01761 | 13 |
| Zm0p9/L32/m2m2p388_s711_ordered | complete | collect | 715000 | 8000 | 0.800 / 0.694 | 0.383 | 0 | 0.01761 | 14 |
| Zm0p9/L32/m2m2p368_s720_disordered | complete | collect | 689000 | 8000 | 0.800 / 0.695 | 0.377 | 0 | 0.01797 | 14 |
| Zm0p9/L32/m2m2p368_s721_ordered | complete | collect | 662000 | 8000 | 0.800 / 0.681 | 0.378 | 0 | 0.01761 | 13 |
| Zm0p95/L24/m2m2p507_s700_disordered | complete | collect | 407000 | 8000 | 0.802 / 0.686 | 0.354 | 0 | 0.02185 | 2 |
| Zm0p95/L24/m2m2p507_s701_ordered | complete | collect | 365000 | 8000 | 0.802 / 0.719 | 0.353 | 0 | 0.02185 | 2 |
| Zm0p95/L24/m2m2p487_s710_disordered | complete | collect | 328000 | 8000 | 0.797 / 0.677 | 0.364 | 0 | 0.02185 | 1 |
| Zm0p95/L24/m2m2p487_s711_ordered | complete | collect | 342000 | 8000 | 0.801 / 0.724 | 0.355 | 0 | 0.02185 | 1 |
| Zm0p95/L24/m2m2p467_s720_disordered | complete | collect | 271000 | 8000 | 0.800 / 0.729 | 0.358 | 0 | 0.02229 | 1 |
| Zm0p95/L24/m2m2p467_s721_ordered | complete | collect | 311000 | 8000 | 0.803 / 0.703 | 0.368 | 0 | 0.02185 | 2 |
| Zm0p95/L32/m2m2p51_s700_disordered | PD rtx_6000_pro | therm | 784979 | 0 | 0.800 / 0.784 | 0.365 | 92 | 0.01797 | 16 |
| Zm0p95/L32/m2m2p51_s701_ordered | PD rtx_6000_pro | therm | 732473 | 0 | 0.800 / 0.772 | 0.365 | 80 | 0.01761 | 15 |
| Zm0p95/L32/m2m2p49_s710_disordered | PD rtx_6000_pro | therm | 600000 | 0 | 0.800 / 0.786 | 0.366 | 68 | 0.01761 | 13 |
| Zm0p95/L32/m2m2p49_s711_ordered | complete | collect | 757000 | 8000 | 0.799 / 0.690 | 0.364 | 0 | 0.01761 | 15 |
| Zm0p95/L32/m2m2p47_s720_disordered | complete | collect | 731000 | 8000 | 0.799 / 0.683 | 0.357 | 0 | 0.01797 | 14 |
| Zm0p95/L32/m2m2p47_s721_ordered | complete | collect | 697000 | 8000 | 0.799 / 0.710 | 0.358 | 0 | 0.01797 | 13 |

### `uline_ext` (8/24 complete)

| run | state | phase | sweeps | collected | HMC acc (mean / min window) | min swap | round-trip walkers | ε median | cont |
|---|---|---|---|---|---|---|---|---|---|
| Zm1/L24/m2m2p63_s1524_disordered | complete | collect | 648000 | 8000 | 0.802 / 0.720 | 0.340 | 0 | 0.02185 | 3 |
| Zm1/L24/m2m2p63_s2524_ordered | complete | collect | 635000 | 8000 | 0.799 / 0.699 | 0.324 | 0 | 0.02229 | 2 |
| Zm1/L24/m2m2p6_s1534_disordered | complete | collect | 445000 | 8000 | 0.800 / 0.648 | 0.345 | 0 | 0.02185 | 1 |
| Zm1/L24/m2m2p6_s2534_ordered | complete | collect | 455000 | 8000 | 0.799 / 0.690 | 0.345 | 0 | 0.02229 | 2 |
| Zm1/L24/m2m2p57_s1544_disordered | complete | collect | 402000 | 8000 | 0.799 / 0.719 | 0.352 | 0 | 0.02229 | 1 |
| Zm1/L24/m2m2p57_s2544_ordered | complete | collect | 375000 | 8000 | 0.795 / 0.665 | 0.356 | 0 | 0.02229 | 1 |
| Zm1/L32/m2m2p63_s1532_disordered | PD rtx_6000_pro | therm | 193393 | 0 | 0.800 / 0.761 | 0.349 | 0 | 0.01779 | 4 |
| Zm1/L32/m2m2p63_s2532_ordered | R h100 | therm | 226000 | 0 | 0.800 / 0.786 | 0.347 | 0 | 0.01797 | 4 |
| Zm1/L32/m2m2p6_s1542_disordered | PD rtx_6000_pro | therm | 226295 | 0 | 0.801 / 0.753 | 0.352 | 1 | 0.01797 | 5 |
| Zm1/L32/m2m2p6_s2542_ordered | R l40s | therm | 313000 | 0 | 0.800 / 0.785 | 0.353 | 1 | 0.01797 | 7 |
| Zm1/L32/m2m2p57_s1552_disordered | PD l40s | therm | 198341 | 0 | 0.800 / 0.754 | 0.361 | 0 | 0.01779 | 5 |
| Zm1/L32/m2m2p57_s2552_ordered | PD rtx_6000_pro | therm | 106288 | 0 | 0.799 / 0.750 | 0.361 | 0 | 0.01761 | 2 |
| Zm1p05/L24/m2m2p71_s1624_disordered | PD rtx_6000_pro | therm | 486844 | 0 | 0.800 / 0.780 | 0.327 | 34 | 0.02185 | 2 |
| Zm1p05/L24/m2m2p71_s2624_ordered | complete | collect | 762000 | 8000 | 0.801 / 0.732 | 0.337 | 0 | 0.02185 | 3 |
| Zm1p05/L24/m2m2p68_s1634_disordered | complete | collect | 733000 | 8000 | 0.798 / 0.677 | 0.331 | 0 | 0.02229 | 3 |
| Zm1p05/L24/m2m2p68_s2634_ordered | PD rtx_6000_pro | therm | 484299 | 0 | 0.800 / 0.763 | 0.337 | 37 | 0.02229 | 2 |
| Zm1p05/L24/m2m2p65_s1644_disordered | PD rtx_6000_pro | therm | 253266 | 0 | 0.799 / 0.744 | 0.340 | 1 | 0.02229 | 1 |
| Zm1p05/L24/m2m2p65_s2644_ordered | PD h100 | therm | 900000 | 0 | 0.800 / 0.784 | 0.341 | 51 | 0.02229 | 4 |
| Zm1p05/L32/m2m2p71_s1632_disordered | PD rtx_6000_pro | therm | 105399 | 0 | 0.800 / 0.757 | 0.345 | 0 | 0.01797 | 2 |
| Zm1p05/L32/m2m2p71_s2632_ordered | R l40s | therm | 325000 | 0 | 0.800 / 0.785 | 0.344 | 0 | 0.01797 | 7 |
| Zm1p05/L32/m2m2p68_s1642_disordered | PD rtx_6000_pro | therm | 46124 | 0 | 0.800 / 0.694 | 0.350 | 0 | 0.01761 | 1 |
| Zm1p05/L32/m2m2p68_s2642_ordered | PD h200 | therm | 186622 | 0 | 0.800 / 0.770 | 0.347 | 0 | 0.01797 | 4 |
| Zm1p05/L32/m2m2p65_s1652_disordered | R h200 | therm | 379000 | 0 | 0.800 / 0.787 | 0.353 | 3 | 0.01797 | 8 |
| Zm1p05/L32/m2m2p65_s2652_ordered | PD rtx_6000_pro | therm | 51420 | 0 | 0.799 / 0.767 | 0.355 | 0 | 0.01797 | 1 |

### `validate` (1/1 complete)

| run | state | phase | sweeps | collected | HMC acc (mean / min window) | min swap | round-trip walkers | ε median | cont |
|---|---|---|---|---|---|---|---|---|---|
| Zm2/L12/m2m1p73_s121 | complete | collect | 24000 | 4000 | 0.811 / 0.798 | 0.393 | 9 | | 0 |

### `zeff` (171/171 complete)

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
| Zm1p75/L48/m2m1p84_s6021 | complete | collect | 40000 | 4000 | 0.787 / 0.730 | nan |  | 0.01451 | 0 |
| Zm1p75/L64/m2m1p84_s6022 | complete | collect | 40000 | 4000 | 0.789 / 0.754 | nan |  | 0.01179 | 0 |
| Zm1p75/L48/m2m1p88_s6023 | complete | collect | 40000 | 4000 | 0.792 / 0.752 | nan |  | 0.01436 | 0 |
| Zm1p75/L64/m2m1p88_s6024 | complete | collect | 40000 | 4000 | 0.786 / 0.730 | nan |  | 0.01167 | 0 |
| Zm1p5/L48/m2m1p2_s6025 | complete | collect | 40000 | 4000 | 0.811 / 0.748 | nan |  | 0.01339 | 0 |
| Zm1p5/L48/m2m1p35_s6026 | complete | collect | 40000 | 4000 | 0.810 / 0.758 | nan |  | 0.01366 | 0 |
| Zm1p5/L48/m2m1p5_s6027 | complete | collect | 40000 | 4000 | 0.805 / 0.767 | nan |  | 0.01366 | 0 |
| Zm1p5/L48/m2m1p65_s6028 | complete | collect | 40000 | 4000 | 0.797 / 0.758 | nan |  | 0.0138 | 0 |
| Zm1p5/L48/m2m1p75_s6029 | complete | collect | 40000 | 4000 | 0.807 / 0.719 | nan |  | 0.01326 | 0 |
| Zm1p5/L48/m2m1p83_s6030 | complete | collect | 40000 | 4000 | 0.792 / 0.742 | nan |  | 0.01423 | 0 |
| Zm1p5/L64/m2m1p83_s6031 | complete | collect | 40000 | 4000 | 0.796 / 0.750 | nan |  | 0.01156 | 0 |
| Zm1p5/L32/m2m1p83_s6032 | complete | collect | 40000 | 4000 | 0.794 / 0.744 | nan |  | 0.01908 | 0 |
| Zm1p5/L48/m2m1p89_s6033 | complete | collect | 40000 | 4000 | 0.781 / 0.733 | nan |  | 0.01437 | 0 |
| Zm1p5/L64/m2m1p89_s6034 | complete | collect | 40000 | 4000 | 0.802 / 0.774 | nan |  | 0.01121 | 0 |
| Zm1p5/L48/m2m1p93_s6035 | complete | collect | 40000 | 4000 | 0.781 / 0.739 | nan |  | 0.01408 | 0 |
| Zm1p5/L64/m2m1p93_s6036 | complete | collect | 40000 | 4000 | 0.784 / 0.744 | nan |  | 0.01144 | 0 |
| Zm1p3/L48/m2m1p25_s6037 | complete | collect | 40000 | 4000 | 0.794 / 0.759 | nan |  | 0.0138 | 0 |
| Zm1p3/L48/m2m1p4_s6038 | complete | collect | 40000 | 4000 | 0.797 / 0.745 | nan |  | 0.01394 | 0 |
| Zm1p3/L48/m2m1p55_s6039 | complete | collect | 40000 | 4000 | 0.810 / 0.781 | nan |  | 0.01394 | 0 |
| Zm1p3/L48/m2m1p7_s6040 | complete | collect | 40000 | 4000 | 0.771 / 0.728 | nan |  | 0.01525 | 0 |
| Zm1p3/L48/m2m1p8_s6041 | complete | collect | 40000 | 4000 | 0.781 / 0.758 | nan |  | 0.01408 | 0 |
| Zm1p3/L48/m2m1p88_s6042 | complete | collect | 40000 | 4000 | 0.814 / 0.782 | nan |  | 0.01326 | 0 |
| Zm1p3/L64/m2m1p88_s6043 | complete | collect | 40000 | 4000 | 0.817 / 0.778 | nan |  | 0.01046 | 0 |
| Zm1p3/L32/m2m1p88_s6044 | complete | collect | 40000 | 4000 | 0.786 / 0.748 | nan |  | 0.01851 | 0 |
| Zm1p3/L48/m2m1p94_s6045 | complete | collect | 40000 | 4000 | 0.798 / 0.748 | nan |  | 0.01366 | 0 |
| Zm1p3/L64/m2m1p94_s6046 | complete | collect | 40000 | 4000 | 0.797 / 0.754 | nan |  | 0.01133 | 0 |
| Zm1p3/L48/m2m1p98_s6047 | complete | collect | 40000 | 4000 | 0.811 / 0.775 | nan |  | 0.0134 | 0 |
| Zm1p3/L64/m2m1p98_s6048 | complete | collect | 40000 | 4000 | 0.793 / 0.720 | nan |  | 0.0111 | 0 |
| Zm1p1716/L48/m2m1p3_s6049 | complete | collect | 40000 | 4000 | 0.814 / 0.765 | nan |  | 0.01274 | 0 |
| Zm1p1716/L48/m2m1p45_s6050 | complete | collect | 40000 | 4000 | 0.830 / 0.785 | nan |  | 0.01262 | 0 |
| Zm1p1716/L48/m2m1p6_s6051 | complete | collect | 40000 | 4000 | 0.797 / 0.751 | nan |  | 0.01408 | 0 |
| Zm1p1716/L48/m2m1p75_s6052 | complete | collect | 40000 | 4000 | 0.816 / 0.776 | nan |  | 0.01313 | 0 |
| Zm1p1716/L48/m2m1p85_s6053 | complete | collect | 40000 | 4000 | 0.788 / 0.707 | nan |  | 0.01394 | 0 |
| Zm1p1716/L48/m2m1p93_s6054 | complete | collect | 40000 | 4000 | 0.769 / 0.730 | nan |  | 0.0151 | 0 |
| Zm1p1716/L64/m2m1p93_s6055 | complete | collect | 40000 | 4000 | 0.799 / 0.762 | nan |  | 0.01088 | 0 |
| Zm1p1716/L32/m2m1p93_s6056 | complete | collect | 40000 | 4000 | 0.835 / 0.789 | nan |  | 0.01675 | 0 |
| Zm1p1716/L48/m2m1p99_s6057 | complete | collect | 40000 | 4000 | 0.787 / 0.751 | nan |  | 0.01408 | 0 |
| Zm1p1716/L64/m2m1p99_s6058 | complete | collect | 40000 | 4000 | 0.803 / 0.756 | nan |  | 0.01056 | 0 |
| Zm1p1716/L48/m2m2p03_s6059 | complete | collect | 40000 | 4000 | 0.823 / 0.778 | nan |  | 0.01261 | 0 |
| Zm1p1716/L64/m2m2p03_s6060 | complete | collect | 40000 | 4000 | 0.807 / 0.760 | nan |  | 0.01066 | 0 |
| Zm1p1/L48/m2m1p8_s6061 | complete | collect | 40000 | 4000 | 0.823 / 0.788 | nan |  | 0.01262 | 0 |
| Zm1p1/L48/m2m1p9_s6062 | complete | collect | 40000 | 4000 | 0.776 / 0.733 | nan |  | 0.01423 | 0 |
| Zm1p1/L48/m2m2_s6063 | complete | collect | 40000 | 4000 | 0.778 / 0.715 | nan |  | 0.01424 | 0 |
| Zm1p1/L48/m2m2p1_s6064 | complete | collect | 40000 | 4000 | 0.813 / 0.709 | nan |  | 0.01212 | 0 |
| Zm1p1/L48/m2m2p2_s6065 | complete | collect | 40000 | 4000 | 0.785 / 0.739 | nan |  | 0.01366 | 0 |
| Zm1p1/L48/m2m2p3_s6066 | complete | collect | 40000 | 4000 | 0.807 / 0.758 | nan |  | 0.013 | 0 |
| Zm1p1/L48/m2m2p4_s6067 | complete | collect | 40000 | 4000 | 0.803 / 0.775 | nan |  | 0.01353 | 0 |
| Zm1p1/L64/m2m2p4_s6068 | complete | collect | 40000 | 4000 | 0.794 / 0.726 | nan |  | 0.01088 | 0 |
| Zm1p1/L32/m2m2p4_s6069 | complete | collect | 40000 | 4000 | 0.823 / 0.789 | nan |  | 0.01675 | 0 |
| Zm1p1/L48/m2m2p5_s6070 | complete | collect | 40000 | 4000 | 0.798 / 0.746 | nan |  | 0.01326 | 0 |
| Zm1p1/L64/m2m2p5_s6071 | complete | collect | 40000 | 4000 | 0.793 / 0.721 | nan |  | 0.01088 | 0 |
| Zm1p1/L48/m2m2p6_s6072 | complete | collect | 40000 | 4000 | 0.791 / 0.768 | nan |  | 0.0138 | 0 |
| Zm1p1/L64/m2m2p6_s6073 | complete | collect | 40000 | 4000 | 0.808 / 0.711 | nan |  | 0.009956 | 0 |
| Zm1p05/L48/m2m1p8_s6074 | complete | collect | 40000 | 4000 | 0.806 / 0.758 | nan |  | 0.01341 | 0 |
| Zm1p05/L48/m2m1p9_s6075 | complete | collect | 40000 | 4000 | 0.769 / 0.715 | nan |  | 0.01495 | 0 |
| Zm1p05/L48/m2m2_s6076 | complete | collect | 40000 | 4000 | 0.800 / 0.761 | nan |  | 0.01313 | 0 |
| Zm1p05/L48/m2m2p1_s6077 | complete | collect | 40000 | 4000 | 0.820 / 0.796 | nan |  | 0.01249 | 0 |
| Zm1p05/L48/m2m2p2_s6078 | complete | collect | 40000 | 4000 | 0.786 / 0.751 | nan |  | 0.01367 | 0 |
| Zm1p05/L48/m2m2p3_s6079 | complete | collect | 40000 | 4000 | 0.816 / 0.781 | nan |  | 0.01287 | 0 |
| Zm1p05/L48/m2m2p4_s6080 | complete | collect | 40000 | 4000 | 0.813 / 0.752 | nan |  | 0.01287 | 0 |
| Zm1p05/L64/m2m2p4_s6081 | complete | collect | 40000 | 4000 | 0.801 / 0.745 | nan |  | 0.01077 | 0 |
| Zm1p05/L32/m2m2p4_s6082 | complete | collect | 40000 | 4000 | 0.820 / 0.773 | nan |  | 0.01659 | 0 |
| Zm1p05/L48/m2m2p5_s6083 | complete | collect | 40000 | 4000 | 0.817 / 0.760 | nan |  | 0.01274 | 0 |
| Zm1p05/L64/m2m2p5_s6084 | complete | collect | 40000 | 4000 | 0.791 / 0.750 | nan |  | 0.01067 | 0 |
| Zm1p05/L48/m2m2p6_s6085 | complete | collect | 40000 | 4000 | 0.814 / 0.764 | nan |  | 0.01287 | 0 |
| Zm1p05/L64/m2m2p6_s6086 | complete | collect | 40000 | 4000 | 0.804 / 0.770 | nan |  | 0.01056 | 0 |
| Zm1/L48/m2m1p8_s6087 | complete | collect | 40000 | 4000 | 0.791 / 0.764 | nan |  | 0.01366 | 0 |
| Zm1/L48/m2m1p9_s6088 | complete | collect | 40000 | 4000 | 0.808 / 0.767 | nan |  | 0.01287 | 0 |
| Zm1/L48/m2m2_s6089 | complete | collect | 40000 | 4000 | 0.791 / 0.757 | nan |  | 0.01381 | 0 |
| Zm1/L48/m2m2p1_s6090 | complete | collect | 40000 | 4000 | 0.795 / 0.757 | nan |  | 0.01353 | 0 |
| Zm1/L48/m2m2p2_s6091 | complete | collect | 40000 | 4000 | 0.810 / 0.755 | nan |  | 0.013 | 0 |
| Zm1/L48/m2m2p3_s6092 | complete | collect | 40000 | 4000 | 0.815 / 0.795 | nan |  | 0.01287 | 0 |
| Zm1/L48/m2m2p4_s6093 | complete | collect | 40000 | 4000 | 0.796 / 0.749 | nan |  | 0.01366 | 0 |
| Zm1/L64/m2m2p4_s6094 | complete | collect | 40000 | 4000 | 0.785 / 0.736 | nan |  | 0.0111 | 0 |
| Zm1/L32/m2m2p4_s6095 | complete | collect | 40000 | 4000 | 0.792 / 0.741 | nan |  | 0.01833 | 0 |
| Zm1/L48/m2m2p5_s6096 | complete | collect | 40000 | 4000 | 0.815 / 0.760 | nan |  | 0.01262 | 0 |
| Zm1/L64/m2m2p5_s6097 | complete | collect | 40000 | 4000 | 0.811 / 0.783 | nan |  | 0.01046 | 0 |
| Zm1/L48/m2m2p6_s6098 | complete | collect | 40000 | 4000 | 0.796 / 0.747 | nan |  | 0.01339 | 0 |
| Zm1/L64/m2m2p6_s6099 | complete | collect | 40000 | 4000 | 0.810 / 0.760 | nan |  | 0.01025 | 0 |
| Zm0p95/L48/m2m1p735_s6100 | complete | collect | 40000 | 4000 | 0.788 / 0.731 | nan |  | 0.01353 | 0 |
| Zm0p95/L48/m2m1p885_s6101 | complete | collect | 40000 | 4000 | 0.825 / 0.782 | nan |  | 0.01249 | 0 |
| Zm0p95/L48/m2m2p035_s6102 | complete | collect | 40000 | 4000 | 0.787 / 0.728 | nan |  | 0.01394 | 0 |
| Zm0p95/L48/m2m2p185_s6103 | complete | collect | 40000 | 4000 | 0.779 / 0.734 | nan |  | 0.01394 | 0 |
| Zm0p95/L48/m2m2p285_s6104 | complete | collect | 40000 | 4000 | 0.812 / 0.764 | nan |  | 0.01261 | 0 |
| Zm0p95/L48/m2m2p365_s6105 | complete | collect | 40000 | 4000 | 0.811 / 0.788 | nan |  | 0.01261 | 0 |
| Zm0p95/L64/m2m2p365_s6106 | complete | collect | 40000 | 4000 | 0.793 / 0.748 | nan |  | 0.01067 | 0 |
| Zm0p95/L32/m2m2p365_s6107 | complete | collect | 40000 | 4000 | 0.813 / 0.783 | nan |  | 0.01726 | 0 |
| Zm0p95/L48/m2m2p425_s6108 | complete | collect | 40000 | 4000 | 0.791 / 0.748 | nan |  | 0.01366 | 0 |
| Zm0p95/L64/m2m2p425_s6109 | complete | collect | 40000 | 4000 | 0.792 / 0.675 | nan |  | 0.01046 | 0 |
| Zm0p95/L48/m2m2p465_s6110 | complete | collect | 40000 | 4000 | 0.795 / 0.765 | nan |  | 0.01326 | 0 |
| Zm0p95/L64/m2m2p465_s6111 | complete | collect | 40000 | 4000 | 0.787 / 0.739 | nan |  | 0.01099 | 0 |
| Zm0p9/L48/m2m1p633_s6112 | complete | collect | 40000 | 4000 | 0.792 / 0.761 | nan |  | 0.01339 | 0 |
| Zm0p9/L48/m2m1p783_s6113 | complete | collect | 40000 | 4000 | 0.803 / 0.761 | nan |  | 0.01326 | 0 |
| Zm0p9/L48/m2m1p933_s6114 | complete | collect | 40000 | 4000 | 0.795 / 0.762 | nan |  | 0.01353 | 0 |
| Zm0p9/L48/m2m2p083_s6115 | complete | collect | 40000 | 4000 | 0.790 / 0.737 | nan |  | 0.01339 | 0 |
| Zm0p9/L48/m2m2p183_s6116 | complete | collect | 40000 | 4000 | 0.783 / 0.740 | nan |  | 0.0138 | 0 |
| Zm0p9/L48/m2m2p263_s6117 | complete | collect | 40000 | 4000 | 0.784 / 0.736 | nan |  | 0.01353 | 0 |
| Zm0p9/L64/m2m2p263_s6118 | complete | collect | 40000 | 4000 | 0.786 / 0.753 | nan |  | 0.01099 | 0 |
| Zm0p9/L32/m2m2p263_s6119 | complete | collect | 40000 | 4000 | 0.793 / 0.758 | nan |  | 0.01833 | 0 |
| Zm0p9/L48/m2m2p323_s6120 | complete | collect | 40000 | 4000 | 0.808 / 0.771 | nan |  | 0.013 | 0 |
| Zm0p9/L64/m2m2p323_s6121 | complete | collect | 40000 | 4000 | 0.820 / 0.710 | nan |  | 0.009747 | 0 |
| Zm0p9/L48/m2m2p363_s6122 | complete | collect | 40000 | 4000 | 0.781 / 0.735 | nan |  | 0.01353 | 0 |
| Zm0p9/L64/m2m2p363_s6123 | complete | collect | 40000 | 4000 | 0.807 / 0.761 | nan |  | 0.01035 | 0 |
| Zm0p8/L48/m2m1p444_s6124 | complete | collect | 40000 | 4000 | 0.805 / 0.769 | nan |  | 0.01313 | 0 |
| Zm0p8/L48/m2m1p594_s6125 | complete | collect | 40000 | 4000 | 0.789 / 0.749 | nan |  | 0.01353 | 0 |
| Zm0p8/L48/m2m1p744_s6126 | complete | collect | 40000 | 4000 | 0.773 / 0.750 | nan |  | 0.01436 | 0 |
| Zm0p8/L48/m2m1p894_s6127 | complete | collect | 40000 | 4000 | 0.801 / 0.729 | nan |  | 0.01249 | 0 |
| Zm0p8/L48/m2m1p994_s6128 | complete | collect | 40000 | 4000 | 0.805 / 0.718 | nan |  | 0.01287 | 0 |
| Zm0p8/L48/m2m2p074_s6129 | complete | collect | 40000 | 4000 | 0.807 / 0.755 | nan |  | 0.013 | 0 |
| Zm0p8/L64/m2m2p074_s6130 | complete | collect | 40000 | 4000 | 0.794 / 0.751 | nan |  | 0.01066 | 0 |
| Zm0p8/L32/m2m2p074_s6131 | complete | collect | 40000 | 4000 | 0.783 / 0.752 | nan |  | 0.01851 | 0 |
| Zm0p8/L48/m2m2p134_s6132 | complete | collect | 40000 | 4000 | 0.817 / 0.749 | nan |  | 0.01238 | 0 |
| Zm0p8/L64/m2m2p134_s6133 | complete | collect | 40000 | 4000 | 0.796 / 0.751 | nan |  | 0.01088 | 0 |
| Zm0p8/L48/m2m2p174_s6134 | complete | collect | 40000 | 4000 | 0.797 / 0.703 | nan |  | 0.01274 | 0 |
| Zm0p8/L64/m2m2p174_s6135 | complete | collect | 40000 | 4000 | 0.801 / 0.760 | nan |  | 0.01045 | 0 |
| Zm0p6/L48/m2m1p122_s6136 | complete | collect | 40000 | 4000 | 0.800 / 0.752 | nan |  | 0.01339 | 0 |
| Zm0p6/L48/m2m1p272_s6137 | complete | collect | 40000 | 4000 | 0.813 / 0.760 | nan |  | 0.01236 | 0 |
| Zm0p6/L48/m2m1p422_s6138 | complete | collect | 40000 | 4000 | 0.804 / 0.772 | nan |  | 0.013 | 0 |
| Zm0p6/L48/m2m1p572_s6139 | complete | collect | 40000 | 4000 | 0.810 / 0.767 | nan |  | 0.01262 | 0 |
| Zm0p6/L48/m2m1p672_s6140 | complete | collect | 40000 | 4000 | 0.791 / 0.659 | nan |  | 0.01261 | 0 |
| Zm0p6/L48/m2m1p752_s6141 | complete | collect | 40000 | 4000 | 0.801 / 0.750 | nan |  | 0.01353 | 0 |
| Zm0p6/L64/m2m1p752_s6142 | complete | collect | 40000 | 4000 | 0.812 / 0.782 | nan |  | 0.01025 | 0 |
| Zm0p6/L32/m2m1p752_s6143 | complete | collect | 40000 | 4000 | 0.792 / 0.753 | nan |  | 0.01797 | 0 |
| Zm0p6/L48/m2m1p812_s6144 | complete | collect | 40000 | 4000 | 0.792 / 0.728 | nan |  | 0.01287 | 0 |
| Zm0p6/L64/m2m1p812_s6145 | complete | collect | 40000 | 4000 | 0.810 / 0.777 | nan |  | 0.01025 | 0 |
| Zm0p6/L48/m2m1p852_s6146 | complete | collect | 40000 | 4000 | 0.819 / 0.789 | nan |  | 0.01262 | 0 |
| Zm0p6/L64/m2m1p852_s6147 | complete | collect | 40000 | 4000 | 0.786 / 0.720 | nan |  | 0.01066 | 0 |
| Zm0p4/L48/m2m0p86_s6148 | complete | collect | 40000 | 4000 | 0.816 / 0.723 | nan |  | 0.01236 | 0 |
| Zm0p4/L48/m2m1p01_s6149 | complete | collect | 40000 | 4000 | 0.796 / 0.747 | nan |  | 0.01313 | 0 |
| Zm0p4/L48/m2m1p16_s6150 | complete | collect | 40000 | 4000 | 0.808 / 0.769 | nan |  | 0.013 | 0 |
| Zm0p4/L48/m2m1p31_s6151 | complete | collect | 40000 | 4000 | 0.812 / 0.788 | nan |  | 0.01274 | 0 |
| Zm0p4/L48/m2m1p41_s6152 | complete | collect | 40000 | 4000 | 0.817 / 0.762 | nan |  | 0.01249 | 0 |
| Zm0p4/L48/m2m1p49_s6153 | complete | collect | 40000 | 4000 | 0.766 / 0.736 | nan |  | 0.01408 | 0 |
| Zm0p4/L64/m2m1p49_s6154 | complete | collect | 40000 | 4000 | 0.779 / 0.720 | nan |  | 0.01102 | 0 |
| Zm0p4/L32/m2m1p49_s6155 | complete | collect | 40000 | 4000 | 0.790 / 0.747 | nan |  | 0.01761 | 0 |
| Zm0p4/L48/m2m1p55_s6156 | complete | collect | 40000 | 4000 | 0.802 / 0.749 | nan |  | 0.01261 | 0 |
| Zm0p4/L64/m2m1p55_s6157 | complete | collect | 40000 | 4000 | 0.811 / 0.771 | nan |  | 0.01015 | 0 |
| Zm0p4/L48/m2m1p59_s6158 | complete | collect | 40000 | 4000 | 0.798 / 0.694 | nan |  | 0.01261 | 0 |
| Zm0p4/L64/m2m1p59_s6159 | complete | collect | 40000 | 4000 | 0.787 / 0.736 | nan |  | 0.01088 | 0 |
| Z0/L48/m2m0p466_s6160 | complete | collect | 40000 | 4000 | 0.798 / 0.761 | nan |  | 0.01249 | 0 |
| Z0/L48/m2m0p616_s6161 | complete | collect | 40000 | 4000 | 0.805 / 0.779 | nan |  | 0.01224 | 0 |
| Z0/L48/m2m0p766_s6162 | complete | collect | 40000 | 4000 | 0.790 / 0.742 | nan |  | 0.01353 | 0 |
| Z0/L48/m2m0p916_s6163 | complete | collect | 40000 | 4000 | 0.793 / 0.712 | nan |  | 0.013 | 0 |
| Z0/L48/m2m1p016_s6164 | complete | collect | 40000 | 4000 | 0.786 / 0.754 | nan |  | 0.01274 | 0 |
| Z0/L48/m2m1p096_s6165 | complete | collect | 40000 | 4000 | 0.821 / 0.786 | nan |  | 0.012 | 0 |
| Z0/L64/m2m1p096_s6166 | complete | collect | 40000 | 4000 | 0.800 / 0.751 | nan |  | 0.009944 | 0 |
| Z0/L32/m2m1p096_s6167 | complete | collect | 40000 | 4000 | 0.808 / 0.770 | nan |  | 0.01709 | 0 |
| Z0/L48/m2m1p156_s6168 | complete | collect | 40000 | 4000 | 0.809 / 0.771 | nan |  | 0.01249 | 0 |
| Z0/L64/m2m1p156_s6169 | complete | collect | 40000 | 4000 | 0.811 / 0.782 | nan |  | 0.01005 | 0 |
| Z0/L48/m2m1p196_s6170 | complete | collect | 40000 | 4000 | 0.819 / 0.782 | nan |  | 0.012 | 0 |
| Z0/L64/m2m1p196_s6171 | complete | collect | 40000 | 4000 | 0.787 / 0.735 | nan |  | 0.01067 | 0 |

### `zeff2` (11/11 complete)

| run | state | phase | sweeps | collected | HMC acc (mean / min window) | min swap | round-trip walkers | ε median | cont |
|---|---|---|---|---|---|---|---|---|---|
| Zm1p5/L48/m2m2p05_s6501 | complete | collect | 40000 | 4000 | 0.788 / 0.732 | nan |  | 0.01437 | 0 |
| Zm1p5/L48/m2m2p15_s6502 | complete | collect | 40000 | 4000 | 0.806 / 0.777 | nan |  | 0.0138 | 0 |
| Zm1p5/L48/m2m2p25_s6503 | complete | collect | 40000 | 4000 | 0.807 / 0.768 | nan |  | 0.0134 | 0 |
| Zm1p3/L48/m2m2p1_s6504 | complete | collect | 40000 | 4000 | 0.784 / 0.753 | nan |  | 0.01422 | 0 |
| Zm1p3/L48/m2m2p2_s6505 | complete | collect | 40000 | 4000 | 0.804 / 0.786 | nan |  | 0.01339 | 0 |
| Zm1p3/L48/m2m2p3_s6506 | complete | collect | 40000 | 4000 | 0.791 / 0.677 | nan |  | 0.01339 | 0 |
| Zm1p3/L48/m2m2p4_s6507 | complete | collect | 40000 | 4000 | 0.812 / 0.754 | nan |  | 0.013 | 0 |
| Zm1p1716/L48/m2m2p15_s6508 | complete | collect | 40000 | 4000 | 0.786 / 0.727 | nan |  | 0.01436 | 0 |
| Zm1p1716/L48/m2m2p25_s6509 | complete | collect | 40000 | 4000 | 0.804 / 0.775 | nan |  | 0.01313 | 0 |
| Zm1p1716/L48/m2m2p35_s6510 | complete | collect | 40000 | 4000 | 0.796 / 0.744 | nan |  | 0.01366 | 0 |
| Zm1p1716/L48/m2m2p45_s6511 | complete | collect | 40000 | 4000 | 0.792 / 0.743 | nan |  | 0.01366 | 0 |

## Operations journal (last 60 lines of `$LP_HMC_RUNS/OPS_JOURNAL.md`)

## 2026-11-24 15:20 UTC
- b13/Zm1p3/L20 all rows complete; analyze_cv_umbrella.py (job 2071360) -> reports/cv_umbrella/b13/Zm1p3/L20/analysis.json

## 2026-11-24 15:47 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/uline/Zm0p85/L32/m2m2p317_s701_ordered

## 2026-11-24 17:36 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/uline_ext/Zm1/L24/m2m2p6_s1534_disordered

## 2026-11-24 18:06 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/uline/Zm0p8/L32/m2m2p18_s720_disordered

## 2026-11-24 18:06 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/uline/Zm0p9/L32/m2m2p388_s711_ordered

## 2026-11-24 18:17 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/uline/Zm0p8/L32/m2m2p2_s710_disordered

## 2026-11-24 19:36 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/b8/Zm1p1716/L20/m2m2p6_s1230

## 2026-11-24 19:43 UTC
- b8/Zm1p1716/L20 all rows complete; analyze_cv_umbrella.py (job 2078150) -> reports/cv_umbrella/b8/Zm1p1716/L20/analysis.json. summary: n_good 132, chi_s_max 7.07(79) at m2 -2.375(3), chi_at_edge TRUE, n_twopeak 8, no coexistence block (bootstrap coexistence_fraction 0.15).

## 2026-11-25 08:49 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/uline_ext/Zm1/L24/m2m2p57_s1544_disordered

## 2026-11-25 08:49 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/uline_ext/Zm1/L24/m2m2p57_s2544_ordered

## 2026-11-25 08:49 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/uline_ext/Zm1/L24/m2m2p63_s1524_disordered

## 2026-11-25 08:49 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/uline_ext/Zm1/L24/m2m2p63_s2524_ordered

## 2026-11-25 08:49 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/uline_ext/Zm1/L24/m2m2p6_s2534_ordered

## 2026-11-25 09:02 UTC
- Run plan r10 merged (e5b7a8f -> hazel-ops 8468c75); local cluster reports for b8/b13 L20 archived to ops/band_analysis/cluster_reports_2026-11-24 (workstation versions now tracked). scancel 7 rows (b8 L28 s1228/s1238, L32 s1232/s1242; b13 L28 s1338, L32 s1332/s1342; 6 pending, 1 running), dirs/checkpoints kept, listed in ops/cancelled_rows.txt (auto_resubmit skips, no IDLE alert). prepare + submit bline (8 rows). Ops scripts now: uline bline s2_zm2_ext b8 b13 uline_ext b8_mixed.

## 2026-11-25 15:42 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/bline/Zm1p1716/L20/m2m2p36_s1620

## 2026-11-25 15:49 UTC
- bline/Zm1p1716/L20 complete -> analysis job 2095093: chi_s_max 11.38(44) at m2 -2.3125(39), not at edge, n_twopeak 11, coexistence 75%: m_eq -2.3008(60), barrier 0.278(97), latent_q 0.01022(91). Combined b8+bline L20 (cv_umbrella/combined/b8_bline, symlinks; job 2095094): chi_s_max 11.38(51) at -2.312(3), m_eq -2.303 but bootstrap sd 0.20, coexistence 40%, barrier 0.247(88). Reports committed to hazel-ops.

## 2026-11-25 21:56 UTC
- exit3 rule uline_ext/Zm1p05/L24/m2m2p65_s2644_ordered: rt 43->51 rising at 900000; CVU_MAX_THERM 900000 -> 1350000 (raise 1/2); resubmitted (uline_ext: submit   cvu_uline_ext_Zm1p05_L24_m2m2p65_s2644  gpu=h100)

## 2026-11-25 23:45 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/uline_ext/Zm1p05/L24/m2m2p71_s2624_ordered

## 2026-11-26 01:26 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/uline_ext/Zm1p05/L24/m2m2p68_s1634_disordered

## 2026-11-26 02:46 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/uline/Zm0p9/L32/m2m2p388_s710_disordered

