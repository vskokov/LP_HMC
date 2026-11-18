#!/usr/bin/env julia

cd(@__DIR__)
using FFTW
using Printf
using Random
using Statistics

const L = parse(Int, get(ENV, "TI_L", "20"))
const FloatType = Float64
const cpu = !(lowercase(get(ENV, "TI_GPU", "false")) in ("1", "true", "yes"))
const λ = FloatType(4.0)
const T = FloatType(1.0)
const Z = FloatType(parse(Float64, ENV["TI_Z"]))
const ε = FloatType(parse(Float64, get(ENV, "TI_EPS", "0.0085")))
const n_lf = parse(Int, get(ENV, "TI_N_LF", "15"))

include("../src/simulation.jl")
include("structure_factor_observables.jl")

to_backend(field) = cpu ? field : CuArray(field)
to_host(field) = cpu ? field : Array(field)

function mode_field(index::CartesianIndex{3}, amplitude)
    n = Tuple(index) .- 1
    field = zeros(Float64, L, L, L)
    for coordinate in CartesianIndices(field)
        phase = 2π * sum(n[axis] * (Tuple(coordinate)[axis] - 1) / L for axis in 1:3)
        field[coordinate] = amplitude * cos(phase)
    end
    return field
end

function independent_mode_indices(geometry, shell_index, dimension)
    chosen = CartesianIndex{3}[]
    directions = Vector{Float64}[]
    for group in geometry.pair_groups[shell_index]
        candidate = lattice_momentum_direction(first(group), L)
        trial = isempty(directions) ? reshape(candidate, 3, 1) : hcat(directions..., candidate)
        if rank(trial; atol=1e-10) > length(directions)
            push!(chosen, first(group)); push!(directions, candidate)
            length(chosen) == dimension && return chosen
        end
    end
    error("shell $(geometry.q[shell_index]) does not span rank $(dimension)")
end

function rank_mode_field(geometry, shell_index, dimension, amplitude)
    modes = independent_mode_indices(geometry, shell_index, dimension)
    field = zeros(Float64, L, L, L)
    for index in modes
        field .+= mode_field(index, amplitude / sqrt(dimension))
    end
    return field
end

function initial_field(kind, mass, geometry, shell_index)
    if kind == :high_mass
        host = 0.1 .* randn(Float64, L, L, L)
    elseif kind == :uniform
        amplitude = sqrt(max(-mass / Float64(λ), 0.05))
        host = fill(amplitude, L, L, L) .+ 0.02 .* randn(L, L, L)
    elseif kind in (:shell, :rank2, :rank3)
        q = geometry.q[shell_index]
        quadratic = mass + Float64(Z) * q + q^2
        amplitude = sqrt(max(-4quadratic / (3Float64(λ)), 0.25))
        dimension = kind == :shell ? 1 : (kind == :rank2 ? 2 : 3)
        host = rank_mode_field(geometry, shell_index, dimension, amplitude) .+
               0.02 .* randn(L, L, L)
    else
        error("unknown branch kind $(kind)")
    end
    return to_backend(host)
end

function advance!(field, mass, sweeps)
    accepted = 0
    for _ in 1:sweeps
        success, _ = hmc_step!(field, mass, Z, ε, n_lf)
        accepted += success
    end
    return accepted
end

function batch_mcse(values; block_size=10)
    blocks = div(length(values), block_size)
    blocks >= 2 || return NaN
    means = [sum(@view values[(index - 1) * block_size + 1:index * block_size]) / block_size
             for index in 1:blocks]
    return std(means; corrected=true) / sqrt(blocks)
end

function measure_point!(field, mass, geometry, rank_index, settle, samples, skip)
    settle_accepts = advance!(field, mass, settle)
    powers = zeros(length(geometry.q))
    peak_counts = zeros(Int, length(geometry.q))
    q_density = Float64[]
    energy_density = Float64[]
    m2_global = Float64[]
    rank_values = NamedTuple[]
    sample_accepts = 0
    for _ in 1:samples
        sample_accepts += advance!(field, mass, skip)
        host_field = to_host(field)
        shell_values = shell_powers(host_field, geometry)
        powers .+= shell_values
        peak_counts[argmax(shell_values)] += 1
        stats = field_statistics(host_field)
        push!(q_density, stats.Q / L^3)
        push!(m2_global, stats.M2)
        push!(energy_density, Float64(calc_total_energy(field, mass, Z)) / L^3)
        push!(rank_values, modulation_rank_observables(host_field, geometry, rank_index))
    end
    powers ./= samples
    mean_peak = argmax(powers)
    modal_peak = argmax(peak_counts)
    return (
        q_density=mean(q_density),
        q_density_mcse=batch_mcse(q_density),
        energy_density=mean(energy_density),
        energy_density_mcse=batch_mcse(energy_density),
        m2_global=mean(m2_global),
        q_mean_peak=geometry.q[mean_peak],
        q_modal_peak=geometry.q[modal_peak],
        peak_S=L^3 * powers[mean_peak] / length(geometry.members[mean_peak]),
        peak_fraction=peak_counts[modal_peak] / samples,
        rank_lambda1=mean(value.lambda1 for value in rank_values),
        rank_lambda2=mean(value.lambda2 for value in rank_values),
        rank_lambda3=mean(value.lambda3 for value in rank_values),
        rank_effective_dimension=mean(value.effective_dimension for value in rank_values),
        rank_background_per_mode=mean(value.background_per_mode for value in rank_values),
        rank_raw_excess_power=mean(value.raw_excess_power for value in rank_values),
        rank_excess_power=mean(value.excess_power for value in rank_values),
        settle_acceptance=settle_accepts / settle,
        sample_acceptance=sample_accepts / (samples * skip),
    )
