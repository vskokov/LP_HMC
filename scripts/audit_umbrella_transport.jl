#!/usr/bin/env julia

"""Read-only continuation probe for effective umbrella-replica transport.

The source checkpoint is never modified. Set `UMBRELLA_CHECKPOINT` and optionally
`UMBRELLA_PROBE_SWEEPS`/`UMBRELLA_PROBE_LAGS`, then pass the normal model options.
When `--diagnostics=PATH` is supplied, one machine-readable CSV row is written.
"""

cd(@__DIR__)

using JLD2
using Printf
using Statistics

include("../src/modelA.jl")


function csv_cell(value)
    text = string(value)
    occursin(r"[,\"\n]", text) || return text
    return "\"" * replace(text, "\"" => "\"\"") * "\""
end


function mean_squared_displacement(positions, lag)
    total = 0.0
    count = 0
    for start in 1:(size(positions, 2) - lag), walker in axes(positions, 1)
        displacement = positions[walker, start + lag] - positions[walker, start]
        total += displacement^2
        count += 1
    end
    return total / count
end


function main()
    checkpoint = get(ENV, "UMBRELLA_CHECKPOINT", "")
    isempty(checkpoint) && error(
        "set UMBRELLA_CHECKPOINT to a schema-3 umbrella checkpoint"
    )
    probe_sweeps = parse(Int, get(ENV, "UMBRELLA_PROBE_SWEEPS", "5000"))
    probe_sweeps > 0 || error("UMBRELLA_PROBE_SWEEPS must be positive")
    lag_text = get(ENV, "UMBRELLA_PROBE_LAGS", "1,2,5,10,20,50,100,200,500,1000")
    lags = sort!(unique(parse.(Int, split(lag_text, ','))))
    all(lag -> 0 < lag <= probe_sweeps, lags) || error(
        "UMBRELLA_PROBE_LAGS must be positive and no larger than the probe"
    )

    payload = jldopen(checkpoint, "r") do file
        file["schema_version"] == 3 || error("umbrella checkpoint schema must be 3")
        file["sampler"] == "umbrella_exchange" || error(
            "checkpoint is not an umbrella-exchange checkpoint"
        )
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
        ([@view(batch[:, :, :, slot]) for slot in 1:nrep], true, batch)
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

    positions = Matrix{Int16}(undef, nrep, probe_sweeps + 1)
    positions[:, 1] .= invperm(state.walker_ids)
    swap_accepts_before = copy(state.swap_accepts)
    swap_attempts_before = copy(state.swap_attempts)
    hmc_accepts_before = copy(state.hmc_accepts)
    hmc_attempts_before = copy(state.hmc_attempts)
    round_trips_before = copy(state.round_trips)

    elapsed = @elapsed begin
        for step in 1:probe_sweeps
            replica_exchange_sweep!(state, Z, ε, n_lf; swap_every=swap_every)
            positions[:, step + 1] .= invperm(state.walker_ids)
        end
        !cpu && CUDA.synchronize()
    end

    deltas = diff(positions; dims=2)
    accepted_swaps = sum(state.swap_accepts .- swap_accepts_before)
    swap_attempts = sum(state.swap_attempts .- swap_attempts_before)
    hmc_accepts = sum(state.hmc_accepts .- hmc_accepts_before)
    hmc_attempts = sum(state.hmc_attempts .- hmc_attempts_before)
    walker_steps = count(!iszero, deltas)
    walker_steps == 2accepted_swaps || error(
        "walker-label movement disagrees with accepted-swap counters"
    )

    continuations = 0
    reversals = 0
    for walker in 1:nrep
        previous_direction = 0
        for step in 1:probe_sweeps
            direction = sign(deltas[walker, step])
            iszero(direction) && continue
            if !iszero(previous_direction)
                direction == previous_direction ? (continuations += 1) : (reversals += 1)
            end
            previous_direction = direction
        end
    end

    msd = Dict(lag => mean_squared_displacement(positions, lag) for lag in lags)
    spans = [maximum(@view positions[walker, :]) - minimum(@view positions[walker, :])
             for walker in 1:nrep]
    low_walkers = count(walker -> any(==(1), @view positions[walker, :]), 1:nrep)
    high_walkers = count(walker -> any(==(nrep), @view positions[walker, :]), 1:nrep)
    largest_lag = last(lags)
    diffusion_per_sweep = msd[largest_lag] / (2largest_lag)
    diffusion_per_lf_step = diffusion_per_sweep / n_lf
    diffusion_per_second = diffusion_per_sweep * probe_sweeps / elapsed
    swap_acceptance = accepted_swaps / swap_attempts
    hmc_acceptance = hmc_accepts / hmc_attempts
    directed_pairs = continuations + reversals
    continuation_fraction = iszero(directed_pairs) ? NaN : continuations / directed_pairs
    new_round_trips = sum(state.round_trips .- round_trips_before)

    println("checkpoint=", abspath(checkpoint))
    println("init_phase=", payload.init_phase)
    println("execution=", is_batched(state) ? "batched" : "serial")
    println("probe_sweeps=", probe_sweeps)
    println("elapsed_seconds=", elapsed)
    println("sweeps_per_second=", probe_sweeps / elapsed)
    println("accepted_swaps=", accepted_swaps)
    println("swap_acceptance=", swap_acceptance)
    println("hmc_acceptance=", hmc_acceptance)
    println("walker_steps=", walker_steps)
    println("direction_continuations=", continuations)
    println("direction_reversals=", reversals)
    println("continuation_fraction=", continuation_fraction)
    println("new_round_trips=", new_round_trips)
    println("walkers_visiting_low_endpoint=", low_walkers)
    println("walkers_visiting_high_endpoint=", high_walkers)
    println("median_walker_span=", median(spans))
    println("maximum_walker_span=", maximum(spans))
    for lag in lags
        println("lag=", lag, " mean_squared_displacement=", msd[lag])
    end
    println("diffusion_per_sweep=", diffusion_per_sweep)
    println("diffusion_per_lf_step=", diffusion_per_lf_step)
    println("diffusion_per_second=", diffusion_per_second)

    output = parsed_args["diagnostics"]
    if !isnothing(output)
        path = abspath(output)
        mkpath(dirname(path))
        columns = [
            "checkpoint", "init_phase", "L", "Z", "m2", "epsilon", "n_lf",
            "trajectory_length", "swap_every", "umbrella_replicas", "probe_sweeps",
            "elapsed_seconds", "sweeps_per_second", "hmc_acceptance",
            "swap_acceptance", "accepted_swaps", "walker_steps",
            "continuation_fraction", "new_round_trips", "walkers_visiting_low_endpoint",
            "walkers_visiting_high_endpoint", "median_walker_span",
            "maximum_walker_span", "largest_lag", "diffusion_per_sweep",
            "diffusion_per_lf_step", "diffusion_per_second",
        ]
        values = Any[
            abspath(checkpoint), payload.init_phase, L, Float64(Z), Float64(m²),
            Float64(ε), n_lf, Float64(ε) * n_lf, swap_every, nrep, probe_sweeps,
            elapsed, probe_sweeps / elapsed, hmc_acceptance, swap_acceptance,
            accepted_swaps, walker_steps, continuation_fraction, new_round_trips,
            low_walkers, high_walkers, median(spans), maximum(spans), largest_lag,
            diffusion_per_sweep, diffusion_per_lf_step, diffusion_per_second,
        ]
        for lag in lags
            push!(columns, "msd_lag_$(lag)")
            push!(values, msd[lag])
        end
        temporary = path * ".tmp"
        open(temporary, "w") do io
            println(io, join(columns, ','))
            println(io, join(csv_cell.(values), ','))
        end
        mv(temporary, path; force=true)
        println("diagnostics=", path)
    end
end


main()
