# Hazel campaign status

Generated 2026-11-21 15:01 UTC by `scripts/hpc_status_report.py` on the cluster (branch `hazel-ops`). Run data are not in git; copy completed stages with rsync (docs/HPC.md §4).

## Operator notes

- **Hardware:** chains use `gpu_partners`/`short_gpu` with GPU types L40S, H100, H200 and RTX PRO 6000. They're picked per (re)submission. On the `gpu` partition (QOS `gpu`, 4 h jobs), H100 jobs start after about 2 h, so `s2_zm2_ext` L36 s135 stays there. The L40 trial never started and was reverted to `short_gpu`. Throughput is about 8 sweeps/s at L=32 and 20–45 sweeps/s at L=24, per GPU.
- **`p9_mixed` (not yet in the run plan; approved by the user on Hazel 2026-11-20):** `p9_pilot` m²=−2.50/−2.65 cannot cross the gap between the uniform branch (P_shell≈0, |M|≈0.7) and the modulated branch (P_shell≳0.02) with the shell ladder. Both stopped with `exit=3` and 0 round trips; the checkpoint diagnostic is in the journal. `p9_mixed` redoes all four masses on s = M² − 2·P_shell over s∈[−0.95, 0.60] with 240 windows, MIN_SWAP 0.1 and MAX_THERM 1.5M. All four masses transport through the gap; see the round-trip counts below. Gate: 30% round-trip walkers.
- **`p9_pilot` m²=−2.20/−2.35** completed normally on the shell coordinate. The −2.50/−2.65 rows are superseded by `p9_mixed`, and their checkpoints are kept.

## Summary

| stage | complete | queued/running | idle |
|---|---|---|---|
| `p9_mixed` | 1/4 | 3 | 0 |
| `p9_pilot` | 2/4 | 0 | 2 |
| `s2_zm1172_prod` | 4/6 | 2 | 0 |
| `s2_zm2_ext` | 1/4 | 3 | 0 |
| `uline` | 24/48 | 24 | 0 |
| `validate` | 1/1 | 0 | 0 |

Running GPUs: h100 3, h200 2, l40s 4, rtx_6000_pro 8

During thermalization the HMC columns show the last check interval (ε adapts per window); for completed/collecting rows they show the whole collect phase. Round-trip walkers reset when collection starts.

## Runs

### `p9_mixed` (1/4 complete)

| run | state | phase | sweeps | collected | HMC acc (mean / min window) | min swap | round-trip walkers | ε median | cont |
|---|---|---|---|---|---|---|---|---|---|
| Zm0p9358/L18/m2m2p2_s950 | PD l40s | therm | 638199 | 0 | 0.800 / 0.734 | 0.221 | 38 | 0.02712 | 3 |
| Zm0p9358/L18/m2m2p35_s951 | complete | collect | 783000 | 4000 | 0.803 / 0.728 | 0.193 | 0 | 0.02712 | 3 |
| Zm0p9358/L18/m2m2p5_s952 | PD l40s | therm | 862300 | 0 | 0.800 / 0.760 | 0.174 | 33 | 0.02767 | 4 |
| Zm0p9358/L18/m2m2p65_s953 | R l40s | therm | 855000 | 0 | 0.800 / 0.784 | 0.128 | 13 | 0.0274 | 4 |

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
| Zm1p1716/L32/m2m2p51_s832 | R h200 | therm | 118000 | 0 | 0.800 / 0.786 | 0.443 | 1 | 0.01797 | 4 |
| Zm1p1716/L32/m2m2p57_s842 | PD rtx_6000_pro | therm | 131896 | 0 | 0.800 / 0.785 | 0.441 | 0 | 0.01797 | 5 |

### `s2_zm2_ext` (1/4 complete)

| run | state | phase | sweeps | collected | HMC acc (mean / min window) | min swap | round-trip walkers | ε median | cont |
|---|---|---|---|---|---|---|---|---|---|
| Zm2/L24/m2m1p88_s132 | complete | collect | 160000 | 4000 | 0.796 / 0.713 | 0.388 | 0 | 0.02415 | 4 |
| Zm2/L30/m2m1p9_s133 | PD h200 | therm | 160006 | 0 | 0.810 / 0.167 | 0.394 | 7 | 0.02 | 6 |
| Zm2/L36/m2m1p92_s134 | PD rtx_6000_pro | therm | 84711 | 0 | 0.800 / 0.778 | 0.397 | 0 | 0.0178 | 5 |
| Zm2/L36/m2m1p96_s135 | R h100 | therm | 102000 | 0 | 0.800 / 0.790 | 0.398 | 0 | 0.01745 | 4 |

