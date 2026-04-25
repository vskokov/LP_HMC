cd(@__DIR__)

using JLD2
using CodecZlib
using Printf

include("../src/modelA.jl")

function op(ϕ)
    (sum(ϕ)/L^2, sum(ϕ.^2))
end

function run_m²(ϕ, m²0)
    maxt = div(L^4,8)
    skip = div(L^2,8)
    mass_id = round(m²0, digits=3)

    open(joinpath(@__DIR__, "..", "data", "magnetization_L_$(L)_mass_$(mass_id)_id_$(seed).dat"), "w") do io
    for i in 0:maxt
        (M, ϕ2) = op(ϕ)
        Printf.@printf(io, "%i %f %f\n", i, M, ϕ2)

        thermalize(ϕ, m²0, skip)

        if maxt%L == 0
            flush(stdout)
        end
    end
    end
end

function main()
    @init_state

    acc = thermalize(ϕ, -3.5, L^3)
    @printf("initial thermalization acceptance=%.3f\n", acc)

    for m²0 in -3.5:-0.01:-4.0
        acc = thermalize(ϕ, m²0, L^2)
        @printf("m²=%.3f  acceptance=%.3f\n", m²0, acc)
        run_m²(ϕ, m²0)
    end
end

main()
