#!/usr/bin/env julia
# Replica-exchange umbrella sampling in a quadratic Fourier-space CV
# (shell power P_*, mixed M^2 - c P_*, or M^2) at fixed (L, Z, m^2).
#
# Configuration by environment variables (all CVU_*):
#   CVU_L, CVU_Z, CVU_M2                 lattice size and couplings
#   CVU_KIND=shell|mixed|M2              collective variable
#   CVU_SHELL_Q                          target k̂² (nearest allowed shell is used)
#   CVU_MIX                              c in M^2 - c P_* (mixed only)
#   CVU_WINDOWS, CVU_SMIN, CVU_SMAX      umbrella ladder (centers smin + (smax-smin) u^power)
#   CVU_KAPPA, CVU_POWER
#   CVU_EPS, CVU_NLF                     HMC integrator (CVU_EPS = initial step size)
#   CVU_EPS_ADAPT=true|false             per-window ε adaptation during thermalisation
#   CVU_ACC_TARGET, CVU_ADAPT_EVERY      target HMC acceptance (0.8), sweeps per update (50)
#   CVU_THERM, CVU_MAX_THERM             minimum / maximum thermalisation sweeps
#   CVU_MIN_RT, CVU_MIN_SWAP             transport gate: walker round-trip fraction, edge acceptance
#   CVU_SAMPLES, CVU_SKIP                production samples per window, sweeps between samples
#   CVU_INIT=umbrella|disordered|ordered initial fields
#   CVU_SEED, CVU_OUT (directory), CVU_GPU, CVU_FP64, CVU_RUNTIME (s, then exit 75)
#
# Output in CVU_OUT: checkpoint.jld2, statistics.csv (time-major: one row per window
# per sample), diagnostics.json, complete.json on success.  Rerun to resume.

cd(@__DIR__)
using JLD2
using Printf
using Random
using Statistics

env(k, d=nothing) = haskey(ENV, k) ? ENV[k] : (d === nothing ? error("missing $k") : d)
truthy(x) = lowercase(x) in ("1", "true", "yes")

const L = parse(Int, env("CVU_L"))
const cpu = !truthy(env("CVU_GPU", "false"))
const FloatType = truthy(env("CVU_FP64", cpu ? "true" : "false")) ? Float64 : Float32
const λ = FloatType(4.0)
const T = FloatType(1.0)
const Z = FloatType(parse(Float64, env("CVU_Z")))
const ε = FloatType(parse(Float64, env("CVU_EPS")))
const n_lf = parse(Int, env("CVU_NLF"))

include("../src/simulation.jl")
include("structure_factor_observables.jl")
include("../src/quadratic_cv.jl")

const M2_VALUE = parse(Float64, env("CVU_M2"))
const KIND = env("CVU_KIND", "shell")
const SHELL_Q = parse(Float64, env("CVU_SHELL_Q", "NaN"))
const MIX = parse(Float64, env("CVU_MIX", "1.0"))
const NW = parse(Int, env("CVU_WINDOWS"))
const SMIN = parse(Float64, env("CVU_SMIN", "0.0"))
const SMAX = parse(Float64, env("CVU_SMAX"))
const KAPPA = parse(Float64, env("CVU_KAPPA"))
const POWER = parse(Float64, env("CVU_POWER", "1.0"))
const THERM = parse(Int, env("CVU_THERM", "2000"))
const MAX_THERM = parse(Int, env("CVU_MAX_THERM", string(20 * THERM)))
const MIN_RT = parse(Float64, env("CVU_MIN_RT", "0.5"))
const MIN_SWAP = parse(Float64, env("CVU_MIN_SWAP", "0.2"))
const SAMPLES = parse(Int, env("CVU_SAMPLES"))
const SKIP = parse(Int, env("CVU_SKIP", "2"))
const INIT = env("CVU_INIT", "umbrella")
const SEED = parse(Int, env("CVU_SEED", "1"))
const OUT = abspath(env("CVU_OUT"))
const RUNTIME = parse(Float64, env("CVU_RUNTIME", "1e12"))
const CHECK_EVERY = parse(Int, env("CVU_CHECK_EVERY", "200"))
# Per-window step-size adaptation.  Only during thermalisation: ε is frozen when the
# run enters the collect phase, so every window samples with a fixed, exact HMC kernel.
const EPS_ADAPT = truthy(env("CVU_EPS_ADAPT", "true"))
const ACC_TARGET = parse(Float64, env("CVU_ACC_TARGET", "0.8"))
const ADAPT_EVERY = parse(Int, env("CVU_ADAPT_EVERY", "50"))
const ADAPT_GAIN = 1.0                       # ε ← ε·exp(gain·(acc − target)) per block
const EPS_MIN, EPS_MAX = Float64(ε) / 50, 1.5 * Float64(ε)
const TAU = Float64(ε) * n_lf                # trajectory length kept for the median window
const NLF_MAX = 8 * n_lf

