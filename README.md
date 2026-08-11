# Model A LP — φ⁴ Scalar Field Theory with Higher-Order Kinetic Term

```
ooo        ooooo   .oooooo.   oooooooooo.   oooooooooooo ooooo                   .o.
`88.       .888'  d8P'  `Y8b  `888'   `Y8b  `888'     `8 `888'                  .888.
 888b     d'888  888      888  888      888  888          888                  .8"888.
 8 Y88. .P  888  888      888  888      888  888oooo8     888                 .8' `888.
 8  `888'   888  888      888  888      888  888    "     888                .88ooo8888.
 8    Y     888  `88b    d88'  888     d88'  888       o  888       o       .8'     `888.
o8o        o888o  `Y8bood8P'  o888bood8P'   o888ooooood8 o888ooooood8      o88o     o8888o
```

## Overview

This code samples the Boltzmann distribution `exp(-H[φ]/T)` for a three-dimensional
φ⁴ scalar field theory with an additional higher-order kinetic term. The free-energy
functional is

```
H[φ] = Σ_x [ Z/2 (∇φ)²  +  1/2 (∇²φ)²  +  m²/2 φ²  +  λ/4 φ⁴ ]
```

with **λ = 4**, **T = 1** (temperature fixed to 1).

The sampling engine is **Hybrid Monte Carlo (HMC)**: global field updates via
leapfrog-integrated molecular dynamics, followed by a Metropolis accept/reject step.
HMC gives O(ξ) autocorrelation scaling near the phase transition (vs O(ξ²) for local
Metropolis), and requires no sublattice decomposition — the force evaluation is
embarrassingly parallel at every site.

---

## Repository Structure

```
modelA_LP/
├── src/
│   ├── modelA.jl          # Module entry point (imports, ASCII header)
│   ├── initialize.jl      # Command-line argument parsing and global constants
│   └── simulation.jl      # HMC engine: force, leapfrog, accept/reject
├── scripts/
│   ├── thermalize.jl      # Thermalises a field configuration and saves it to disk
│   ├── measure.jl         # Measures observables over a range of mass values
│   ├── measure_single.jl  # Measures observables at a single mass value
│   ├── snap.jl            # Generates an ensemble of field snapshots
│   ├── bootstrap.jl       # Bootstrap statistical analysis utilities
│   ├── test_hmc.jl        # Correctness tests for the HMC engine
│   ├── measure.sh         # Bash wrapper for measure.jl
│   ├── therm.sh           # Bash wrapper for thermalize.jl
│   ├── submit_therm.sh    # LSF batch submission for thermalization (GPU)
│   ├── submit_snap.sh     # LSF batch submission for snapshot generation (GPU)
│   ├── submit_measure.sh  # LSF batch submission for measurements (GPU)
│   ├── submit_reweight.sh # LSF batch submission for reweighting (GPU)
│   ├── run_cpu.sh         # LSF job template — CPU (16 threads)
│   ├── run_h100.sh        # LSF job template — H100 GPU
│   ├── run_l40s.sh        # LSF job template — L40S GPU
│   └── watch.sh           # Progress monitor for measurement jobs
├── data/                  # Output directory for all simulation data
├── Project.toml           # Julia project dependencies
└── Manifest.toml          # Exact dependency versions
```

---

## HMC Implementation

### Boundary Conditions

The simulation uses a 3D cubic lattice of side length **L** with **periodic (toroidal)
boundary conditions**:

```julia
NNp(n) = n % L + 1            # forward neighbour (1-indexed, wraps at L)
NNm(n) = (n + L - 2) % L + 1  # backward neighbour
```

### Force Kernel

The HMC molecular dynamics force is `F(x) = -δH/δφ(x)`:

```
F(x) = Z·∇²φ(x)  -  ∇⁴φ(x)  -  m²·φ(x)  -  λ·φ(x)³
```

where the lattice Laplacian sums the 6 nearest neighbours:

```
∇²φ(x) = Σ_μ [φ(x+μ̂) + φ(x-μ̂)] - 6φ(x)
```

and the bilaplacian `∇⁴φ = ∇²(∇²φ)` is computed via two passes: store
`lapϕ = ∇²φ` for all sites, then apply `∇²` to `lapϕ`. This two-pass approach
is exact and straightforward to verify.

### Leapfrog Integrator

Standard Störmer-Verlet scheme for `n_lf` steps of size `ε`:

