# Plane-averaged profiles and harmonic content of intermediate-window fields of a CV checkpoint.
#   julia --project=. scripts/cv_state_profiles.jl runs/cv_umbrella/<stage>/.../checkpoint.jld2
using JLD2, Statistics, Printf
f = jldopen(ARGS[1]); ϕ = f["fields"]; c = f["centers"]; L = f["L"]; close(f)
for r in 100:8:200
    x = Float64.(ϕ[:,:,:,r])
    prof = [vec(mean(x; dims=setdiff(1:3,(a,)))) for a in 1:3]
    a = argmax(std.(prof)); p = prof[a]
    k = 2pi/L; X = 0:L-1
    A1 = abs(sum(p .* exp.(im*k*X)))*2/L; A3 = abs(sum(p .* exp.(3im*k*X)))*2/L; A2 = abs(sum(p .* exp.(2im*k*X)))*2/L
    @printf("c=%6.3f M=%+.3f A1=%.3f A2=%.3f A3=%.3f A3/A1=%.2f  prof=%s\n", c[r], mean(x), A1, A2, A3, A3/A1, join([@sprintf("%+.2f",v) for v in p], " "))
end
