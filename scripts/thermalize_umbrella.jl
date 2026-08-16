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
        maximum_production_sweeps=max_production_sweeps,
        minimum_round_trip_fraction=Float64(min_round_trip_fraction),
        minimum_swap_acceptance=Float64(min_swap_acceptance),
        round_trip_walker_fraction=round_trip_walker_fraction(state),
        transport_gate_passed=thermalization_complete,
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

function load_umbrella_state(path)
    payload = jldopen(path, "r") do file
        file["schema_version"] == 3 || error("umbrella checkpoint schema must be 3")
        file["sampler"] == "umbrella_exchange" ||
            error("checkpoint is not umbrella exchange")
        (
            fields=file["replica_fields"], masses=file["masses"],
            centers=file["umbrella_centers"], kappas=file["umbrella_kappas"],
            walker_ids=file["walker_ids"], walker_stage=file["walker_stage"],
            round_trips=file["round_trips"], swap_phase=file["swap_phase"],
            sweeps=file["sweeps"], hmc_attempts=file["hmc_attempts"],
            hmc_accepts=file["hmc_accepts"], swap_attempts=file["swap_attempts"],
            swap_accepts=file["swap_accepts"], init_phase=file["init_phase"],
        )
    end
    nrep = size(payload.fields, 4)
    fields, batched, field_batch = if cpu
        ([ArrayType(payload.fields[:, :, :, slot]) for slot in 1:nrep], false, nothing)
    else
        batch = ArrayType(payload.fields)
        ([@view batch[:, :, :, slot] for slot in 1:nrep], true, batch)
    end
    state = ReplicaExchangeState(
        fields, FloatType.(payload.masses);
        umbrella_centers=FloatType.(payload.centers),
        umbrella_kappas=FloatType.(payload.kappas), batched=batched,
        field_batch=field_batch, walker_ids=payload.walker_ids,
        walker_stage=payload.walker_stage, round_trips=payload.round_trips,
        swap_phase=payload.swap_phase, sweeps=payload.sweeps,
        hmc_attempts=payload.hmc_attempts, hmc_accepts=payload.hmc_accepts,
        swap_attempts=payload.swap_attempts, swap_accepts=payload.swap_accepts,
    )
    return state, String(payload.init_phase)
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
    resuming = !isnothing(init_arg)
    state = if resuming
        loaded, checkpoint_phase = load_umbrella_state(init_arg)
        checkpoint_phase == init_phase || error("checkpoint initial phase mismatch")
        loaded.umbrella_centers == centers || error("umbrella centers mismatch")
        loaded.umbrella_kappas == kappas || error("umbrella kappas mismatch")
        all(==(m²), loaded.masses) || error("checkpoint mass mismatch")
        loaded
    else
        initial_fields = [
            initial_field(L, m², init_phase; umbrella_center=center) for center in centers
        ]
        if cpu
            ReplicaExchangeState(initial_fields, masses;
                                 umbrella_centers=centers, umbrella_kappas=kappas)
        else
            field_batch = cat(initial_fields...; dims=4)
            fields = [@view field_batch[:, :, :, slot] for slot in eachindex(centers)]
            ReplicaExchangeState(fields, masses; umbrella_centers=centers,
                                 umbrella_kappas=kappas, batched=true,
                                 field_batch=field_batch)
        end
    end
    checkpoint = abspath(parsed_args["checkpoint"])
    mkpath(dirname(checkpoint))
    @printf("sampler=umbrella_exchange execution=%s replicas=%d centers=[%.6g,%.6g] kappa=%.6g\n",
            is_batched(state) ? "batched" : "serial", length(state.fields),
            first(centers), last(centers), umbrella_kappa)
    flush(stdout)

    if !resuming && startup_sweeps > 0
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

    minimum_sweeps = production_sweeps > 0 ? production_sweeps : L^3
    maximum_sweeps = max_production_sweeps > 0 ? max_production_sweeps : minimum_sweeps
    maximum_sweeps >= minimum_sweeps ||
        error("--max-production-sweeps must be at least --production-sweeps")
    checkpoint_block = max(L^2, cld(maximum_sweeps, L))
    passed = transport_gate_passed(
        state, minimum_sweeps, min_round_trip_fraction, min_swap_acceptance
    )
    @printf("transport_gate minimum_sweeps=%d maximum_sweeps=%d minimum_round_trip_fraction=%.3f minimum_swap_acceptance=%.3f resumed=%s initial_sweeps=%d\n",
            minimum_sweeps, maximum_sweeps, min_round_trip_fraction,
            min_swap_acceptance,
            string(resuming), state.sweeps)
    flush(stdout)
    while !passed && state.sweeps < maximum_sweeps
        block = min(checkpoint_block, maximum_sweeps - state.sweeps)
        replica_exchange!(state, block, Z, ε, n_lf; swap_every=swap_every)
        passed = transport_gate_passed(
            state, minimum_sweeps, min_round_trip_fraction, min_swap_acceptance
        )
        @printf("stage=production sweeps=%d hmc_acceptance=%s swap_acceptance=%s round_trips=%d round_trip_walker_fraction=%.3f gate=%s\n",
                state.sweeps,
                join(round.(acceptance_rates(state.hmc_accepts,
                                             state.hmc_attempts); digits=3), ","),
                join(round.(acceptance_rates(state.swap_accepts,
                                             state.swap_attempts); digits=3), ","),
                sum(state.round_trips), round_trip_walker_fraction(state),
                passed ? "passed" : "pending")
        flush(stdout)
        save_umbrella_checkpoint(checkpoint, state;
                                 thermalization_complete=passed)
    end
    save_umbrella_checkpoint(checkpoint, state; thermalization_complete=passed)
    passed || error(
        "umbrella transport gate failed at $(state.sweeps) sweeps: " *
        "round-trip walker fraction=$(round_trip_walker_fraction(state)) " *
        "(required $(min_round_trip_fraction)), minimum swap acceptance=" *
        "$(minimum(acceptance_rates(state.swap_accepts, state.swap_attempts))) " *
        "(required $(min_swap_acceptance)); checkpoint is resumable"
    )
    @printf("transport_gate=passed sweeps=%d round_trips=%d round_trip_walker_fraction=%.6f\n",
            state.sweeps, sum(state.round_trips), round_trip_walker_fraction(state))
    @printf("checkpoint=%s\n", checkpoint)
end

main()
