# scripts/test_hmc.jl
# Four correctness checks for the HMC implementation.
# Usage: julia --project=. scripts/test_hmc.jl

cd(@__DIR__)
using Printf
using Random

const L         = 6
const FloatType = Float64
const ArrayType = Array
const cpu       = true
const λ         = FloatType(4.0)
const T         = FloatType(1.0)
const Z         = FloatType(1.0)
const n_lf      = 10
const ε         = FloatType(0.1)

include("../src/simulation.jl")

Random.seed!(42)

n_pass = Ref(0)
n_fail = Ref(0)

function report(name, passed, detail)
    tag = passed ? "PASS" : "FAIL"
    @printf("%s  %-30s  %s\n", tag, name, detail)
    passed ? (n_pass[] += 1) : (n_fail[] += 1)
end

# Test 1 — Force finite-difference check
# Verifies F(x) = -δH/δφ(x) via central differences at every site.
let
    ϕ = randn(L, L, L)
    m²_test = FloatType(-2.28587)
    F = similar(ϕ)
    compute_force!(F, ϕ, m²_test, Z)

    δ = 1e-5
    max_rel_err = 0.0
    for x3 in 1:L, x2 in 1:L, x1 in 1:L
        ϕp = copy(ϕ); ϕp[x1,x2,x3] += δ
        ϕm = copy(ϕ); ϕm[x1,x2,x3] -= δ
        F_fd = -(calc_total_energy(ϕp, m²_test, Z) - calc_total_energy(ϕm, m²_test, Z)) / (2δ)
        rel_err = abs(F[x1,x2,x3] - F_fd) / (abs(F[x1,x2,x3]) + 1e-10)
        max_rel_err = max(max_rel_err, rel_err)
    end
    report("Force FD check", max_rel_err < 1e-4, @sprintf("max_rel_err=%.2e", max_rel_err))
end

# Test 2 — Sufficient statistics and the exact reweighting action difference
let
    ϕ = randn(L, L, L)
    stats = sufficient_statistics(ϕ)
    M_brute = sum(ϕ) / L^3
    Q_brute = sum(abs2, ϕ)
    G_brute = 0.0
    for x3 in 1:L, x2 in 1:L, x1 in 1:L
        G_brute += (ϕ[NNp(x1), x2, x3] - ϕ[x1, x2, x3])^2
        G_brute += (ϕ[x1, NNp(x2), x3] - ϕ[x1, x2, x3])^2
        G_brute += (ϕ[x1, x2, NNp(x3)] - ϕ[x1, x2, x3])^2
    end
    stats_error = maximum(abs.((stats.M - M_brute, stats.Q - Q_brute, stats.G - G_brute)))

    source_m2, source_Z = -2.31, 0.83
    target_m2, target_Z = -2.07, -0.14
    direct = calc_total_energy(ϕ, target_m2, target_Z) -
             calc_total_energy(ϕ, source_m2, source_Z)
    sufficient = 0.5 * (target_m2 - source_m2) * stats.Q +
                 0.5 * (target_Z - source_Z) * stats.G
    action_error = abs(direct - sufficient)
    passed = stats_error < 1e-11 && action_error < 1e-10 * max(1.0, abs(direct))
    report("Reweight sufficient statistics", passed,
           @sprintf("stats_err=%.2e  action_err=%.2e", stats_error, action_error))
end

# Test 3 — Energy conservation
# Leapfrog with small ε should conserve the Hamiltonian to O(ε²).
let
    ϕ = randn(L, L, L)
    m²_test = FloatType(-2.28587)
    π_field = randn(L, L, L)

    H_old = calc_hamiltonian(ϕ, π_field, m²_test, Z)

    ϕ_test = copy(ϕ)
    π_test = copy(π_field)
    leapfrog!(ϕ_test, π_test, m²_test, Z, FloatType(0.01), 50)

    H_new = calc_hamiltonian(ϕ_test, π_test, m²_test, Z)
    rel_err = abs(H_new - H_old) / abs(H_old)
    report("Energy conservation", rel_err < 2e-3, @sprintf("|ΔH|/|H|=%.2e", rel_err))
end

# Test 4 — Reversibility
# Forward trajectory followed by momentum negation and backward trajectory
# must return to the starting configuration.
let
    ϕ = randn(L, L, L)
    m²_test = FloatType(-2.28587)
    π_field = randn(L, L, L)

    ϕ_initial = copy(ϕ)
    ϕ_test = copy(ϕ)
    π_test = copy(π_field)

    leapfrog!(ϕ_test, π_test, m²_test, Z, FloatType(0.1), n_lf)
    π_test .*= -1
    leapfrog!(ϕ_test, π_test, m²_test, Z, FloatType(0.1), n_lf)

    max_diff = maximum(abs.(ϕ_test .- ϕ_initial))
    report("Reversibility", max_diff < 1e-5, @sprintf("max|Δϕ|=%.2e", max_diff))
end

# Test 5 — Acceptance rate sanity
# 200 HMC trajectories near the phase transition should give a reasonable acceptance rate.
let
    Random.seed!(3)
    ϕ = randn(L, L, L)
    m²_test = FloatType(-2.28587)
    n_traj = 200
    n_acc = 0
    for _ in 1:n_traj
        accepted, _ = hmc_step!(ϕ, m²_test, Z, FloatType(0.1), 10)
        n_acc += accepted
    end
    acc_rate = n_acc / n_traj
    report("Acceptance rate sanity", 0.5 < acc_rate < 0.99, @sprintf("rate=%.3f", acc_rate))
end

@printf("\n%d passed, %d failed\n", n_pass[], n_fail[])
n_fail[] > 0 && exit(1)
