# Hazel run plan — which stages to run

**Revision:** 3 (2026-11-21). Maintained from the workstation. Hazel agent: read this after every `git pull`. It is the only authority on *what* to run. `docs/HPC_AGENT.md` says *how*.

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
| 2 | `uline` | **ACTIVE** | 48 | whether the symmetric→uniform line turns first order near its end (gate G1) | M² coordinate; Z = −0.80, −0.85, −0.90, −0.95; L = 24, 32; 3 masses × ordered/disordered starts. L=32 rows are ~35-job chains. |
| 3 | `s2_zm1172_prod` | **ACTIVE** | 6 | symmetric→lamellar line and barrier scaling at Z = −1.1716 (p=8) | L = 16, 24, 32, two masses each. Transport is slow at this Z (pilots: 0–1 round-trip walkers). Expect `exit=3` at the thermalization cap; follow the §3 rule in HPC_AGENT.md (raise `CVU_MAX_THERM` ×1.5 if round trips are still increasing). |
| 4 | `s2_zm2_ext` | **ACTIVE** | 4 | barrier ∝ L² test at Z = −2 | L=36 (two masses) and second seeds at L=24/30. These complement, not duplicate, the LOCAL `s2_zm2` runs; seeds differ. |
| 5 | `p9_pilot` | DONE (2 of 4) | 4 | — | m² = −2.20, −2.35 complete. −2.50 and −2.65 cannot cross the uniform/modulated gap on the shell CV, so they are superseded by `p9_mixed`. Keep their checkpoints and do not resubmit them. |
| 6 | `p9_mixed` | **ACTIVE** | 4 | meeting region at p=9: uniform vs modulated vs symmetric along s = M² − 2 P_shell | L=18, m² = −2.20 … −2.65, 240 windows. When complete, run `analyze_cv_umbrella.py` on it, as for `p9_pilot`, and report. |
| — | `s2_zm2` | LOCAL | 3 | — | L=18 done; L=24/30 were frozen, now resuming on the workstation with ε adaptation (caps 700k/900k) |
| — | `lro` | LOCAL / DONE | 11 | — | L ≥ 24 rows invalid (frozen HMC with fixed ε); superseded by `lro2` |
| — | `lro2` | LOCAL | 6 | — | reruns of the L ≥ 24 `lro` points with ε adaptation, on the workstation |
| — | `s2_zm1172` | LOCAL / DONE | 3 | — | pilots, superseded by `s2_zm1172_prod` |

Commands, with `LP_HMC_RUNS` set as in HPC_AGENT.md §1:

```bash
git pull --ff-only
python3 scripts/cv_campaign.py prepare --stage uline s2_zm1172_prod s2_zm2_ext p9_mixed   # only stages never prepared before
python3 scripts/cv_campaign.py submit  --stage uline s2_zm1172_prod s2_zm2_ext p9_mixed
python3 scripts/cv_campaign.py status  --stage uline s2_zm1172_prod s2_zm2_ext p9_mixed
```

`prepare` must not be rerun for a stage that already has runs (HPC_AGENT.md §3). When a later revision adds rows to an existing stage, the revision says explicitly how to add them.

## Reporting back

Report in `$LP_HMC_RUNS/OPS_JOURNAL.md`, and to the user when asked, in these cases:

- every completed row, giving its label, wall-clock time from first submission, number of continuations and final `diagnostics.json` (min_swap, round_trip_walkers, hmc_acceptance_mean);
- when a stage completes, stating it explicitly ("stage X complete"); the user then copies it to the workstation for analysis;
- for `p9_pilot` and `p9_mixed`, also run `python3 scripts/analyze_cv_umbrella.py --dir $LP_HMC_RUNS/cv_umbrella/p9_pilot/Zm0p9358/L18 --bootstrap 20 --span 0.3` and report the `summary` block. Do not interpret it beyond reporting.

## Revision log

- **r1 (2026-11-19):** initial plan. ACTIVE: `uline`, `s2_zm1172_prod`, `s2_zm2_ext`, `p9_pilot`.
- **r3 (2026-11-21):** `p9_mixed` (approved on Hazel 2026-11-20) recorded as ACTIVE; `p9_pilot` rows −2.50/−2.65 superseded. The trial on the `gpu` partition (4 h jobs) for long-pole rows is approved; revert to `short_gpu` if those jobs do not start within a few hours. Validation re-check on the workstation: m_eq −1.7280(40) vs −1.7297(39), barrier 1.114(55) vs 1.261(56) (1.9σ), latent 0.0288(6) vs 0.0297(4). Passes.
- **r2 (2026-11-20):** the workstation reviewed and merged the `hazel-ops` commits up to 07a7441 (ε adaptation, device-side bias force, GPU-type list, x86-64-v3 target) into `phase-diagram-paper`; all CPU/GPU tests pass on the A6000 too. From now on, pull `phase-diagram-paper` and rebase `hazel-ops` on it. The workstation found the same frozen-HMC problem in its own L ≥ 24 runs: new LOCAL stage `lro2`; local `s2_zm2` L24/L30 resume with adaptation. No change to the ACTIVE list. The agent changed `cv_umbrella.jl` sampling code, which §4 of HPC_AGENT.md forbids; this time the change was correct and needed. Next time, stop and escalate first, and propose the change on `hazel-ops` without deploying it to production runs.
