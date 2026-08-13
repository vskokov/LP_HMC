# HMC tuning at Z=-0.6, m2=-1.85764

The selected parameters were measured in Float64 on an NVIDIA RTX A2000 using
`scripts/benchmark_hmc_defaults.jl`. Four independent configurations were
advanced in one CUDA batch; half began in the ordered basin and half in the
disordered basin.

The broad scan used 8,000 measured trajectories per candidate. Independent-seed
confirmations used 12,000 trajectories per candidate. `n_lf` was selected by
effective samples per 1,000 force evaluations, using the slower of the M^2 and Q
autocorrelation measurements. Epsilon was chosen near the 70--80% HMC acceptance
band. A refined epsilon scan was used for L=32.

`selected_parameters.csv` is the table consumed manually to define
`scripts/hmc_defaults.py`. The `candidates_*.csv`, `confirmation_*.csv`, and
`refinement_*.csv` files preserve the measurements behind the selection.

These are center-point defaults. A wide replica-exchange mass ladder can have a
lower acceptance at one endpoint, so production diagnostics must still check
every HMC slot. Explicit `--eps` and `--n-lf` values override these defaults.
