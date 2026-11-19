# Hazel run plan — which stages to run

**Revision:** 1 (2026-11-19). Maintained from the workstation. Hazel agent: read this after every `git pull`. It is the only authority on *what* to run. `docs/HPC_AGENT.md` says *how*.

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
| 5 | `p9_pilot` | **ACTIVE** | 4 | where the uniform and lamellar lines meet (Z = −0.9358, p=9) | L=18 shell-coordinate pilots, m² = −2.20, −2.35, −2.50, −2.65. Short (hours). Report when all four are complete; production masses follow in a later revision. |
| — | `s2_zm2` | LOCAL | 3 | — | L=18 done, L=24 running, L=30 queued on the workstation |
| — | `lro` | LOCAL / DONE | 11 | — | analysed on the workstation |
| — | `s2_zm1172` | LOCAL / DONE | 3 | — | pilots, superseded by `s2_zm1172_prod` |

Commands, with `LP_HMC_RUNS` set as in HPC_AGENT.md §1:

```bash
git pull --ff-only
python3 scripts/cv_campaign.py prepare --stage uline s2_zm1172_prod s2_zm2_ext p9_pilot   # only stages never prepared before
python3 scripts/cv_campaign.py submit  --stage uline s2_zm1172_prod s2_zm2_ext p9_pilot
python3 scripts/cv_campaign.py status  --stage uline s2_zm1172_prod s2_zm2_ext p9_pilot
```

`prepare` must not be rerun for a stage that already has runs (HPC_AGENT.md §3). When a later revision adds rows to an existing stage, the revision says explicitly how to add them.

## Reporting back

Report in `$LP_HMC_RUNS/OPS_JOURNAL.md`, and to the user when asked, in these cases:

- every completed row, giving its label, wall-clock time from first submission, number of continuations and final `diagnostics.json` (min_swap, round_trip_walkers, hmc_acceptance_mean);
- when a stage completes, stating it explicitly ("stage X complete"); the user then copies it to the workstation for analysis;
- for `p9_pilot`, also run `python3 scripts/analyze_cv_umbrella.py --dir $LP_HMC_RUNS/cv_umbrella/p9_pilot/Zm0p9358/L18 --bootstrap 20 --span 0.3` and report the `summary` block. Do not interpret it beyond reporting.

## Revision log

- **r1 (2026-11-19):** initial plan. ACTIVE: `uline`, `s2_zm1172_prod`, `s2_zm2_ext`, `p9_pilot`.
