#!/usr/bin/env julia

# Cluster check for CUDA observables and batched replica-exchange HMC.
# Usage: julia --project=. scripts/test_reweight_stats_gpu.jl 6 --fp64

cd(@__DIR__)
using Printf

include("../src/modelA.jl")

function main()
    cpu && error("this check requires CUDA; omit --cpu")
    FloatType == Float64 || error("this check requires --fp64")

    ϕ = hotstart(L)
    stats = sufficient_statistics(ϕ)
    host = Array(ϕ)

    M_brute = sum(host) / L^3
    Q_brute = sum(abs2, host)
    G_brute = 0.0
    for x3 in 1:L, x2 in 1:L, x1 in 1:L
        value = host[x1, x2, x3]
        G_brute += (host[NNp(x1), x2, x3] - value)^2
        G_brute += (host[x1, NNp(x2), x3] - value)^2
        G_brute += (host[x1, x2, NNp(x3)] - value)^2
    end

    source_m2, source_Z = -2.31, 0.83
    target_m2, target_Z = -2.07, -0.14
    direct = Float64(calc_total_energy(ϕ, target_m2, target_Z) -
                     calc_total_energy(ϕ, source_m2, source_Z))
    sufficient = 0.5 * (target_m2 - source_m2) * stats.Q +
                 0.5 * (target_Z - source_Z) * stats.G

    stats_error = maximum(abs.((stats.M - M_brute, stats.Q - Q_brute, stats.G - G_brute)))
    action_error = abs(direct - sufficient)
    tolerance = 1e-10 * max(1.0, Q_brute, G_brute, abs(direct))

    ladder = mass_ladder(FloatType(source_m2), 3, FloatType(0.2))
    first, second, third = copy(ϕ), copy(ϕ), copy(ϕ)
    exchange = ReplicaExchangeState([first, second, third], ladder)
    swap_accepted, _ = attempt_replica_swap!(exchange, 1; q_left=1.0, q_right=4.0)
    reference_swap_ok = swap_accepted && exchange.fields[1] === second &&
                        exchange.fields[2] === first && exchange.walker_ids == [2, 1, 3]

    field_batch = cat(copy(ϕ), copy(ϕ), copy(ϕ); dims=4)
    batch_fields = [@view field_batch[:, :, :, slot] for slot in eachindex(ladder)]
    batch = ReplicaExchangeState(batch_fields, ladder; batched=true)

    compute_force_batched!(batch.workspace.force, batch.workspace.laplacian,
                           field_batch, batch.workspace.device_masses, FloatType(source_Z))
    CUDA.synchronize()
    force_error = 0.0
    for slot in eachindex(ladder)
        scalar_force = similar(batch.fields[slot])
        compute_force!(scalar_force, batch.fields[slot], ladder[slot], FloatType(source_Z))
        CUDA.synchronize()
        force_error = max(force_error, maximum(abs, Array(
            scalar_force .- batch.workspace.force[:, :, :, slot]
        )))
    end

    fill!(batch.workspace.momentum, FloatType(0.125))
    batched_hamiltonians!(batch.workspace.old_hamiltonians, batch.workspace.site_energy,
                          field_batch, batch.workspace.momentum,
                          batch.workspace.device_masses, FloatType(source_Z))
    scalar_hamiltonians = [
        Float64(calc_total_energy(batch.fields[slot], ladder[slot], FloatType(source_Z))) +
        0.5 * Float64(sum(abs2, batch.workspace.momentum[:, :, :, slot]))
        for slot in eachindex(ladder)
    ]
    hamiltonian_error = maximum(abs.(batch.workspace.old_hamiltonians .- scalar_hamiltonians))

    left_before = Array(batch.fields[1])
    right_before = Array(batch.fields[2])
    batch_swap_accepted, _ = attempt_replica_swap!(batch, 1; q_left=1.0, q_right=4.0)
    CUDA.synchronize()
    batch_swap_ok = batch_swap_accepted && Array(batch.fields[1]) == right_before &&
                    Array(batch.fields[2]) == left_before && batch.walker_ids == [2, 1, 3]

    attempts_before = copy(batch.hmc_attempts)
    replica_exchange_sweep!(batch, FloatType(source_Z), FloatType(0.001), 2;
                            swap_every=2)
    CUDA.synchronize()
    sweep_ok = batch.hmc_attempts == attempts_before .+ 1 &&
               all(isfinite, Array(field_batch))

    force_tolerance = 1e-11 * max(1.0, maximum(abs, Array(batch.workspace.force)))
    hamiltonian_tolerance = 1e-10 * max(1.0, maximum(abs, scalar_hamiltonians))
    passed = stats_error <= tolerance && action_error <= tolerance && reference_swap_ok &&
             force_error <= force_tolerance && hamiltonian_error <= hamiltonian_tolerance &&
             batch_swap_ok && sweep_ok

    @printf("%s  CUDA reweight/exchange  stats_err=%.3e action_err=%.3e serial_swap=%s\n",
            passed ? "PASS" : "FAIL", stats_error, action_error, reference_swap_ok)
    @printf("      batched HMC         force_err=%.3e H_err=%.3e batch_swap=%s sweep=%s\n",
            force_error, hamiltonian_error, batch_swap_ok, sweep_ok)
    @printf("      tolerances          stats=%.3e force=%.3e H=%.3e\n",
            tolerance, force_tolerance, hamiltonian_tolerance)
    passed || exit(1)
end

main()
