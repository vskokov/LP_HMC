# CLAUDE.md — Developer Guide for modelA_LP

## What this codebase does

Samples the Boltzmann distribution `exp(-H[φ]/T)` for a 3D φ⁴ scalar field theory
with a higher-order kinetic term `1/2 (∇²φ)²`. The sampler is **Hybrid Monte Carlo
(HMC)**. Only equilibrium observables are needed: magnetization `M = Σφ/L³` and `Σφ²`.

The Hamiltonian is:
```
H[φ] = Σ_x [ Z/2 (∇φ)²  +  1/2 (∇²φ)²  +  m²/2 φ²  +  λ/4 φ⁴ ]
```
Fixed: λ=4, T=1. Tunable via CLI: Z, m², L, ε, n_lf.

## File map

```
src/modelA.jl       Entry point: imports, ASCII art, includes initialize.jl + simulation.jl
src/initialize.jl   ArgParse → global constants (L, λ, T, Z, m², ε, n_lf, FloatType, ...)
src/simulation.jl   HMC engine (compute_force!, leapfrog!, hmc_step!, thermalize)
src/replica_exchange.jl  Centered m² ladders, alternating swaps, mixing diagnostics
scripts/thermalize.jl   Run thermalization, save .jld2, print acceptance rate
scripts/measure.jl      Mass scan, measure observables
scripts/measure_single.jl  Single-mass measurement + energy output
scripts/snap.jl         Save 2500 field snapshots
scripts/bootstrap.jl    Pure statistics — no simulation calls
scripts/test_hmc.jl     Correctness tests (runs standalone, no ArgParse)
scripts/test_replica_exchange.jl  CPU correctness tests for mass tempering
```

## Architecture: CPU/GPU dispatch

`initialize.jl` sets `const cpu = parsed_args["cpu"]` and `const FloatType`.

`simulation.jl` starts with:
```julia
!cpu && using CUDA
```
Then uses `@static if cpu ... else ... end` at **module level** to define separate
CPU and GPU implementations of `compute_force!` and `calc_total_energy`. `@static if`
evaluates the condition at parse/lowering time and prunes the dead branch before macro
expansion — this is required because `@cuda` is a macro that would fail to expand if
CUDA is not loaded, even in a branch that is never executed at runtime.

Inside function bodies (e.g. `hmc_step!`), plain `if cpu ... else ... end` is safe
because the CUDA calls there (`CUDA.randn`) are regular function references resolved
lazily at runtime, not macros.

## Key functions in simulation.jl

| Function | Signature | Notes |
|----------|-----------|-------|
| `compute_force!` | `(F, ϕ, m², Z)` | Two-pass: ∇²ϕ → ∇⁴ϕ. No data races, all sites parallel. |
| `calc_total_energy` | `(ϕ, m², Z)` | Returns scalar H[φ]. CPU: Float64 accumulator. GPU: CuArray sum. |
| `calc_hamiltonian` | `(ϕ, π, m², Z)` | H[φ] + Σπ²/2 |
| `leapfrog!` | `(ϕ, π, m², Z, ε, n_lf)` | Mutates ϕ and π in-place. |
| `hmc_step!` | `(ϕ, m², Z, ε, n_lf)` | Returns `(accepted::Bool, ΔH::Float64)`. |
| `thermalize` | `(ϕ, m², N)` | Runs N HMC steps. Returns acceptance rate ∈ [0,1]. |

`src/replica_exchange.jl` adds an independent mass-tempering layer without changing
these APIs. It advances one HMC trajectory at every fixed mass coordinate, alternates
adjacent swap pairs, and accepts swaps from the exact `Q=sum(ϕ^2)` crossed-action
difference. The central coordinate is always the requested source mass.

## Global constants (set by initialize.jl, in scope everywhere)

`L`, `λ`, `T`, `Z`, `m²`, `ε`, `n_lf`, `FloatType`, `ArrayType`, `cpu`, `seed`,
`Δt`, `Rate`, `ξ` (last three are legacy from the old Langevin engine, kept for
backward compatibility).

