#!/usr/bin/env julia

"""
Benchmark HMC `(epsilon, n_lf)` candidates for one lattice size on CUDA.

Several independent chains are advanced in one CUDA batch.  Half start in the
disordered basin and half in the ordered basin.  For every candidate `n_lf`, a
short epsilon grid locates acceptance near the requested target, followed by a
longer run that measures autocorrelation of M^2 and Q.  The reported efficiency
is effective samples per 1000 force evaluations, so it is portable between GPUs.
"""

using ArgParse
using CUDA
using LinearAlgebra
using Printf
using Random
using Statistics

function parse_cli()
    settings = ArgParseSettings(
        description="Benchmark HMC defaults at one (L, Z, m2) point on CUDA",
    )
    @add_arg_table settings begin
        "L"
            arg_type = Int
            required = true
        "--Z"
            arg_type = Float64
            required = true
        "--mass"
            arg_type = Float64
            required = true
        "--output"
            arg_type = String
            required = true
        "--nlfs"
            arg_type = String
            default = "4,6,8,12,16,24,32"
        "--eps-center-L12"
            help = "epsilon grid center at L=12, scaled as L^(-3/4)"
            arg_type = Float64
            default = 0.060
        "--eps-factors"
            arg_type = String
            default = "0.25,0.35,0.50,0.65,0.80,1.00,1.20"
        "--target-acceptance"
            arg_type = Float64
            default = 0.75
        "--base-eps-factor"
            help = "independent conservative epsilon factor used only for base warmup"
            arg_type = Float64
            default = 0.25
        "--base-warmup"
            help = "safe HMC trajectories before candidate copies are made"
            arg_type = Int
            default = 2000
        "--candidate-warmup"
            arg_type = Int
            default = 500
        "--probe-steps"
            arg_type = Int
            default = 500
        "--samples"
            arg_type = Int
            default = 8000
        "--chains"
            help = "independent chains in the CUDA batch (must be even)"
            arg_type = Int
            default = 4
        "--seed"
            arg_type = Int
            default = 20260813
    end
    return parse_args(settings)
end

parse_ints(text) = parse.(Int, strip.(split(text, ',')))
parse_floats(text) = parse.(Float64, strip.(split(text, ',')))

const pa = parse_cli()
const cpu = false
const FloatType = Float64
const ArrayType = CuArray
const L = pa["L"]
const λ = FloatType(4.0)
const T = FloatType(1.0)
const Z = FloatType(pa["Z"])
const m² = FloatType(pa["mass"])

include(joinpath(@__DIR__, "..", "src", "simulation.jl"))

function initial_batch(chains::Int)
    iseven(chains) || error("--chains must be even")
    chains >= 2 || error("--chains must be at least 2")
    host = Array{FloatType}(undef, L, L, L, chains)
    half = chains ÷ 2
    amplitude = sqrt(max(-m² / λ, zero(FloatType)))
    for chain in 1:chains
        if chain <= half
            host[:, :, :, chain] .= FloatType(0.05) .* randn(FloatType, L, L, L)
        else
            sign = isodd(chain) ? one(FloatType) : -one(FloatType)
            host[:, :, :, chain] .=
                sign * amplitude .+ FloatType(0.05) .* randn(FloatType, L, L, L)
        end
    end
    return CuArray(host)
end

function evolve!(fields, workspace, eps, nlf, steps; observe=false)
    chains = size(fields, 4)
    accepts = zeros(Int, chains)
    m2_values = observe ? Matrix{Float64}(undef, steps, chains) : zeros(0, 0)
    q_values = observe ? Matrix{Float64}(undef, steps, chains) : zeros(0, 0)
    reshaped = reshape(fields, L^3, chains)
    CUDA.synchronize()
    started = time_ns()
    for step in 1:steps
        accepted, _ = hmc_step_batched!(fields, Z, eps, nlf, workspace)
        accepts .+= accepted
        if observe
            magnetizations = vec(Array(sum(reshaped; dims=1))) ./ L^3
            quadratic = vec(Array(sum(abs2, reshaped; dims=1))) ./ L^3
            m2_values[step, :] .= magnetizations .^ 2
            q_values[step, :] .= quadratic
        end
    end
    CUDA.synchronize()
    seconds = (time_ns() - started) / 1e9
    return (acceptance=accepts ./ steps, seconds, m2_values, q_values)
end

function positive_window_iat(values)
    x = Float64.(values)
    count = length(x)
    centered = x .- mean(x)
    variance = sum(abs2, centered) / count
    (!isfinite(variance) || variance <= 0) && return 0.5
    result = 0.5
    for lag in 1:min(count ÷ 2, 3000)
        covariance = dot(view(centered, 1:(count-lag)),
                         view(centered, (lag+1):count)) / (count-lag)
        rho = covariance / variance
        (!isfinite(rho) || rho <= 0) && break
        result += rho
    end
    return max(0.5, result)
end

