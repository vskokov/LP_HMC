#!/usr/bin/env julia

using JLD2

length(ARGS) == 7 || error("usage: validate_checkpoint.jl PATH L Z M2 EPS N_LF SEED")
path, L_text, Z_text, m2_text, eps_text, n_lf_text, seed_text = ARGS

expected = (
    L=parse(Int, L_text), Z=parse(Float64, Z_text), m2=parse(Float64, m2_text),
    epsilon=parse(Float64, eps_text), n_lf=parse(Int, n_lf_text), seed=parse(Int, seed_text),
)

try
    jldopen(path, "r") do file
        required = ("ϕ", "schema_version", "L", "Z", "m²", "epsilon", "n_lf", "seed")
        all(haskey(file, key) for key in required) || error("missing checkpoint metadata")
        file["schema_version"] == 1 || error("unsupported checkpoint schema")
        size(file["ϕ"]) == (expected.L, expected.L, expected.L) || error("field size mismatch")
        file["L"] == expected.L || error("L mismatch")
        Float64(file["Z"]) == expected.Z || error("Z mismatch")
        Float64(file["m²"]) == expected.m2 || error("m2 mismatch")
        Float64(file["epsilon"]) == expected.epsilon || error("epsilon mismatch")
        file["n_lf"] == expected.n_lf || error("n_lf mismatch")
        file["seed"] == expected.seed || error("seed mismatch")
    end
catch exception
    println(stderr, "invalid checkpoint: ", sprint(showerror, exception))
    exit(1)
end

println("valid checkpoint")