end

function main()
    seed = parse(Int, ENV["TI_SEED"])
    Random.seed!(seed)
    !cpu && CUDA.seed!(seed)
    !cpu && (CUDA.functional() || error("CUDA is not functional"))
    masses = sort(parse.(Float64, split(ENV["TI_MASSES"], ";")))
    output = abspath(ENV["TI_OUTPUT"])
    settle = parse(Int, get(ENV, "TI_SETTLE", "100"))
    initial_settle = parse(Int, get(ENV, "TI_INITIAL_SETTLE", "300"))
    samples = parse(Int, get(ENV, "TI_SAMPLES", "100"))
    skip = parse(Int, get(ENV, "TI_SKIP", "2"))
    shell_count = parse(Int, get(ENV, "TI_SHELL_COUNT", "5"))
    geometry = momentum_shells(L)
    q_bare = clamp(-Float64(Z) / 2, 0.0, 12.0)
    nonzero = findall(q -> q > 1e-12, geometry.q)
    target_q = parse(Float64, get(ENV, "TI_TARGET_Q", string(q_bare)))
    nearest = sort(nonzero; by=index -> (abs(geometry.q[index] - target_q), geometry.q[index]))
    shell_indices = sort(nearest[1:min(shell_count, length(nearest))]; by=index -> geometry.q[index])
    branches = [(:uniform, "uniform", 0)]
    append!(branches, [(:shell, "shell_$(index)", index) for index in shell_indices])
    rank_starts = lowercase(get(ENV, "TI_RANK_STARTS", "false")) in ("1", "true", "yes")
    if rank_starts
        for index in shell_indices, dimension in (2, 3)
            push!(branches, (dimension == 2 ? :rank2 : :rank3,
                             "rank$(dimension)_shell_$(index)", index))
        end
    end
    push!(branches, (:high_mass, "high_mass", 0))
    default_rank_index = first(sort(nonzero; by=index -> abs(geometry.q[index] - q_bare)))

    mkpath(dirname(output))
    temporary = output * ".tmp"
    open(temporary, "w") do io
        println(io, "Z,branch,m2,q_bare,q_initialized,Q_density,Q_density_mcse,M2_global,energy_density,energy_density_mcse,q_mean_peak,q_modal_peak,peak_S,peak_fraction,rank_lambda1,rank_lambda2,rank_lambda3,rank_effective_dimension,rank_background_per_mode,rank_raw_excess_power,rank_excess_power,settle_acceptance,sample_acceptance,samples,shell_index")
        for (kind, branch, shell_index) in branches
            branch_masses = kind == :high_mass ? reverse(masses) : masses
            field = initial_field(kind, first(branch_masses), geometry, shell_index)
            initialized_q = kind in (:shell, :rank2, :rank3) ? geometry.q[shell_index] :
                            (kind == :uniform ? 0.0 : NaN)
            rank_index = shell_index > 0 ? shell_index : default_rank_index
            for (index, mass) in enumerate(branch_masses)
                result = measure_point!(field, mass, geometry, rank_index,
                                        index == 1 ? initial_settle : settle,
                                        samples, skip)
                @printf(io, "%.12g,%s,%.12g,%.12g,%.12g,%.17g,%.17g,%.17g,%.17g,%.17g,%.12g,%.12g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.12g,%.12g,%d,%d\n",
                        Z, branch, mass, q_bare, initialized_q,
                        result.q_density, result.q_density_mcse, result.m2_global,
                        result.energy_density, result.energy_density_mcse,
                        result.q_mean_peak, result.q_modal_peak, result.peak_S,
                        result.peak_fraction, result.rank_lambda1, result.rank_lambda2,
                        result.rank_lambda3, result.rank_effective_dimension,
                        result.rank_background_per_mode, result.rank_raw_excess_power,
                        result.rank_excess_power, result.settle_acceptance,
                        result.sample_acceptance, samples, shell_index)
                flush(io)
            end
        end
    end
    mv(temporary, output; force=true)
    @printf("multishell_ti backend=%s L=%d Z=%.3f masses=%d shells=%s output=%s\n",
            cpu ? "cpu" : "cuda", L, Z, length(masses),
            join(geometry.q[shell_indices], ";"), output)
end

main()
