#!/usr/bin/env julia
# Read-only diagnostic of cv_umbrella checkpoints: per window (slot) the walker id, CV
# value, uniform magnetization M, Q/V and shell orientation d_eff — to look for a basin
# split hidden from the CV (e.g. M>0 / M<0 / M≈0 groups that never exchange).
#   DIAG_SHELL_Q=0.467911 julia --project=. scripts/diag_umbrella_checkpoint.jl ckpt1.jld2 [ckpt2 ...]
cd(@__DIR__)
using JLD2, Printf, Statistics

const PATHS = ARGS
const L = Int(load(PATHS[1], "L"))
const cpu = true
const FloatType = Float64
const λ = 4.0
const T = 1.0
include("../src/simulation.jl")
include("structure_factor_observables.jl")
include("../src/quadratic_cv.jl")

const CV = make_cv(L, "shell"; shell_target=parse(Float64, get(ENV, "DIAG_SHELL_Q", "1.0")))

for path in PATHS
    d = load(path)
    f = Float64.(d["fields"]); n = size(f, 4)
    s = cv_values(CV, f)
    obs = shell_observables(CV, f)
    M = [mean(view(f, :, :, :, r)) for r in 1:n]
    Q = [mean(abs2, view(f, :, :, :, r)) for r in 1:n]
    c = d["centers"]
    println("\n=== ", path)
    @printf("L=%d m2=%.4g phase=%s sweeps=%d windows=%d cv=%s\n", L, d["m2"], d["phase"], d["sweeps"], n, d["cv_label"])
    println(" slot walker   center      s(P*)       M        Q/V    d_eff   trips")
    for r in 1:n
        @printf("%5d %6d %9.4f %10.5f %8.4f %8.4f %6.2f %6d\n", r, d["walker"][r], c[r], s[r], M[r], Q[r],
                obs[r].d_eff, d["trips"][d["walker"][r]])
    end
    # summary: groups by sign/size of M
    groups = Dict("M>+0.2" => count(>(0.2), M), "M<-0.2" => count(<(-0.2), M),
                  "|M|<=0.2" => count(x -> abs(x) <= 0.2, M))
    println("groups: ", groups)
    # runs of consecutive slots with the same M class (a split ladder shows long blocks)
    cls = [m > 0.2 ? '+' : m < -0.2 ? '-' : '0' for m in M]
    println("M class by slot: ", String(cls))
    println("d_eff class by slot (1=lamellar,2=columnar,3=cubic): ",
            String([o.d_eff < 1.5 ? '1' : o.d_eff < 2.5 ? '2' : '3' for o in obs]))
end
