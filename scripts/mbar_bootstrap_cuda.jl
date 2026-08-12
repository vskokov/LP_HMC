#!/usr/bin/env julia

using ArgParse
using CUDA
using Printf

function parse_cli()
    settings = ArgParseSettings()
    @add_arg_table settings begin
        "--directory"
            arg_type = String
            required = true
        "--samples"
            arg_type = Int
            required = true
        "--sources"
            arg_type = Int
            required = true
        "--runs"
            arg_type = Int
            required = true
        "--targets"
            arg_type = Int
            required = true
        "--draws"
            arg_type = Int
            required = true
        "--starts-per-draw"
            arg_type = Int
            required = true
        "--batch-size"
            arg_type = Int
            default = 8
        "--target-chunk"
            arg_type = Int
            default = 16
        "--tolerance"
            arg_type = Float64
            default = 1e-10
        "--max-iterations"
            arg_type = Int
            default = 10_000
    end
    return parse_args(settings)
end

read_vector(path, ::Type{T}, count) where {T} = open(path, "r") do io
    read!(io, Vector{T}(undef, count))
end

function gather_kernel!(destination, source, starts, run_of_sample, local_position,
                        run_data_offsets, run_start_offsets, run_sizes, block_sizes,
                        samples)
    flat = (blockIdx().x - 1) * blockDim().x + threadIdx().x
    if flat <= length(destination)
        sample = (flat - 1) % samples + 1
        draw = (flat - 1) ÷ samples + 1
        run = run_of_sample[sample]
        position = local_position[sample]
        block_size = block_sizes[run]
        block = position ÷ block_size
        within = position % block_size
        start = starts[run_start_offsets[run] + block, draw]
        source_local = (start + within) % run_sizes[run]
        destination[sample, draw] = source[run_data_offsets[run] + source_local]
    end
    return
end

function gather_batch!(destination, source, starts, metadata, samples)
    threads = 256
    blocks = cld(length(destination), threads)
    run_of_sample, local_position, run_data_offsets, run_start_offsets,
        run_sizes, block_sizes = metadata
    @cuda threads=threads blocks=blocks gather_kernel!(
        destination, source, starts, run_of_sample, local_position,
        run_data_offsets, run_start_offsets, run_sizes, block_sizes, samples
    )
end

function denominator_kernel!(denominator, Q, G, source_m2, source_Z,
                             log_counts, free_energies, source_count)
    index = (blockIdx().x - 1) * blockDim().x + threadIdx().x
    if index <= length(denominator)
        sample = (index - 1) % size(Q, 1) + 1
        draw = (index - 1) ÷ size(Q, 1) + 1
        q = Q[sample, draw]
        g = G[sample, draw]
        maximum_value = -Inf
        for source in 1:source_count
            value = log_counts[source] + free_energies[source, draw] -
                    0.5 * (source_m2[source] * q + source_Z[source] * g)
            maximum_value = max(maximum_value, value)
        end
        total = 0.0
        for source in 1:source_count
            value = log_counts[source] + free_energies[source, draw] -
                    0.5 * (source_m2[source] * q + source_Z[source] * g)
            total += exp(value - maximum_value)
        end
        denominator[sample, draw] = maximum_value + log(total)
    end
    return
end

function solve_mbar!(Q, G, source_m2, source_Z, log_counts;
                     tolerance, max_iterations)
    samples, draws = size(Q)
    source_count = length(source_m2)
    source_m2_host = Array(source_m2)
    source_Z_host = Array(source_Z)
    denominator = similar(Q)
    work = similar(Q)
    free_host = zeros(Float64, source_count, draws)
    free_device = CuArray(free_host)
    threads = 256
    blocks = cld(length(denominator), threads)
    iterations = 0
    converged = false
    for iteration in 1:max_iterations
        @cuda threads=threads blocks=blocks denominator_kernel!(
            denominator, Q, G, source_m2, source_Z, log_counts,
            free_device, source_count
        )
        updated = similar(free_host)
        for source in 1:source_count
            mass = source_m2_host[source]
            zvalue = source_Z_host[source]
            @. work = -0.5 * (mass * Q + zvalue * G) - denominator
            maxima = maximum(work; dims=1)
            totals = sum(exp.(work .- maxima); dims=1)
            updated[source, :] .= vec(Array(-(maxima .+ log.(totals))))
        end
        updated .-= updated[1:1, :]
        difference = maximum(abs.(updated .- free_host))
        free_host = updated
        copyto!(free_device, free_host)
        iterations = iteration
        if difference < tolerance
            converged = true
            break
        end
    end
    converged || error("batched MBAR did not converge in $max_iterations iterations")
    @cuda threads=threads blocks=blocks denominator_kernel!(
        denominator, Q, G, source_m2, source_Z, log_counts,
        free_device, source_count
    )
    return denominator, iterations
end

