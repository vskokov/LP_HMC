#!/usr/bin/env julia
# Unbiased HMC measurement of the shell-resolved structure factor S(k̂²) in the
# symmetric phase: the fluctuation-renormalized dispersion G⁻¹(k) = 1/S(k), its peak
# k̂²*, and Z_eff.  Independent replicas run as one batch (the CV-HMC kernel of
# src/quadratic_cv.jl with zero bias, so no swaps and no umbrella).
#
# Configuration (environment):
#   SK_L, SK_Z, SK_M2            lattice and couplings
#   SK_REPS                      independent replicas (default 8)
#   SK_EPS, SK_NLF               initial HMC step / leapfrog steps (ε adapts in therm)
#   SK_THERM, SK_SAMPLES, SK_SKIP  thermalisation sweeps, samples, sweeps per sample
#   SK_BLOCK                     samples per written block (default 100)
#   SK_KMAX                      largest k̂² recorded (default 3.0)
#   SK_SEED, SK_OUT, SK_GPU, SK_RUNTIME (s, then checkpoint and exit 75)
#   SK_INIT                      random (default, small noise) | uniform | lamellar | slab |
#                                symslab (x <= L/2 disordered noise, x > L/2 lamellar)
#   SK_INIT_N                    lamellar start: n wavelengths across L, k = 2πn/L
#                                (default: nearest to the bare peak k̂² = -Z/2)
#     uniform  φ = +sqrt(-m²/λ);  lamellar  φ = A cos(kx), A² = 4|m² + Zk̂² + k̂⁴|/(3λ)
#     slab     x < L/2 uniform, x ≥ L/2 lamellar: odd replicas modulated along x (layers
#              parallel to the interfaces), even replicas along y (layers perpendicular).
#              Direct-coexistence test: the phase with lower free energy invades the box.
#
# Output in SK_OUT:
#   sk.csv     block,replica,q,deg,S       S = <|φ_k|²>/V averaged over the shell and block
#   obs.csv    sample,replica,M2,Q,P_max,q_max   per sample; P_max = largest shell power
#              Σ_shell|φ_k|²/V² for 0 < k̂² ≤ KMAX (an ordering detector), q_max its k̂²
#   checkpoint.jld2, diagnostics.json, complete.json

cd(@__DIR__)
using JLD2
using Printf
using Random
using Statistics

env(k, d=nothing) = haskey(ENV, k) ? ENV[k] : (d === nothing ? error("missing $k") : d)
truthy(x) = lowercase(x) in ("1", "true", "yes")

const L = parse(Int, env("SK_L"))
const cpu = !truthy(env("SK_GPU", "false"))
const FloatType = cpu ? Float64 : Float32
const λ = FloatType(4.0)
const T = FloatType(1.0)
const Z = FloatType(parse(Float64, env("SK_Z")))
const ε = FloatType(parse(Float64, env("SK_EPS")))
const n_lf = parse(Int, env("SK_NLF"))

include("../src/simulation.jl")
include("structure_factor_observables.jl")
include("../src/quadratic_cv.jl")
using FFTW
!cpu && using CUDA.CUFFT

const M2_VALUE = parse(Float64, env("SK_M2"))
const NR = parse(Int, env("SK_REPS", "8"))
const THERM = parse(Int, env("SK_THERM", "20000"))
const SAMPLES = parse(Int, env("SK_SAMPLES", "4000"))
const SKIP = parse(Int, env("SK_SKIP", "5"))
const BLOCK = parse(Int, env("SK_BLOCK", "100"))
const KMAX = parse(Float64, env("SK_KMAX", "3.0"))
const SEED = parse(Int, env("SK_SEED", "1"))
const OUT = abspath(env("SK_OUT"))
const RUNTIME = parse(Float64, env("SK_RUNTIME", env("CVU_RUNTIME", "1e12")))   # CVU_RUNTIME: Slurm backend
const ACC_TARGET, ADAPT_EVERY = 0.8, 50
const EPS_MIN, EPS_MAX = Float64(ε) / 50, 1.5 * Float64(ε)
const TAU = Float64(ε) * n_lf
const INIT = env("SK_INIT", "random")
const INIT_N = parse(Int, env("SK_INIT_N", "0"))
INIT in ("random", "uniform", "lamellar", "slab", "symslab") || error("SK_INIT must be random|uniform|lamellar|slab|symslab")
SAMPLES % BLOCK == 0 || error("SK_SAMPLES must be a multiple of SK_BLOCK")

