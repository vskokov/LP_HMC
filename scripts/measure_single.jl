cd(@__DIR__)

using JLD2
using CodecZlib
using Printf
using FFTW

include("../src/modelA.jl")

function op(ϕ)
    phik = cpu ? fft(ϕ) : Array(CUFFT.fft(ϕ))
    average = phik[1,1,1]/L^3
    (real(average), phik[:,1,1])
end

function main()
    @init_state

    thermalize(ϕ, m², L^2)

    maxt = 50L^2
    skip = div(L^2,8)
    mass_id = round(m², digits=3)
    Z_id = round(Z, digits=3)

    mag_path = joinpath(@__DIR__, "..", "data", "magnetization_L_$(L)_Z_$(Z_id)_mass_$(mass_id)_id_$(seed).dat")
    ene_path = joinpath(@__DIR__, "..", "data", "energy_L_$(L)_Z_$(Z_id)_mass_$(mass_id)_id_$(seed).dat")

    open(mag_path, "w") do io_mag
    open(ene_path, "w") do io_ene
    for i in 0:maxt
        (M, ϕk) = op(ϕ)
        Printf.@printf(io_mag, "%i %f", i*skip, M)
        for kx in 1:L÷2
            Printf.@printf(io_mag, " %.15f %.15f", real(ϕk[kx]), imag(ϕk[kx]))
        end
        Printf.@printf(io_mag, "\n")

        H = calc_total_energy(ϕ, m², Z)
        Printf.@printf(io_ene, "%i %.15f\n", i*skip, H)

        thermalize(ϕ, m², skip)

        flush(stdout)
    end
    end
    end
end

main()
