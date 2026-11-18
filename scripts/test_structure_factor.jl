#!/usr/bin/env julia

using Test
include("structure_factor_observables.jl")

@testset "momentum shells" begin
    L = 8
    geometry = momentum_shells(L)
    @test geometry.q[1] == 0.0
    @test sum(length, geometry.members) == L^3
    @test all(length(group) in (1, 2) for shell in geometry.pair_groups for group in shell)

    uniform = fill(2.5, L, L, L)
    powers = shell_powers(uniform, geometry)
    @test powers[1] ≈ 2.5^2 atol=1e-12
    @test sum(powers[2:end]) < 1e-24
    @test sum(powers) ≈ sum(abs2, uniform) / L^3 atol=1e-12

    axial = [cospi(2 * (x - 1) / L) for x in 1:L, y in 1:L, z in 1:L]
    axial_powers = shell_powers(axial, geometry)
    expected_q = 4sinpi(1 / L)^2
    shell = selected_shell_index(geometry, expected_q)
    @test argmax(axial_powers) == shell
    orientation = shell_orientation(axial, geometry, shell)
    @test orientation.maximum_fraction ≈ 1.0 atol=1e-12
    @test orientation.participation ≈ 1.0 atol=1e-12

    rank1 = modulation_rank_observables(axial, geometry, shell)
    @test rank1.lambda1 ≈ 1.0 atol=1e-12
    @test rank1.lambda2 < 1e-12
    @test rank1.effective_dimension ≈ 1.0 atol=1e-12

    planar = [cospi(2 * (x - 1) / L) + cospi(2 * (y - 1) / L)
              for x in 1:L, y in 1:L, z in 1:L]
    rank2 = modulation_rank_observables(planar, geometry, shell)
    @test rank2.lambda1 ≈ 0.5 atol=1e-12
    @test rank2.lambda2 ≈ 0.5 atol=1e-12
    @test rank2.lambda3 < 1e-12
    @test rank2.effective_dimension ≈ 2.0 atol=1e-12

    spatial = [cospi(2 * (x - 1) / L) + cospi(2 * (y - 1) / L) +
               cospi(2 * (z - 1) / L) for x in 1:L, y in 1:L, z in 1:L]
    rank3 = modulation_rank_observables(spatial, geometry, shell)
    @test rank3.lambda1 ≈ 1 / 3 atol=1e-12
    @test rank3.lambda3 ≈ 1 / 3 atol=1e-12
    @test rank3.effective_dimension ≈ 3.0 atol=1e-12

    translated = circshift(planar, (2, 3, 1))
    shifted_rank2 = modulation_rank_observables(translated, geometry, shell)
    @test [shifted_rank2.lambda1, shifted_rank2.lambda2, shifted_rank2.lambda3] ≈
          [rank2.lambda1, rank2.lambda2, rank2.lambda3] atol=1e-12
    rotated_rank2 = modulation_rank_observables(permutedims(planar, (3, 1, 2)), geometry, shell)
    signed_rank2 = modulation_rank_observables(-planar, geometry, shell)
    @test [rotated_rank2.lambda1, rotated_rank2.lambda2, rotated_rank2.lambda3] ≈
          [rank2.lambda1, rank2.lambda2, rank2.lambda3] atol=1e-12
    @test [signed_rank2.lambda1, signed_rank2.lambda2, signed_rank2.lambda3] ≈
          [rank2.lambda1, rank2.lambda2, rank2.lambda3] atol=1e-12
end

println("structure_factor_observables PASS")
