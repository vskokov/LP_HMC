# Tune HMC leapfrog parameters (ε, n_lf) across lattice sizes.
#
# For each L, searches candidate n_lf values; for each n_lf finds (approximately)
# the largest ε with median acceptance ≥ acc-low (maximizes τ = ε·n_lf at the lower
# acceptance edge). Optionally pulls ε upward until acceptance drops into the upper
# band acc-high when probes sit above the band (too conservative).
#
# Requires subprocess calls to hmc_acceptance_probe.jl (fresh globals per probe).
#
# Usage:
#   julia --project=. scripts/hmc_tune_suite.jl [--cpu] [--fp64] [--output path.csv]
# Example (quick CPU smoke):
#   julia --project=. scripts/hmc_tune_suite.jl --cpu --fp64 --Ls 6 --nlfs 10 \\
#       --probe-steps 400 --replicas 1 --bisect-iters 25

cd(@__DIR__)

using ArgParse
using Printf
using Statistics

const PROBE_SCRIPT = joinpath(@__DIR__, "hmc_acceptance_probe.jl")
const PROJECT_ROOT = joinpath(@__DIR__, "..")

function parse_commandline()
    s = ArgParseSettings(description = "Auto-tune HMC ε and n_lf for listed L")

    @add_arg_table s begin
        "--Ls"
            help = "comma-separated lattice sizes, e.g. 6,8,12,16,24,32,36"
            arg_type = String
            default = "6,8,12,16,24,32,36"
        "--nlfs"
            help = "comma-separated candidate leapfrog counts"
            arg_type = String
            default = "10,12,15,20,25,30"
        "--acc-low"
            help = "minimum acceptable median acceptance"
            arg_type = Float64
            default = 0.70
        "--acc-high"
            help = "maximum acceptable median acceptance"
            arg_type = Float64
            default = 0.80
        "--eps-ref-L24"
            help = "reference ε at L=24 for heuristic bracket center ~ L^{-3/4} scaling"
            arg_type = Float64
            default = 0.02
        "--L-ref"
            help = "reference L paired with --eps-ref-L24"
            arg_type = Int
            default = 24
        "--eps-bracket-factor"
            help = "emin = center/factor, emax = center*factor where center = eps_ref*(L_ref/L)^0.75"
            arg_type = Float64
            default = 48.0
        "--eps-abs-cap"
            help = "never probe ε above this (leapfrog stability / sanity)"
            arg_type = Float64
            default = 0.42
        "--eps-floor"
            help = "never probe ε below this"
            arg_type = Float64
            default = 1e-5
        "--probe-steps"
            help = "HMC trajectories per probe subprocess"
            arg_type = Int
            default = 4000
        "--replicas"
            help = "median acceptance over this many probe runs (different RNG seeds)"
            arg_type = Int
            default = 3
        "--base-seed"
            help = "base seed for reproducible replica seeds (0 → deterministic hash without fixed seed)"
            arg_type = Int
            default = 424242
        "--mass"
            arg_type = Float64
            default = -2.28587
        "--Z"
            arg_type = Float64
            default = 1.0
        "--bisect-iters"
            help = "bisection iterations per (L, n_lf) bracket"
            arg_type = Int
            default = 45
        "--expand-iters"
            help = "max bracket extensions when endpoints lack acc(acc_low)/acc(acc_high) separation"
            arg_type = Int
            default = 28
        "--expand-factor"
            arg_type = Float64
            default = 1.35
        "--output"
            help = "CSV path for one row per L (best τ in band)"
            arg_type = String
            default = joinpath(PROJECT_ROOT, "data", "hmc_tune_recommended.csv")
        "--cpu"
            action = :store_true
        "--fp64"
            action = :store_true
        "--quiet"
            help = "suppress per-nlf diagnostic lines"
            action = :store_true
    end

    return parse_args(s)
end

function parse_int_list(s::AbstractString)::Vector{Int}
    parts = split(s, ','; keepempty = false)
    isempty(parts) && return Int[]
    return [parse(Int, strip(p)) for p in parts]
end

function replica_seed(base::Int, replica::Int, L::Int, nlf::Int, eps::Float64)::Int
    base == 0 && return 0
    # deterministic, collision-resistant enough for tuning seeds
    h = floor(Int, eps * 1e9)
    return base + replica * 97_621 + L * 503 + nlf * 3_037 + mod(h, 100_003)
end

