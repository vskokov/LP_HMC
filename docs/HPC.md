# Running the GPU campaigns on NCSU Hazel (Slurm)

The campaign drivers (`scripts/cv_campaign.py`) can submit jobs in two ways:

- the local A6000 queue (`tsp`);
- Slurm on Hazel, via `scripts/slurm_backend.py`.

On Slurm, every run directory becomes a chain of **≤2 h jobs**. Each job does three things:

1. It runs the simulation with a budget of `runtime_minutes` (default 100 min).
2. At the end of the budget, the simulation saves its checkpoint and exits with code 75.
3. The job then resubmits itself.

A rerun resumes exactly where the previous job stopped. This has been verified: across 12 interruptions, the samples stayed contiguous with no duplicates.

Other exit codes stop the chain and need a human decision. For example, code 3 means the transport gate was not met by `MAX_THERM`.

Cluster settings live in `configs/hpc/hazel.json`. Everything in it can be overridden:

- `--gpu` and `--runtime-minutes` on the command line;
- a different config file via `LP_HMC_HPC_CONFIG`.

`gpu_type` may be a comma list, for example `l40s,h100,h200` (the default) or `--gpu l40s,h200`. Hazel refuses untyped GPU requests, so every job still names one type. On each submission, including every self-resubmission of a chain, `slurm_backend.py pick-gpu` chooses the listed type that could start soonest. It ranks by the smaller of idle GPUs and remaining per-user `short_gpu` cap (L40S 4, H100 2, H200 2), then by remaining cap as a fraction of the cap, so a backlog of queued jobs splits in proportion to the caps. If a query fails, it falls back to the first type. A chain may therefore move between GPU types; the checkpoint is device-independent.

## 0. One-time setup

```bash
git clone https://github.com/vskokov/LP_HMC && cd LP_HMC && git checkout phase-diagram-paper
module avail julia cuda          # adjust "modules" in configs/hpc/hazel.json if versions differ
si --gpus                        # see which GPU types are idle; pick gpu_type accordingly
export LP_HMC_RUNS=/share/$GROUP/$USER/lp_hmc_runs   # run directories (checkpoints, CSVs)
```

`LP_HMC_RUNS` must be set in every shell that runs `prepare`, `submit` or `status`. The paths written into the manifests depend on it.

The Julia depot defaults to `/usr/local/usrapps/$GROUP/$USER/julia_depot`. This is persistent storage, so the precompiled packages survive between jobs.

## 1. Self-test

This instantiates the project, precompiles it, and runs the correctness tests on one GPU:

```bash
python3 scripts/slurm_backend.py selftest --gpu l40s
# output: $LP_HMC_RUNS/hpc_selftest/<jobid>.out
grep -E "PASS|FAIL|exit=" $LP_HMC_RUNS/hpc_selftest/*.out
```

Every test must print PASS, with exit=0 for each test script. The tests are `test_hmc.jl`, `test_replica_exchange.jl`, `test_quadratic_cv.jl` and `test_umbrella_gpu.jl`.

If the GPU type changes, also check the HMC acceptance in the validation run. The step size ε is scaled for L as in `CLAUDE.md`, and it does not depend on the device.

## 2. Validation against the local reference

This reruns the local point Z=−2, L=12, m²=−1.73 with a new seed:

```bash
python3 scripts/cv_campaign.py prepare --stage validate
python3 scripts/cv_campaign.py submit  --stage validate --gpu l40s
python3 scripts/cv_campaign.py status  --stage validate
# when complete:
python3 scripts/analyze_cv_umbrella.py --dir $LP_HMC_RUNS/cv_umbrella/validate/Zm2/L12
```

The run takes about 10–20 min on an L40S or A100.

Acceptance requires agreement within about 3σ with the local result in `reports/cv_umbrella/s2/Zm2/L12/analysis.json`:

| quantity | local (A6000, seed 21) |
|---|---|
| m_eq (equal-weight mass) | −1.7297 ± 0.0039 |
| barrier ΔF | 1.261 ± 0.056 |
| latent Δ(Q/V) | 0.0297 ± 0.0004 |
| d_eff of the ordered peak | 1.04 |

## 3. Production

```bash
python3 scripts/cv_campaign.py prepare --stage s2_zm2 lro      # etc.; see the stage list in the docstring
python3 scripts/cv_campaign.py submit  --stage s2_zm2 --gpu l40s
python3 scripts/cv_campaign.py status  --stage s2_zm2          # complete / active / IDLE rows
```

`submit` is idempotent. It skips rows that are complete or already queued. Rerun it to restart any chain that died, for example after a node failure or a non-75 exit; first read that run's latest `slurm/<jobid>.out`.

Per-run logs are in `<run>/slurm/*.out`. The number of continuations so far is in `<run>/slurm/continuations`.

## 4. Copying results back

Analysis and the paper figures run on the workstation. The preferred route is the
research-storage share, mounted on Hazel as `/rsstu/users/v/vskokov/gluon` and on the
workstation as `/hpc` (exchange directory `2026/lp_hmc_sync/`):

```bash
python3 scripts/hpc_sync.py push     # on Hazel (the operator does this every pass)
python3 scripts/hpc_sync.py pull     # on the workstation; LOCAL stages are never pulled
```

Alternatively, copy everything except the checkpoints over ssh:

```bash
rsync -av --exclude 'checkpoint.jld2' hazel:/share/$GROUP/$USER/lp_hmc_runs/cv_umbrella/ runs/cv_umbrella/
```

Keep the cluster copy, including the checkpoints, until the analysis is final. A run can be extended later by raising `CVU_SAMPLES` in the manifest and resubmitting.