### `uline` (24/48 complete)

| run | state | phase | sweeps | collected | HMC acc (mean / min window) | min swap | round-trip walkers | ε median | cont |
|---|---|---|---|---|---|---|---|---|---|
| Zm0p8/L24/m2m2p215_s700_disordered | complete | collect | 249000 | 8000 | 0.799 / 0.692 | 0.391 | 0 | 0.02185 | 2 |
| Zm0p8/L24/m2m2p215_s701_ordered | complete | collect | 247000 | 8000 | 0.800 / 0.720 | 0.379 | 0 | 0.02185 | 1 |
| Zm0p8/L24/m2m2p195_s710_disordered | complete | collect | 218000 | 8000 | 0.798 / 0.707 | 0.385 | 0 | 0.02185 | 0 |
| Zm0p8/L24/m2m2p195_s711_ordered | complete | collect | 237000 | 8000 | 0.798 / 0.687 | 0.380 | 0 | 0.02185 | 2 |
| Zm0p8/L24/m2m2p175_s720_disordered | complete | collect | 210000 | 8000 | 0.800 / 0.703 | 0.389 | 0 | 0.02185 | 1 |
| Zm0p8/L24/m2m2p175_s721_ordered | complete | collect | 272000 | 8000 | 0.807 / 0.708 | 0.387 | 0 | 0.02142 | 3 |
| Zm0p8/L32/m2m2p22_s700_disordered | PD l40s | therm | 235895 | 0 | 0.800 / 0.780 | 0.397 | 15 | 0.01761 | 5 |
| Zm0p8/L32/m2m2p22_s701_ordered | PD rtx_6000_pro | therm | 279701 | 0 | 0.800 / 0.776 | 0.396 | 10 | 0.01761 | 6 |
| Zm0p8/L32/m2m2p2_s710_disordered | PD h200 | therm | 154120 | 0 | 0.799 / 0.675 | 0.397 | 2 | 0.01761 | 4 |
| Zm0p8/L32/m2m2p2_s711_ordered | PD l40s | therm | 233635 | 0 | 0.799 / 0.769 | 0.396 | 13 | 0.01726 | 5 |
| Zm0p8/L32/m2m2p18_s720_disordered | R l40s | therm | 228000 | 0 | 0.800 / 0.785 | 0.394 | 7 | 0.01761 | 4 |
| Zm0p8/L32/m2m2p18_s721_ordered | PD rtx_6000_pro | therm | 302344 | 0 | 0.800 / 0.753 | 0.395 | 21 | 0.01761 | 6 |
| Zm0p85/L24/m2m2p31_s700_disordered | complete | collect | 286000 | 8000 | 0.800 / 0.738 | 0.381 | 0 | 0.02185 | 1 |
| Zm0p85/L24/m2m2p31_s701_ordered | complete | collect | 267000 | 8000 | 0.802 / 0.700 | 0.374 | 0 | 0.02185 | 2 |
| Zm0p85/L24/m2m2p29_s710_disordered | complete | collect | 247000 | 8000 | 0.802 / 0.726 | 0.380 | 0 | 0.02185 | 1 |
| Zm0p85/L24/m2m2p29_s711_ordered | complete | collect | 272000 | 8000 | 0.800 / 0.708 | 0.377 | 0 | 0.02185 | 1 |
| Zm0p85/L24/m2m2p27_s720_disordered | complete | collect | 251000 | 8000 | 0.801 / 0.710 | 0.387 | 0 | 0.02185 | 1 |
| Zm0p85/L24/m2m2p27_s721_ordered | complete | collect | 235000 | 8000 | 0.799 / 0.695 | 0.382 | 0 | 0.02185 | 1 |
| Zm0p85/L32/m2m2p317_s700_disordered | R rtx_6000_pro | therm | 244000 | 0 | 0.800 / 0.782 | 0.387 | 9 | 0.01761 | 5 |
| Zm0p85/L32/m2m2p317_s701_ordered | R rtx_6000_pro | therm | 259000 | 0 | 0.800 / 0.785 | 0.382 | 6 | 0.01761 | 5 |
| Zm0p85/L32/m2m2p297_s710_disordered | PD rtx_6000_pro | therm | 243539 | 0 | 0.801 / 0.772 | 0.389 | 11 | 0.01797 | 6 |
| Zm0p85/L32/m2m2p297_s711_ordered | R l40s | therm | 186000 | 0 | 0.800 / 0.785 | 0.390 | 7 | 0.01761 | 4 |
| Zm0p85/L32/m2m2p277_s720_disordered | R rtx_6000_pro | therm | 244000 | 0 | 0.800 / 0.786 | 0.392 | 11 | 0.01761 | 5 |
| Zm0p85/L32/m2m2p277_s721_ordered | R rtx_6000_pro | therm | 210000 | 0 | 0.800 / 0.785 | 0.394 | 6 | 0.01761 | 4 |
| Zm0p9/L24/m2m2p404_s700_disordered | complete | collect | 295000 | 8000 | 0.797 / 0.676 | 0.367 | 0 | 0.02229 | 1 |
| Zm0p9/L24/m2m2p404_s701_ordered | complete | collect | 300000 | 8000 | 0.800 / 0.700 | 0.366 | 0 | 0.02185 | 1 |
| Zm0p9/L24/m2m2p384_s710_disordered | complete | collect | 272000 | 8000 | 0.807 / 0.731 | 0.373 | 0 | 0.02142 | 1 |
| Zm0p9/L24/m2m2p384_s711_ordered | complete | collect | 297000 | 8000 | 0.798 / 0.691 | 0.374 | 0 | 0.02185 | 1 |
| Zm0p9/L24/m2m2p364_s720_disordered | complete | collect | 280000 | 8000 | 0.799 / 0.708 | 0.370 | 0 | 0.02207 | 1 |
| Zm0p9/L24/m2m2p364_s721_ordered | complete | collect | 265000 | 8000 | 0.798 / 0.719 | 0.377 | 0 | 0.02207 | 1 |
| Zm0p9/L32/m2m2p408_s700_disordered | R rtx_6000_pro | therm | 217000 | 0 | 0.800 / 0.783 | 0.374 | 1 | 0.01761 | 4 |
| Zm0p9/L32/m2m2p408_s701_ordered | R rtx_6000_pro | therm | 201000 | 0 | 0.800 / 0.785 | 0.374 | 1 | 0.01761 | 4 |
| Zm0p9/L32/m2m2p388_s710_disordered | R rtx_6000_pro | therm | 169000 | 0 | 0.800 / 0.785 | 0.380 | 0 | 0.01797 | 4 |
| Zm0p9/L32/m2m2p388_s711_ordered | PD h200 | therm | 222352 | 0 | 0.798 / 0.759 | 0.378 | 2 | 0.01726 | 5 |
| Zm0p9/L32/m2m2p368_s720_disordered | R h100 | therm | 169000 | 0 | 0.799 / 0.787 | 0.383 | 1 | 0.01761 | 4 |
| Zm0p9/L32/m2m2p368_s721_ordered | R h100 | therm | 162000 | 0 | 0.799 / 0.783 | 0.380 | 2 | 0.01761 | 4 |
| Zm0p95/L24/m2m2p507_s700_disordered | complete | collect | 407000 | 8000 | 0.802 / 0.686 | 0.354 | 0 | 0.02185 | 2 |
| Zm0p95/L24/m2m2p507_s701_ordered | complete | collect | 365000 | 8000 | 0.802 / 0.719 | 0.353 | 0 | 0.02185 | 2 |
| Zm0p95/L24/m2m2p487_s710_disordered | complete | collect | 328000 | 8000 | 0.797 / 0.677 | 0.364 | 0 | 0.02185 | 1 |
| Zm0p95/L24/m2m2p487_s711_ordered | complete | collect | 342000 | 8000 | 0.801 / 0.724 | 0.355 | 0 | 0.02185 | 1 |
| Zm0p95/L24/m2m2p467_s720_disordered | complete | collect | 271000 | 8000 | 0.800 / 0.729 | 0.358 | 0 | 0.02229 | 1 |
| Zm0p95/L24/m2m2p467_s721_ordered | complete | collect | 311000 | 8000 | 0.803 / 0.703 | 0.368 | 0 | 0.02185 | 2 |
| Zm0p95/L32/m2m2p51_s700_disordered | PD rtx_6000_pro | therm | 177889 | 0 | 0.800 / 0.784 | 0.364 | 0 | 0.01761 | 4 |
| Zm0p95/L32/m2m2p51_s701_ordered | PD rtx_6000_pro | therm | 181581 | 0 | 0.800 / 0.775 | 0.365 | 0 | 0.01761 | 4 |
| Zm0p95/L32/m2m2p49_s710_disordered | PD rtx_6000_pro | therm | 174749 | 0 | 0.800 / 0.777 | 0.365 | 1 | 0.01779 | 4 |
| Zm0p95/L32/m2m2p49_s711_ordered | R rtx_6000_pro | therm | 201000 | 0 | 0.800 / 0.787 | 0.369 | 2 | 0.01761 | 4 |
| Zm0p95/L32/m2m2p47_s720_disordered | R h200 | therm | 177000 | 0 | 0.800 / 0.785 | 0.370 | 0 | 0.01797 | 3 |
| Zm0p95/L32/m2m2p47_s721_ordered | R l40s | therm | 167000 | 0 | 0.800 / 0.785 | 0.369 | 0 | 0.01797 | 3 |

