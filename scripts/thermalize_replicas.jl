#!/usr/bin/env julia

cd(@__DIR__)

using JLD2
using Printf

include("../src/modelA.jl")

function save_checkpoint(path, state)
    temporary = path * ".tmp"
    host_fields = is_batched(state) ? Array(state.batch) :
                  cat((Array(field) for field in state.fields)...; dims=4)
    center = target_slot(state)
    jldsave(temporary, true;
        ϕ=Array(state.fields[center]),
        replica_fields=host_fields,
        schema_version=2,
        sampler="replica_exchange",
        L=L, Z=Float64(Z), m²=Float64(m²), λ=Float64(λ), T=Float64(T),
        epsilon=Float64(ε), n_lf=n_lf, seed=seed,
        fp64=(FloatType == Float64), cpu=cpu,
        replica_execution=(is_batched(state) ? "batched" : "serial"),
        tempering_replicas=length(state.fields), mass_span=Float64(mass_span),
        swap_every=swap_every, masses=Float64.(state.masses),
        init_phase=init_phase,
        ordered_sign=(init_phase == "ordered" ? (isodd(seed) ? 1 : -1) : 0),
        walker_ids=state.walker_ids, walker_stage=state.walker_stage,
        round_trips=state.round_trips, swap_phase=state.swap_phase,
        sweeps=state.sweeps, hmc_attempts=state.hmc_attempts,
        hmc_accepts=state.hmc_accepts, swap_attempts=state.swap_attempts,
        swap_accepts=state.swap_accepts)
    mv(temporary, path; force=true)
end

function main()
    tempering_replicas > 1 || error("thermalize_replicas.jl requires --tempering-replicas > 1")
    swap_every > 0 || error("--swap-every must be positive")
    isnothing(parsed_args["checkpoint"]) && error("--checkpoint is required")
    masses = mass_ladder(m², tempering_replicas, mass_span)
    initial_fields = [initial_field(L, mass) for mass in masses]
    state = if cpu
        ReplicaExchangeState(initial_fields, masses)
    else
        field_batch = cat(initial_fields...; dims=4)
        fields = [@view field_batch[:, :, :, slot] for slot in eachindex(masses)]
        ReplicaExchangeState(fields, masses; batched=true, field_batch=field_batch)
    end
    checkpoint = abspath(parsed_args["checkpoint"])
    mkpath(dirname(checkpoint))
    @printf("replica_execution=%s replicas=%d batch_shape=%s\n",
            is_batched(state) ? "batched" : "serial", length(state.fields),
            is_batched(state) ? string(size(state.batch)) : "n/a")
    flush(stdout)

    for _ in 1:L
        replica_exchange!(state, L^2, Z, ε, n_lf; swap_every=swap_every)
        hmc_rates = acceptance_rates(state.hmc_accepts, state.hmc_attempts)
        swap_rates = acceptance_rates(state.swap_accepts, state.swap_attempts)
        @printf("sweeps=%d hmc_acceptance=%s swap_acceptance=%s round_trips=%d\n",
                state.sweeps, join(round.(hmc_rates; digits=3), ","),
                join(round.(swap_rates; digits=3), ","), sum(state.round_trips))
        flush(stdout)
        save_checkpoint(checkpoint, state)
    end
    @printf("init_phase=%s ordered_sign=%d\n", init_phase,
            init_phase == "ordered" ? (isodd(seed) ? 1 : -1) : 0)
    @printf("checkpoint=%s\n", checkpoint)
end

main()
