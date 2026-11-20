#!/usr/bin/env julia
# GPU checks of the CV bias path in src/quadratic_cv.jl (device-side force with cached
# FFT plans, M² fast path, per-replica ε, masked accept).  Needs a GPU.
#   julia --project=. scripts/test_quadratic_cv_gpu.jl
cd(@__DIR__)
using CUDA
using FFTW
using Printf
using Random
CUDA.functional() || error("CUDA is not functional")

const L = 8
const FloatType = Float32
const ArrayType = CuArray
const cpu = false
const λ = FloatType(4)
const T = FloatType(1)
include("../src/simulation.jl")
include("structure_factor_observables.jl")
include("../src/quadratic_cv.jl")

passed = Ref(0); failed = Ref(0)
report(name, ok, detail="") = (@printf("%s  %-44s %s\n", ok ? "PASS" : "FAIL", name, detail);
                               ok ? (passed[] += 1) : (failed[] += 1))
Random.seed!(5); CUDA.seed!(5)
n = 6
host = 0.4 .* randn(L, L, L, n) .+ 0.3
batch = CuArray(FloatType.(host))
centers = collect(range(0.02, 0.3; length=n)); kappas = fill(5000.0, n)
V = L^3

# Host reference of the bias force −κ(s−c)·(2/V)·Re IFFT(w φ̃), in Float64.
function bias_reference(cv, host)
    w = Float64.(Array(cv.weights))
    out = similar(host); s = zeros(n)
    for r in 1:n
        φk = fft(host[:, :, :, r])
        s[r] = sum(w .* abs2.(φk)) / V^2
        out[:, :, :, r] = -kappas[r] * (s[r] - centers[r]) * (2 / V) .* real.(ifft(w .* φk))
    end
    return out, s
end

for kind in ("M2", "shell")
    cv = make_cv(L, kind; shell_target=1.0)
    ws = make_cv_workspace(batch, fill(-2.0, n))
    Fphys = similar(batch); F = similar(batch)
    compute_force_batched!(Fphys, ws.laplacian, batch, ws.base.device_masses, FloatType(-1), ws.base)
    cv_force!(F, batch, ws, FloatType(-1), cv, centers, kappas)
    ref, sref = bias_reference(cv, Float64.(host))
    bias = Array(F) .- Array(Fphys)
    err = maximum(abs.(bias .- ref)) / max(maximum(abs.(ref)), 1e-12)
    report("$kind bias force == host reference", err < 2e-4, @sprintf("rel_err=%.2e", err))
    sv = cv_values(cv, batch)
    report("$kind cv_values == host reference", maximum(abs.(sv .- sref) ./ max.(sref, 1e-12)) < 1e-4,
           @sprintf("max_rel=%.2e", maximum(abs.(sv .- sref) ./ max.(sref, 1e-12))))
    # second call reuses the cached buffers and must give the same force
    F2 = similar(batch)
    cv_force!(F2, batch, ws, FloatType(-1), cv, centers, kappas)
    report("$kind cached second call identical", Array(F2) == Array(F))
end

# Per-replica ε: a uniform vector must reproduce the scalar trajectory exactly.
cv = make_cv(L, "shell"; shell_target=1.0)
b1 = copy(batch); b2 = copy(batch)
ws1 = make_cv_workspace(b1, fill(-2.0, n)); ws2 = make_cv_workspace(b2, fill(-2.0, n))
CUDA.seed!(11); a1, d1 = hmc_step_cv!(b1, FloatType(-1), 0.02, 10, ws1, cv, centers, kappas; rng=MersenneTwister(3))
CUDA.seed!(11); a2, d2 = hmc_step_cv!(b2, FloatType(-1), fill(0.02, n), 10, ws2, cv, centers, kappas; rng=MersenneTwister(3))
report("uniform ε vector == scalar ε", Array(b1) == Array(b2) && d1 == d2,
       @sprintf("max|Δφ|=%.1e", maximum(abs.(Array(b1) .- Array(b2)))))

# Per-replica ε is exact per replica: replica r of a vector-ε step equals a scalar step
# with ε_r from the same fields and the same momenta (same CUDA seed).
eps = collect(range(0.002, 0.01; length=n))
bv = copy(batch); wsv = make_cv_workspace(bv, fill(-2.0, n))
CUDA.seed!(17); _, dHv = hmc_step_cv!(bv, FloatType(-1), eps, 20, wsv, cv, centers, kappas; rng=MersenneTwister(9))
for r in (1, n)
    bs = copy(batch); wss = make_cv_workspace(bs, fill(-2.0, n))
    CUDA.seed!(17); _, dHs = hmc_step_cv!(bs, FloatType(-1), eps[r], 20, wss, cv, centers, kappas; rng=MersenneTwister(9))
    # equal up to FMA-contraction differences between the two broadcast kernels
    report("vector ε replica $r == scalar ε_$r", isapprox(dHv[r], dHs[r]; rtol=1e-4, atol=1e-4) &&
           isapprox(Array(wsv.proposal)[:, :, :, r], Array(wss.proposal)[:, :, :, r]; rtol=1e-5),
           @sprintf("ΔH=%.4g vs %.4g", dHv[r], dHs[r]))
end

# Masked accept copies exactly the accepted replicas.
f = CuArray(zeros(FloatType, L, L, L, n)); p = CuArray(ones(FloatType, L, L, L, n))
acc = [isodd(r) for r in 1:n]
_accept_copy!(f, p, acc)
got = [all(Array(f)[:, :, :, r] .== (acc[r] ? 1 : 0)) for r in 1:n]
report("masked accept copies accepted replicas only", all(got))

@printf("\n%d passed, %d failed\n", passed[], failed[])
failed[] == 0 ? println("ALL PASS") : exit(1)
