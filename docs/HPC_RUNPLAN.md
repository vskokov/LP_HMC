# Hazel run plan — which stages to run

**Revision:** 9 (2026-11-24). Maintained from the workstation. Hazel agent: read this after every `git pull`. It is the only authority on *what* to run. `docs/HPC_AGENT.md` says *how*.

**GPU budget:** unlimited. Throughput is limited only by the queue, so keep every ACTIVE stage fully submitted. Escalation for failures, wrong-looking data, or a run hitting its caps still applies.

## Status keys

- **ACTIVE**: prepare (once) and keep submitted until every row is complete.
- **HOLD**: do not prepare or submit. It will be switched to ACTIVE here when its prerequisites are met.
- **LOCAL**: runs on the workstation GPU. Never submit it on Hazel; that would duplicate runs.
- **DONE**: finished. Nothing to do.

## Stages

Submit ACTIVE stages in the order listed. When the queue is congested, earlier rows have priority.

| # | stage | status | rows | what it decides | notes |
|---|---|---|---|---|---|
| 1 | `validate` | DONE | 1 | cluster reproduces the workstation | passed 2026-11-19 |
| 2 | `uline` | **ACTIVE** | 48 | whether the symmetric→uniform line turns first order near its end (gate G1) | M² coordinate; Z = −0.80, −0.85, −0.90, −0.95; L = 24, 32; 3 masses × ordered/disordered starts. L=24 complete; L=32 rows are the long pole. |
| 3 | `s2_zm2_ext` | **ACTIVE** | 4 | barrier ∝ L² test at Z = −2 | L=36 (two masses) and second seeds at L=24/30. These complement, not duplicate, the LOCAL `s2_zm2` runs; seeds differ. |
| 5a | `zeff` | DONE (r9) | 171 | renormalized Z: G⁻¹(k) = 1/S(k) in the symmetric phase on a (Z, m²) grid | Plain HMC, 8 independent replicas per row, **no umbrella, no swaps, no transport gate**; script `scripts/sk_symmetric.jl` (env `SK_*`), selected by `cv_campaign.py` automatically. L=48 (115 rows), L=64 (42), L=32 (14). One job per row (L=64 may need one continuation, exit 75 as usual). Output `sk.csv`, `obs.csv` (no `statistics.csv`). Expected: some rows close to m²_c order from the disordered start; that is a result, not a failure. |
| 5b | `zeff2` | DONE (r9) | 11 | follow the S(k) peak down to the ordering onset at Z = −1.5, −1.3, −1.1716 | Same as `zeff` (plain HMC, `sk_symmetric.jl`, L=48). Rows that order from the disordered start are a result. |
| 5c | `b8` | **ACTIVE (new, r8)** | 6 | p=8-region symmetric→lamellar coexistence and barrier vs L, orientation-independent | **Band CV** `CVU_KIND=band`, k̂² ∈ [0.36, 0.62] (all modes, any orientation); Z = −1.1716; L = 20 (m² −2.50, −2.60), 28 (−2.55, −2.65), 32 (−2.58, −2.68); s ∈ [0, 0.5]; caps 0.4M / 0.9M / 1.3M. Gate and §3 rules as `s2_zm1172_prod`. |
| 5d | `b13` | **ACTIVE (new, r8)** | 6 | same at Z = −1.3 (moat still well defined, closer to the meeting region) | Band k̂² ∈ [0.37, 0.70]; L = 20 (m² −2.39, −2.49), 28 (−2.44, −2.54), 32 (−2.47, −2.57). Otherwise as `b8`. |
| 5e | `uline_ext` | **ACTIVE (new, r8)** | 24 | does the uniform line continue to Z = −1.0, −1.05, where the renormalized moat closes? | M² CV, profile as `uline`; Z = −1.0 (m² −2.63, −2.60, −2.57), −1.05 (−2.71, −2.68, −2.65); L = 24, 32; ordered/disordered starts; cap 0.9M. |
| 5f | `b8_mixed` | **ACTIVE, L=20 only (r9)**; L=28 rows **CANCELLED (r9)** | 4 | uniform vs lamellar deep in the ordered region at Z = −1.1716 (replaces `p8_mixed`) | `CVU_KIND=mixedband`, s = M² − 2 P_band, band [0.36, 0.62], s ∈ [−1.2, 0.75]; L = 20 (352 windows), 28 (584); m² = −2.7, −2.9. Gate 15% round-trip walkers, min swap 0.1; caps 2M / 3.5M. Lowest priority. r9: submit only with `--lmax 20`; `scancel` the two L=28 chains (m² −2.7, −2.9), do not resubmit them, keep their directories. |
| 6 | `p9_L27` | **CANCELLED (r9)** | 2 | second size for the p=9 symmetric→uniform coexistence (barrier vs L) | Mixed CV, L=27, m² = −2.42, −2.47, s ∈ [−0.6, 0.6], 340 windows. Gate 15%, min swap 0.1, cap 3M. r9: `scancel` both chains, do not resubmit, keep checkpoints and data. |
| — | `s2_zm1172_prod` | DONE (4 of 6); **L=32 rows CANCELLED (r5)** | 6 | — | L=16/24 complete. The two L=32 rows (m² = −2.51, −2.57) sit above the transition (r5 log): `scancel` their jobs, do not resubmit them, keep their checkpoints. Superseded by `p8_shift`. |
| — | `p9_pilot` | DONE (2 of 4) | 4 | — | m² = −2.20, −2.35 complete; −2.50/−2.65 superseded by `p9_mixed`. Keep checkpoints, do not resubmit. |
| — | `p9_mixed` | DONE | 4 | — | complete 2026-11-21; analysed on the workstation (r5 log). |
| — | `p8_mixed`, `p8_shift` | **SUPERSEDED (r8)** | 11 | — | On hold since r6; replaced by `b8` / `b8_mixed`. Do not resubmit; keep checkpoints and data. |
| — | `s2_zm2` | LOCAL / DONE | 3 | — | L=18/24/30 complete on the workstation |
| — | `lro` | LOCAL / DONE | 11 | — | L ≥ 24 rows invalid (frozen HMC with fixed ε); superseded by `lro2` |
| — | `lro2` | LOCAL / DONE | 6 | — | reruns of the L ≥ 24 `lro` points with ε adaptation; complete |
| — | `s2_zm1172` | LOCAL / DONE | 3 | — | pilots, superseded by `s2_zm1172_prod` |