mkpath(OUT)
const CKPT = joinpath(OUT, "checkpoint.jld2")
const STATS = joinpath(OUT, "statistics.csv")
const DIAG = joinpath(OUT, "diagnostics.json")
const DONE = joinpath(OUT, "complete.json")

centers = SMIN .+ (SMAX - SMIN) .* range(0, 1; length=NW) .^ POWER |> collect
kappas = fill(KAPPA, NW)

# ------------------------------------------------------------------ initial fields
function initial_field(center, rng)
    f = 0.05 .* randn(rng, L, L, L)
    if INIT == "disordered"
        return f
    elseif INIT == "ordered"
        return f .+ sqrt(max(-M2_VALUE / λ, 0.05))
    end
    # umbrella: field whose CV is near the window centre
    if KIND == "M2" || (KIND == "mixed" && center >= 0)
        return f .+ sqrt(max(center, 0.0))
    end
    target = KIND == "shell" ? center : -center / MIX
    A = sqrt(2 * max(target, 0.0))
    n = round(Int, L * asin(sqrt(CV.shell_q) / 2) / π)   # axis mode nearest the shell
    axis = rand(rng, 1:3)
    for I in CartesianIndices(f)
        f[I] += A * cos(2π * n * (Tuple(I)[axis] - 1) / L)
    end
    return f
end

cpu && FFTW.set_num_threads(Threads.nthreads())   # before any plan is made
const CV = make_cv(L, KIND; shell_target=SHELL_Q, mix=MIX)
to_backend(x) = cpu ? x : CuArray(x)

# ------------------------------------------------------------------ state
mutable struct RunState
    batch::Any
    walker::Vector{Int}
    stage::Vector{Int}         # 0 none, 1 visited low end, 2 then visited high end
    trips::Vector{Int}
    swap_att::Vector{Int}
    swap_acc::Vector{Int}
    hmc_att::Int
    hmc_acc::Vector{Int}
    sweeps::Int
    phase::String              # "therm" or "collect"
    collected::Int
    phase_flip::Int
    eps::Vector{Float64}       # per-window HMC step size
    nlf::Int                   # leapfrog steps (common to all windows)
    blk_acc::Vector{Int}       # acceptances in the current adaptation block
    blk_att::Int
    chk_acc::Vector{Int}       # acceptances since the last gate check
    chk_att::Int
end

function save_state(st::RunState)
    tmp = CKPT * ".tmp"
    jldsave(tmp, true; fields=Array(st.batch), walker=st.walker, stage=st.stage,
            trips=st.trips, swap_att=st.swap_att, swap_acc=st.swap_acc, hmc_att=st.hmc_att,
            hmc_acc=st.hmc_acc, sweeps=st.sweeps, phase=st.phase, collected=st.collected,
            phase_flip=st.phase_flip, eps=st.eps, nlf=st.nlf, centers=centers, kappas=kappas, L=L, Z=Float64(Z),
            m2=M2_VALUE, kind=KIND, cv_label=CV.label, seed=SEED)
    mv(tmp, CKPT; force=true)
