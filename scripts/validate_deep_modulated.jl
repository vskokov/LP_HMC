#!/usr/bin/env julia

cd(@__DIR__)
using FFTW
using Printf
using Random

const L = parse(Int, get(ENV, "MODULATED_L", "16"))
const FloatType = Float64
const ArrayType = Array
const cpu = true
const λ = FloatType(4.0)
const T = FloatType(1.0)
const Z = FloatType(parse(Float64, get(ENV, "MODULATED_Z", "-4.0")))
const m² = FloatType(parse(Float64, get(ENV, "MODULATED_M2", "-1.0")))
const ε = FloatType(parse(Float64, get(ENV, "MODULATED_EPS", "0.0195")))
const n_lf = parse(Int, get(ENV, "MODULATED_N_LF", "15"))

include("../src/simulation.jl")
include("structure_factor_observables.jl")

function stripe(axis::Int, mode::Int, amplitude::Float64, phase::Float64=0.0)
    field = zeros(Float64, L, L, L)
    for index in CartesianIndices(field)
        coordinate = Tuple(index)[axis] - 1
        field[index] = amplitude * cos(2π * mode * coordinate / L + phase)
    end
    return field
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
    iseven(L) || error("MODULATED_L must be even")
    Random.seed!(parse(Int, get(ENV, "MODULATED_SEED", "417")))
    geometry = momentum_shells(L)
    q_mean_field = clamp(-Float64(Z) / 2, 0.0, 12.0)
    shell_index = argmin(abs.(geometry.q .- q_mean_field))
    selected_q = geometry.q[shell_index]
    # Use the lowest axial Fourier integer on the selected shell when possible.
    axial_modes = [(n, 4sinpi(n / L)^2) for n in 1:div(L, 2)]
    mode, axial_q = axial_modes[argmin(abs(last(item) - selected_q) for item in axial_modes)]
    abs(axial_q - selected_q) < 5e-11 || error("selected shell has no axial representative")
    quadratic = Float64(m²) + Float64(Z) * selected_q + selected_q^2
    quadratic < 0 || error("chosen mode is not mean-field unstable")
    amplitude = sqrt(-4quadratic / (3Float64(λ)))

    synthetic_powers = zeros(length(geometry.q))
    synthetic_orientations = Float64[]
    synthetic_dimensions = Float64[]
    synthetic_count = 0
    for axis in 1:3, phase in (0.0, π / 5, 2π / 5)
        field = stripe(axis, mode, amplitude, phase)
        observables = fourier_shell_observables(field, geometry, shell_index)
        synthetic_powers .+= observables.powers
        push!(synthetic_orientations, observables.maximum_fraction)
        push!(synthetic_dimensions,
              modulation_rank_observables(field, geometry, shell_index).effective_dimension)
        synthetic_count += 1
    end
    synthetic_powers ./= synthetic_count
    synthetic_peak = argmax(synthetic_powers)

    field = stripe(1, mode, amplitude)
    field .+= 0.02 .* randn(size(field))
    warmup = parse(Int, get(ENV, "MODULATED_WARMUP", "400"))
    samples = parse(Int, get(ENV, "MODULATED_SAMPLES", "100"))
    skip = parse(Int, get(ENV, "MODULATED_SKIP", "2"))
    accepted = advance!(field, warmup)
    hmc_powers = zeros(length(geometry.q))
    orientation_max = Float64[]
    orientation_participation = Float64[]
    rank_lambda1 = Float64[]
    rank_lambda2 = Float64[]
    rank_lambda3 = Float64[]
    rank_dimensions = Float64[]
    rank_raw_excess = Float64[]
    accepted_measure = 0
    for _ in 1:samples
        accepted_measure += advance!(field, skip)
        observables = fourier_shell_observables(field, geometry, shell_index)
        hmc_powers .+= observables.powers
        push!(orientation_max, observables.maximum_fraction)
        push!(orientation_participation, observables.participation)
        rank_observables = modulation_rank_observables(field, geometry, shell_index)
        push!(rank_lambda1, rank_observables.lambda1)
        push!(rank_lambda2, rank_observables.lambda2)
        push!(rank_lambda3, rank_observables.lambda3)
        push!(rank_dimensions, rank_observables.effective_dimension)
        push!(rank_raw_excess, rank_observables.raw_excess_power)
    end
    hmc_powers ./= samples
    hmc_peak = argmax(hmc_powers)

    output_dir = abspath(get(ENV, "MODULATED_OUTPUT",
                             "../reports/structure_factor_cpu/deep_modulated_validation"))
    mkpath(output_dir)
    open(joinpath(output_dir, "spectrum.csv"), "w") do io
        println(io, "q,degeneracy,synthetic_S_per_mode,hmc_S_per_mode")
        volume = L^3
        for index in eachindex(geometry.q)
            degeneracy = length(geometry.members[index])
            @printf(io, "%.12g,%d,%.17g,%.17g\n", geometry.q[index], degeneracy,
                    volume * synthetic_powers[index] / degeneracy,
                    volume * hmc_powers[index] / degeneracy)
        end
    end
    open(joinpath(output_dir, "summary.csv"), "w") do io
        println(io, "L,Z,m2,q_mean_field,q_selected,q_synthetic_peak,q_hmc_peak,mode,amplitude,warmup_acceptance,measurement_acceptance,synthetic_orientation_max,hmc_orientation_max,hmc_orientation_participation,synthetic_rank_effective_dimension,hmc_rank_lambda1,hmc_rank_lambda2,hmc_rank_lambda3,hmc_rank_effective_dimension,hmc_rank_raw_excess_power")
        @printf(io, "%d,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%d,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g\n",
                L, Z, m², q_mean_field, selected_q, geometry.q[synthetic_peak], geometry.q[hmc_peak],
                mode, amplitude, accepted / warmup, accepted_measure / (samples * skip),
                sum(synthetic_orientations) / length(synthetic_orientations),
                sum(orientation_max) / length(orientation_max),
                sum(orientation_participation) / length(orientation_participation),
                sum(synthetic_dimensions) / length(synthetic_dimensions),
                sum(rank_lambda1) / length(rank_lambda1),
                sum(rank_lambda2) / length(rank_lambda2),
                sum(rank_lambda3) / length(rank_lambda3),
                sum(rank_dimensions) / length(rank_dimensions),
                sum(rank_raw_excess) / length(rank_raw_excess))
    end
    @printf("deep_modulated q_mf=%.6f q_shell=%.6f synthetic_peak=%.6f hmc_peak=%.6f acceptance=%.3f output=%s\n",
            q_mean_field, selected_q, geometry.q[synthetic_peak], geometry.q[hmc_peak],
            accepted_measure / (samples * skip), output_dir)
end

main()
