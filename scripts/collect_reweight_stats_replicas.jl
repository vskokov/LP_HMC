#!/usr/bin/env julia

cd(@__DIR__)

using JLD2
using Printf

include("../src/modelA.jl")

function load_replica_state(path)
    payload = jldopen(path, "r") do file
        file["schema_version"] == 2 || error("replica checkpoint schema must be 2")
        file["sampler"] == "replica_exchange" || error("checkpoint is not replica exchange")
        (
            fields=file["replica_fields"], masses=file["masses"],
            walker_ids=file["walker_ids"], walker_stage=file["walker_stage"],
            round_trips=file["round_trips"], swap_phase=file["swap_phase"],
            sweeps=file["sweeps"], hmc_attempts=file["hmc_attempts"],
            hmc_accepts=file["hmc_accepts"], swap_attempts=file["swap_attempts"],
            swap_accepts=file["swap_accepts"],
            init_phase=(haskey(file, "init_phase") ? file["init_phase"] : "hot"),
        )
    end
    nrep = size(payload.fields, 4)
    masses = FloatType.(payload.masses)
    fields, batched = if cpu
        ([ArrayType(payload.fields[:, :, :, slot]) for slot in 1:nrep], false)
    else
        field_batch = ArrayType(payload.fields)
        ([@view field_batch[:, :, :, slot] for slot in 1:nrep], true)
    end
    state = ReplicaExchangeState(fields, masses; batched=batched,
        walker_ids=payload.walker_ids, walker_stage=payload.walker_stage,
        round_trips=payload.round_trips, swap_phase=payload.swap_phase,
        sweeps=payload.sweeps, hmc_attempts=payload.hmc_attempts,
        hmc_accepts=payload.hmc_accepts, swap_attempts=payload.swap_attempts,
        swap_accepts=payload.swap_accepts)
    return state, String(payload.init_phase)
end

function write_metadata(io, state, samples, skip, warmup)
    println(io, "# schema_version=2")
    println(io, "# sampler=replica_exchange")
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
    println(io, "# replica_execution=$(is_batched(state) ? "batched" : "serial")")
    println(io, "# samples=$(samples)")
    println(io, "# skip=$(skip)")
    println(io, "# warmup=$(warmup)")
    println(io, "# tempering_replicas=$(length(state.fields))")
    println(io, "# mass_span=$(repr(Float64(mass_span)))")
    println(io, "# swap_every=$(swap_every)")
    println(io, "# masses=$(join(Float64.(state.masses), ";"))")
    println(io, "# init_phase=$(init_phase)")
    println(io, "# phase_threshold=$(repr(phase_threshold))")
end

magnetization(field) = Float64(sum(field)) / L^3

function main()
    samples = parsed_args["samples"]
    skip = parsed_args["skip"]
    warmup = parsed_args["warmup"]
    output_arg = parsed_args["output"]
    diagnostics_arg = parsed_args["diagnostics"]
    samples > 0 || error("--samples must be positive")
    skip > 0 || error("--skip must be positive")
    warmup >= 0 || error("--warmup must be non-negative")
    swap_every > 0 || error("--swap-every must be positive")
    isnothing(init_arg) && error("--init replica checkpoint is required")
    isnothing(output_arg) && error("--output is required")
    isnothing(diagnostics_arg) && error("--diagnostics is required")

    state, checkpoint_init_phase = load_replica_state(init_arg)
    checkpoint_init_phase == init_phase ||
        error("checkpoint init_phase=$(checkpoint_init_phase) does not match --init-phase=$(init_phase)")
    expected_masses = mass_ladder(m², tempering_replicas, mass_span)
    state.masses == expected_masses || error("checkpoint mass ladder does not match arguments")
    warmup > 0 && replica_exchange!(state, warmup, Z, ε, n_lf; swap_every=swap_every)

    output = abspath(output_arg)
    diagnostics = abspath(diagnostics_arg)
    mkpath(dirname(output)); mkpath(dirname(diagnostics))
    output_tmp = output * ".tmp.$(getpid())"
    diagnostics_tmp = diagnostics * ".tmp.$(getpid())"
    center = target_slot(state)
    ordered_visits = 0
    phase_transitions = 0
    previous_ordered = nothing

    try
        open(output_tmp, "w") do stats_io
            open(diagnostics_tmp, "w") do diag_io
                write_metadata(stats_io, state, samples, skip, warmup)
                println(stats_io, "trajectory,M,M2,M4,Q,G,acceptance_rate")
                diag_columns = vcat(
                    ["trajectory"],
                    ["hmc_acceptance_slot_$(i)" for i in eachindex(state.fields)],
                    ["swap_acceptance_$(i)_$(i + 1)" for i in eachindex(state.swap_attempts)],
                    ["round_trips_total", "target_M", "target_abs_M",
                     "target_phase_ordered", "target_ordered_fraction",
                     "target_phase_transitions", "walker_id_low",
                     "walker_id_target", "walker_id_high", "M_low", "M_high"],
                )
                println(diag_io, join(diag_columns, ","))

                for sample in 1:samples
                    old_attempts = state.hmc_attempts[center]
                    old_accepts = state.hmc_accepts[center]
                    replica_exchange!(state, skip, Z, ε, n_lf; swap_every=swap_every)
                    stats = sufficient_statistics(state.fields[center])
                    attempts = state.hmc_attempts[center] - old_attempts
                    accepted = state.hmc_accepts[center] - old_accepts
                    interval_acceptance = attempts == 0 ? 0.0 : accepted / attempts
                    M2 = stats.M^2
                    ordered = abs(stats.M) >= phase_threshold
                    ordered_visits += ordered
                    if !isnothing(previous_ordered) && ordered != previous_ordered
                        phase_transitions += 1
                    end
                    previous_ordered = ordered
                    ordered_fraction = ordered_visits / sample
                    low_M = center == firstindex(state.fields) ? stats.M :
                            magnetization(state.fields[firstindex(state.fields)])
                    high_M = center == lastindex(state.fields) ? stats.M :
                             magnetization(state.fields[lastindex(state.fields)])
                    @printf(stats_io, "%d,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g\n",
                            state.sweeps, stats.M, M2, M2^2, stats.Q, stats.G,
                            interval_acceptance)
                    diag_values = vcat(
                        [state.sweeps],
                        acceptance_rates(state.hmc_accepts, state.hmc_attempts),
                        acceptance_rates(state.swap_accepts, state.swap_attempts),
                        [sum(state.round_trips), stats.M, abs(stats.M), Int(ordered),
                         ordered_fraction, phase_transitions,
                         state.walker_ids[firstindex(state.fields)],
                         state.walker_ids[center], state.walker_ids[lastindex(state.fields)],
                         low_M, high_M],
                    )
                    println(diag_io, join(diag_values, ","))
                    if sample % 100 == 0
                        flush(stats_io); flush(diag_io)
                        swap_rates = acceptance_rates(state.swap_accepts, state.swap_attempts)
                        @printf("samples_completed=%d min_swap_acceptance=%.3f ordered_fraction=%.4f phase_transitions=%d round_trips=%d\n",
                                sample, minimum(swap_rates), ordered_fraction,
                                phase_transitions, sum(state.round_trips))
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
