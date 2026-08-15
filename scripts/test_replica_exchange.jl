#!/usr/bin/env julia

cd(@__DIR__)
using Printf
using Random

const L         = 4
const FloatType = Float64
const ArrayType = Array
const cpu       = true
const λ         = 4.0
const T         = 1.0
const Z         = 1.0
const n_lf      = 4
const ε         = 0.02

include("../src/simulation.jl")
include("../src/replica_exchange.jl")

passed = Ref(0)
failed = Ref(0)
function report(name, ok, detail="")
    @printf("%s  %-32s %s\n", ok ? "PASS" : "FAIL", name, detail)
    ok ? (passed[] += 1) : (failed[] += 1)
end

let
    ladder = mass_ladder(-2.25, 5, 0.4)
    report("Centered mass ladder",
           ladder == [-2.45, -2.35, -2.25, -2.15, -2.05], repr(ladder))
    invalid = 0
    for (n, span) in ((2, 0.2), (4, 0.2), (3, 0.0))
        try
            mass_ladder(-2.25, n, span)
        catch exception
            exception isa ArgumentError && (invalid += 1)
        end
    end
    report("Mass ladder validation", invalid == 3, "rejected=$(invalid)/3")
end

let
    fields = [zeros(L, L, L) for _ in 1:3]
    state = ReplicaExchangeState(fields, mass_ladder(-2.25, 3, 0.2);
                                 walker_stage=[1, 2, 1], round_trips=[0, 0, 2],
                                 sweeps=11)
    low, high = walker_endpoint_coverage(state)
    report("Exchange-round denominator", exchange_rounds(state, 2) == 5)
    report("Per-walker endpoint coverage",
           low == [true, true, true] && high == [false, true, true],
           "low=$(low) high=$(high)")
end

let
    first = randn(L, L, L)
    second = randn(L, L, L)
    m1, m2 = -2.4, -2.1
    direct = calc_total_energy(second, m1, Z) + calc_total_energy(first, m2, Z) -
             calc_total_energy(first, m1, Z) - calc_total_energy(second, m2, Z)
    sufficient = swap_action_difference(m1, m2, quadratic_statistic(first),
                                        quadratic_statistic(second))
    err = abs(direct - sufficient)
    report("Exact swap action", err < 1e-10 * max(1.0, abs(direct)), @sprintf("err=%.2e", err))
end

let
    low_q = fill(0.125, L, L, L)  # Q = 1
    high_q = fill(0.25, L, L, L)  # Q = 4
    state = ReplicaExchangeState([low_q, high_q], [-2.0, -1.0])
    accepted, delta = attempt_replica_swap!(state, 1; q_left=1.0, q_right=4.0,
                                            rng=MersenneTwister(1))
    report("Accepted reference swap",
           accepted && state.fields[1] === high_q && state.walker_ids == [2, 1],
           "delta=$(delta)")

    first, second = fill(1.0, 1, 1, 1), fill(2.0, 1, 1, 1)
    rejected = ReplicaExchangeState([first, second], [-2.0, -1.0])
    accepted2, delta2 = attempt_replica_swap!(rejected, 1; q_left=10_000.0, q_right=0.0,
                                              rng=MersenneTwister(2))
    report("Rejected swap unchanged",
           !accepted2 && rejected.fields[1] === first && rejected.walker_ids == [1, 2],
           "delta=$(delta2)")
end

let
    Random.seed!(7)
    fields = [randn(L, L, L) for _ in 1:3]
    state = ReplicaExchangeState(fields, mass_ladder(-2.25, 3, 0.2))
    replica_exchange!(state, 2, Z, ε, n_lf; swap_every=1)
    report("Alternating exchange sweeps",
           state.sweeps == 2 && state.swap_attempts == [1, 1] &&
           state.hmc_attempts == [2, 2, 2],
           "swap_attempts=$(state.swap_attempts)")
    reset_replica_diagnostics!(state)
    report("Discarded-stage diagnostic reset",
           state.sweeps == 0 && state.walker_ids == [1, 2, 3] &&
           state.walker_stage == [1, 0, 0] && all(==(0), state.hmc_attempts) &&
           all(==(0), state.hmc_accepts) && all(==(0), state.swap_attempts) &&
           all(==(0), state.swap_accepts) && all(==(0), state.round_trips))
end

@printf("\n%d passed, %d failed\n", passed[], failed[])
failed[] > 0 && exit(1)