### `validate` (1/1 complete)

| run | state | phase | sweeps | collected | HMC acc (mean / min window) | min swap | round-trip walkers | ε median | cont |
|---|---|---|---|---|---|---|---|---|---|
| Zm2/L12/m2m1p73_s121 | complete | collect | 24000 | 4000 | 0.811 / 0.798 | 0.393 | 9 | | 0 |

## Operations journal (last 60 lines of `$LP_HMC_RUNS/OPS_JOURNAL.md`)

- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/uline/Zm0p9/L24/m2m2p404_s701_ordered

## 2026-11-21 02:15 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/uline/Zm0p9/L24/m2m2p364_s720_disordered

## 2026-11-21 03:35 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/uline/Zm0p95/L24/m2m2p487_s710_disordered

## 2026-11-21 04:05 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/uline/Zm0p95/L24/m2m2p487_s711_ordered

## 2026-11-21 04:15 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/uline/Zm0p8/L24/m2m2p175_s721_ordered

## 2026-11-21 04:35 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/uline/Zm0p95/L24/m2m2p467_s720_disordered

## 2026-11-21 05:46 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/uline/Zm0p85/L24/m2m2p31_s701_ordered

## 2026-11-21 07:25 UTC
- USER OK to try gpu partition. Moved 2 pending long-pole rows (uline Zm0p95/L32/m2m2p49_s710 -> l40/h100 pick; s2_zm2_ext Zm2/L36/m2m1p96_s135 -> h100) to partition gpu / QOS gpu, 4 h jobs (runtime 220 min); configs ops/hazel_gpu_partition.json(.h100). Their short_gpu pending jobs cancelled first (no overlap). test-only estimated start ~Feb 2027 (unreliable); revert to short_gpu if not started in a few hours.