end

function load_state()
    d = load(CKPT)
    d["centers"] == centers && d["kappas"] == kappas || error("checkpoint ladder mismatch")
    d["m2"] == M2_VALUE && d["cv_label"] == CV.label || error("checkpoint parameter mismatch")
    # Checkpoints written before ε adaptation existed carry no "eps": start from CVU_EPS.
    # A collect-phase run keeps the ε it was sampling with (scalar CVU_EPS in that case).
    eps = haskey(d, "eps") ? Float64.(d["eps"]) : fill(Float64(ε), NW)
    st = RunState(to_backend(FloatType.(d["fields"])), d["walker"], d["stage"], d["trips"],
                  d["swap_att"], d["swap_acc"], d["hmc_att"], d["hmc_acc"], d["sweeps"],
                  d["phase"], d["collected"], d["phase_flip"], eps,
                  haskey(d, "nlf") ? Int(d["nlf"]) : n_lf, zeros(Int, NW), 0,
                  zeros(Int, NW), 0)
    if !haskey(d, "eps") && EPS_ADAPT && st.phase == "therm"
        # First resume with adaptation: transport statistics gathered with the old ε are
        # meaningless if HMC was frozen (swaps between unmoving, near-identical fields are
        # accepted trivially and count as round trips).  Restart them; keep the fields.
        st.trips .= 0; st.stage .= 0; st.swap_att .= 0; st.swap_acc .= 0
        st.hmc_att = 0; st.hmc_acc .= 0
        println("resume: ε adaptation enabled on a pre-adaptation checkpoint; transport statistics reset")
    end
    return st
end

function sweep!(st::RunState, ws, buffer, rng)
    acc, _ = hmc_step_cv!(st.batch, Z, st.eps, st.nlf, ws, CV, centers, kappas; rng=rng)
    st.hmc_att += 1
    st.hmc_acc .+= acc
    st.chk_att += 1
    st.chk_acc .+= acc
    if EPS_ADAPT && st.phase == "therm"
        st.blk_att += 1
        st.blk_acc .+= acc
        if st.blk_att >= ADAPT_EVERY
            rate = st.blk_acc ./ st.blk_att
            st.eps .= clamp.(st.eps .* exp.(ADAPT_GAIN .* (rate .- ACC_TARGET)), EPS_MIN, EPS_MAX)
            st.nlf = clamp(round(Int, TAU / median(st.eps)), 1, NLF_MAX)
            st.blk_acc .= 0; st.blk_att = 0
        end
    end
    s = cv_values(CV, st.batch)
    for left in st.phase_flip:2:(NW - 1)
        r = left + 1
        Δ = cv_swap_delta(s[left], s[r], centers[left], centers[r], kappas[left], kappas[r])
        st.swap_att[left] += 1
        if Δ <= 0 || log(rand(rng)) < -Δ
            swap_slices!(st.batch, left, r, buffer)
            st.walker[left], st.walker[r] = st.walker[r], st.walker[left]
            s[left], s[r] = s[r], s[left]
            st.swap_acc[left] += 1
        end
    end
    st.phase_flip = st.phase_flip == 1 ? 2 : 1
    lo, hi = st.walker[1], st.walker[end]
    st.stage[lo] == 2 && (st.trips[lo] += 1)
    st.stage[lo] = 1
    st.stage[hi] == 1 && (st.stage[hi] = 2)
    st.sweeps += 1
    return s
end

# Transport gate.  With ε adaptation it also requires every window to have a working HMC
# kernel over the last check interval (frozen windows make swaps and round trips
# meaningless).
gate(st) = (count(>(0), st.trips) / NW >= MIN_RT) &&
           minimum(st.swap_acc ./ max.(st.swap_att, 1)) >= MIN_SWAP &&
           (!EPS_ADAPT || (st.chk_att >= 100 &&
                           minimum(st.chk_acc) / st.chk_att >= 0.5 * ACC_TARGET))