```
π(ε/2)   ← π(0)      + (ε/2) F(φ(0))      # initial half-step
φ(iε)    ← φ((i-1)ε) + ε π(iε - ε/2)      # full steps (i = 1…n_lf)
π(iε+ε/2)← π(iε-ε/2) + ε F(φ(iε))
φ(n_lf ε)← φ((n_lf-1)ε) + ε π(n_lf ε - ε/2)
π(n_lf ε)← π(n_lf ε - ε/2) + (ε/2) F(φ(n_lf ε))  # final half-step
```

The integrator is symplectic (volume-preserving) and time-reversible, which
guarantees detailed balance after Metropolis correction.

### HMC Step

```
1. Draw π ~ N(0,1) independently at every site   (momentum refreshment)
2. H_old = H[φ] + Σ π²/2
3. (φ', π') = leapfrog(φ, π, n_lf, ε)
4. H_new = H[φ'] + Σ π'²/2
5. Accept φ' with probability min(1, exp(-(H_new - H_old)/T))
```

The acceptance rate is returned by `thermalize` and printed at each outer iteration.
Target: **70–80% acceptance**. Tune `--eps` to reach this range (see stability note
below).

### Leapfrog Stability and Volume Scaling

The `(∇²φ)²` term dominates the force spectrum. Its maximum lattice eigenvalue is
~16 (at k = π in all directions), giving a leapfrog stability bound of roughly
`ε ≲ 1/√8 ≈ 0.35`.

The binding constraint in practice is **volume scaling**: the Hamiltonian change per
trajectory scales as `|ΔH| ~ ε² × L^(3/2)`, so the acceptance rate degrades sharply
with both ε and L. To maintain 70–80% acceptance, ε must decrease as `L^(-3/4)` when
scaling up the lattice.

Empirical tuning results at `m² = -2.28587` (near the phase transition):

| L | ε | n_lf | τ = n_lf·ε | acceptance |
|---|---|------|------------|------------|
| 6 | 0.10 | 10 | 1.0 | ~57% |
| 12 | 0.04 | 20 | 0.8 | ~73% |
| 24 | 0.02 | 10 | 0.2 | ~75% |

For L=24, the trajectory length τ=0.2 is shorter than ideal for decorrelation;
`--n_lf 15 --eps 0.02` (τ=0.3) provides a better balance.

**Do not** follow the naive advice to "increase ε for larger lattices" — the volume
scaling means you must *decrease* ε as L grows.

### Parallelisation

| Backend | Mechanism | Selection |
|---------|-----------|-----------|
| CPU | `Threads.@threads` over all L³ sites | `--cpu` flag |
| GPU | CUDA kernels (256 threads/block) | default |

Force evaluation has no data races — every site can be computed simultaneously —
so no sublattice decomposition is needed.

---

## Parameters

All parameters are set via command-line arguments:

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `size` (positional) | `Int` | **required** | Lattice side length L |
| `--mass` | `Float64` | `-2.28587` | Mass parameter m² |
| `--Z` | `Float64` | `1.0` | Coefficient of Z/2 (∇φ)² |
| `--n_lf` | `Int` | `10` | Leapfrog steps per HMC trajectory |
| `--eps` | `Float64` | `0.1` | Leapfrog step size ε |
| `--rng` | `Int` | `0` | Random seed (0 = unseeded) |
| `--fp64` | flag | off | Use Float64 instead of Float32 |
| `--cpu` | flag | off | Use CPU threading instead of GPU |
| `--init` | `String` | — | Path to `.jld2` initial configuration (default: Gaussian hotstart) |
| `--dt` | `Float64` | `0.04` | *(legacy, unused by HMC engine)* |

**Fixed physical constants:**

| Symbol | Value | Description |
|--------|-------|-------------|
| λ | 4.0 | φ⁴ self-coupling |
| T | 1.0 | Temperature |

---

## Workflow

### 0. Test the HMC engine

```bash
julia --project=. scripts/test_hmc.jl
```

Runs four correctness checks on a small L=6 lattice (CPU, Float64, no CLI args):
force finite-difference check, energy conservation, reversibility, and acceptance
rate sanity. All four should print `PASS`.

### 1. Thermalization

```bash
julia --project=. scripts/thermalize.jl <L> [options]
```

Runs `L` outer iterations, each performing `L²` HMC trajectories, and saves the
field to disk after each outer iteration in `data/` as
`thermalized_L_<L>_id_<seed>.jld2`. Prints the acceptance rate at each step:

```
t=1  acceptance=0.782
t=2  acceptance=0.779
...
```

### 2. Single-mass measurement

```bash
julia --project=. scripts/measure_single.jl <L> --init <state.jld2> [options]
```