## 2026-11-21 08:01 UTC
- RTX PRO 6000 benchmark (job 2015968, gpu41 Turin, copies of production checkpoints): L24 M2 224 win 23 sweeps/s, L32 M2 344 win 8.9 sweeps/s, hmc 0.80 (min 0.68-0.72). Added rtx_6000_pro to gpu_type list (commit pushed); refreshed uline/s2_zm1172_prod/s2_zm2_ext job.sh (re-applied gpu-partition config to the 2 trial rows); retyped 8 pending L>=30 jobs to rtx_6000_pro.

## 2026-11-21 08:06 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/uline/Zm0p95/L24/m2m2p467_s721_ordered

## 2026-11-21 08:09 UTC
- merged origin/phase-diagram-paper (run plan r2) into hazel-ops (merge, not rebase: no force-push); conflict in cv_campaign.py STAGES resolved (lro2 + p9_mixed). Added scripts/hpc_status_report.py -> docs/HPC_STATUS.md, pushed hourly by ops/push_status.sh. Noted r2 process rule: future sampling-code changes -> escalate + propose on hazel-ops before deploying.

## 2026-11-21 08:25 UTC
- pulled run plan r3/r4 (merged into hazel-ops). First hpc_sync push via xfer job 2016159 (servxfer, 34 s): share /rsstu/users/v/vskokov/gluon/2026/lp_hmc_sync verified: cv_umbrella/{p9_mixed,p9_pilot,s2_zm1172_prod,s2_zm2_ext,uline,validate}, OPS_JOURNAL.md, HPC_STATUS.md, LAST_PUSH 'servxfer 2026-11-21T03:24:55'; 4.5G; 0 checkpoints. LP_HMC_SHARE default path is correct. Hourly: status report + git push + xfer sync job (ops/push_status.sh).

## 2026-11-21 09:00 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/uline/Zm0p95/L24/m2m2p507_s701_ordered

## 2026-11-21 09:20 UTC
- COMPLETE /share/gluonsaturation/vskokov/lp_hmc_runs/cv_umbrella/uline/Zm0p95/L24/m2m2p507_s700_disordered

## 2026-11-21 09:50 UTC
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

