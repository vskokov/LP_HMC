#!/usr/bin/env julia

using JLD2

length(ARGS) == 14 || error(
    "usage: validate_umbrella_checkpoint.jl PATH L Z M2 EPS N_LF REPLICAS MIN MAX KAPPA POWER MIN_SWEEPS MIN_RT_FRACTION MIN_SWAP_ACCEPTANCE"
)

path = ARGS[1]
expected = (
    L=parse(Int, ARGS[2]), Z=parse(Float64, ARGS[3]), m2=parse(Float64, ARGS[4]),
    eps=parse(Float64, ARGS[5]), n_lf=parse(Int, ARGS[6]), replicas=parse(Int, ARGS[7]),
    minimum=parse(Float64, ARGS[8]), maximum=parse(Float64, ARGS[9]),
    kappa=parse(Float64, ARGS[10]),
    power=parse(Float64, ARGS[11]),
    minimum_sweeps=parse(Int, ARGS[12]),
    minimum_round_trip_fraction=parse(Float64, ARGS[13]),
    minimum_swap_acceptance=parse(Float64, ARGS[14]),
)
close(left, right) = isapprox(Float64(left), Float64(right); rtol=2e-6, atol=2e-7)

passed = jldopen(path, "r") do file
    file["schema_version"] == 3 || error("schema mismatch")
    file["sampler"] == "umbrella_exchange" || error("sampler mismatch")
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
    round_trips = file["round_trips"]
    fraction = count(>(0), round_trips) / length(round_trips)
    attempts, accepts = file["swap_attempts"], file["swap_accepts"]
    swap_rates = [attempts[i] == 0 ? 0.0 : accepts[i] / attempts[i]
                  for i in eachindex(attempts)]
    file["sweeps"] >= expected.minimum_sweeps &&
        fraction >= expected.minimum_round_trip_fraction &&
        minimum(swap_rates) >= expected.minimum_swap_acceptance
end

if passed
    println("valid complete umbrella checkpoint")
else
    println("valid resumable umbrella checkpoint")
    exit(10)
end
