# Acceptance-rate probe for HMC tuning (standalone globals + simulation.jl only).
#
# Prints one floating acceptance rate on stdout (machine-parseable).
#
# Usage:
#   julia --project=. scripts/hmc_acceptance_probe.jl L \\
#       [--eps ε] [--n_lf N] [--probe-steps Ns] [--mass m²] [--Z Z] [--rng seed] [--cpu] [--fp64]

cd(@__DIR__)

using ArgParse
using CUDA
using Distributions
using Printf
using Random

function parse_commandline()
    s = ArgParseSettings(description = "Measure HMC acceptance over N probe trajectories")

    @add_arg_table s begin
        "L"
            help = "lattice side length"
            arg_type = Int
            required = true
        "--eps"
            help = "leapfrog step size ε"
            arg_type = Float64
            default = 0.1
        "--n_lf"
            help = "number of leapfrog steps per trajectory"
            arg_type = Int
            default = 10
        "--probe-steps"
            help = "number of HMC trajectories for acceptance estimate"
            arg_type = Int
            default = 4000
        "--mass"
            help = "mass parameter m²"
            arg_type = Float64
            default = -2.28587
        "--Z"
            help = "coefficient Z of Z/2 (∇φ)²"
            arg_type = Float64
            default = 1.0
        "--rng"
            help = "RNG seed (0 = non-deterministic seed)"
            arg_type = Int
            default = 0
        "--cpu"
            help = "run on CPU"
            action = :store_true
        "--fp64"
            help = "use Float64"
            action = :store_true
    end

    return parse_args(s)
end

pa = parse_commandline()

const cpu       = pa["cpu"]
const FloatType = pa["fp64"] ? Float64 : Float32
const ArrayType = cpu ? Array : CuArray

const L    = pa["L"]
const λ    = FloatType(4.0)
const T    = FloatType(1.0)
const Z    = FloatType(pa["Z"])
const m²   = FloatType(pa["mass"])
const n_lf = pa["n_lf"]
const ε    = FloatType(pa["eps"])

const seed = pa["rng"]

const ξ = Normal(FloatType(0.0), FloatType(1.0))

function hotstart(n)
    ArrayType(rand(ξ, n, n, n))
end

include("../src/simulation.jl")

if seed != 0
    Random.seed!(seed)
    !cpu && CUDA.seed!(seed)
end

function main()
    ϕ = hotstart(L)
    acc = thermalize(ϕ, m², pa["probe-steps"])
    @printf("%.8f\n", acc)
end

main()
