#!/usr/bin/env julia

using JLD2

length(ARGS) == 11 || error(
    "usage: validate_umbrella_checkpoint.jl PATH L Z M2 EPS N_LF REPLICAS MIN MAX KAPPA POWER"
)

path = ARGS[1]
expected = (
    L=parse(Int, ARGS[2]), Z=parse(Float64, ARGS[3]), m2=parse(Float64, ARGS[4]),
    eps=parse(Float64, ARGS[5]), n_lf=parse(Int, ARGS[6]), replicas=parse(Int, ARGS[7]),
    minimum=parse(Float64, ARGS[8]), maximum=parse(Float64, ARGS[9]),
    kappa=parse(Float64, ARGS[10]),
    power=parse(Float64, ARGS[11]),
)
close(left, right) = isapprox(Float64(left), Float64(right); rtol=2e-6, atol=2e-7)

jldopen(path, "r") do file
    file["schema_version"] == 3 || error("schema mismatch")
    file["sampler"] == "umbrella_exchange" || error("sampler mismatch")
    file["thermalization_complete"] || error("thermalization incomplete")
    file["L"] == expected.L || error("L mismatch")
    close(file["Z"], expected.Z) || error("Z mismatch")
    close(file["m²"], expected.m2) || error("mass mismatch")
    close(file["epsilon"], expected.eps) || error("epsilon mismatch")
    file["n_lf"] == expected.n_lf || error("n_lf mismatch")
    file["umbrella_replicas"] == expected.replicas || error("replica mismatch")
    centers = Float64.(file["umbrella_centers"])
    kappas = Float64.(file["umbrella_kappas"])
    coordinate = collect(range(0.0, 1.0; length=expected.replicas))
    expected_centers = expected.minimum .+ (expected.maximum - expected.minimum) .*
                       coordinate .^ expected.power
    all(close.(centers, expected_centers)) ||
        error("center mismatch")
    all(close.(kappas, fill(expected.kappa, expected.replicas))) || error("kappa mismatch")
end

println("valid umbrella checkpoint")