function diagnostics(st, t0)
    rate = st.swap_acc ./ max.(st.swap_att, 1)
    return Dict("sweeps" => st.sweeps, "phase" => st.phase, "collected" => st.collected,
                "min_swap" => minimum(rate), "median_swap" => median(rate),
                "hmc_acceptance_min" => minimum(st.hmc_acc) / max(st.hmc_att, 1),
                "hmc_acceptance_mean" => mean(st.hmc_acc) / max(st.hmc_att, 1),
                "round_trip_walkers" => count(>(0), st.trips), "total_round_trips" => sum(st.trips),
                "elapsed_s" => time() - t0, "cv" => CV.label, "L" => L, "Z" => Float64(Z),
                "m2" => M2_VALUE, "windows" => NW, "eps_min" => minimum(st.eps),
                "eps_median" => median(st.eps), "eps_max" => maximum(st.eps), "n_lf" => st.nlf,
                "eps_adapt" => EPS_ADAPT && st.phase == "therm",
                "hmc_recent_min" => minimum(st.chk_acc) / max(st.chk_att, 1),
                "hmc_recent_mean" => mean(st.chk_acc) / max(st.chk_att, 1))
end

function write_json(path, d)
    open(path * ".tmp", "w") do io
        println(io, "{", join(("\"$k\": " * (v isa AbstractString ? "\"$v\"" : string(v)) for (k, v) in d), ", "), "}")
    end
    mv(path * ".tmp", path; force=true)
end

function header(io, st)
    for (k, v) in (("schema", "cv_umbrella_1"), ("L", L), ("Z", Float64(Z)), ("m2", M2_VALUE),
                   ("lambda", Float64(λ)), ("temperature", Float64(T)), ("cv", CV.label),
                   ("cv_kind", KIND), ("shell_q", CV.shell_q), ("mix", MIX),
                   ("epsilon", median(st.eps)), ("epsilons", join(st.eps, ";")),
                   ("eps_adapted", EPS_ADAPT), ("n_lf", st.nlf), ("windows", NW),
                   ("samples_per_window", SAMPLES), ("skip", SKIP), ("seed", SEED),
                   ("float_type", string(FloatType)), ("device", cpu ? "cpu" : "cuda"),
                   ("centers", join(centers, ";")), ("kappas", join(kappas, ";")))
        println(io, "# $k=$v")
    end
    println(io, "sample,slot,walker_id,center,kappa,s,M,Q,G,P_shell,P_maxpair,lambda1,lambda2,lambda3,d_eff")
end