mkpath(OUT)
const CKPT, SKF, OBSF = joinpath(OUT, "checkpoint.jld2"), joinpath(OUT, "sk.csv"), joinpath(OUT, "obs.csv")
const DIAG, DONE = joinpath(OUT, "diagnostics.json"), joinpath(OUT, "complete.json")

# Shell map for 0 ≤ k̂² ≤ KMAX: linear site indices and their shell number.
function shell_map()
    s = [4sinpi(n / L)^2 for n in 0:L-1]
    keyed = Dict{Float64,Vector{Int}}()
    lin = LinearIndices((L, L, L))
    for I in CartesianIndices((L, L, L))
        q = round(s[I[1]] + s[I[2]] + s[I[3]]; digits=10)
        q <= KMAX + 1e-9 && push!(get!(keyed, q, Int[]), lin[I])
    end
    qs = sort!(collect(keys(keyed)))
    idx = Int[]; sid = Int[]
    for (j, q) in enumerate(qs)
        append!(idx, keyed[q]); append!(sid, fill(j, length(keyed[q])))
    end
    return qs, [length(keyed[q]) for q in qs], idx, sid
end
const QS, DEG, IDX, SID = shell_map()
const NS = length(QS)
const IDX_DEV = cpu ? IDX : CuArray(IDX)

"""Per replica: shell sums Σ_shell |φ_k|²/V (length NS × NR)."""
function shell_sums(batch)
    V = L^3
    F = cpu ? fft(batch, (1, 2, 3)) : CUFFT.fft(batch, (1, 2, 3))
    flat = reshape(abs2.(F), V, NR)
    sub = Array(flat[IDX_DEV, :]) ./ V          # |φ_k|²/V = S(k) sample
    out = zeros(Float64, NS, NR)
    @inbounds for r in 1:NR, i in eachindex(SID)
        out[SID[i], r] += sub[i, r]
    end
    return out
end

function initial_fields(rng)
    host = 0.05 .* randn(rng, L, L, L, NR)
    INIT == "random" && return host
    z, m2 = Float64(Z), M2_VALUE
    n = INIT_N > 0 ? INIT_N : max(1, round(Int, L * 2asin(sqrt(clamp(-z / 8, 0, 1))) / 2π))
    k = 2π * n / L
    q = 4sin(k / 2)^2
    A = sqrt(max(-4 * (m2 + z * q + q^2) / (3 * Float64(λ)), 0.09))
    u = sqrt(max(-m2 / Float64(λ), 0.09))
    @printf("init %s: u=%.4f  lamellar n=%d khat2=%.4f A=%.4f\n", INIT, u, n, q, A)
    for r in 1:NR, x in 1:L, y in 1:L
        if INIT == "symslab" && x <= L ÷ 2
            continue                                   # disordered half: noise only
        elseif INIT == "uniform" || (INIT == "slab" && x <= L ÷ 2)
            host[x, y, :, r] .+= u
        else
            c = (INIT in ("slab", "symslab") && iseven(r)) ? y : x
            host[x, y, :, r] .+= A * cos(k * (c - 1))
        end
    end
    return host
end