`thermalize` uses `Z`, `ε`, `n_lf` directly from module scope. All other physics
functions take them as explicit arguments (good for testability).

## Force derivation

The force `F(x) = -δH/δφ(x)` is computed in two passes:

1. `lapϕ[x] = ∇²φ(x) = Σ_μ [φ(x+μ̂) + φ(x-μ̂)] - 6φ(x)` (6 neighbours)
2. `F[x] = Z·lapϕ[x] - ∇²lapϕ[x] - m²·φ[x] - λ·φ[x]³`

Do NOT expand ∇⁴ into a hardcoded 18-site stencil — the two-pass approach is the
only one that is straightforward to verify correct.

## thermalize signature — do not change

```julia
function thermalize(ϕ, m², N) → acceptance_rate::Float64
```

Called from `thermalize.jl`, `measure.jl`, `measure_single.jl`, and `snap.jl`.
`m²` is passed explicitly (not read from the module constant) so that `measure.jl`
can scan different mass values.

## Running the correctness tests

```bash
julia --project=. scripts/test_hmc.jl
```

`test_hmc.jl` sets up all constants directly (L=6, Float64, CPU) and includes
`simulation.jl` without going through ArgParse. Four tests:
1. Force finite-difference check — `|F - (-∂H/∂φ_fd)| / |F| < 1e-4`
2. Energy conservation — `|ΔH| / |H| < 1e-3` with ε=0.01, n_lf=50
3. Reversibility — `max|φ_final - φ_initial| < 1e-5` after forward+reverse trajectory
4. Acceptance rate sanity — 0.5 < rate < 0.99 over 200 trajectories

All checks must print `PASS` before any simulation run is trusted.

Run `julia --project=. scripts/test_replica_exchange.jl` for the mass-ladder, exact
swap-action, reference-swap, rejection, and alternating-schedule checks.

## Tuning ε and n_lf

- Target acceptance rate: **70–80%**
- Leapfrog stability bound: `ε ≲ 1/√8 ≈ 0.35` (the `(∇²φ)²` term dominates)
- **Binding constraint is volume scaling**: `|ΔH| ~ ε² × L^(3/2)`, so ε must scale
  as `L^(-3/4)` to keep acceptance fixed — **decrease** ε as L grows, not increase.

Empirically measured at m²=-2.28587 (near phase transition):

| L | ε | n_lf | τ | acceptance |
|---|---|------|---|------------|
| 6 | 0.10 | 10 | 1.0 | ~57% |
| 12 | 0.04 | 20 | 0.8 | ~73% |
| 24 | 0.02 | 10 | 0.2 | ~75% |

For L=24, `--n_lf 15 --eps 0.02` (τ=0.3) gives better decorrelation than n_lf=10.

The rapid acceptance collapse at larger ε (e.g., 0% at ε=0.18 for L=12) is caused
by `|ΔH|` growing as ε², not by leapfrog instability. Non-monotonic acceptance vs ε
at fixed n_lf is a known leapfrog resonance effect — avoid tuning by monotone search.

## What NOT to touch

- The ASCII art header in `src/modelA.jl`
- The `@init_state` macro in `src/initialize.jl`
- The `NNp`/`NNm` functions in `src/simulation.jl`
- The `op(ϕ)` function in `scripts/measure.jl`
- `scripts/bootstrap.jl` — pure statistics, no simulation dependency
- All shell scripts (`*.sh`)
- `Project.toml` / `Manifest.toml` — no new dependencies needed

## Common pitfalls

- **Float32 overflow in exp**: Use `ΔH < 0 || rand() < exp(-ΔH / T)` — the guard
  short-circuits before computing `exp` for large negative ΔH.
- **GPU random numbers**: Use `CUDA.randn(FloatType, L, L, L)`, not
  `ArrayType(randn(...))` which generates on CPU and transfers.
- **m² is a scan variable**: Never capture it from the module constant inside
  `hmc_step!` — it is passed as an argument through the call chain.
- **Valid L**: HMC has no sublattice constraint; any L ≥ 2 works. (The old
  Metropolis engine required L to have a divisor p ≥ 3 with L ≥ 2p.)
