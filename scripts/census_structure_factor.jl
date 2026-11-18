#!/usr/bin/env julia

using JLD2
using Printf
include("structure_factor_observables.jl")

length(ARGS) == 2 || error("usage: census_structure_factor.jl CHECKPOINT OUTPUT.csv")
checkpoint, output = abspath.(ARGS)

payload = jldopen(checkpoint, "r") do file
    sampler = String(file["sampler"])
    sampler in ("umbrella_exchange", "umbrella_collection", "structure_factor_collection") ||
        error("unsupported checkpoint sampler $(sampler)")
    fields = file["replica_fields"]
    (
        fields=fields,
        L=Int(haskey(file, "L") ? file["L"] : size(fields, 1)),
        Z=Float64(file["Z"]), m2=Float64(file["m²"]),
        centers=Float64.(file["umbrella_centers"]),
        kappas=Float64.(file["umbrella_kappas"]),
        walkers=Int.(file["walker_ids"]),
        phase=String(file["init_phase"]), sampler=sampler,
        selected_q=(haskey(file, "selected_q") ? Float64(file["selected_q"]) : NaN),
    )
end

geometry = momentum_shells(payload.L)
selected_index = isfinite(payload.selected_q) ? selected_shell_index(geometry, payload.selected_q) : 0
mkpath(dirname(output))
temporary = output * ".tmp.$(getpid())"
open(temporary, "w") do io
    println(io, "# schema_version=$(selected_index > 0 ? 2 : 1)")
    println(io, "# source_checkpoint=$(checkpoint)")
    println(io, "# source_sampler=$(payload.sampler)")
    println(io, "# L=$(payload.L)")
    println(io, "# Z=$(repr(payload.Z))")
    println(io, "# m2=$(repr(payload.m2))")
    println(io, "# init_phase=$(payload.phase)")
    println(io, "# shell_q=$(join(repr.(geometry.q), ";"))")
    println(io, "# shell_degeneracy=$(join(length.(geometry.members), ";"))")
    if selected_index > 0
        println(io, "# selected_q=$(repr(geometry.q[selected_index]))")
        println(io, "# selected_degeneracy=$(length(geometry.members[selected_index]))")
    end
    shell_names = [@sprintf("P_q%03d", index - 1) for index in eachindex(geometry.q)]
    rank_names = selected_index > 0 ? [
        "rank_tensor_xx", "rank_tensor_yy", "rank_tensor_zz", "rank_tensor_xy",
        "rank_tensor_xz", "rank_tensor_yz", "rank_lambda1", "rank_lambda2",
        "rank_lambda3", "rank_effective_dimension", "rank_background_per_mode",
        "rank_raw_power", "rank_raw_excess_power", "rank_excess_power",
    ] : String[]
    println(io, join(vcat(["slot", "walker_id", "umbrella_center", "umbrella_kappa",
                           "M", "M2", "Q", "G"], rank_names, shell_names), ","))
    for slot in axes(payload.fields, 4)
        field = @view payload.fields[:, :, :, slot]
        stats = field_statistics(field)
        powers = shell_powers(field, geometry)
        @printf(io, "%d,%d,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g",
                slot, payload.walkers[slot], payload.centers[slot], payload.kappas[slot],
                stats.M, stats.M2, stats.Q, stats.G)
        if selected_index > 0
            rank = if geometry.q[selected_index] > 1e-12
                modulation_rank_observables(field, geometry, selected_index)
            else
                (tensor_xx=0.0, tensor_yy=0.0, tensor_zz=0.0,
                 tensor_xy=0.0, tensor_xz=0.0, tensor_yz=0.0,
                 lambda1=0.0, lambda2=0.0, lambda3=0.0,
                 effective_dimension=0.0, background_per_mode=0.0,
                 raw_power=0.0, raw_excess_power=0.0, excess_power=0.0)
            end
            for value in (rank.tensor_xx, rank.tensor_yy, rank.tensor_zz,
                          rank.tensor_xy, rank.tensor_xz, rank.tensor_yz,
                          rank.lambda1, rank.lambda2, rank.lambda3,
                          rank.effective_dimension, rank.background_per_mode,
                          rank.raw_power, rank.raw_excess_power, rank.excess_power)
                @printf(io, ",%.17g", value)
            end
        end
        for power in powers
            @printf(io, ",%.17g", power)
        end
        println(io)
    end
end
mv(temporary, output; force=true)
println("census=$(output)")
