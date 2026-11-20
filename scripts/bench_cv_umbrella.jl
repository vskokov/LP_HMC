#!/usr/bin/env julia
# GPU timing breakdown of one CV-umbrella sweep (host-overhead diagnosis).
#   BENCH_L=24 BENCH_NW=112 BENCH_KIND=shell BENCH_NLF=43 julia --project=. scripts/bench_cv_umbrella.jl
cd(@__DIR__)
using Printf
using Random
using Statistics

const L = parse(Int, get(ENV, "BENCH_L", "24"))
const cpu = false
const FloatType = Float32
const λ = FloatType(4.0)
const T = FloatType(1.0)
const NW = parse(Int, get(ENV, "BENCH_NW", "112"))
const KIND = get(ENV, "BENCH_KIND", "shell")
const NLF = parse(Int, get(ENV, "BENCH_NLF", "43"))
const ε = FloatType(0.02)

include("../src/simulation.jl")
include("structure_factor_observables.jl")
include("../src/quadratic_cv.jl")

CV = make_cv(L, KIND; shell_target=1.0)
centers = collect(range(0, 0.5; length=NW)); kappas = fill(20000.0 * (L / 12)^3, NW)
batch = CuArray(FloatType.(0.3 .* randn(L, L, L, NW)))
ws = make_cv_workspace(batch, fill(-2.0, NW))
F = similar(batch)

function timeit(f, n)
    f(); CUDA.synchronize()                     # compile / warm up
    t = time_ns()
    for _ in 1:n
        f()
    end
    CUDA.synchronize()
    return (time_ns() - t) / n / 1e6            # ms per call
end

@printf("L=%d NW=%d kind=%s nlf=%d sites=%d device=%s host=%s\n", L, NW, KIND, NLF,
        length(batch), CUDA.name(CUDA.device()), gethostname())
r(name, ms) = @printf("  %-40s %9.3f ms\n", name, ms)
r("physical force (batched kernels)", timeit(() -> compute_force_batched!(F, ws.laplacian, batch, ws.base.device_masses, FloatType(-1), ws.base), 50))
r("fft3 (plan each call)", timeit(() -> _fft3(batch), 20))
p = plan_fft(batch .+ 0im, (1, 2, 3)); bc = batch .+ 0im
r("plan_fft creation", timeit(() -> plan_fft(bc, (1, 2, 3)), 5))
r("fft3 with cached plan", timeit(() -> p * bc, 20))
r("cv_values_and_gradient!", timeit(() -> cv_values_and_gradient!(ws.grad, CV, batch), 20))
r("cv_force! (phys + bias)", timeit(() -> cv_force!(F, batch, ws, FloatType(-1), CV, centers, kappas), 20))
r("cv_hamiltonians", timeit(() -> cv_hamiltonians(batch, ws.momentum, ws, FloatType(-1), CV, centers, kappas), 20))
r("cv_values", timeit(() -> cv_values(CV, batch), 20))
r("hmc_step_cv! (one sweep's HMC)", timeit(() -> hmc_step_cv!(batch, FloatType(-1), ε, NLF, ws, CV, centers, kappas), 3))
buf = similar(batch, L, L, L)
r("swap_slices! x NW/2", timeit(() -> foreach(i -> swap_slices!(batch, i, i + 1, buf), 1:2:NW-1), 5))
r("shell_observables", timeit(() -> shell_observables(CV, batch), 3))
r("sufficient_statistics_batched", timeit(() -> sufficient_statistics_batched(batch, ws.base), 5))