Evolves the field for `50·L²` HMC trajectories, sampling every `L²/8` steps.
Writes to `data/`:
- `magnetization_L_<L>_Z_<Z>_mass_<m²>_id_<seed>.dat` — step, M, Fourier modes
- `energy_L_<L>_Z_<Z>_mass_<m²>_id_<seed>.dat` — step, H[φ]

where `M = Σφᵢ / L³` is the mean field value.

### 3. Mass scan

```bash
julia --project=. scripts/measure.jl <L> --init <state.jld2> [options]
```

Scans mass values from m² = −3.5 down to −4.0 in steps of 0.01, printing
the acceptance rate at each mass step.

### 4. Snapshot generation

```bash
julia --project=. scripts/snap.jl <L> --init <state.jld2> [options]
```

Saves 2500 field configurations (separated by `L²` HMC trajectories each) to
`data/snapshot_L_<L>_seed_<seed>_id_<idx>.jld2`.

### 5. Statistical analysis

`scripts/bootstrap.jl` provides `average`, `variance`, and `bootstrap` functions
for computing means and uncertainties from measurement files.

### 6. Two-parameter Binder-cumulant reweighting

Create a Slurm array for one lattice size from repeated points and/or a two-column
`Z,m2` CSV.  HMC tuning is intentionally required:

```bash
python3 scripts/submit_reweight_array.py \
    --L 24 --point=0.1,-2.30 --point=0.2,-2.25 \
    --points-csv scan_points.csv --replicas 4 \
    --eps 0.02 --n-lf 15 --samples 2000 --skip 12 \
    --partition gpu --gpu-resource gpu:h100:1 \
    --time 08:00:00 --mem 24G --cpus 4 \
    --module cuda/12.3 --run-name binder_L24 --dry-run
```

The dry run writes `runs/<run-name>/manifest.csv` and `array_job.sh`, then prints
every command without calling `sbatch`. Remove `--dry-run` to submit. Add `--resume`
to validate and reuse matching checkpoints and completed statistics files. Every
retained configuration records `M`, `M2`, `M4`, `Q=sum(phi^2)`, `G=sum(grad(phi)^2)`,
and interval acceptance in a metadata-prefixed CSV.

Analyze one or more manifests and overlay all available lattice sizes:

```bash
python3 reweight_binder.py \
    --manifest runs/binder_L12/manifest.csv \
    --manifest runs/binder_L24/manifest.csv \
    --start 0.1 -2.30 --end 0.3 -2.20 --num 201 \
    --output plots/binder_line --bootstrap 500 --block-size auto
```

This writes `plots/binder_line.csv` and `plots/binder_line.png`. Targets use only
the nearest source coordinate (replicas at that coordinate are combined); the CSV
retains low-overlap points and labels them with `warning_status=low_ess`.

Run the CUDA observable/action-identity and batched-replica HMC check on a GPU node
before production. This also compares batched and single-replica forces and
Hamiltonians, verifies a physical slot swap, and advances one complete batch sweep:

```bash
julia --project=. scripts/test_reweight_stats_gpu.jl 6 --fp64
```

While a representative `L=12` task is running, inspect the actual batched workload
from another shell with:

```bash
nvidia-smi pmon -s um -d 1
```

Use samples taken after Julia compilation and warmup when comparing SM utilization.
The job log must show `replica_execution=batched`; after completion, use the site's
Slurm GPU-efficiency report as the authoritative H200 measurement.

#### Replica-exchange HMC near a first-order transition

Add a centered mass-tempering ladder to each independent source run with
`--tempering-replicas` and `--mass-span`. The count must be odd so that the requested
source mass is the exact central slot. `--replicas` continues to mean independent
chains:

```bash
python3 scripts/submit_reweight_array.py \
    --L 24 --points-csv three_source_points.csv --replicas 12 \
    --tempering-replicas 9 --mass-span 0.12 --swap-every 1 \
    --init-schedule split --phase-threshold 0.25 \
    --eps 0.02 --n-lf 15 --samples 2000 --skip 12 \
    --partition gpu --gpu-resource gpu:h100:1 \
    --time 08:00:00 --mem 24G --cpus 4 \
    --module cuda/12.3 --run-name binder_tempered_L24 --dry-run
```

The ladder endpoints are `m2 - mass_span/2` and `m2 + mass_span/2`; adjacent even and
odd pairs alternate after complete HMC sweeps. On CUDA, one Slurm task stores the
whole ladder as one contiguous `(L,L,L,nreplicas)` array. Every HMC kernel advances
all mass slots in one launch, which exposes enough independent lattice sites to use
large GPUs efficiently. Accepted exchanges copy the two corresponding device slices;
the masses remain attached to their fixed slots. The CPU fallback retains the serial
per-replica implementation. The first thermalizer log line reports
`replica_execution=batched` and the 4D batch shape, so production logs make the
selected path explicit. No new submission option is required.

