"""State for a mass-tempered replica-exchange HMC ladder."""
mutable struct ReplicaExchangeState{A,T<:AbstractFloat}
    fields::Vector{A}
    masses::Vector{T}
    batch::Any
    workspace::Any
    walker_ids::Vector{Int}
    walker_stage::Vector{Int}
    round_trips::Vector{Int}
    swap_phase::Int
    sweeps::Int
    hmc_attempts::Vector{Int}
    hmc_accepts::Vector{Int}
    swap_attempts::Vector{Int}
    swap_accepts::Vector{Int}
end

"""Return an odd, evenly spaced ladder centered exactly on `target_m2`."""
function mass_ladder(target_m2::T, count::Int, span::T) where {T<:AbstractFloat}
    count == 1 && return T[target_m2]
    count >= 3 || throw(ArgumentError("tempering replica count must be 1 or at least 3"))
    isodd(count) || throw(ArgumentError("tempering replica count must be odd"))
    isfinite(span) && span > zero(T) ||
        throw(ArgumentError("mass span must be finite and positive when tempering is enabled"))
    masses = collect(range(target_m2 - span / 2, target_m2 + span / 2; length=count))
    masses[(count + 1) ÷ 2] = target_m2
    return masses
end

function ReplicaExchangeState(fields::Vector{A}, masses::Vector{T};
                              batched=false,
                              field_batch=nothing,
                              walker_ids=collect(1:length(fields)),
                              walker_stage=zeros(Int, length(fields)),
                              round_trips=zeros(Int, length(fields)),
                              swap_phase=1, sweeps=0,
                              hmc_attempts=zeros(Int, length(fields)),
                              hmc_accepts=zeros(Int, length(fields)),
                              swap_attempts=zeros(Int, max(0, length(fields) - 1)),
                              swap_accepts=zeros(Int, max(0, length(fields) - 1))) where {A,T<:AbstractFloat}
    length(fields) == length(masses) || throw(ArgumentError("one field is required per mass"))
    length(fields) > 0 || throw(ArgumentError("replica ladder cannot be empty"))
    batch = if batched
        cpu && throw(ArgumentError("batched replica HMC requires CUDA"))
        isnothing(field_batch) &&
            throw(ArgumentError("field_batch is required for batched replica HMC"))
        size(field_batch) == (L, L, L, length(fields)) ||
            throw(ArgumentError("field_batch must have shape (L,L,L,replicas)"))
        field_batch
    else
        nothing
    end
    workspace = batched ? make_batched_workspace(batch, masses) : nothing
    state = ReplicaExchangeState{A,T}(
        fields, masses, batch, workspace,
        collect(walker_ids), collect(walker_stage), collect(round_trips),
        swap_phase, sweeps, collect(hmc_attempts), collect(hmc_accepts),
        collect(swap_attempts), collect(swap_accepts),
    )
    if state.sweeps == 0 && length(fields) > 1
        state.walker_stage[state.walker_ids[1]] = 1
    end
    return state
end

is_batched(state::ReplicaExchangeState) = !isnothing(state.workspace)

"""Reset counters and walker labels after a discarded startup stage."""
function reset_replica_diagnostics!(state::ReplicaExchangeState)
    replicas = length(state.fields)
    state.walker_ids .= 1:replicas
    fill!(state.walker_stage, 0)
    fill!(state.round_trips, 0)
    state.swap_phase = 1
    state.sweeps = 0
    fill!(state.hmc_attempts, 0)
    fill!(state.hmc_accepts, 0)
    fill!(state.swap_attempts, 0)
    fill!(state.swap_accepts, 0)
    replicas > 1 && (state.walker_stage[1] = 1)
    return state
end

function batched_quadratic_statistics(state::ReplicaExchangeState)
    is_batched(state) || return quadratic_statistic.(state.fields)
    values = sum(abs2, state.batch; dims=(1, 2, 3))
    return Float64.(vec(Array(values)))
end

