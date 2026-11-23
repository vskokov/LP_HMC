# Layer-phase spectrum S_θ(q⊥) of the final lamellar fields (lro/lro2 checkpoints).
#   julia --project=. scripts/lamellar_layer_phase.jl runs/cv_umbrella/lro2/Zm2/L36/*/checkpoint.jld2
using JLD2, FFTW, Statistics, Printf
for path in ARGS
    f = jldopen(path); ϕ = nothing
    for k in keys(f); v = f[k]; (v isa AbstractArray && ndims(v) == 4) && (ϕ = Array(v)); end; close(f)
    L = size(ϕ, 1); nrep = size(ϕ, 4)
    acc = Dict{Float64,Vector{Float64}}(); amps = Float64[]
    for r in 1:nrep
        x = Float64.(ϕ[:, :, :, r])
        prof = [vec(mean(x; dims=setdiff(1:3, (a,)))) for a in 1:3]
        a = argmax(std.(prof)); x = permutedims(x, (a, setdiff(1:3, (a,))...))
        P = abs.(fft(prof[a])); n = argmax(P[2:L÷2+1]); q = 2π * n / L
        c = dropdims(sum(x .* reshape(exp.(-im * q .* (0:L-1)), L, 1, 1); dims=1); dims=1) .* (2 / L)
        push!(amps, mean(abs.(c)))
        θ = angle.(c ./ mean(c))          # phase relative to the mean layer position
        F = abs2.(fft(θ)) ./ L^2
        for I in CartesianIndices(F)
            I == CartesianIndex(1, 1) && continue
            n1, n2 = Tuple(I) .- 1
            k2 = round(4sin(π * n1 / L)^2 + 4sin(π * n2 / L)^2, digits=4)
            push!(get!(acc, k2, Float64[]), F[I])
        end
        r == 1 && @printf("%s L=%d q=2π·%d/L |c|=%.3f  rms θ=%.4f\n", path, L, n, mean(abs.(c)), std(θ))
    end
    ks = sort(collect(keys(acc)))[1:6]
    for k in ks
        v = acc[k]; @printf("   q⊥²=%.4f  S_θ=%.5f ± %.5f  (n=%d)   q⁴·S=%.5f  q²·S=%.5f\n", k, mean(v), std(v)/sqrt(length(v)), length(v), k^2*mean(v), k*mean(v))
    end
    @printf("   S_θ at largest q⊥: %.5f\n", mean(acc[maximum(keys(acc))]))
end
