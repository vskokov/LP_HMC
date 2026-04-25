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

const seed = parsed_args["rng"]
if seed != 0
    Random.seed!(seed)
    !cpu && CUDA.seed!(seed)
end

function hotstart(n)
    ArrayType(rand(ξ, n, n, n))
end

init_arg = parsed_args["init"]

##
if isnothing(init_arg)

macro init_state() esc(:( ϕ = hotstart(L) )) end

else

macro init_state()
    file = jldopen(init_arg, "r")
    ϕ = ArrayType(file["ϕ"])
    return esc(:( ϕ = $ϕ ))
end

end
##