function run_probe(; L, eps, nlf, pa, replica_idx::Int)::Float64
    jc = Base.julia_cmd()
    rng = replica_seed(pa["base-seed"], replica_idx, L, nlf, eps)
    cmd = `$jc --project=$PROJECT_ROOT $PROBE_SCRIPT $L --eps=$eps --n_lf=$nlf --probe-steps=$(pa["probe-steps"]) --mass=$(pa["mass"]) --Z=$(pa["Z"]) --rng=$rng`
    pa["cpu"] && (cmd = `$cmd --cpu`)
    pa["fp64"] && (cmd = `$cmd --fp64`)
    io = IOBuffer()
    errio = IOBuffer()
    proc = run(pipeline(ignorestatus(cmd), stdout = io, stderr = errio))
    if !success(proc)
        error("probe failed for L=$L eps=$eps nlf=$nlf:\n$(String(take!(errio)))")
    end
    line = strip(String(take!(io)))
    isempty(line) && error("probe produced empty stdout for L=$L eps=$eps nlf=$nlf")
    return parse(Float64, line)
end

function median_accept(L::Int, eps::Float64, nlf::Int, pa)::Float64
    nrep = max(1, pa["replicas"])
    accs = Vector{Float64}(undef, nrep)
    for i in 1:nrep
        accs[i] = run_probe(; L, eps, nlf, pa, replica_idx = i)
    end
    return median(accs)
end

"""
Extend `hi` upward until median acceptance falls below `acc_low` (need a "bad" right bracket).
Caps by `--eps-abs-cap` and `--expand-iters`.
"""
function widen_hi_acc_below_low!(L::Int, nlf::Int, hi::Float64, pa)::Float64
    local h = hi
    for _ in 1:pa["expand-iters"]
        median_accept(L, h, nlf, pa) < pa["acc-low"] && break
        h = min(h * pa["expand-factor"], pa["eps-abs-cap"])
        if h >= pa["eps-abs-cap"] - 1e-15
            break
        end
    end
    return h
end

"""Shrink `lo` downward until median acceptance is at least `acc_low`."""
function tighten_lo_acc_above_low!(L::Int, nlf::Int, lo::Float64, pa)::Float64
    local l = lo
    for _ in 1:pa["expand-iters"]
        median_accept(L, l, nlf, pa) >= pa["acc-low"] && break
        l = max(l / pa["expand-factor"], pa["eps-floor"])
        if l <= pa["eps-floor"] + 1e-15
            break
        end
    end
    return l
end

"""Largest ε in [eps_small, eps_large] with median_acc ≥ acc_low (monotone acc vs ε assumed)."""
function bisect_largest_eps(L::Int, nlf::Int, eps_small::Float64, eps_large::Float64, pa)::Tuple{Float64,Float64}
    lo = eps_small
    hi = eps_large
    acc_lo = median_accept(L, lo, nlf, pa)
    acc_hi = median_accept(L, hi, nlf, pa)

    if acc_lo < pa["acc-low"]
        return (NaN, acc_lo)
    end

    if acc_hi >= pa["acc-low"]
        final_acc = acc_hi
        return (hi, final_acc)
    end

    for _ in 1:pa["bisect-iters"]
        mid = (lo + hi) / 2
        if median_accept(L, mid, nlf, pa) >= pa["acc-low"]
            lo = mid
        else
            hi = mid
        end
    end
    final_acc = median_accept(L, lo, nlf, pa)
    return (lo, final_acc)
end

"""If acceptance is still above acc_high, increase ε in multiplicative steps."""
function lift_eps_if_too_conservative!(L::Int, nlf::Int, eps::Float64, acc::Float64, pa)::Tuple{Float64,Float64}
    local e = eps
    local a = acc
    guard = 0
    while a > pa["acc-high"] && e < pa["eps-abs-cap"] - 1e-15 && guard < pa["expand-iters"]
        e = min(e * pa["expand-factor"], pa["eps-abs-cap"])
        a = median_accept(L, e, nlf, pa)
        guard += 1
    end
    return (e, a)
end

function bracket_for_L(L::Int, pa)::Tuple{Float64,Float64}
    ref = Float64(pa["L-ref"])
    c = pa["eps-ref-L24"] * (ref / Float64(L))^0.75
    f = pa["eps-bracket-factor"]
    emin = max(c / f, pa["eps-floor"])
    emax = min(c * f, pa["eps-abs-cap"])
    if emax <= emin * 1.0001
        emax = min(emin * 8.0, pa["eps-abs-cap"])
    end
    return (emin, emax)
end