`--init-schedule split` requires an even independent `--replicas` count. The first
half of the independent jobs start from a near-zero disordered field, and the second
half start near the positive or negative classical ordered minimum (the sign is
chosen reproducibly from the task seed). The complete ladder within one job starts
in the same basin. The manifest and checkpoints record `init_phase`, so `--resume`
cannot silently reuse a checkpoint from the other basin. The legacy default is
`--init-schedule hot`.

Only the central mass slot is written to the standard statistics CSV, so the existing
`reweight_binder.py` command is unchanged. `runs/<run-name>/diagnostics/` contains
per-slot HMC acceptance, per-pair swap acceptance, and completed walker round trips.
Inspect these diagnostics to tune the ladder spacing before trusting a production
ensemble. `--resume` validates the complete ladder checkpoint as well as its target
parameters.

Each diagnostic row also records the target magnetization and phase, cumulative
ordered-phase occupancy and transition count, endpoint magnetizations, and the
walker IDs at the low, target, and high slots. Progress output reports the minimum
swap acceptance and phase statistics every 100 retained samples. Summarize completed
runs in disjoint blocks with:

```bash
python3 scripts/summarize_tempering.py \
    --manifest runs/binder_tempered_L24/manifest.csv \
    --block-size 5000 --phase-threshold 0.25
```

This writes `phase_blocks.csv` beside the manifest and compares pooled Binder
cumulants and phase occupancy between ordered-start and disordered-start jobs.

The replica-exchange CPU correctness check is:

```bash
julia --project=. scripts/test_replica_exchange.jl
```

#### Local task-spooler runs

For a small local GPU study, create the same manifest-backed tasks and enqueue them
with task-spooler (`tsp`). The default concurrency is one, so independent jobs do
not compete for a single GPU:

```bash
python3 scripts/submit_reweight_tsp.py \
    --L 6 --point=-1.05,-2.75 --replicas 4 \
    --tempering-replicas 5 --mass-span 0.2 --swap-every 1 \
    --init-schedule split --phase-threshold 0.25 \
    --eps 0.05 --n-lf 8 --warmup 216 --samples 2000 --skip 12 \
    --slots 1 --run-name local_tempered_L6 --dry-run
```

Remove `--dry-run` to set `tsp -S 1` and enqueue the tasks. Inspect the queue with
`tsp`, follow one task with `tsp -t TASK_ID`, and use `--resume` only with an exactly
matching existing manifest. A pre-existing run is otherwise rejected to prevent
accidental data or manifest replacement.

---

## Valid Lattice Sizes

HMC requires no sublattice decomposition, so **any L ≥ 2 is valid**.

---

## Dependencies

| Package | Purpose |
|---------|---------|
| [ArgParse.jl](https://github.com/carlobaldassi/ArgParse.jl) | Command-line argument parsing |
| [CUDA.jl](https://github.com/JuliaGPU/CUDA.jl) | GPU acceleration |
| [Distributions.jl](https://github.com/JuliaStats/Distributions.jl) | Gaussian hotstart |
| [JLD2.jl](https://github.com/JuliaIO/JLD2.jl) | Binary field snapshots |
| [CodecZlib.jl](https://github.com/JuliaIO/CodecZlib.jl) | Compressed JLD2 output |
| Printf | Formatted output |

Install with:

```bash
julia --project=. -e 'using Pkg; Pkg.instantiate()'
```

---

## Example Usage

```bash
# Test the HMC engine first
julia --project=. scripts/test_hmc.jl

# Thermalise on GPU (default), L=24, default mass (m² = -2.28587)
julia --project=. scripts/thermalize.jl 24

# Thermalise on CPU with 8 threads, Float64, custom seed
julia --project=. --threads 8 scripts/thermalize.jl 24 --cpu --fp64 --rng 42

# Tuned parameters for L=12 (~73% acceptance)
julia --project=. scripts/thermalize.jl 12 --cpu --eps 0.04 --n_lf 20

# Tuned parameters for L=24 (~75% acceptance)
julia --project=. scripts/thermalize.jl 24 --cpu --eps 0.02 --n_lf 10

# Measure from a thermalised starting configuration
julia --project=. scripts/measure_single.jl 24 \
    --init data/thermalized_L_24_id_42.jld2 --rng 42

# Measure at a specific mass (m² = -2.38587)
julia --project=. scripts/measure_single.jl 24 --mass -2.38587 \
    --init data/thermalized_L_24_id_42.jld2
```