Commands, with `LP_HMC_RUNS` set as in HPC_AGENT.md §1:

```bash
git pull --ff-only
python3 scripts/cv_campaign.py prepare --stage zeff        # once (r7)
python3 scripts/cv_campaign.py prepare --stage zeff2 b8 b13 uline_ext b8_mixed   # once (r8)
python3 scripts/cv_campaign.py submit  --stage uline s2_zm2_ext b8 b13 uline_ext
python3 scripts/cv_campaign.py --lmax 20 submit --stage b8_mixed          # r9: L=20 rows only
python3 scripts/cv_campaign.py status  --stage uline s2_zm2_ext zeff zeff2 b8 b13 uline_ext p9_L27 b8_mixed
```

`prepare` must not be rerun for a stage that already has runs (HPC_AGENT.md §3). When a later revision adds rows to an existing stage, the revision says explicitly how to add them.

## Reporting back

Report in `$LP_HMC_RUNS/OPS_JOURNAL.md`, and to the user when asked, in these cases:

- every completed row, giving its label, wall-clock time from first submission, number of continuations and final `diagnostics.json` (min_swap, round_trip_walkers, hmc_acceptance_mean);
- when a stage completes, stating it explicitly ("stage X complete"); the user then copies it to the workstation for analysis;
- for `b8`, `b13` and `b8_mixed`, when a (Z, L) directory has all its rows complete, also run `analyze_cv_umbrella.py --dir <that dir> --bootstrap 20 --span 0.3` and report the `summary` block (the earlier `p9_pilot`/`p9_mixed` instruction is done);
- (done) for `p9_pilot` and `p9_mixed`, also run `python3 scripts/analyze_cv_umbrella.py --dir $LP_HMC_RUNS/cv_umbrella/p9_pilot/Zm0p9358/L18 --bootstrap 20 --span 0.3` and report the `summary` block. Do not interpret it beyond reporting.

## Revision log

- **r9 (2026-11-24):** approved by the user, after the ETA estimate of 2026-11-24 (~700 jobs left, GPU access 3–5 on average).
  - **`p9_L27` CANCELLED.** `scancel` both chains; keep checkpoints and data; drop it from `submit`. Reason: the full S(k) data show the renormalized moat closes between Z = −1.1 and −1.05, so at Z9 = −0.936 the relevant states are uniform slabs, not period-9 lamellae; `uline_ext` covers this region.
  - **`b8_mixed` trimmed to L=20.** `scancel` the two L=28 chains (if submitted); submit only with `--lmax 20` as in the commands above. Keep their directories.
  - **`zeff`, `zeff2` DONE** (analysed on the workstation); dropped from `submit`.
  - Priority otherwise unchanged: `uline`, `s2_zm2_ext`, `b8`, `b13`, `uline_ext`, then `b8_mixed` L=20.

