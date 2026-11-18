#!/usr/bin/env julia

cd(@__DIR__)
using JLD2
using Printf
using FFTW
include("../src/modelA.jl")
include("structure_factor_observables.jl")

struct StructureRuntimeExceeded <: Exception end

function load_structure_state(path)
    payload = jldopen(path, "r") do file
        sampler = String(file["sampler"])
        sampler in ("umbrella_exchange", "umbrella_collection", "structure_factor_collection") ||
            error("unsupported sampler $(sampler)")
        sampler == "umbrella_exchange" && !file["thermalization_complete"] &&
            error("thermalization is incomplete")
        fields = file["replica_fields"]
        (
            sampler=sampler, fields=fields, masses=FloatType.(file["masses"]),
            centers=FloatType.(file["umbrella_centers"]),
            kappas=FloatType.(file["umbrella_kappas"]),
            walker_ids=Int.(file["walker_ids"]), walker_stage=Int.(file["walker_stage"]),
            round_trips=Int.(file["round_trips"]), swap_phase=Int(file["swap_phase"]),
            sweeps=Int(file["sweeps"]), hmc_attempts=Int.(file["hmc_attempts"]),
            hmc_accepts=Int.(file["hmc_accepts"]),
            swap_attempts=Int.(file["swap_attempts"]),
            swap_accepts=Int.(file["swap_accepts"]),
            init_phase=String(file["init_phase"]),
            structure_collected=(haskey(file, "structure_collected_samples") ?
                                 Int(file["structure_collected_samples"]) : 0),
            source_collected=(haskey(file, "source_collected_samples") ?
                              Int(file["source_collected_samples"]) :
                              (haskey(file, "collected_samples") ? Int(file["collected_samples"]) : 0)),
        )
    end
    cpu || error("structure-factor shard collection is CPU-only")
    nrep = size(payload.fields, 4)
    fields = [ArrayType(payload.fields[:, :, :, slot]) for slot in 1:nrep]
    state = ReplicaExchangeState(
        fields, payload.masses; umbrella_centers=payload.centers,
        umbrella_kappas=payload.kappas, walker_ids=payload.walker_ids,
        walker_stage=payload.walker_stage, round_trips=payload.round_trips,
        swap_phase=payload.swap_phase, sweeps=payload.sweeps,
        hmc_attempts=payload.hmc_attempts, hmc_accepts=payload.hmc_accepts,
        swap_attempts=payload.swap_attempts, swap_accepts=payload.swap_accepts,
    )
    return state, payload
end

function save_structure_state(path, state, payload, collected, selected_q, q_cut)
    temporary = path * ".tmp"
    host_fields = cat((Array(field) for field in state.fields)...; dims=4)
    jldsave(temporary, true;
        schema_version=1, sampler="structure_factor_collection",
        L=L, Z=Float64(Z), m²=Float64(m²), epsilon=Float64(ε), n_lf=n_lf,
        seed=seed, replica_fields=host_fields, masses=Float64.(state.masses),
        umbrella_centers=Float64.(state.umbrella_centers),
        umbrella_kappas=Float64.(state.umbrella_kappas),
        umbrella_power=Float64(umbrella_power), swap_every=swap_every,
        init_phase=payload.init_phase, walker_ids=state.walker_ids,
        walker_stage=state.walker_stage, round_trips=state.round_trips,
        swap_phase=state.swap_phase, sweeps=state.sweeps,
        hmc_attempts=state.hmc_attempts, hmc_accepts=state.hmc_accepts,
        swap_attempts=state.swap_attempts, swap_accepts=state.swap_accepts,
        structure_collected_samples=collected,
        source_collected_samples=payload.source_collected,
        selected_q=Float64(selected_q), q_cut=Float64(q_cut))
    mv(temporary, path; force=true)
end

