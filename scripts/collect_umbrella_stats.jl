#!/usr/bin/env julia

cd(@__DIR__)

using JLD2
using Printf

include("../src/modelA.jl")

function load_umbrella_state(path)
    payload = jldopen(path, "r") do file
        file["schema_version"] == 3 || error("umbrella checkpoint schema must be 3")
        file["sampler"] == "umbrella_exchange" ||
            error("checkpoint is not umbrella exchange")
        file["thermalization_complete"] || error("thermalization is incomplete")
        (
            fields=file["replica_fields"], masses=file["masses"],
            centers=file["umbrella_centers"], kappas=file["umbrella_kappas"],
            walker_ids=file["walker_ids"], walker_stage=file["walker_stage"],
            round_trips=file["round_trips"], swap_phase=file["swap_phase"],
            sweeps=file["sweeps"], hmc_attempts=file["hmc_attempts"],
            hmc_accepts=file["hmc_accepts"], swap_attempts=file["swap_attempts"],
            swap_accepts=file["swap_accepts"], init_phase=file["init_phase"],
            thermalization_sweeps=file["sweeps"],
            thermalization_round_trips=sum(file["round_trips"]),
            thermalization_round_trip_fraction=
                count(>(0), file["round_trips"]) / length(file["round_trips"]),
            thermalization_min_swap_acceptance=minimum([
                file["swap_attempts"][i] == 0 ? 0.0 :
                file["swap_accepts"][i] / file["swap_attempts"][i]
                for i in eachindex(file["swap_attempts"])
            ]),
            transport_gate_passed=(haskey(file, "transport_gate_passed") ?
                                   file["transport_gate_passed"] :
                                   file["thermalization_complete"]),
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
    summary = (
        sweeps=Int(payload.thermalization_sweeps),
        round_trips=Int(payload.thermalization_round_trips),
        round_trip_fraction=Float64(payload.thermalization_round_trip_fraction),
        min_swap_acceptance=Float64(payload.thermalization_min_swap_acceptance),
        gate_passed=Bool(payload.transport_gate_passed),
    )
    return state, String(payload.init_phase), summary
end

function write_metadata(io, state, samples, skip, warmup, thermalization)
    println(io, "# schema_version=3")
    println(io, "# sampler=umbrella_exchange")
    println(io, "# L=$(L)")
    println(io, "# Z=$(repr(Float64(Z)))")
    println(io, "# m2=$(repr(Float64(m²)))")
    println(io, "# epsilon=$(repr(Float64(ε)))")
    println(io, "# n_lf=$(n_lf)")
    println(io, "# seed=$(seed)")
    println(io, "# lambda=$(repr(Float64(λ)))")
    println(io, "# temperature=$(repr(Float64(T)))")
    println(io, "# float_type=$(FloatType)")
    println(io, "# device=$(cpu ? "cpu" : "cuda")")
    println(io, "# samples_per_window=$(samples)")
    println(io, "# skip=$(skip)")
    println(io, "# warmup=$(warmup)")
    println(io, "# thermalization_sweeps=$(thermalization.sweeps)")
    println(io, "# thermalization_round_trips=$(thermalization.round_trips)")
    println(io, "# thermalization_round_trip_fraction=$(thermalization.round_trip_fraction)")
    println(io, "# thermalization_min_swap_acceptance=$(thermalization.min_swap_acceptance)")
    println(io, "# transport_gate_passed=$(thermalization.gate_passed)")
    println(io, "# umbrella_replicas=$(length(state.fields))")
    println(io, "# umbrella_coordinate=M2")
    println(io, "# umbrella_centers=$(join(Float64.(state.umbrella_centers), ";"))")
    println(io, "# umbrella_kappas=$(join(Float64.(state.umbrella_kappas), ";"))")
    println(io, "# umbrella_power=$(repr(Float64(umbrella_power)))")
    println(io, "# swap_every=$(swap_every)")
    println(io, "# init_phase=$(init_phase)")
end

function main()
    samples = parsed_args["samples"]
    skip = parsed_args["skip"]
    warmup = parsed_args["warmup"]
    output_arg = parsed_args["output"]
    diagnostics_arg = parsed_args["diagnostics"]
    samples > 0 || error("--samples must be positive")
    skip > 0 || error("--skip must be positive")
    warmup >= 0 || error("--warmup must be non-negative")
    isnothing(init_arg) && error("--init umbrella checkpoint is required")
    isnothing(output_arg) && error("--output is required")
    isnothing(diagnostics_arg) && error("--diagnostics is required")

    state, checkpoint_phase, thermalization = load_umbrella_state(init_arg)
    checkpoint_phase == init_phase || error("checkpoint initial phase mismatch")
    minimum_sweeps = production_sweeps > 0 ? production_sweeps : L^3
    (thermalization.gate_passed && thermalization.sweeps >= minimum_sweeps &&
     thermalization.round_trip_fraction >= min_round_trip_fraction &&
     thermalization.min_swap_acceptance >= min_swap_acceptance) ||
        error("checkpoint transport gate did not pass")
    expected_centers, expected_kappas = umbrella_ladder(
        umbrella_min, umbrella_max, umbrella_replicas, umbrella_kappa;
        power=umbrella_power
    )
    state.umbrella_centers == expected_centers || error("umbrella centers mismatch")
    state.umbrella_kappas == expected_kappas || error("umbrella kappas mismatch")
    all(==(m²), state.masses) || error("checkpoint mass mismatch")
    warmup > 0 && replica_exchange!(state, warmup, Z, ε, n_lf;
                                    swap_every=swap_every)
    reset_replica_diagnostics!(state)

    output = abspath(output_arg)
    diagnostics = abspath(diagnostics_arg)
    mkpath(dirname(output)); mkpath(dirname(diagnostics))
    output_tmp = output * ".tmp.$(getpid())"
    diagnostics_tmp = diagnostics * ".tmp.$(getpid())"
    try
        open(output_tmp, "w") do stats_io
            open(diagnostics_tmp, "w") do diag_io
                write_metadata(stats_io, state, samples, skip, warmup, thermalization)
                println(stats_io,
                    "trajectory,slot,walker_id,umbrella_center,umbrella_kappa,M,M2,M4,Q,G,acceptance_rate")
                println(diag_io,
                    "trajectory,round_trips_total,walkers_with_round_trip,min_hmc_acceptance,min_swap_acceptance," *
                    join(["swap_acceptance_$(i)_$(i + 1)" for i in eachindex(state.swap_attempts)], ","))
                for sample in 1:samples
                    previous_attempts = copy(state.hmc_attempts)
                    previous_accepts = copy(state.hmc_accepts)
                    replica_exchange!(state, skip, Z, ε, n_lf; swap_every=swap_every)
                    interval_attempts = state.hmc_attempts .- previous_attempts
                    interval_accepts = state.hmc_accepts .- previous_accepts
                    interval_rates = acceptance_rates(interval_accepts, interval_attempts)
                    all_stats = replica_sufficient_statistics(state)
                    for slot in eachindex(state.fields)
                        M2 = all_stats.M[slot]^2
                        @printf(stats_io,
                            "%d,%d,%d,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g\n",
                            state.sweeps, slot, state.walker_ids[slot],
                            state.umbrella_centers[slot], state.umbrella_kappas[slot],
                            all_stats.M[slot], M2, M2^2, all_stats.Q[slot],
                            all_stats.G[slot], interval_rates[slot])
                    end
                    swap_rates = acceptance_rates(state.swap_accepts, state.swap_attempts)
                    @printf(diag_io, "%d,%d,%d,%.17g,%.17g,%s\n",
                            state.sweeps, sum(state.round_trips),
                            count(>(0), state.round_trips),
                            minimum(acceptance_rates(state.hmc_accepts,
                                                     state.hmc_attempts)),
                            minimum(swap_rates), join(swap_rates, ","))
                    if sample % 100 == 0
                        flush(stats_io); flush(diag_io)
                        @printf("samples_per_window=%d min_swap_acceptance=%.3f round_trips=%d\n",
                                sample, minimum(swap_rates), sum(state.round_trips))
                        flush(stdout)
                    end
                end
            end
        end
        mv(output_tmp, output; force=true)
        mv(diagnostics_tmp, diagnostics; force=true)
    finally
        isfile(output_tmp) && rm(output_tmp)
        isfile(diagnostics_tmp) && rm(diagnostics_tmp)
    end
    @printf("statistics=%s\ndiagnostics=%s\n", output, diagnostics)
end

main()
