#!/usr/bin/env julia
# End-to-end CPU checks of per-window ε adaptation in scripts/cv_umbrella.jl.
#   julia --project=. scripts/test_eps_adapt.jl
# Runs cv_umbrella.jl as a subprocess on a small lattice:
#   1. ε starts 4× too large → adaptation must bring every window into range, the run
#      must pass the gate and complete; collect-phase ε must be frozen (header == final).
#   2. A pre-adaptation checkpoint (no "eps" key) must resume with transport statistics
#      reset and complete.
using JLD2, Printf, Statistics

const ROOT = dirname(@__DIR__)
const SCRIPT = joinpath(@__DIR__, "cv_umbrella.jl")
passed = Ref(0); failed = Ref(0)
report(name, ok, detail="") = (@printf("%s  %-46s %s\n", ok ? "PASS" : "FAIL", name, detail);
                               ok ? (passed[] += 1) : (failed[] += 1))

base = Dict("CVU_L" => "6", "CVU_Z" => "-1.0", "CVU_M2" => "-2.0", "CVU_KIND" => "shell",
            "CVU_SHELL_Q" => "1.0", "CVU_WINDOWS" => "8", "CVU_SMIN" => "0.0",
            "CVU_SMAX" => "0.4", "CVU_KAPPA" => "2000", "CVU_POWER" => "1.0",
            "CVU_THERM" => "600", "CVU_MAX_THERM" => "20000", "CVU_MIN_RT" => "0.25",
            "CVU_MIN_SWAP" => "0.05", "CVU_SAMPLES" => "150", "CVU_SKIP" => "2",
            "CVU_CHECK_EVERY" => "200", "CVU_INIT" => "umbrella", "CVU_SEED" => "7",
            "CVU_NLF" => "10", "CVU_GPU" => "false", "CVU_FP64" => "true")

function run_cvu(env, out)
    cmd = Cmd(`$(Base.julia_cmd()) --startup-file=no --project=$ROOT $SCRIPT`;
              env=merge(copy(ENV), env, Dict("CVU_OUT" => out)))
    log = read(ignorestatus(cmd), String)
    return log
end
diag(out) = JLD2.load(joinpath(out, "checkpoint.jld2"))
header_eps(out) = parse.(Float64, split(only(l[12:end] for l in eachline(joinpath(out, "statistics.csv"))
                                             if startswith(l, "# epsilons=")), ';'))

tmp = mktempdir()

# 1. too-large initial ε
out1 = joinpath(tmp, "big_eps")
log1 = run_cvu(merge(base, Dict("CVU_EPS" => "0.4")), out1)
done1 = isfile(joinpath(out1, "complete.json"))
report("run with ε0=0.4 completes", done1, done1 ? "" : last(log1, 600))
if done1
    d = diag(out1)
    acc = d["hmc_acc"] ./ d["hmc_att"]            # collect-phase acceptance per window
    report("collect acceptance per window in [0.5, 0.97]", all(0.5 .<= acc .<= 0.97),
           @sprintf("min=%.3f max=%.3f", minimum(acc), maximum(acc)))
    report("adapted ε below ε0 and within bounds", all(0.4 / 50 .<= d["eps"] .< 0.4),
           @sprintf("ε=[%.4f, %.4f]", extrema(d["eps"])...))
    report("collect ε frozen (header == checkpoint)", header_eps(out1) == d["eps"])
    lines = count(l -> !startswith(l, "#"), eachline(joinpath(out1, "statistics.csv"))) - 1
    report("statistics rows = samples × windows", lines == 150 * 8, "rows=$lines")
end

# 2. resume from a pre-adaptation checkpoint
out2 = joinpath(tmp, "legacy")
run_cvu(merge(base, Dict("CVU_EPS" => "0.4", "CVU_EPS_ADAPT" => "false", "CVU_RUNTIME" => "1e12",
                         "CVU_MAX_THERM" => "400", "CVU_THERM" => "400", "CVU_MIN_RT" => "1.01")), out2)   # gate impossible: exit 3 at cap
ck = joinpath(out2, "checkpoint.jld2")
d0 = JLD2.load(ck)
report("legacy run reached the cap with a checkpoint", isfile(ck) && d0["phase"] == "therm",
       "sweeps=$(d0["sweeps"])")
delete!(d0, "eps")                                  # emulate a pre-adaptation checkpoint
jldsave(ck; (Symbol(k) => v for (k, v) in d0)...)
log2 = run_cvu(merge(base, Dict("CVU_EPS" => "0.4")), out2)
report("legacy resume resets transport statistics", occursin("transport statistics reset", log2))
done2 = isfile(joinpath(out2, "complete.json"))
report("legacy resume completes with adaptation", done2, done2 ? "" : last(log2, 600))

@printf("\n%d passed, %d failed\n", passed[], failed[])
failed[] == 0 ? println("ALL PASS") : exit(1)