function evaluate_targets(Q, G, M2, M4, denominator, target_Z, target_m2;
                          chunk_size=16)
    samples, draws = size(Q)
    target_count = length(target_Z)
    result = Matrix{Float64}(undef, draws, target_count)
    for draw in 1:draws
        q = reshape(@view(Q[:, draw]), 1, samples)
        g = reshape(@view(G[:, draw]), 1, samples)
        m2_values = @view(M2[:, draw])
        m4_values = @view(M4[:, draw])
        denom = reshape(@view(denominator[:, draw]), 1, samples)
        for first in 1:chunk_size:target_count
            last = min(target_count, first + chunk_size - 1)
            tz = reshape(@view(target_Z[first:last]), :, 1)
            tm = reshape(@view(target_m2[first:last]), :, 1)
            logweights = @. -0.5 * (tm * q + tz * g) - denom
            maxima = maximum(logweights; dims=2)
            weights = exp.(logweights .- maxima)
            normalizations = sum(weights; dims=2)
            means2 = (weights * m2_values) ./ vec(normalizations)
            means4 = (weights * m4_values) ./ vec(normalizations)
            result[draw, first:last] .= Array(@. 1.0 - means4 / (3.0 * means2^2))
        end
    end
    return result
end

function main()
    args = parse_cli()
    directory = args["directory"]
    samples = args["samples"]
    source_count = args["sources"]
    run_count = args["runs"]
    target_count = args["targets"]
    draws = args["draws"]
    starts_per_draw = args["starts-per-draw"]
    batch_size = max(1, min(args["batch-size"], draws))

    CUDA.functional() || error("CUDA is not functional")
    @printf(stderr, "CUDA MBAR backend: device=%s, samples=%d, draws=%d, batch=%d\n",
            CUDA.name(CUDA.device()), samples, draws, batch_size)

    base_M2 = CuArray(read_vector(joinpath(directory, "M2.bin"), Float64, samples))
    base_M4 = CuArray(read_vector(joinpath(directory, "M4.bin"), Float64, samples))
    base_Q = CuArray(read_vector(joinpath(directory, "Q.bin"), Float64, samples))
    base_G = CuArray(read_vector(joinpath(directory, "G.bin"), Float64, samples))
    source_Z = CuArray(read_vector(joinpath(directory, "source_Z.bin"), Float64, source_count))
    source_m2 = CuArray(read_vector(joinpath(directory, "source_m2.bin"), Float64, source_count))
    source_counts = read_vector(joinpath(directory, "source_counts.bin"), Int64, source_count)
    log_counts = CuArray(log.(Float64.(source_counts)))
    target_Z = CuArray(read_vector(joinpath(directory, "target_Z.bin"), Float64, target_count))
    target_m2 = CuArray(read_vector(joinpath(directory, "target_m2.bin"), Float64, target_count))

    run_of_sample = CuArray(read_vector(joinpath(directory, "run_of_sample.bin"), Int32, samples))
    local_position = CuArray(read_vector(joinpath(directory, "local_position.bin"), Int32, samples))
    run_data_offsets = CuArray(read_vector(joinpath(directory, "run_data_offsets.bin"), Int64, run_count))
    run_start_offsets = CuArray(read_vector(joinpath(directory, "run_start_offsets.bin"), Int64, run_count))
    run_sizes = CuArray(read_vector(joinpath(directory, "run_sizes.bin"), Int64, run_count))
    block_sizes = CuArray(read_vector(joinpath(directory, "block_sizes.bin"), Int64, run_count))
    metadata = (run_of_sample, local_position, run_data_offsets,
                run_start_offsets, run_sizes, block_sizes)

    starts_io = open(joinpath(directory, "starts.bin"), "r")
    estimates_io = open(joinpath(directory, "estimates.bin"), "w")
    started = time()
    completed = 0
    try
        while completed < draws
            current = min(batch_size, draws - completed)
            host_starts = Matrix{Int32}(undef, starts_per_draw, current)
            read!(starts_io, vec(host_starts))
            starts = CuArray(host_starts)
            M2 = CuArray{Float64}(undef, samples, current)
            M4 = similar(M2); Q = similar(M2); G = similar(M2)
            gather_batch!(M2, base_M2, starts, metadata, samples)
            gather_batch!(M4, base_M4, starts, metadata, samples)
            gather_batch!(Q, base_Q, starts, metadata, samples)
            gather_batch!(G, base_G, starts, metadata, samples)
            denominator, iterations = solve_mbar!(
                Q, G, source_m2, source_Z, log_counts;
                tolerance=args["tolerance"], max_iterations=args["max-iterations"]
            )
            estimates = evaluate_targets(
                Q, G, M2, M4, denominator, target_Z, target_m2;
                chunk_size=args["target-chunk"]
            )
            write(estimates_io, vec(permutedims(estimates)))
            completed += current
            elapsed = time() - started
            rate = completed / elapsed
            eta = (draws - completed) / rate
            @printf(stderr,
                    "CUDA MBAR bootstrap: %d/%d (%.0f%%), iterations=%d, elapsed=%.1fs, ETA=%.1fs\n",
                    completed, draws, 100 * completed / draws, iterations, elapsed, eta)
            flush(stderr)
            CUDA.reclaim()
        end
    finally
        close(starts_io)
        close(estimates_io)
    end
end

main()
