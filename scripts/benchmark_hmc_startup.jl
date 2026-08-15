#!/usr/bin/env julia

cd(@__DIR__)

using ArgParse
using CUDA
using Distributions
using Printf
using Random
using Statistics

function arguments()
    settings = ArgParseSettings()
    @add_arg_table settings begin
        "--Z"
            arg_type = Float64
            default = -0.6
        "--mass"
            arg_type = Float64
            default = -1.85764
        "--eps-values"
            help = "comma-separated startup step sizes"
            default = "0.006,0.008,0.01,0.012,0.015,0.02"
        "--trajectory-length"
            help = "target eps*n_lf; n_lf is rounded separately for each eps"
            arg_type = Float64
            default = 0.24
        "--fixed-n-lf"
            help = "fixed leapfrog count for ladder screening (zero uses trajectory length)"
            arg_type = Int
            default = 0
        "--min-acceptance"
            help = "minimum per-slot interval acceptance required in every block and phase"
            arg_type = Float64
            default = 0.7
        "--sweeps"
            help = "cold-start sweeps per phase and candidate"
            arg_type = Int
            default = 0
        "--block-size"
            help = "reporting interval; zero means L^2"
            arg_type = Int
            default = 0
        "--tempering-replicas"
            arg_type = Int
            default = 17
        "--mass-span"
            arg_type = Float64
            default = 0.6
        "--swap-every"
            arg_type = Int
            default = 5
        "--rng"
            arg_type = Int
            default = 1729
        "--fp64"
            action = :store_true
        "--cpu"
            action = :store_true
        "--output"
            default = ""
        "size"
            arg_type = Int
            required = true
    end
    return parse_args(settings)
end

const options = arguments()
const L = options["size"]
const cpu = options["cpu"]
const FloatType = options["fp64"] ? Float64 : Float32
const ArrayType = cpu ? Array : CuArray
const λ = FloatType(4.0)
const T = FloatType(1.0)
const Z = FloatType(options["Z"])

include("../src/simulation.jl")
include("../src/replica_exchange.jl")

function parse_eps_values(text)
    values = parse.(Float64, strip.(split(text, ',')))
    isempty(values) && error("--eps-values cannot be empty")
    all(isfinite(value) && value > 0 for value in values) ||
        error("all --eps-values must be finite and positive")
    return values
end

function phase_field(n, mass, phase, seed_value)
    noise = ArrayType(randn(FloatType, n, n, n))
    if phase == "disordered"
        return FloatType(0.05) .* noise
    end
    sign = isodd(seed_value) ? one(FloatType) : -one(FloatType)
    amplitude = sqrt(max(-FloatType(mass) / λ, zero(FloatType)))
    return fill!(similar(noise), sign * amplitude) .+ FloatType(0.05) .* noise
end

magnetization(field) = Float64(sum(field)) / L^3
host_batch(state) = is_batched(state) ? Array(state.batch) :
                    cat((Array(field) for field in state.fields)...; dims=4)

function make_state(masses, phase, seed_value)
    fields = [phase_field(L, mass, phase, seed_value) for mass in masses]
    if cpu
        return ReplicaExchangeState(fields, masses)
    end
    batch = cat(fields...; dims=4)
    views = [@view batch[:, :, :, slot] for slot in eachindex(masses)]
    return ReplicaExchangeState(views, masses; batched=true, field_batch=batch)
end

