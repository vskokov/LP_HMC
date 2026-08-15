#!/usr/bin/env julia

cd(@__DIR__)

using JLD2
using Printf

include("../src/modelA.jl")

function save_umbrella_checkpoint(path, state; thermalization_complete=false)
    temporary = path * ".tmp"
    host_fields = is_batched(state) ? Array(state.batch) :
                  cat((Array(field) for field in state.fields)...; dims=4)
    middle = cld(length(state.fields), 2)
    jldsave(temporary, true;
        ϕ=Array(state.fields[middle]), replica_fields=host_fields,
        schema_version=3, sampler="umbrella_exchange",
        L=L, Z=Float64(Z), m²=Float64(m²), λ=Float64(λ), T=Float64(T),
        epsilon=Float64(ε), n_lf=n_lf, seed=seed,
        startup_epsilon=Float64(startup_ε), startup_n_lf=startup_n_lf,
        startup_sweeps=startup_sweeps,
        requested_production_sweeps=production_sweeps,
        thermalization_complete=thermalization_complete,
        fp64=(FloatType == Float64), cpu=cpu,
        replica_execution=(is_batched(state) ? "batched" : "serial"),
        umbrella_replicas=length(state.fields),
        umbrella_centers=Float64.(state.umbrella_centers),
        umbrella_kappas=Float64.(state.umbrella_kappas),
        umbrella_power=Float64(umbrella_power),
        umbrella_coordinate="M2", swap_every=swap_every,
        masses=Float64.(state.masses), init_phase=init_phase,
        ordered_sign=(init_phase == "ordered" ? (isodd(seed) ? 1 : -1) : 0),
        walker_ids=state.walker_ids, walker_stage=state.walker_stage,
        round_trips=state.round_trips, swap_phase=state.swap_phase,
        sweeps=state.sweeps, hmc_attempts=state.hmc_attempts,
        hmc_accepts=state.hmc_accepts, swap_attempts=state.swap_attempts,
        swap_accepts=state.swap_accepts)
    mv(temporary, path; force=true)
end

function main()
    umbrella_replicas >= 2 ||
        error("thermalize_umbrella.jl requires --umbrella-replicas >= 2")
    swap_every > 0 || error("--swap-every must be positive")
    isnothing(parsed_args["checkpoint"]) && error("--checkpoint is required")
    centers, kappas = umbrella_ladder(
        umbrella_min, umbrella_max, umbrella_replicas, umbrella_kappa;
        power=umbrella_power
    )
    masses = fill(m², umbrella_replicas)
    initial_fields = [
        initial_field(L, m², init_phase; umbrella_center=center) for center in centers
    ]
    state = if cpu
        ReplicaExchangeState(initial_fields, masses;
                             umbrella_centers=centers, umbrella_kappas=kappas)
    else
        field_batch = cat(initial_fields...; dims=4)
        fields = [@view field_batch[:, :, :, slot] for slot in eachindex(centers)]
        ReplicaExchangeState(fields, masses; umbrella_centers=centers,
                             umbrella_kappas=kappas, batched=true,
                             field_batch=field_batch)
    end
    checkpoint = abspath(parsed_args["checkpoint"])
    mkpath(dirname(checkpoint))
    @printf("sampler=umbrella_exchange execution=%s replicas=%d centers=[%.6g,%.6g] kappa=%.6g\n",
            is_batched(state) ? "batched" : "serial", length(state.fields),
            first(centers), last(centers), umbrella_kappa)
    flush(stdout)

    if startup_sweeps > 0
        completed = 0
        while completed < startup_sweeps
            block = min(L^2, startup_sweeps - completed)
            replica_exchange!(state, block, Z, startup_ε, startup_n_lf;
                              swap_every=swap_every)
            completed += block
            @printf("stage=startup sweeps=%d/%d hmc_acceptance=%s round_trips=%d\n",
                    completed, startup_sweeps,
                    join(round.(acceptance_rates(state.hmc_accepts,
                                                 state.hmc_attempts); digits=3), ","),
                    sum(state.round_trips))
            flush(stdout)
        end
        reset_replica_diagnostics!(state)
    end

    total_production_sweeps = production_sweeps > 0 ? production_sweeps : L^3
    checkpoint_block = max(L^2, cld(total_production_sweeps, L))
    completed = 0
    while completed < total_production_sweeps
        block = min(checkpoint_block, total_production_sweeps - completed)
        replica_exchange!(state, block, Z, ε, n_lf; swap_every=swap_every)
        completed += block
        @printf("stage=production sweeps=%d hmc_acceptance=%s swap_acceptance=%s round_trips=%d\n",
                state.sweeps,
                join(round.(acceptance_rates(state.hmc_accepts,
                                             state.hmc_attempts); digits=3), ","),
                join(round.(acceptance_rates(state.swap_accepts,
                                             state.swap_attempts); digits=3), ","),
                sum(state.round_trips))
        flush(stdout)
        save_umbrella_checkpoint(checkpoint, state;
                                 thermalization_complete=(completed == total_production_sweeps))
    end
    @printf("checkpoint=%s\n", checkpoint)
end

main()
