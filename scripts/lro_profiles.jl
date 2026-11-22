#!/usr/bin/env julia
# Plane-averaged lamellar profiles φ̄(x) from the final fields of the unbiased lamellar
# runs (runs/cv_umbrella/lro, lro2).  For each replica the modulation axis is the one with
# the largest variance of the plane average; the profile is shifted so that its maximum
# sits at x = 0.  Output: reports/profiles/lro_profiles.csv
#   julia --project=. scripts/lro_profiles.jl runs/cv_umbrella/lro2/Zm2/L36/m2m3_s186 ...
using JLD2, Statistics, Printf

out = joinpath(@__DIR__, "..", "reports", "profiles", "lro_profiles.csv")
mkpath(dirname(out))
open(out, "w") do io
    println(io, "run,L,replica,axis,x,phi")
    for d in ARGS
        f = jldopen(joinpath(d, "checkpoint.jld2"), "r")
        ϕ = nothing
        for k in keys(f)
            v = f[k]
            (v isa AbstractArray && ndims(v) == 4) && (ϕ = Array(v))
        end
        close(f)
        L = size(ϕ, 1)
        for r in 1:size(ϕ, 4)
            x = Float64.(ϕ[:, :, :, r])
            prof = [vec(mean(x; dims=setdiff(1:3, (a,)))) for a in 1:3]
            a = argmax([std(p) for p in prof])
            p = circshift(prof[a], 1 - argmax(prof[a]))
            for (i, v) in enumerate(p)
                @printf(io, "%s,%d,%d,%d,%d,%.6f\n", d, L, r, a, i - 1, v)
            end
        end
    end
end
println("wrote ", out)