function main()
    t0 = time()
    isfile(DONE) && (println("already complete"); return 0)
    rng = MersenneTwister(SEED)
    Random.seed!(SEED); !cpu && CUDA.seed!(SEED)
    cv = make_cv(L, "M2")
    centers, kappas = zeros(NR), zeros(NR)          # zero bias: plain HMC per replica
    if isfile(CKPT)
        d = load(CKPT)
        d["m2"] == M2_VALUE && d["L"] == L && d["Z"] == Float64(Z) || error("checkpoint parameter mismatch")
        batch = cpu ? FloatType.(d["fields"]) : CuArray(FloatType.(d["fields"]))
        sweeps, collected, phase = d["sweeps"], d["collected"], d["phase"]
        eps, nlf, acc_all, att_all = Float64.(d["eps"]), d["nlf"], d["acc"], d["att"]
    else
        host = initial_fields(rng)
        batch = cpu ? FloatType.(host) : CuArray(FloatType.(host))
        sweeps, collected, phase = 0, 0, "therm"
        eps, nlf, acc_all, att_all = fill(Float64(ε), NR), n_lf, zeros(Int, NR), 0
    end
    rng = MersenneTwister(hash((SEED, sweeps, collected)))
    !cpu && CUDA.seed!(rand(rng, UInt32))
    ws = make_cv_workspace(batch, fill(M2_VALUE, NR))
    save(ph) = (jldsave(CKPT * ".tmp", true; fields=Array(batch), sweeps=sweeps, collected=collected,
                        phase=ph, eps=eps, nlf=nlf, acc=acc_all, att=att_all, m2=M2_VALUE, L=L,
                        Z=Float64(Z), seed=SEED);
                mv(CKPT * ".tmp", CKPT; force=true))
    diag() = Dict("sweeps" => sweeps, "collected" => collected, "phase" => phase, "L" => L,
                  "Z" => Float64(Z), "m2" => M2_VALUE, "replicas" => NR, "init" => INIT, "init_n" => INIT_N,
                  "hmc_acceptance_mean" => mean(acc_all) / max(att_all, 1),
                  "hmc_acceptance_min" => minimum(acc_all) / max(att_all, 1),
                  "eps_median" => median(eps), "n_lf" => nlf, "elapsed_s" => time() - t0)
    function write_json(path, d)
        open(path * ".tmp", "w") do io
            println(io, "{", join(("\"$k\": " * (v isa AbstractString ? "\"$v\"" : string(v)) for (k, v) in d), ", "), "}")
        end
        mv(path * ".tmp", path; force=true)
    end
    blk_acc, blk_att = zeros(Int, NR), 0
    while phase == "therm"
        acc, _ = hmc_step_cv!(batch, Z, eps, nlf, ws, cv, centers, kappas; rng=rng)
        sweeps += 1; blk_acc .+= acc; blk_att += 1
        if blk_att >= ADAPT_EVERY
            eps .= clamp.(eps .* exp.(blk_acc ./ blk_att .- ACC_TARGET), EPS_MIN, EPS_MAX)
            nlf = clamp(round(Int, TAU / median(eps)), 1, 8 * n_lf)
            blk_acc .= 0; blk_att = 0
        end
        if sweeps % 1000 == 0
            save("therm"); write_json(DIAG, diag())
            @printf("therm %d eps=%.4g nlf=%d\n", sweeps, median(eps), nlf)
            time() - t0 > RUNTIME && return 75
        end
        if sweeps >= THERM
            phase = "collect"
            for f in (SKF, OBSF); isfile(f) && rm(f); end
            open(io -> println(io, "# L=$L Z=$(Float64(Z)) m2=$M2_VALUE replicas=$NR kmax=$KMAX\nblock,replica,q,deg,S"), SKF, "w")
            open(io -> println(io, "# L=$L Z=$(Float64(Z)) m2=$M2_VALUE\nsample,replica,M2,Q,P_max,q_max"), OBSF, "w")
            save("collect")
        end
    end
    # Truncate rows written after the last checkpoint (checkpoints sit at block ends).
    for (f, rows) in ((SKF, (collected ÷ BLOCK) * NR * NS), (OBSF, collected * NR))
        lines = readlines(f)
        keep = 2 + rows
        length(lines) != keep && open(fh -> foreach(l -> println(fh, l), lines[1:min(keep, end)]), f, "w")
    end
    acc_all .= 0; att_all = 0
    sk, obs = open(SKF, "a"), open(OBSF, "a")
    blocksum = zeros(Float64, NS, NR)
    try
        while collected < SAMPLES
            for _ in 1:SKIP
                acc, _ = hmc_step_cv!(batch, Z, eps, nlf, ws, cv, centers, kappas; rng=rng)
                sweeps += 1; acc_all .+= acc; att_all += 1
            end
            collected += 1
            ss = shell_sums(batch)
            blocksum .+= ss
            V = L^3
            Qv = vec(Array(sum(abs2.(batch); dims=(1, 2, 3)))) ./ V
            for r in 1:NR
                P = ss[:, r] ./ V                         # shell power Σ|φ_k|²/V²
                j = argmax(view(P, 2:NS)) + 1
                @printf(obs, "%d,%d,%.8g,%.8g,%.8g,%.10g\n", collected, r, P[1], Qv[r], P[j], QS[j])
            end
            if collected % BLOCK == 0
                b = collected ÷ BLOCK
                for r in 1:NR, j in 1:NS
                    @printf(sk, "%d,%d,%.10g,%d,%.8g\n", b, r, QS[j], DEG[j], blocksum[j, r] / (BLOCK * DEG[j]))
                end
                blocksum .= 0
                flush(sk); flush(obs)
                save("collect"); write_json(DIAG, diag())
                @printf("collect %d/%d acc=%.3f\n", collected, SAMPLES, mean(acc_all) / att_all)
                time() - t0 > RUNTIME && collected < SAMPLES && return 75
            end
        end
    finally
        close(sk); close(obs)
    end
    write_json(DIAG, diag()); write_json(DONE, diag())
    println("complete")
    return 0
end

exit(main())
