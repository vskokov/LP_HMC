#!/usr/bin/env julia

# Cluster check for the CUDA sufficient-statistics path.
# Usage: julia --project=. scripts/test_reweight_stats_gpu.jl 6 --fp64

cd(@__DIR__)
using Printf

include("../src/modelA.jl")

function main()
    cpu && error("this check requires CUDA; omit --cpu")
    FloatType == Float64 || error("this check requires --fp64")

    ϕ = hotstart(L)
    stats = sufficient_statistics(ϕ)
    host = Array(ϕ)

    M_brute = sum(host) / L^3
    Q_brute = sum(abs2, host)
    G_brute = 0.0
    for x3 in 1:L, x2 in 1:L, x1 in 1:L
        value = host[x1, x2, x3]
        G_brute += (host[NNp(x1), x2, x3] - value)^2
        G_brute += (host[x1, NNp(x2), x3] - value)^2
        G_brute += (host[x1, x2, NNp(x3)] - value)^2
    end

    source_m2, source_Z = -2.31, 0.83
    target_m2, target_Z = -2.07, -0.14
    direct = Float64(calc_total_energy(ϕ, target_m2, target_Z) -
                     calc_total_energy(ϕ, source_m2, source_Z))
    sufficient = 0.5 * (target_m2 - source_m2) * stats.Q +
                 0.5 * (target_Z - source_Z) * stats.G

    stats_error = maximum(abs.((stats.M - M_brute, stats.Q - Q_brute, stats.G - G_brute)))
    action_error = abs(direct - sufficient)
    tolerance = 1e-10 * max(1.0, Q_brute, G_brute, abs(direct))

    ladder = mass_ladder(FloatType(source_m2), 3, FloatType(0.2))
    first, second, third = copy(ϕ), copy(ϕ), copy(ϕ)
    exchange = ReplicaExchangeState([first, second, third], ladder)
    swap_accepted, _ = attempt_replica_swap!(exchange, 1; q_left=1.0, q_right=4.0)
    reference_swap_ok = swap_accepted && exchange.fields[1] === second &&
                        exchange.fields[2] === first && exchange.walker_ids == [2, 1, 3]

    passed = stats_error <= tolerance && action_error <= tolerance && reference_swap_ok

    @printf("%s  CUDA reweight/exchange  stats_err=%.3e action_err=%.3e reference_swap=%s tolerance=%.3e\n",
            passed ? "PASS" : "FAIL", stats_error, action_error, reference_swap_ok, tolerance)
    passed || exit(1)
end

main()