- **r8 (2026-11-23):** approved by the user. From the S(k) analysis (local + first 93 `zeff` rows): for Z ≤ −1.17 the renormalized peak lies below the bare −Z/2 and drifts down toward the transition (Z8: 0.43–0.48 vs 0.586); for −1.1 ≤ Z ≤ −0.9 it slides to k → 0 as m² approaches the transition. `p9_mixed` s ≈ 0 states are uniform-phase slabs/domain walls. New ACTIVE stages `zeff2`, `b8`, `b13`, `uline_ext`, `b8_mixed` (band coordinates, `CVU_BAND_LO/HI`). `p8_shift`/`p8_mixed` are SUPERSEDED (keep their data). Submit order as in the table; `b8_mixed` last.
- **r7 (2026-11-22):** approved by the user. New ACTIVE stage `zeff`: 171 short unbiased runs measuring the fluctuation-renormalized dispersion (Z_eff, peak k̂²*) across Z = −2 … 0, which sets the momentum bands and box sizes of the coming modulated-phase stages.
  - `prepare --stage zeff` once, then `submit`. Priority after `s2_zm2_ext`, before `p9_L27`.
  - **Diagnostics differ from the umbrella stages:** `diagnostics.json` has `sweeps`, `collected`, `phase`, `hmc_acceptance_mean/min` (collect phase), `eps_median`; there are no swap or round-trip fields, and the §3 transport rules do not apply. HMC acceptance should be 0.7–0.9.
  - A row is complete when `complete.json` exists; `hpc_sync.py push` carries the stage like any other (sk.csv ≈ 0.5–1 MB per row).
  - When the stage completes, report it; no analysis on the cluster.

- **r6 (2026-11-22):** approved by the user.
  - **Why:** fluctuations renormalize Z, so the preferred modulation momentum is not the bare k̂² = −Z/2 that the "commensurate" Z_p and the single-shell coordinate assume. Measured in the disordered windows: k̂²* ≈ 0.88–0.91 at Z = −2 (bare 1.0), ≈ 0.41–0.46 at Z = −1.1716 (bare 0.586). At p = 8, L = 16, the low-shell-power windows hold an ordered (111) lamella on k̂² = 0.457, so the p = 8 shell coordinate mislabels the phases.
  - **HOLD `p8_shift` and `p8_mixed`:** `scancel` their chains, do not resubmit, keep all checkpoints and data. They will be replaced by band-coordinate stages (new CV kinds `band` / `mixedband`, `CVU_BAND_LO/HI`, added in this revision; existing kinds are unchanged).
  - **Checkpoints for inspection (one-off):** `python3 scripts/hpc_sync.py push --checkpoints p9_mixed s2_zm1172_prod` (about 6–60 MB per run). Record it in the journal.
  - **Unchanged:** `uline`, `s2_zm2_ext`, `p9_L27` continue. The new `cv_umbrella.jl` writes one extra header line (`band=`) and is otherwise identical for the existing kinds, so running chains may pick it up at their next continuation.

- **r5 (2026-11-22):** approved by the user. Workstation analysis (commit dc1372d):
  - **Z = −2:** first order. Barrier 1.16 / 5.18 / 11.8 / 19.3 kT at L = 12 / 18 / 24 / 30; m²_c ≈ −1.861.
  - **Z = −1.1716:** m_eq = −2.65(2) at L = 16, but below −2.70 at L = 24, so the `s2_zm1172_prod` L=32 masses miss the transition. Cancel those two rows; new stage `p8_shift` at lower masses; new stage `p8_mixed` for the uniform-vs-lamellar question at p = 8.
  - **Z = −0.9358, L = 18 (`p9_mixed`):** symmetric→uniform, m_eq = −2.449(2), barrier 5.1(2) kT, no lamellar minimum for m² ∈ [−2.2, −2.8]. New stage `p9_L27` gives the second size.
  - **Priority** (queue congestion only): table order, `uline` first (gate G1).
  - **Operator steps:** `git pull`; `scancel` the two `s2_zm1172_prod` L32 chains; `prepare` the three new stages (once); `submit`; journal it.

- **r1 (2026-11-19):** initial plan. ACTIVE: `uline`, `s2_zm1172_prod`, `s2_zm2_ext`, `p9_pilot`.
- **r4 (2026-11-21):** data exchange through research storage: run `python3 scripts/hpc_status_report.py && python3 scripts/hpc_sync.py push` at the end of every pass (HPC_AGENT.md §2). Push once right away after pulling this revision.
- **r3 (2026-11-21):** `p9_mixed` (approved on Hazel 2026-11-20) recorded as ACTIVE; `p9_pilot` rows −2.50/−2.65 superseded. The trial on the `gpu` partition (4 h jobs) for long-pole rows is approved; revert to `short_gpu` if those jobs do not start within a few hours. Validation re-check on the workstation: m_eq −1.7280(40) vs −1.7297(39), barrier 1.114(55) vs 1.261(56) (1.9σ), latent 0.0288(6) vs 0.0297(4). Passes.
- **r2 (2026-11-20):** the workstation reviewed and merged the `hazel-ops` commits up to 07a7441 (ε adaptation, device-side bias force, GPU-type list, x86-64-v3 target) into `phase-diagram-paper`; all CPU/GPU tests pass on the A6000 too. From now on, pull `phase-diagram-paper` and rebase `hazel-ops` on it. The workstation found the same frozen-HMC problem in its own L ≥ 24 runs: new LOCAL stage `lro2`; local `s2_zm2` L24/L30 resume with adaptation. No change to the ACTIVE list. The agent changed `cv_umbrella.jl` sampling code, which §4 of HPC_AGENT.md forbids; this time the change was correct and needed. Next time, stop and escalate first, and propose the change on `hazel-ops` without deploying it to production runs.
