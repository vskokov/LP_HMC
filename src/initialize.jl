using ArgParse
using Distributions
using Random
using CUDA

function parse_commandline()
    s = ArgParseSettings()

    @add_arg_table s begin
        "--mass"
            help = "actual mass parameter m² (used directly, not as a shift relative to a reference value)"
            arg_type = Float64
            default = -2.28587
        "--Z"
            help = "coefficient Z of the conventional kinetic term Z/2 (∇φ)²"
            arg_type = Float64
            default = 1.0
        "--dt"
            help = "size of time step"
            arg_type = Float64
            default = 0.04
        "--rng"
            help = "seed for random number generation"
            arg_type = Int
            default = 0
        "--fp64"
            help = "flag to use Float64 type rather than Float32"
            action = :store_true
        "--init"
            help = "path of .jld2 file with initial state"
            arg_type = String
        "--cpu"
            help = "parallelize on CPU rather than GPU"
            action = :store_true
        "--n_lf"
            help = "number of leapfrog steps per HMC trajectory"
            arg_type = Int
            default = 10
        "--eps"
            help = "leapfrog step size ε for HMC (tune for ~70-80% acceptance)"
            arg_type = Float64
            default = 0.1
        "--startup-eps"
            help = "HMC step size used only during discarded cold-start stabilization"
            arg_type = Float64
            default = 0.0
        "--startup-n-lf"
            help = "leapfrog steps used only during cold-start stabilization"
            arg_type = Int
            default = 0
        "--startup-sweeps"
            help = "discarded cold-start HMC sweeps before normal thermalization"
            arg_type = Int
            default = 0
        "--checkpoint"
            help = "explicit output checkpoint path (thermalize.jl)"
            arg_type = String
        "--samples"
            help = "number of retained configurations (collect_reweight_stats.jl)"
            arg_type = Int
            default = 1000
        "--skip"
            help = "HMC trajectories between retained configurations"
            arg_type = Int
            default = 1
        "--warmup"
            help = "additional HMC trajectories before collection"
            arg_type = Int
            default = 0
        "--output"
            help = "explicit statistics output path (collect_reweight_stats.jl)"
            arg_type = String
        "--diagnostics"
            help = "replica-exchange diagnostics CSV output path"
            arg_type = String
        "--tempering-replicas"
            help = "number of mass-tempering slots (1 disables replica exchange; otherwise odd and >= 3)"
            arg_type = Int
            default = 1
        "--mass-span"
            help = "total centered m² span covered by the tempering ladder"
            arg_type = Float64
            default = 0.0
        "--swap-every"
            help = "replica-exchange attempt cadence in complete HMC sweeps"
            arg_type = Int
            default = 1
        "--init-phase"
            help = "initial field basin: hot, disordered, or ordered"
            arg_type = String
            default = "hot"
        "--phase-threshold"
            help = "absolute magnetization threshold used for phase diagnostics"
            arg_type = Float64
            default = 0.25
        "size"
            help = "side length of lattice"
            arg_type = Int
            required = true
    end

    return parse_args(s)
end

#=
 Parameters below are
 1. L is the number of lattice sites in each dimension; it accepts the second argument passed to julia   
 2. λ is the 4 field coupling
 3. Γ is the scalar field diffusion rate; in our calculations we set it to 1, assuming that the time is measured in the appropriate units 
 4. T is the temperature 
 5. m² is the mass parameter; its value is passed directly via the --mass flag (default: -2.28587)
 6. Z is the coefficient of the conventional kinetic term Z/2 (∇φ)²
 =#

parsed_args = parse_commandline()

const cpu = parsed_args["cpu"]
const FloatType = parsed_args["fp64"] ? Float64 : Float32
const ArrayType = cpu ? Array : CuArray

const λ = FloatType(4.0)
const Γ = FloatType(1.0)
const T = FloatType(1.0)
const Z = FloatType(parsed_args["Z"])

const L = parsed_args["size"]
const m² = FloatType(parsed_args["mass"])
const Δt = FloatType(parsed_args["dt"]/Γ)

const Rate= FloatType(sqrt(2.0*Δt*Γ))
const ξ = Normal(FloatType(0.0), FloatType(1.0))

const n_lf = parsed_args["n_lf"]
const ε    = FloatType(parsed_args["eps"])
const startup_ε = FloatType(parsed_args["startup-eps"])
const startup_n_lf = parsed_args["startup-n-lf"]
const startup_sweeps = parsed_args["startup-sweeps"]
const tempering_replicas = parsed_args["tempering-replicas"]
const mass_span = FloatType(parsed_args["mass-span"])
const swap_every = parsed_args["swap-every"]
const init_phase = parsed_args["init-phase"]
const phase_threshold = Float64(parsed_args["phase-threshold"])

init_phase in ("hot", "disordered", "ordered") ||
    error("--init-phase must be hot, disordered, or ordered")
isfinite(phase_threshold) && phase_threshold > 0 ||
    error("--phase-threshold must be finite and positive")
startup_sweeps >= 0 || error("--startup-sweeps must be non-negative")
if startup_sweeps > 0
    isfinite(startup_ε) && startup_ε > 0 || error("--startup-eps must be positive")
    startup_n_lf > 0 || error("--startup-n-lf must be positive")
end

const seed = parsed_args["rng"]
if seed != 0
    Random.seed!(seed)
    !cpu && CUDA.seed!(seed)
end

function hotstart(n)
    ArrayType(rand(ξ, n, n, n))
end

"""Near-zero field used to seed the disordered basin."""
function disorderedstart(n)
    FloatType(0.05) .* hotstart(n)
end

"""Uniform classical minimum plus small noise, used to seed the ordered basin."""
function orderedstart(n, mass; sign::Int=(isodd(seed) ? 1 : -1))
    sign in (-1, 1) || throw(ArgumentError("ordered-start sign must be -1 or 1"))
    amplitude = sqrt(max(-FloatType(mass) / λ, zero(FloatType)))
    field = ArrayType(fill(FloatType(sign) * amplitude, n, n, n))
    field .+= FloatType(0.05) .* hotstart(n)
    return field
end

function initial_field(n, mass, phase::AbstractString=init_phase)
    phase == "hot" && return hotstart(n)
    phase == "disordered" && return disorderedstart(n)
    phase == "ordered" && return orderedstart(n, mass)
    throw(ArgumentError("initial phase must be hot, disordered, or ordered"))
end

init_arg = parsed_args["init"]

##
if isnothing(init_arg)

macro init_state() esc(:( ϕ = initial_field(L, m²) )) end

else

macro init_state()
    file = jldopen(init_arg, "r")
    ϕ = ArrayType(file["ϕ"])
    return esc(:( ϕ = $ϕ ))
end

end
##
