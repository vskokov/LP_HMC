#!/usr/bin/env julia

using JLD2

length(ARGS) in (7, 10, 11, 14) ||
    error("usage: validate_checkpoint.jl PATH L Z M2 EPS N_LF SEED [startup STARTUP_EPS STARTUP_N_LF STARTUP_SWEEPS | TEMPERING_REPLICAS MASS_SPAN SWAP_EVERY [INIT_PHASE [STARTUP_EPS STARTUP_N_LF STARTUP_SWEEPS]]]")
path, L_text, Z_text, m2_text, eps_text, n_lf_text, seed_text = ARGS[1:7]
single_startup = length(ARGS) == 11 && ARGS[8] == "startup"
tempering = length(ARGS) >= 10 && !single_startup

expected = (
    L=parse(Int, L_text), Z=parse(Float64, Z_text), m2=parse(Float64, m2_text),
    epsilon=parse(Float64, eps_text), n_lf=parse(Int, n_lf_text), seed=parse(Int, seed_text),
)

try
    jldopen(path, "r") do file
        required = ("ϕ", "schema_version", "L", "Z", "m²", "epsilon", "n_lf", "seed")
        all(haskey(file, key) for key in required) || error("missing checkpoint metadata")
        haskey(file, "thermalization_complete") || error("checkpoint predates completion guard")
        file["thermalization_complete"] == true || error("thermalization is incomplete")
        file["schema_version"] in (1, 2) || error("unsupported checkpoint schema")
        size(file["ϕ"]) == (expected.L, expected.L, expected.L) || error("field size mismatch")
        file["L"] == expected.L || error("L mismatch")
        Float64(file["Z"]) == expected.Z || error("Z mismatch")
        Float64(file["m²"]) == expected.m2 || error("m2 mismatch")
        Float64(file["epsilon"]) == expected.epsilon || error("epsilon mismatch")
        file["n_lf"] == expected.n_lf || error("n_lf mismatch")
        file["seed"] == expected.seed || error("seed mismatch")
        if single_startup
            startup_required = ("startup_epsilon", "startup_n_lf", "startup_sweeps")
            all(haskey(file, key) for key in startup_required) ||
                error("missing startup HMC metadata")
            Float64(file["startup_epsilon"]) == parse(Float64, ARGS[9]) ||
                error("startup epsilon mismatch")
            file["startup_n_lf"] == parse(Int, ARGS[10]) ||
                error("startup n_lf mismatch")
            file["startup_sweeps"] == parse(Int, ARGS[11]) ||
                error("startup sweeps mismatch")
        end
        if tempering
            expected_replicas = parse(Int, ARGS[8])
            expected_span = parse(Float64, ARGS[9])
            expected_swap_every = parse(Int, ARGS[10])
            expected_init_phase = length(ARGS) >= 11 ? ARGS[11] : "hot"
            replica_required = (
                "sampler", "replica_fields", "tempering_replicas", "mass_span",
                "swap_every", "masses", "walker_ids", "walker_stage", "round_trips",
                "swap_phase", "sweeps", "hmc_attempts", "hmc_accepts",
                "swap_attempts", "swap_accepts",
            )
            all(haskey(file, key) for key in replica_required) ||
                error("missing replica checkpoint metadata")
            file["schema_version"] == 2 || error("replica checkpoint schema mismatch")
            file["sampler"] == "replica_exchange" || error("sampler mismatch")
            file["tempering_replicas"] == expected_replicas || error("replica count mismatch")
            Float64(file["mass_span"]) == expected_span || error("mass span mismatch")
            file["swap_every"] == expected_swap_every || error("swap cadence mismatch")
            checkpoint_init_phase = haskey(file, "init_phase") ? String(file["init_phase"]) : "hot"
            checkpoint_init_phase == expected_init_phase || error("initial phase mismatch")
            if length(ARGS) == 14
                startup_required = ("startup_epsilon", "startup_n_lf", "startup_sweeps")
                all(haskey(file, key) for key in startup_required) ||
                    error("missing startup HMC metadata")
                Float64(file["startup_epsilon"]) == parse(Float64, ARGS[12]) ||
                    error("startup epsilon mismatch")
                file["startup_n_lf"] == parse(Int, ARGS[13]) ||
                    error("startup n_lf mismatch")
                file["startup_sweeps"] == parse(Int, ARGS[14]) ||
                    error("startup sweeps mismatch")
            end
            size(file["replica_fields"]) ==
                (expected.L, expected.L, expected.L, expected_replicas) ||
                error("replica field size mismatch")
            masses = collect(range(expected.m2 - expected_span / 2,
                                   expected.m2 + expected_span / 2;
                                   length=expected_replicas))
            masses[(expected_replicas + 1) ÷ 2] = expected.m2
            Float64.(file["masses"]) == masses || error("mass ladder mismatch")
        else
            file["schema_version"] == 1 || error("single-replica checkpoint schema mismatch")
        end
    end
catch exception
    println(stderr, "invalid checkpoint: ", sprint(showerror, exception))
    exit(1)
end

println("valid checkpoint")