function main()
    replicas = options["tempering-replicas"]
    replicas >= 3 && isodd(replicas) ||
        error("--tempering-replicas must be odd and at least 3")
    options["mass-span"] > 0 || error("--mass-span must be positive")
    options["swap-every"] > 0 || error("--swap-every must be positive")
    sweeps = options["sweeps"] == 0 ? L^3 : options["sweeps"]
    block_size = options["block-size"] == 0 ? L^2 : options["block-size"]
    sweeps > 0 && block_size > 0 || error("sweeps and block size must be positive")
    tau = options["trajectory-length"]
    tau > 0 || error("--trajectory-length must be positive")
    0 <= options["min-acceptance"] <= 1 || error("--min-acceptance must be in [0,1]")
    eps_values = parse_eps_values(options["eps-values"])
    masses = FloatType.(mass_ladder(FloatType(options["mass"]), replicas,
                                    FloatType(options["mass-span"])))
    output = isempty(options["output"]) ?
        abspath("startup_hmc_L$(L).csv") : abspath(options["output"])
    mkpath(dirname(output))
    temporary = output * ".tmp.$(getpid())"
    screening = Dict{Float64,NamedTuple}()

    open(temporary, "w") do io
        println(io, "L,Z,m2,phase,epsilon,n_lf,trajectory_length,tempering_replicas," *
                    "mass_span,swap_every,block,sweeps," *
                    "acceptance_min,acceptance_mean,acceptance_max,zero_slots," *
                    "swap_acceptance_min,swap_acceptance_median,unused_edges," *
                    "M_low,M_target,M_high,rms_displacement,round_trips," *
                    "exchange_rounds,round_trip_walker_fraction," *
                    "low_endpoint_walker_fraction,high_endpoint_walker_fraction,seconds")
        for epsilon64 in eps_values,
            (phase_index, phase) in enumerate(("disordered", "ordered"))
            # Common random numbers make candidate comparisons sensitive to the
            # integrator rather than to a luckier initial field or RNG stream.
            seed_value = options["rng"] + phase_index
            Random.seed!(seed_value)
            !cpu && CUDA.seed!(seed_value)
            state = make_state(masses, phase, seed_value)
            initial = host_batch(state)
            leapfrog_steps = options["fixed-n-lf"] > 0 ? options["fixed-n-lf"] :
                               max(1, round(Int, tau / epsilon64))
            candidate_worst = get(screening, epsilon64,
                                  (minimum=1.0, zero_slots=0,
                                   n_lf=leapfrog_steps))
            epsilon = FloatType(epsilon64)
            completed = 0
            block_index = 0
            while completed < sweeps
                block_sweeps = min(block_size, sweeps - completed)
                previous_accepts = copy(state.hmc_accepts)
                previous_attempts = copy(state.hmc_attempts)
                elapsed = @elapsed replica_exchange!(
                    state, block_sweeps, Z, epsilon, leapfrog_steps;
                    swap_every=options["swap-every"]
                )
                rates = acceptance_rates(state.hmc_accepts .- previous_accepts,
                                         state.hmc_attempts .- previous_attempts)
                candidate_worst = (
                    minimum=min(candidate_worst.minimum, minimum(rates)),
                    zero_slots=candidate_worst.zero_slots + count(==(0.0), rates),
                    n_lf=leapfrog_steps,
                )
                screening[epsilon64] = candidate_worst
                completed += block_sweeps
                block_index += 1
                center = target_slot(state)
                current = host_batch(state)
                rms = sqrt(sum(abs2, current .- initial) / length(initial))
                swap_rates = acceptance_rates(state.swap_accepts, state.swap_attempts)
                low_coverage, high_coverage = walker_endpoint_coverage(state)
                values = (
                    L, Float64(Z), options["mass"], phase, epsilon64,
                    leapfrog_steps, epsilon64 * leapfrog_steps, replicas,
                    options["mass-span"], options["swap-every"], block_index,
                    completed, minimum(rates), sum(rates) / length(rates),
                    maximum(rates), count(==(0.0), rates), minimum(swap_rates),
                    median(swap_rates), count(==(0), state.swap_accepts),
                    magnetization(state.fields[1]), magnetization(state.fields[center]),
                    magnetization(state.fields[end]), rms, sum(state.round_trips),
                    exchange_rounds(state, options["swap-every"]),
                    count(>(0), state.round_trips) / replicas,
                    count(low_coverage) / replicas, count(high_coverage) / replicas,
                    elapsed,
                )
                println(io, join(values, ','))
                flush(io)
                @printf("phase=%s eps=%.6g n_lf=%d sweeps=%d/%d acceptance[min/mean/max]=%.3f/%.3f/%.3f zero_slots=%d\n",
                        phase, epsilon64, leapfrog_steps, completed, sweeps,
                        minimum(rates), sum(rates) / length(rates), maximum(rates),
                        count(==(0.0), rates))
                flush(stdout)
            end
        end
    end
    mv(temporary, output; force=true)
    eligible = [(epsilon, result) for (epsilon, result) in screening
                if result.minimum >= options["min-acceptance"] && result.zero_slots == 0]
    if isempty(eligible)
        @printf("startup_screening=no_candidate_met_threshold min_acceptance=%.3f\n",
                options["min-acceptance"])
    else
        epsilon, result = first(sort(eligible; by=item -> (item[2].n_lf, -item[1])))
        @printf("startup_screening=recommended eps=%.10g n_lf=%d worst_acceptance=%.3f criterion=screening_only\n",
                epsilon, result.n_lf, result.minimum)
    end
    @printf("benchmark=%s\n", output)
end

main()