function main()
    t0 = time()
    isfile(DONE) && (println("already complete: $DONE"); return 0)
    rng = MersenneTwister(SEED)
    Random.seed!(SEED); !cpu && CUDA.seed!(SEED)
    st = if isfile(CKPT)
        load_state()
    else
        host = cat((initial_field(c, rng) for c in centers)...; dims=4)
        RunState(to_backend(FloatType.(host)), collect(1:NW), zeros(Int, NW), zeros(Int, NW),
                 zeros(Int, NW - 1), zeros(Int, NW - 1), 0, zeros(Int, NW), 0, "therm", 0, 1,
                 fill(Float64(ε), NW), n_lf, zeros(Int, NW), 0, zeros(Int, NW), 0)
    end
    # Re-seed after resume so continued chains do not replay random numbers.
    rng = MersenneTwister(hash((SEED, st.sweeps, st.collected)))
    Random.seed!(hash((SEED, st.sweeps, 1))); !cpu && CUDA.seed!(rand(rng, UInt32))
    ws = make_cv_workspace(st.batch, fill(M2_VALUE, NW))
    buffer = similar(st.batch, L, L, L)
    @printf("cv_umbrella L=%d Z=%.6g m2=%.6g cv=%s windows=%d device=%s phase=%s sweeps=%d\n",
            L, Z, M2_VALUE, CV.label, NW, cpu ? "cpu" : "cuda", st.phase, st.sweeps)
    out_of_time() = time() - t0 > RUNTIME
    while st.phase == "therm"
        sweep!(st, ws, buffer, rng)
        if st.sweeps % CHECK_EVERY != 0 && out_of_time()
            # Budget exhausted between gate checks (large L): checkpoint and yield.
            save_state(st); write_json(DIAG, diagnostics(st, t0))
            return 75
        end
        if st.sweeps % CHECK_EVERY == 0
            d = diagnostics(st, t0)
            @printf("therm sweeps=%d min_swap=%.3f rt_walkers=%d/%d hmc=%.3f recent_min=%.3f eps=[%.4g,%.4g,%.4g] nlf=%d\n",
                    st.sweeps, d["min_swap"], d["round_trip_walkers"], NW, d["hmc_acceptance_mean"],
                    d["hmc_recent_min"], d["eps_min"], d["eps_median"], d["eps_max"], st.nlf)
            if st.sweeps >= THERM && gate(st)
                st.phase = "collect"
                st.swap_att .= 0; st.swap_acc .= 0; st.hmc_att = 0; st.hmc_acc .= 0
                st.trips .= 0; st.stage .= 0
                isfile(STATS) && rm(STATS)
                open(io -> header(io, st), STATS, "w")
            elseif st.sweeps >= MAX_THERM
                save_state(st); write_json(DIAG, diagnostics(st, t0))
                println("transport gate not met by max sweeps; checkpoint kept"); return 3
            end
            save_state(st); write_json(DIAG, diagnostics(st, t0))
            st.chk_acc .= 0; st.chk_att = 0          # after the diagnostics are written
            out_of_time() && return 75
        end
    end
    # Drop rows written after the last checkpoint (crash between flush and save).
    if isfile(STATS)
        lines = readlines(STATS)
        nhead = count(l -> startswith(l, "#"), lines) + 1
        keep = nhead + st.collected * NW
        if length(lines) != keep
            open(STATS, "w") do fh
                foreach(l -> println(fh, l), lines[1:min(keep, length(lines))])
            end
        end
    end
    io = open(STATS, "a")
    try
        while st.collected < SAMPLES
            for _ in 1:SKIP
                sweep!(st, ws, buffer, rng)
            end
            st.collected += 1
            s = cv_values(CV, st.batch)
            stats = if cpu
                v = Vector{NamedTuple{(:M, :Q, :G), NTuple{3, Float64}}}(undef, NW)
                Threads.@threads for r in 1:NW
                    v[r] = sufficient_statistics(view(st.batch, :, :, :, r))
                end
                v
            else
                b = sufficient_statistics_batched(st.batch, ws.base)
                [(M=b.M[r], Q=b.Q[r], G=b.G[r]) for r in 1:NW]
            end
            obs = shell_observables(CV, st.batch)
            for r in 1:NW
                o = obs === nothing ? (P_shell=NaN, P_maxpair=NaN, lambda1=NaN, lambda2=NaN, lambda3=NaN, d_eff=NaN) : obs[r]
                @printf(io, "%d,%d,%d,%.12g,%.8g,%.10g,%.10g,%.10g,%.10g,%.10g,%.10g,%.6g,%.6g,%.6g,%.6g\n",
                        st.collected, r, st.walker[r], centers[r], kappas[r], s[r], stats[r].M,
                        stats[r].Q, stats[r].G, o.P_shell, o.P_maxpair, o.lambda1, o.lambda2,
                        o.lambda3, o.d_eff)
            end
            if st.collected % 50 == 0 || st.collected == SAMPLES || out_of_time()
                flush(io)
                save_state(st); write_json(DIAG, diagnostics(st, t0))
                @printf("collect %d/%d min_swap=%.3f rt=%d\n", st.collected, SAMPLES,
                        diagnostics(st, t0)["min_swap"], sum(st.trips))
                if out_of_time() && st.collected < SAMPLES
                    return 75
                end
            end
        end
    finally
        close(io)
    end
    save_state(st)
    d = diagnostics(st, t0)
    write_json(DIAG, d); write_json(DONE, d)
    println("complete")
    return 0
end

exit(main())
