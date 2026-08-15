#!/usr/bin/env julia

cd(@__DIR__)

using CUDA
using Printf
using Random

CUDA.functional() || error("CUDA is not functional")

const L = 4
const FloatType = Float32
const ArrayType = CuArray
const cpu = false
const λ = FloatType(4)
const T = FloatType(1)

include("../src/simulation.jl")
include("../src/replica_exchange.jl")

passed = Ref(0)
failed = Ref(0)
function report(name, ok, detail="")
    @printf("%s  %-34s %s\n", ok ? "PASS" : "FAIL", name, detail)
    ok ? (passed[] += 1) : (failed[] += 1)
end

Random.seed!(41)
CUDA.seed!(41)
replicas = 5
masses = Float32.(fill(-2.0, replicas))
centers, kappas = umbrella_ladder(0.0f0, 0.4f0, replicas, 80.0f0)
batch = CuArray(randn(Float32, L, L, L, replicas))
fields = [@view batch[:, :, :, slot] for slot in 1:replicas]
state = ReplicaExchangeState(fields, masses; umbrella_centers=centers,
    umbrella_kappas=kappas, batched=true, field_batch=batch)
workspace = state.workspace

randn!(workspace.momentum)
batched_hamiltonians!(workspace.old_hamiltonians, workspace.site_energy, batch,
    workspace.momentum, workspace.device_masses, 1.0f0, workspace)
serial_hamiltonians = [
    calc_hamiltonian_umbrella(fields[slot], @view(workspace.momentum[:, :, :, slot]),
                              masses[slot], 1.0f0, centers[slot], kappas[slot])
    for slot in 1:replicas
]
energy_error = maximum(abs.(workspace.old_hamiltonians .- serial_hamiltonians))
report("Batched umbrella Hamiltonian", energy_error < 2e-4,
       @sprintf("max_error=%.3e", energy_error))

compute_force_batched!(workspace.force, workspace.laplacian, batch,
                       workspace.device_masses, 1.0f0, workspace)
force_errors = Float64[]
for slot in 1:replicas
    reference = similar(fields[slot])
    compute_force_umbrella!(reference, fields[slot], masses[slot], 1.0f0,
                            centers[slot], kappas[slot])
    push!(force_errors, maximum(abs.(Array(reference .- @view(workspace.force[:, :, :, slot])))))
end
report("Batched umbrella force", maximum(force_errors) < 2e-5,
       @sprintf("max_error=%.3e", maximum(force_errors)))

batched_stats = replica_sufficient_statistics(state)
serial_stats = sufficient_statistics.(fields)
stats_error = maximum(vcat(
    abs.(batched_stats.M .- [value.M for value in serial_stats]),
    abs.(batched_stats.Q .- [value.Q for value in serial_stats]),
    abs.(batched_stats.G .- [value.G for value in serial_stats]),
))
report("Batched sufficient statistics", stats_error < 2e-4,
       @sprintf("max_error=%.3e", stats_error))

replica_exchange!(state, 4, 1.0f0, 0.02f0, 4; swap_every=1,
                  rng=MersenneTwister(52))
report("Batched umbrella exchange sweep",
       state.sweeps == 4 && all(==(4), state.hmc_attempts) &&
       sum(state.swap_attempts) == 8 && all(isfinite, Array(state.batch)),
       "swaps=$(sum(state.swap_accepts))/$(sum(state.swap_attempts))")

@printf("\n%d passed, %d failed\n", passed[], failed[])
failed[] > 0 && exit(1)
