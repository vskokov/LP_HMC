cd(@__DIR__)

using JLD2
using CodecZlib
using Printf

include("../src/modelA.jl")

function main()
    @init_state

    mass_id = round(m², digits=3)
    Z_id    = round(Z,  digits=3)
    checkpoint_arg = parsed_args["checkpoint"]
    checkpoint = isnothing(checkpoint_arg) ?
        joinpath(@__DIR__, "..", "data", "thermalized_L_$(L)_Z_$(Z_id)_mass_$(mass_id)_id_$(seed).jld2") :
        abspath(checkpoint_arg)
    mkpath(dirname(checkpoint))

    for i in 1:L
      acc = thermalize(ϕ, m², L^2)
      @printf("acceptance=%.3f\n", acc)
      flush(stdout)
      temporary = checkpoint * ".tmp"
      jldsave(temporary, true;
          ϕ=Array(ϕ),
          schema_version=1,
          L=L,
          Z=Float64(Z),
          m²=Float64(m²),
          λ=Float64(λ),
          T=Float64(T),
          epsilon=Float64(ε),
          n_lf=n_lf,
          seed=seed,
          fp64=(FloatType == Float64),
          cpu=cpu,
          checkpoint_path=checkpoint,
          initial_state=isnothing(init_arg) ? "" : abspath(init_arg),
          outer_iterations_completed=i,
          trajectories_completed=i * L^2,
          last_acceptance_rate=acc)
      mv(temporary, checkpoint; force=true)
    end
    @printf("checkpoint=%s\n", checkpoint)
end

main()