function tune_one_nlf(L::Int, nlf::Int, pa)::NamedTuple
    emin0, emax0 = bracket_for_L(L, pa)
    hi = widen_hi_acc_below_low!(L, nlf, emax0, pa)
    lo = tighten_lo_acc_above_low!(L, nlf, emin0, pa)

    eps_star, acc_star = bisect_largest_eps(L, nlf, lo, hi, pa)
    if isnan(eps_star)
        return (; eps = NaN, acc = acc_star, tau = NaN, ok = false, note = "acc(lo)<acc_low")
    end

    eps2, acc2 = lift_eps_if_too_conservative!(L, nlf, eps_star, acc_star, pa)

    in_band = (pa["acc-low"] <= acc2 <= pa["acc-high"])
    tau = eps2 * Float64(nlf)
    note = in_band ? "" : "outside_band"
    return (; eps = eps2, acc = acc2, tau, ok = in_band, note)
end

function midpoint_distance(pa, acc::Float64)::Float64
    m = (pa["acc-low"] + pa["acc-high"]) / 2
    return abs(acc - m)
end

function pick_best_candidate(rows::Vector{NamedTuple}, pa)::Union{Nothing,NamedTuple}
    rows = [r for r in rows if isfinite(r.eps) && isfinite(r.acc)]
    isempty(rows) && return nothing

    inband = [r for r in rows if r.ok]
    if !isempty(inband)
        best = inband[1]
        for r in inband[2:end]
            if r.tau > best.tau || (r.tau ≈ best.tau && (r.acc > best.acc || (r.acc ≈ best.acc && r.nlf < best.nlf)))
                best = r
            end
        end
        return merge(best, (; picked_reason = "max_tau_in_band"))
    end

    # Fallback: closest median acceptance to midpoint of band; tie-break max tau
    scored = sort(rows, by = r -> (midpoint_distance(pa, r.acc), -r.tau))
    best = scored[1]
    return merge(best, (; picked_reason = "closest_acc_midpoint"))
end

function main()
    pa = parse_commandline()
    Ls = parse_int_list(pa["Ls"])
    nlfs = parse_int_list(pa["nlfs"])
    isempty(Ls) && error("--Ls empty")
    isempty(nlfs) && error("--nlfs empty")

    out_path = pa["output"]
    dir = dirname(out_path)
    isdir(dir) || mkpath(dir)

    csv_lines = String[]
    push!(csv_lines, "L,n_lf,eps,tau,acc_median,in_band,picked_reason,nlf_notes")

    @printf(
        "acc band [%.2f, %.2f]  replicas=%d  probe-steps=%d  eps ref @ L=%d: %.5f\n\n",
        pa["acc-low"],
        pa["acc-high"],
        pa["replicas"],
        pa["probe-steps"],
        pa["L-ref"],
        pa["eps-ref-L24"],
    )

    for L in Ls
        emin, emax = bracket_for_L(L, pa)
        !pa["quiet"] && @printf("--- L=%d  initial bracket emin=%.6g emax=%.6g ---\n", L, emin, emax)

        cand = NamedTuple[]
        for nlf in nlfs
            r = tune_one_nlf(L, nlf, pa)
            row = merge((; L, nlf), r)
            push!(cand, row)
            !pa["quiet"] &&
                @printf(
                    "  n_lf=%2d  eps=%8.5f  acc=%.4f  tau=%8.5f  ok=%s  %s\n",
                    nlf,
                    r.eps,
                    r.acc,
                    r.tau,
                    string(r.ok),
                    r.note,
                )
        end

        best = pick_best_candidate(cand, pa)
        best === nothing && continue

        picked_reason = best.picked_reason
        inb = best.ok ? "true" : "false"
        notes = isempty(best.note) ? best.note : best.note
        line = @sprintf(
            "%d,%d,%.8f,%.8f,%.8f,%s,%s,\"%s\"",
            best.L,
            best.nlf,
            best.eps,
            best.tau,
            best.acc,
            inb,
            picked_reason,
            notes,
        )
        push!(csv_lines, line)

        @printf(
            "\n>> BEST L=%d  n_lf=%d  eps=%.8f  tau=%.8f  acc=%.5f  in_band=%s  (%s)\n\n",
            best.L,
            best.nlf,
            best.eps,
            best.tau,
            best.acc,
            string(best.ok),
            picked_reason,
        )
    end

    write(out_path, join(csv_lines, "\n") * "\n")
    @printf("Wrote %s\n", out_path)
end

main()
