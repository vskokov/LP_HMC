#!/usr/bin/env julia

cd(@__DIR__)
using JLD2
using Printf
include("../src/modelA.jl")

struct RuntimeBudgetExceeded <: Exception end

function load_collection_state(path)
    payload = jldopen(path, "r") do file
        sampler = String(file["sampler"])
        sampler in ("umbrella_exchange", "umbrella_collection") || error("bad sampler")
        sampler == "umbrella_exchange" && !file["thermalization_complete"] &&
            error("thermalization is incomplete")
        (
            fields=file["replica_fields"], masses=file["masses"],
            centers=file["umbrella_centers"], kappas=file["umbrella_kappas"],
            walker_ids=file["walker_ids"], walker_stage=file["walker_stage"],
            round_trips=file["round_trips"], swap_phase=file["swap_phase"],
            sweeps=file["sweeps"], hmc_attempts=file["hmc_attempts"],
            hmc_accepts=file["hmc_accepts"], swap_attempts=file["swap_attempts"],
            swap_accepts=file["swap_accepts"], init_phase=String(file["init_phase"]),
            collected=(haskey(file, "collected_samples") ? Int(file["collected_samples"]) : 0),
            thermal_sweeps=(haskey(file, "thermalization_sweeps") ?
                Int(file["thermalization_sweeps"]) : Int(file["sweeps"])),
            thermal_round_trips=(haskey(file, "thermalization_round_trips") ?
                Int(file["thermalization_round_trips"]) : sum(file["round_trips"])),
            thermal_fraction=(haskey(file, "thermalization_round_trip_fraction") ?
                Float64(file["thermalization_round_trip_fraction"]) :
                count(>(0), file["round_trips"]) / length(file["round_trips"])),
            thermal_swap=(haskey(file, "thermalization_min_swap_acceptance") ?
                Float64(file["thermalization_min_swap_acceptance"]) : minimum([
                    file["swap_attempts"][i] == 0 ? 0.0 :
                    file["swap_accepts"][i] / file["swap_attempts"][i]
                    for i in eachindex(file["swap_attempts"])])),
        )
    end
    nrep = size(payload.fields, 4)
    fields, batched, field_batch = if cpu
        ([ArrayType(payload.fields[:, :, :, slot]) for slot in 1:nrep], false, nothing)
    else
        batch = ArrayType(payload.fields)
        ([@view batch[:, :, :, slot] for slot in 1:nrep], true, batch)
    end
    state = ReplicaExchangeState(fields, FloatType.(payload.masses);
        umbrella_centers=FloatType.(payload.centers), umbrella_kappas=FloatType.(payload.kappas),
        batched=batched, field_batch=field_batch, walker_ids=payload.walker_ids,
        walker_stage=payload.walker_stage, round_trips=payload.round_trips,
        swap_phase=payload.swap_phase, sweeps=payload.sweeps,
        hmc_attempts=payload.hmc_attempts, hmc_accepts=payload.hmc_accepts,
        swap_attempts=payload.swap_attempts, swap_accepts=payload.swap_accepts)
    return state, payload
end

function save_collection_state(path, state, payload, collected)
    temporary = path * ".tmp"
    host_fields = is_batched(state) ? Array(state.batch) :
        cat((Array(field) for field in state.fields)...; dims=4)
    jldsave(temporary, true; schema_version=1, sampler="umbrella_collection",
        L=L, Z=Float64(Z), m²=Float64(m²), epsilon=Float64(ε), n_lf=n_lf, seed=seed,
        replica_fields=host_fields, masses=Float64.(state.masses),
        umbrella_centers=Float64.(state.umbrella_centers),
        umbrella_kappas=Float64.(state.umbrella_kappas), umbrella_power=Float64(umbrella_power),
        swap_every=swap_every, init_phase=payload.init_phase,
        walker_ids=state.walker_ids, walker_stage=state.walker_stage,
        round_trips=state.round_trips, swap_phase=state.swap_phase, sweeps=state.sweeps,
        hmc_attempts=state.hmc_attempts, hmc_accepts=state.hmc_accepts,
        swap_attempts=state.swap_attempts, swap_accepts=state.swap_accepts,
        collected_samples=collected, thermalization_sweeps=payload.thermal_sweeps,
        thermalization_round_trips=payload.thermal_round_trips,
        thermalization_round_trip_fraction=payload.thermal_fraction,
        thermalization_min_swap_acceptance=payload.thermal_swap)
    mv(temporary, path; force=true)