function main()
    any(isnothing, (init_arg, parsed_args["output"], parsed_args["diagnostics"],
                    parsed_args["collection-checkpoint"])) && error("all input/output paths are required")
    samples = parsed_args["samples"]
    samples > 0 || error("--samples must be positive")
    selected_q = parse(Float64, get(ENV, "STRUCTURE_SELECTED_Q", "NaN"))
    q_cut = parse(Float64, get(ENV, "STRUCTURE_Q_CUT", "2.0"))
    isfinite(selected_q) && selected_q >= 0 || error("STRUCTURE_SELECTED_Q must be a nonnegative shell q")
    q_cut > 0 || error("STRUCTURE_Q_CUT must be positive")
    FFTW.set_num_threads(1)

    state, payload = load_structure_state(init_arg)
    payload.init_phase == init_phase || error("initial phase mismatch")
    expected_collected = parse(Int, get(ENV, "STRUCTURE_EXPECTED_COLLECTED",
                                        string(block_index * samples)))
    payload.structure_collected == expected_collected ||
        error("structure progress mismatch: checkpoint=$(payload.structure_collected), expected=$(expected_collected)")
    all(==(m²), state.masses) || error("checkpoint mass mismatch")
    geometry = momentum_shells(L)
    selected_index = selected_shell_index(geometry, selected_q)
    stored_indices = findall(q -> q <= q_cut + 5e-11, geometry.q)
    selected_index in stored_indices || push!(stored_indices, selected_index)
    sort!(unique!(stored_indices))
    shell_columns = [@sprintf("P_q%03d", index - 1) for index in stored_indices]

    output = abspath(parsed_args["output"])
    diagnostics = abspath(parsed_args["diagnostics"])
    checkpoint = abspath(parsed_args["collection-checkpoint"])
    mkpath.(dirname.((output, diagnostics, checkpoint)))
    output_tmp = output * ".tmp"
    diagnostics_tmp = diagnostics * ".tmp"
    started = time()
    try
        open(output_tmp, "w") do stats_io
            open(diagnostics_tmp, "w") do diag_io
                for (key, value) in (
                    "schema_version"=>2, "sampler"=>"structure_factor_umbrella",
                    "L"=>L, "Z"=>Float64(Z), "m2"=>Float64(m²), "temperature"=>Float64(T),
                    "lambda"=>Float64(λ), "seed"=>seed, "samples_per_window"=>samples,
                    "skip"=>parsed_args["skip"], "block_index"=>block_index,
                    "init_phase"=>init_phase, "selected_q"=>geometry.q[selected_index],
                    "selected_degeneracy"=>length(geometry.members[selected_index]),
                    "q_cut"=>q_cut,
                    "stored_shell_q"=>join(repr.(geometry.q[stored_indices]), ";"),
                    "stored_shell_degeneracy"=>join(length.(geometry.members[stored_indices]), ";"),
                )
                    println(stats_io, "# $(key)=$(value)")
                end
                base = ["trajectory", "slot", "walker_id", "umbrella_center", "umbrella_kappa",
                        "M", "M2", "M4", "Q", "G", "H", "P_selected", "orientation_max_fraction",
                        "orientation_participation", "rank_tensor_xx", "rank_tensor_yy",
                        "rank_tensor_zz", "rank_tensor_xy", "rank_tensor_xz", "rank_tensor_yz",
                        "rank_lambda1", "rank_lambda2", "rank_lambda3", "rank_effective_dimension",
                        "rank_background_per_mode", "rank_raw_power", "rank_raw_excess_power",
                        "rank_excess_power", "acceptance_rate"]
                println(stats_io, join(vcat(base, shell_columns), ","))
                println(diag_io, "trajectory,round_trips_total,walkers_with_round_trip,min_hmc_acceptance,min_swap_acceptance")
                for _ in 1:samples
                    old_attempts = copy(state.hmc_attempts)
                    old_accepts = copy(state.hmc_accepts)
                    replica_exchange!(state, parsed_args["skip"], Z, ε, n_lf; swap_every=swap_every)
                    interval_rates = acceptance_rates(state.hmc_accepts .- old_accepts,
                                                      state.hmc_attempts .- old_attempts)
                    all_stats = replica_sufficient_statistics(state)
                    for slot in eachindex(state.fields)
                        field = state.fields[slot]
                        fourier = fourier_shell_observables(field, geometry, selected_index)
                        rank = if geometry.q[selected_index] > 1e-12
                            modulation_rank_observables(field, geometry, selected_index)
                        else
                            (tensor_xx=0.0, tensor_yy=0.0, tensor_zz=0.0,
                             tensor_xy=0.0, tensor_xz=0.0, tensor_yz=0.0,
                             lambda1=0.0, lambda2=0.0, lambda3=0.0,
                             effective_dimension=0.0, background_per_mode=0.0,
                             raw_power=0.0, raw_excess_power=0.0, excess_power=0.0)
                        end
                        M2 = all_stats.M[slot]^2
                        H = Float64(calc_total_energy(field, m², Z))
                        values = Any[state.sweeps, slot, state.walker_ids[slot],
                                     state.umbrella_centers[slot], state.umbrella_kappas[slot],
                                     all_stats.M[slot], M2, M2^2, all_stats.Q[slot], all_stats.G[slot], H,
                                     fourier.powers[selected_index], fourier.maximum_fraction,
                                     fourier.participation,
                                     rank.tensor_xx, rank.tensor_yy, rank.tensor_zz,
                                     rank.tensor_xy, rank.tensor_xz, rank.tensor_yz,
                                     rank.lambda1, rank.lambda2, rank.lambda3,
                                     rank.effective_dimension, rank.background_per_mode,
                                     rank.raw_power, rank.raw_excess_power, rank.excess_power,
                                     interval_rates[slot]]
                        append!(values, fourier.powers[stored_indices])
                        println(stats_io, join(values, ","))
                    end
                    swap_rates = acceptance_rates(state.swap_accepts, state.swap_attempts)
                    println(diag_io, join((state.sweeps, sum(state.round_trips),
                        count(>(0), state.round_trips),
                        minimum(acceptance_rates(state.hmc_accepts, state.hmc_attempts)),
                        minimum(swap_rates)), ","))
                    if runtime_seconds > 0 && time() - started >= runtime_seconds
                        throw(StructureRuntimeExceeded())
                    end
                end
            end
        end
    catch error
        isfile(output_tmp) && rm(output_tmp)
        isfile(diagnostics_tmp) && rm(diagnostics_tmp)
        error isa StructureRuntimeExceeded && exit(75)
        rethrow()
    end
    mv(output_tmp, output; force=true)
    mv(diagnostics_tmp, diagnostics; force=true)
    save_structure_state(checkpoint, state, payload,
                         payload.structure_collected + samples, geometry.q[selected_index], q_cut)
    @printf("structure_shard=%d samples=%d checkpoint=%s\n", block_index, samples, checkpoint)
end

main()
