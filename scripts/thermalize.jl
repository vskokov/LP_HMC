cd(@__DIR__)

using JLD2
using CodecZlib
using Printf

include("../src/modelA.jl")

function main()
    @init_state

    for t in 1:L
        acc = thermalize(ϕ, m², L^3)
        @printf("t=%d  acceptance=%.3f\n", t, acc)
        flush(stdout)
        jldsave(joinpath(@__DIR__, "..", "data", "thermalized_L_$(L)_id_$(seed).jld2"), true; ϕ=Array(ϕ), m²=m², t=t)
    end
end

main()
