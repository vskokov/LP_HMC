cd(@__DIR__)

using JLD2
using CodecZlib
using Printf

include("../src/modelA.jl")

function advance_hmc!(field, mass, sweeps, epsilon, leapfrog_steps)
    accepted = 0
    for _ in 1:sweeps
        step_accepted, _ = hmc_step!(field, mass, Z, epsilon, leapfrog_steps)
        accepted += step_accepted
    end
    return sweeps == 0 ? 0.0 : accepted / sweeps
end

function main()
    @init_state

    mass_id = round(m², digits=3)
    Z_id    = round(Z,  digits=3)
    checkpoint_arg = parsed_args["checkpoint"]
    checkpoint = isnothing(checkpoint_arg) ?
        joinpath(@__DIR__, "..", "data", "thermalized_L_$(L)_Z_$(Z_id)_mass_$(mass_id)_id_$(seed).jld2") :
        abspath(checkpoint_arg)
    mkpath(dirname(checkpoint))

    if startup_sweeps > 0
      completed = 0
      while completed < startup_sweeps
        block = min(L^2, startup_sweeps - completed)
        acc = advance_hmc!(ϕ, m², block, startup_ε, startup_n_lf)
        completed += block
        @printf("stage=startup sweeps=%d/%d acceptance=%.3f\n",
                completed, startup_sweeps, acc)
        flush(stdout)
      end
    end

    for i in 1:L
      acc = advance_hmc!(ϕ, m², L^2, ε, n_lf)
      @printf("stage=production acceptance=%.3f\n", acc)
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
          startup_epsilon=Float64(startup_ε),
          startup_n_lf=startup_n_lf,
          startup_sweeps=startup_sweeps,
          thermalization_complete=(i == L),
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
