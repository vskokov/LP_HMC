#!/usr/bin/env julia

cd(@__DIR__)
using FFTW
using Printf
using Random

const L = 16
const FloatType = Float64
const ArrayType = Array
const cpu = true
const λ = FloatType(4.0)
const T = FloatType(1.0)
const Z = FloatType(parse(Float64, ENV["MODSCAN_Z"]))
const m² = FloatType(parse(Float64, ENV["MODSCAN_M2"]))
const ε = FloatType(parse(Float64, get(ENV, "MODSCAN_EPS", "0.012")))
const n_lf = parse(Int, get(ENV, "MODSCAN_N_LF", "15"))

include("../src/simulation.jl")
include("structure_factor_observables.jl")

function mode_field(index::CartesianIndex{3}, amplitude)
    n = Tuple(index) .- 1
    return [amplitude * cos(2π * sum(n[axis] * (coordinate[axis] - 1) / L
                                    for axis in 1:3))
            for coordinate in CartesianIndices((L, L, L))] |>
           values -> reshape(values, L, L, L)
end

function initial_field(kind, geometry, modulated_index, amplitude)
    if kind == "disordered"
        return 0.1 .* randn(Float64, L, L, L)
    elseif kind == "uniform"
        uniform_amplitude = sqrt(max(-Float64(m²) / Float64(λ), 0.05))
        return fill(uniform_amplitude, L, L, L) .+ 0.02 .* randn(L, L, L)
    elseif kind == "modulated"
        representative = geometry.members[modulated_index][1]
        return mode_field(representative, amplitude) .+ 0.02 .* randn(L, L, L)
    end
    error("unknown MODSCAN_INIT=$(kind)")
end

function advance!(field, sweeps)
    accepted = 0
    for _ in 1:sweeps
        success, _ = hmc_step!(field, m², Z, ε, n_lf)
        accepted += success
    end
    return accepted
end

function main()
    seed = parse(Int, ENV["MODSCAN_SEED"])
    Random.seed!(seed)
    init = ENV["MODSCAN_INIT"]
    output = abspath(ENV["MODSCAN_OUTPUT"])
    warmup = parse(Int, get(ENV, "MODSCAN_WARMUP", "300"))
    samples = parse(Int, get(ENV, "MODSCAN_SAMPLES", "100"))
    skip = parse(Int, get(ENV, "MODSCAN_SKIP", "2"))
    geometry = momentum_shells(L)
    q_bare = clamp(-Float64(Z) / 2, 0.0, 12.0)
    modulated_index = argmin(abs.(geometry.q .- q_bare))
    q_modulated = geometry.q[modulated_index]
    quadratic = Float64(m²) + Float64(Z) * q_modulated + q_modulated^2
    amplitude = sqrt(max(-4quadratic / (3Float64(λ)), 0.25))
    field = initial_field(init, geometry, modulated_index, amplitude)

    warmup_accepts = advance!(field, warmup)
    mean_powers = zeros(length(geometry.q))
    peak_counts = zeros(Int, length(geometry.q))
    measurement_accepts = 0
    m2_values = Float64[]
    energy_values = Float64[]
    selected_orientation = Float64[]
    for _ in 1:samples
        measurement_accepts += advance!(field, skip)
        observables = fourier_shell_observables(field, geometry, modulated_index)
        mean_powers .+= observables.powers
        peak_counts[argmax(observables.powers)] += 1
        stats = field_statistics(field)
        push!(m2_values, stats.M2)
        push!(energy_values, Float64(calc_total_energy(field, m², Z)) / L^3)
        push!(selected_orientation, observables.maximum_fraction)
    end
    mean_powers ./= samples
    mean_peak = argmax(mean_powers)
    modal_peak = argmax(peak_counts)

    mkpath(output)
    open(joinpath(output, "spectrum.csv"), "w") do io
        println(io, "q,degeneracy,S_per_mode,peak_fraction")
        for index in eachindex(geometry.q)
            @printf(io, "%.12g,%d,%.17g,%.17g\n", geometry.q[index],
                    length(geometry.members[index]),
                    L^3 * mean_powers[index] / length(geometry.members[index]),
                    peak_counts[index] / samples)
        end
    end
    open(joinpath(output, "summary.csv"), "w") do io
        println(io, "Z,m2,init,seed,q_bare,q_initialized,q_mean_peak,q_modal_peak,mean_peak_S,mean_M2,mean_energy_density,mean_orientation_max,warmup_acceptance,measurement_acceptance,samples")
        @printf(io, "%.12g,%.12g,%s,%d,%.12g,%.12g,%.12g,%.12g,%.17g,%.17g,%.17g,%.17g,%.12g,%.12g,%d\n",
                Z, m², init, seed, q_bare, q_modulated, geometry.q[mean_peak],
                geometry.q[modal_peak], L^3 * mean_powers[mean_peak] /
                length(geometry.members[mean_peak]), sum(m2_values) / samples,
                sum(energy_values) / samples, sum(selected_orientation) / samples,
                warmup_accepts / warmup, measurement_accepts / (samples * skip), samples)
    end
    @printf("modscan Z=%.3f m2=%.6f init=%s q_peak=%.6f acc=%.3f\n",
            Z, m², init, geometry.q[mean_peak], measurement_accepts / (samples * skip))
end

main()