function swap_field_slots!(state::ReplicaExchangeState, left::Int, right::Int)
    if !is_batched(state)
        state.fields[left], state.fields[right] = state.fields[right], state.fields[left]
        return
    end
    temporary = state.workspace.swap_buffer
    copyto!(temporary, state.fields[left])
    copyto!(state.fields[left], state.fields[right])
    copyto!(state.fields[right], temporary)
end

target_slot(state::ReplicaExchangeState) = (length(state.fields) + 1) ÷ 2
quadratic_statistic(ϕ) = Float64(sum(abs2, ϕ))

"""Exact crossed-action difference for swapping two configurations at fixed Z."""
swap_action_difference(m2_i, m2_j, q_i, q_j) =
    0.5 * (Float64(m2_i) - Float64(m2_j)) * (Float64(q_j) - Float64(q_i))

function _record_endpoint_visits!(state::ReplicaExchangeState)
    length(state.fields) > 1 || return
    low_walker = state.walker_ids[1]
    high_walker = state.walker_ids[end]
    if state.walker_stage[low_walker] == 2
        state.round_trips[low_walker] += 1
    end
    state.walker_stage[low_walker] = 1
    if state.walker_stage[high_walker] == 1
        state.walker_stage[high_walker] = 2
    end
end

function attempt_replica_swap!(state::ReplicaExchangeState, left::Int;
                               q_left=nothing, q_right=nothing,
                               rng=Random.default_rng())
    right = left + 1
    1 <= left < length(state.fields) || throw(BoundsError(state.fields, right))
    ql = isnothing(q_left) ? quadratic_statistic(state.fields[left]) : Float64(q_left)
    qr = isnothing(q_right) ? quadratic_statistic(state.fields[right]) : Float64(q_right)
    ΔS = swap_action_difference(state.masses[left], state.masses[right], ql, qr)
    state.swap_attempts[left] += 1
    accepted = ΔS <= 0 || log(rand(rng)) < -ΔS / Float64(T)
    if accepted
        swap_field_slots!(state, left, right)
        state.walker_ids[left], state.walker_ids[right] =
            state.walker_ids[right], state.walker_ids[left]
        state.swap_accepts[left] += 1
    end
    return accepted, ΔS
end

"""Advance every slot once, then attempt one alternating set of adjacent swaps."""
function replica_exchange_sweep!(state::ReplicaExchangeState, Z_value, eps, leapfrog_steps;
                                 swap_every::Int=1, rng=Random.default_rng())
    swap_every > 0 || throw(ArgumentError("swap_every must be positive"))
    if is_batched(state)
        accepted, _ = hmc_step_batched!(
            state.batch, Z_value, eps, leapfrog_steps, state.workspace; rng=rng
        )
        state.hmc_attempts .+= 1
        state.hmc_accepts .+= accepted
    else
        for slot in eachindex(state.fields)
            accepted, _ = hmc_step!(state.fields[slot], state.masses[slot], Z_value,
                                    eps, leapfrog_steps)
            state.hmc_attempts[slot] += 1
            state.hmc_accepts[slot] += accepted
        end
    end
    state.sweeps += 1
    if length(state.fields) > 1 && state.sweeps % swap_every == 0
        q = batched_quadratic_statistics(state)
        for left in state.swap_phase:2:(length(state.fields) - 1)
            accepted, _ = attempt_replica_swap!(state, left;
                                                q_left=q[left], q_right=q[left + 1], rng=rng)
            if accepted
                q[left], q[left + 1] = q[left + 1], q[left]
            end
        end
        state.swap_phase = state.swap_phase == 1 ? 2 : 1
        _record_endpoint_visits!(state)
    end
    return state
end

function replica_exchange!(state::ReplicaExchangeState, sweeps::Int, Z_value, eps,
                           leapfrog_steps; swap_every::Int=1, rng=Random.default_rng())
    sweeps >= 0 || throw(ArgumentError("sweeps must be non-negative"))
    for _ in 1:sweeps
        replica_exchange_sweep!(state, Z_value, eps, leapfrog_steps;
                                swap_every=swap_every, rng=rng)
    end
    return state
end

acceptance_rates(accepts, attempts) =
    [attempts[i] == 0 ? 0.0 : accepts[i] / attempts[i] for i in eachindex(attempts)]