end

function main()
    isnothing(init_arg) && error("--init is required")
    output = parsed_args["output"]; diagnostics = parsed_args["diagnostics"]
    checkpoint = parsed_args["collection-checkpoint"]
    any(isnothing, (output, diagnostics, checkpoint)) && error("output paths are required")
    samples = parsed_args["samples"]
    state, payload = load_collection_state(init_arg)
    payload.init_phase == init_phase || error("initial phase mismatch")
    payload.collected == block_index * samples || error("collection block index mismatch")
    expected_centers, expected_kappas = umbrella_ladder(umbrella_min, umbrella_max,
        umbrella_replicas, umbrella_kappa; power=umbrella_power)
    state.umbrella_centers == expected_centers || error("umbrella centers mismatch")
    state.umbrella_kappas == expected_kappas || error("umbrella kappas mismatch")
    mkpath(dirname(abspath(output))); mkpath(dirname(abspath(diagnostics)))
    output_tmp = abspath(output) * ".tmp"; diagnostics_tmp = abspath(diagnostics) * ".tmp"
    started_at = time()
    try
      open(output_tmp, "w") do stats_io
        open(diagnostics_tmp, "w") do diag_io
            println(stats_io, "trajectory,slot,walker_id,umbrella_center,umbrella_kappa,M,M2,M4,Q,G,acceptance_rate")
            println(diag_io, "trajectory,round_trips_total,walkers_with_round_trip,min_hmc_acceptance,min_swap_acceptance," *
                join(["swap_acceptance_$(i)_$(i + 1)" for i in eachindex(state.swap_attempts)], ","))
            for _ in 1:samples
                old_attempts = copy(state.hmc_attempts); old_accepts = copy(state.hmc_accepts)
                replica_exchange!(state, parsed_args["skip"], Z, ε, n_lf; swap_every=swap_every)
                interval_rates = acceptance_rates(state.hmc_accepts .- old_accepts,
                    state.hmc_attempts .- old_attempts)
                all_stats = replica_sufficient_statistics(state)
                for slot in eachindex(state.fields)
                    M2 = all_stats.M[slot]^2
                    @printf(stats_io, "%d,%d,%d,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g\n",
                        state.sweeps, slot, state.walker_ids[slot], state.umbrella_centers[slot],
                        state.umbrella_kappas[slot], all_stats.M[slot], M2, M2^2,
                        all_stats.Q[slot], all_stats.G[slot], interval_rates[slot])
                end
                swap_rates = acceptance_rates(state.swap_accepts, state.swap_attempts)
                @printf(diag_io, "%d,%d,%d,%.17g,%.17g,%s\n", state.sweeps,
                    sum(state.round_trips), count(>(0), state.round_trips),
                    minimum(acceptance_rates(state.hmc_accepts, state.hmc_attempts)),
                    minimum(swap_rates), join(swap_rates, ","))
                if runtime_seconds > 0 && time() - started_at >= runtime_seconds
                    throw(RuntimeBudgetExceeded())
                end
            end
        end
      end
    catch error
        isfile(output_tmp) && rm(output_tmp); isfile(diagnostics_tmp) && rm(diagnostics_tmp)
        if error isa RuntimeBudgetExceeded
            @printf("runtime_budget_exhausted stage=collection shard=%d\n", block_index)
            exit(75)
        end
        rethrow()
    end
    mv(output_tmp, abspath(output); force=true); mv(diagnostics_tmp, abspath(diagnostics); force=true)
    save_collection_state(abspath(checkpoint), state, payload, payload.collected + samples)
    @printf("collection_shard=%d samples=%d checkpoint=%s\n", block_index, samples, checkpoint)
end

main()
