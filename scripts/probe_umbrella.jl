#!/usr/bin/env julia

cd(@__DIR__)

using Printf
using Statistics

include("../src/modelA.jl")

function main()
    umbrella_replicas >= 2 || error("--umbrella-replicas must be at least 2")
    sweeps = parsed_args["samples"]
    sweeps > 0 || error("--samples is used as the probe sweep count and must be positive")
    centers, kappas = umbrella_ladder(
        umbrella_min, umbrella_max, umbrella_replicas, umbrella_kappa;
        power=umbrella_power
    )
    masses = fill(m², umbrella_replicas)
    initial_fields = [
        initial_field(L, m², init_phase; umbrella_center=center) for center in centers
    ]
    state = if cpu
        ReplicaExchangeState(initial_fields, masses; umbrella_centers=centers,
                             umbrella_kappas=kappas)
    else
        batch = cat(initial_fields...; dims=4)
        fields = [@view batch[:, :, :, slot] for slot in eachindex(centers)]
        ReplicaExchangeState(fields, masses; umbrella_centers=centers,
                             umbrella_kappas=kappas, batched=true,
                             field_batch=batch)
    end
    if startup_sweeps > 0
        startup_elapsed = @elapsed replica_exchange!(
            state, startup_sweeps, Z, startup_ε, startup_n_lf;
            swap_every=swap_every
        )
        startup_rates = acceptance_rates(state.hmc_accepts, state.hmc_attempts)
        @printf("startup_sweeps=%d startup_elapsed_seconds=%.6f startup_hmc_acceptance_min=%.4f median=%.4f max=%.4f\n",
                startup_sweeps, startup_elapsed, minimum(startup_rates),
                median(startup_rates), maximum(startup_rates))
        reset_replica_diagnostics!(state)
    end
    elapsed = @elapsed replica_exchange!(state, sweeps, Z, ε, n_lf;
                                         swap_every=swap_every)
    coordinates = batched_umbrella_statistics(state)
    hmc_rates = acceptance_rates(state.hmc_accepts, state.hmc_attempts)
    swap_rates = acceptance_rates(state.swap_accepts, state.swap_attempts)
    @printf("L=%d replicas=%d sweeps=%d elapsed_seconds=%.6f sweeps_per_second=%.6f\n",
            L, umbrella_replicas, sweeps, elapsed, sweeps / elapsed)
    if umbrella_replicas <= 50
        @printf("hmc_acceptance=%s\n", join(round.(hmc_rates; digits=4), ","))
        @printf("swap_acceptance=%s\n", join(round.(swap_rates; digits=4), ","))
        @printf("M2=%s\n", join(round.(coordinates; digits=6), ","))
    else
        @printf("hmc_acceptance_min=%.4f median=%.4f max=%.4f\n",
                minimum(hmc_rates), median(hmc_rates), maximum(hmc_rates))
        @printf("swap_acceptance_min=%.4f median=%.4f max=%.4f bottleneck_edge=%d\n",
                minimum(swap_rates), median(swap_rates), maximum(swap_rates),
                argmin(swap_rates))
        deviations = abs.(coordinates .- centers)
        @printf("M2_first=%.6g M2_last=%.6g max_center_deviation=%.6g deviation_slot=%d\n",
                first(coordinates), last(coordinates), maximum(deviations),
                argmax(deviations))
    end
    @printf("round_trips=%d\n", sum(state.round_trips))
end

main()
