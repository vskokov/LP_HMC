cd(@__DIR__)

using JLD2
using CodecZlib
using Printf

include("../src/modelA.jl")

function main()
    @init_state

    mass_id = round(m², digits=3)
    Z_id    = round(Z,  digits=3)

    for i in 1:L
      acc = thermalize(ϕ, m², L^2)
      @printf("acceptance=%.3f\n", acc)
      flush(stdout)
      jldsave(joinpath(@__DIR__, "..", "data", "thermalized_L_$(L)_Z_$(Z_id)_mass_$(mass_id)_id_$(seed).jld2"), true; ϕ=Array(ϕ), m²=m²)
    end
end

main()
