#!/usr/bin/env julia

cd(@__DIR__)

using Printf

include("../src/modelA.jl")

const REWEIGHT_SCHEMA_VERSION = 1

function main()
    @init_state

    samples = parsed_args["samples"]
    skip = parsed_args["skip"]
    warmup = parsed_args["warmup"]
    output_arg = parsed_args["output"]

    samples > 0 || error("--samples must be positive")
    skip > 0 || error("--skip must be positive")
    warmup >= 0 || error("--warmup must be non-negative")
    isnothing(output_arg) && error("--output is required")

    output = abspath(output_arg)
    mkpath(dirname(output))
    temporary = output * ".tmp.$(getpid())"
    device = cpu ? "cpu" : "cuda"

    if warmup > 0
        acc = thermalize(ϕ, m², warmup)
        @printf("warmup_acceptance=%.6f\n", acc)
    end

    try
        open(temporary, "w") do io
            println(io, "# schema_version=$(REWEIGHT_SCHEMA_VERSION)")
            println(io, "# L=$(L)")
            println(io, "# Z=$(repr(Float64(Z)))")
            println(io, "# m2=$(repr(Float64(m²)))")
            println(io, "# epsilon=$(repr(Float64(ε)))")
            println(io, "# n_lf=$(n_lf)")
            println(io, "# seed=$(seed)")
            println(io, "# lambda=$(repr(Float64(λ)))")
            println(io, "# temperature=$(repr(Float64(T)))")
            println(io, "# float_type=$(FloatType)")
            println(io, "# device=$(device)")
            println(io, "# samples=$(samples)")
            println(io, "# skip=$(skip)")
            println(io, "# warmup=$(warmup)")
            println(io, "trajectory,M,M2,M4,Q,G,acceptance_rate")

            for i in 1:samples
                acceptance = thermalize(ϕ, m², skip)
                stats = sufficient_statistics(ϕ)
                M2 = stats.M^2
                M4 = M2^2
                trajectory = warmup + i * skip
                @printf(io, "%d,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g\n",
                        trajectory, stats.M, M2, M4, stats.Q, stats.G, acceptance)
                if i % 100 == 0
                    flush(io)
                    @printf("samples_completed=%d\n", i)
                    flush(stdout)
                end
            end
        end
        mv(temporary, output; force=true)
    finally
        isfile(temporary) && rm(temporary)
    end
    @printf("statistics=%s\n", output)
end

main()