function candidate_score(m2_iats, q_iats, nlf)
    # A robust typical-chain score.  Each chain is limited by its slower observable.
    limiting_iats = max.(m2_iats, q_iats)
    robust_iat = median(limiting_iats)
    return 500.0 / (nlf * robust_iat), robust_iat
end

function main()
    CUDA.functional() || error("CUDA is not functional")
    pa["samples"] >= 1000 || error("--samples must be at least 1000")
    Random.seed!(pa["seed"] + L)
    CUDA.seed!(pa["seed"] + L)

    nlfs = parse_ints(pa["nlfs"])
    factors = parse_floats(pa["eps-factors"])
    all(nlfs .> 0) || error("all --nlfs values must be positive")
    all(factors .> 0) || error("all --eps-factors values must be positive")
    center = pa["eps-center-L12"] * (12 / Float64(L))^0.75
    masses = fill(m², pa["chains"])

    base = initial_batch(pa["chains"])
    base_workspace = make_batched_workspace(base, masses)
    pa["base-eps-factor"] > 0 || error("--base-eps-factor must be positive")
    safe_eps = center * pa["base-eps-factor"]
    warm = evolve!(base, base_workspace, safe_eps, 8, pa["base-warmup"])
    @printf(
        "L=%d device=%s base_eps=%.8f base_acceptance=%s\n",
        L, CUDA.name(CUDA.device()), safe_eps,
        join((@sprintf("%.3f", value) for value in warm.acceptance), ";"),
    )

    header = [
        "L", "Z", "m2", "n_lf", "eps", "tau", "probe_acceptance",
        "acceptance_mean", "acceptance_min", "acceptance_max",
        "iat_M2_median", "iat_Q_median", "robust_limiting_iat",
        "ess_per_1000_force", "seconds", "samples", "chains",
    ]
    rows = NamedTuple[]

    for nlf in nlfs
        probes = NamedTuple[]
        for factor in factors
            eps = center * factor
            fields = copy(base)
            workspace = make_batched_workspace(fields, masses)
            result = evolve!(fields, workspace, eps, nlf, pa["probe-steps"])
            mean_acceptance = mean(result.acceptance)
            push!(probes, (; eps, mean_acceptance, minimum_acceptance=minimum(result.acceptance)))
            @printf(
                "PROBE L=%d nlf=%d eps=%.8f acceptance=%.3f min=%.3f\n",
                L, nlf, eps, mean_acceptance, minimum(result.acceptance),
            )
        end
        viable = filter(p -> p.minimum_acceptance >= 0.50, probes)
        pool = isempty(viable) ? probes : viable
        chosen = sort(pool; by=p -> abs(p.mean_acceptance - pa["target-acceptance"]))[1]

        fields = copy(base)
        workspace = make_batched_workspace(fields, masses)
        evolve!(fields, workspace, chosen.eps, nlf, pa["candidate-warmup"])
        result = evolve!(fields, workspace, chosen.eps, nlf, pa["samples"]; observe=true)
        m2_iats = [positive_window_iat(view(result.m2_values, :, chain))
                   for chain in 1:pa["chains"]]
        q_iats = [positive_window_iat(view(result.q_values, :, chain))
                  for chain in 1:pa["chains"]]
        score, robust_iat = candidate_score(m2_iats, q_iats, nlf)
        row = (;
            L, Z=Float64(Z), m2=Float64(m²), n_lf=nlf, eps=chosen.eps,
            tau=chosen.eps*nlf, probe_acceptance=chosen.mean_acceptance,
            acceptance_mean=mean(result.acceptance),
            acceptance_min=minimum(result.acceptance),
            acceptance_max=maximum(result.acceptance),
            iat_M2_median=median(m2_iats), iat_Q_median=median(q_iats),
            robust_limiting_iat=robust_iat, ess_per_1000_force=score,
            seconds=result.seconds, samples=pa["samples"], chains=pa["chains"],
        )
        push!(rows, row)
        @printf(
            "RESULT L=%d nlf=%d eps=%.8f acc=%.3f [%.3f,%.3f] iatM2=%.1f iatQ=%.1f score=%.5f\n",
            L, nlf, chosen.eps, row.acceptance_mean, row.acceptance_min,
            row.acceptance_max, row.iat_M2_median, row.iat_Q_median, score,
        )
        flush(stdout)
    end

    eligible = filter(r -> r.acceptance_min >= 0.55 && r.acceptance_mean >= 0.60, rows)
    best = argmax(r -> r.ess_per_1000_force, isempty(eligible) ? rows : eligible)
    @printf(
        "BEST L=%d eps=%.10g n_lf=%d acceptance=%.3f score=%.6f\n",
        L, best.eps, best.n_lf, best.acceptance_mean, best.ess_per_1000_force,
    )

    mkpath(dirname(pa["output"]))
    open(pa["output"], "w") do io
        println(io, join(header, ','))
        for row in rows
            println(io, join((getproperty(row, Symbol(name)) for name in header), ','))
        end
    end
end

main()
