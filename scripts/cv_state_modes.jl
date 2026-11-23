# Dominant Fourier modes of the window fields in a CV-umbrella checkpoint (every 12th window).
#   julia --project=. scripts/cv_state_modes.jl runs/cv_umbrella/<stage>/.../checkpoint.jld2
using JLD2, FFTW, Printf, Statistics
for path in ARGS
    f = jldopen(path); ϕ = f["fields"]; c = f["centers"]; m2 = f["m2"]; L = f["L"]; close(f)
    V = L^3
    k2(n) = 4sin(pi*n/L)^2
    println("== ", path, "  m2=", m2)
    println(" center    M2       P(k=0)/V  top k̂²   P_top  (n1,n2,n3)     frac_top  P(k̂²∈[0,0.2])  P(k̂²∈[0.4,0.55])")
    for r in 1:12:size(ϕ,4)
        x = Float64.(ϕ[:,:,:,r]); F = abs2.(fft(x)) ./ V^2
        M2 = F[1,1,1]
        tot = sum(F) - M2
        best = 0.0; bi = (0,0,0); lo = 0.0; mid = 0.0
        for I in CartesianIndices(F)
            I == CartesianIndex(1,1,1) && continue
            n = Tuple(I) .- 1; q = sum(k2.(n))
            q <= 0.2 && (lo += F[I]); 0.4 <= q <= 0.55 && (mid += F[I])
            F[I] > best && (best = F[I]; bi = n)
        end
        nn = map(n -> n > L÷2 ? n - L : n, bi)
        @printf(" %7.3f  %.4f  %.4f  %.3f  %.4f  %-14s %.3f   %.4f   %.4f\n", c[r], M2, M2, sum(k2.(bi)), best, string(nn), best/tot, lo, mid)
    end
end
