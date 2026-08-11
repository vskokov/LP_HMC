!cpu && using CUDA

function NNp(n)
    n%L+1
end

function NNm(n)
    (n+L-2)%L+1
end

##
@static if cpu

function compute_force!(F, ϕ, m², Z)
    lapϕ = similar(ϕ)
    Threads.@threads for x3 in 1:L
        for x2 in 1:L, x1 in 1:L
            lapϕ[x1,x2,x3] = (
                ϕ[NNp(x1),x2,x3] + ϕ[NNm(x1),x2,x3] +
                ϕ[x1,NNp(x2),x3] + ϕ[x1,NNm(x2),x3] +
                ϕ[x1,x2,NNp(x3)] + ϕ[x1,x2,NNm(x3)] - 6*ϕ[x1,x2,x3]
            )
        end
    end
    Threads.@threads for x3 in 1:L
        for x2 in 1:L, x1 in 1:L
            l0   = lapϕ[x1,x2,x3]
            lap2 = (
                lapϕ[NNp(x1),x2,x3] + lapϕ[NNm(x1),x2,x3] +
                lapϕ[x1,NNp(x2),x3] + lapϕ[x1,NNm(x2),x3] +
                lapϕ[x1,x2,NNp(x3)] + lapϕ[x1,x2,NNm(x3)] - 6*l0
            )
            F[x1,x2,x3] = Z*l0 - lap2 - m²*ϕ[x1,x2,x3] - λ*ϕ[x1,x2,x3]^3
        end
    end
end

function calc_total_energy(ϕ, m², Z)
    H = 0.0
    for x3 in 1:L, x2 in 1:L, x1 in 1:L
        ϕ0 = ϕ[x1, x2, x3]

        ϕp_x = ϕ[NNp(x1), x2, x3]
        ϕm_x = ϕ[NNm(x1), x2, x3]
        ϕp_y = ϕ[x1, NNp(x2), x3]
        ϕm_y = ϕ[x1, NNm(x2), x3]
        ϕp_z = ϕ[x1, x2, NNp(x3)]
        ϕm_z = ϕ[x1, x2, NNm(x3)]

        lapl  = (ϕp_x + ϕm_x - 2ϕ0) + (ϕp_y + ϕm_y - 2ϕ0) + (ϕp_z + ϕm_z - 2ϕ0)
        grad2 = (ϕp_x - ϕ0)^2 + (ϕp_y - ϕ0)^2 + (ϕp_z - ϕ0)^2

        H += 0.5 * lapl^2 + (Z / 2.0) * grad2 + (m² / 2.0) * ϕ0^2 + (λ / 4.0) * ϕ0^4
    end
    return H
end

"""
    sufficient_statistics(ϕ) -> (M, Q, G)

Return the uniform magnetization `M = sum(ϕ)/L^3`, the quadratic statistic
`Q = sum(ϕ^2)`, and the positive-direction nearest-neighbour gradient statistic
`G = sum(x,μ>0) (ϕ[x+μ]-ϕ[x])^2`.  Accumulation is performed in Float64 on CPU.
"""
function sufficient_statistics(ϕ)
    sumϕ = 0.0
    Q = 0.0
    G = 0.0
    for x3 in 1:L, x2 in 1:L, x1 in 1:L
        ϕ0 = Float64(ϕ[x1, x2, x3])
        sumϕ += ϕ0
        Q += ϕ0^2
        G += (Float64(ϕ[NNp(x1), x2, x3]) - ϕ0)^2
        G += (Float64(ϕ[x1, NNp(x2), x3]) - ϕ0)^2
        G += (Float64(ϕ[x1, x2, NNp(x3)]) - ϕ0)^2
    end
    return (M=sumϕ / L^3, Q=Q, G=G)
end

else

# At L=12 with 11 replicas, 128 threads yields 149 independent blocks.  This is
# enough to cover all SMs on an H200, whereas 256 threads would launch only 75.
const BATCH_THREADS = 128

function _lap_kernel!(lapϕ, ϕ)
    idx = (blockIdx().x - 1) * blockDim().x + threadIdx().x
    if idx <= L^3
        flat = idx - 1
        x1 = flat % L + 1
        x2 = (flat ÷ L) % L + 1
        x3 = flat ÷ L^2 + 1
        lapϕ[x1,x2,x3] = (
            ϕ[NNp(x1),x2,x3] + ϕ[NNm(x1),x2,x3] +
            ϕ[x1,NNp(x2),x3] + ϕ[x1,NNm(x2),x3] +
            ϕ[x1,x2,NNp(x3)] + ϕ[x1,x2,NNm(x3)] - 6*ϕ[x1,x2,x3]
        )
    end
    return nothing
end

function _force_kernel!(F, lapϕ, ϕ, m², Z)
    idx = (blockIdx().x - 1) * blockDim().x + threadIdx().x
    if idx <= L^3
        flat = idx - 1
        x1 = flat % L + 1
        x2 = (flat ÷ L) % L + 1
        x3 = flat ÷ L^2 + 1
        l0   = lapϕ[x1,x2,x3]
        lap2 = (
            lapϕ[NNp(x1),x2,x3] + lapϕ[NNm(x1),x2,x3] +
            lapϕ[x1,NNp(x2),x3] + lapϕ[x1,NNm(x2),x3] +
            lapϕ[x1,x2,NNp(x3)] + lapϕ[x1,x2,NNm(x3)] - 6*l0
        )
        F[x1,x2,x3] = Z*l0 - lap2 - m²*ϕ[x1,x2,x3] - λ*ϕ[x1,x2,x3]^3
    end
    return nothing
end

function compute_force!(F, ϕ, m², Z)
    lapϕ = CuArray{FloatType}(undef, L, L, L)
    Ntot = L^3
    th = 256
    bl = cld(Ntot, th)
    @cuda threads=th blocks=bl _lap_kernel!(lapϕ, ϕ)
    @cuda threads=th blocks=bl _force_kernel!(F, lapϕ, ϕ, m², Z)
end

function _energy_kernel!(H_arr, ϕ, m², Z)
    idx = (blockIdx().x - 1) * blockDim().x + threadIdx().x
    if idx <= L^3
        flat = idx - 1
        x1 = flat % L + 1
        x2 = (flat ÷ L) % L + 1
        x3 = flat ÷ L^2 + 1

        ϕ0 = ϕ[x1, x2, x3]

        ϕp_x = ϕ[NNp(x1), x2, x3]
        ϕm_x = ϕ[NNm(x1), x2, x3]
        ϕp_y = ϕ[x1, NNp(x2), x3]
        ϕm_y = ϕ[x1, NNm(x2), x3]
        ϕp_z = ϕ[x1, x2, NNp(x3)]
        ϕm_z = ϕ[x1, x2, NNm(x3)]

        lapl  = (ϕp_x + ϕm_x - 2ϕ0) + (ϕp_y + ϕm_y - 2ϕ0) + (ϕp_z + ϕm_z - 2ϕ0)
        grad2 = (ϕp_x - ϕ0)^2 + (ϕp_y - ϕ0)^2 + (ϕp_z - ϕ0)^2

        H_arr[idx] = FloatType(0.5) * lapl^2 + (Z * FloatType(0.5)) * grad2 +
                     (m² * FloatType(0.5)) * ϕ0^2 + (λ * FloatType(0.25)) * ϕ0^4
    end
    return nothing
end

function calc_total_energy(ϕ, m², Z)
    Ntot = L^3
    H_arr = CuArray{FloatType}(undef, Ntot)
    en_threads = 256
    en_blocks = cld(Ntot, en_threads)
    @cuda threads=en_threads blocks=en_blocks _energy_kernel!(H_arr, ϕ, m², Z)
    return sum(H_arr)
end

function _statistics_kernel!(sum_arr, q_arr, g_arr, ϕ)
    idx = (blockIdx().x - 1) * blockDim().x + threadIdx().x
    if idx <= L^3
        flat = idx - 1
        x1 = flat % L + 1
        x2 = (flat ÷ L) % L + 1
        x3 = flat ÷ L^2 + 1
        ϕ0 = ϕ[x1, x2, x3]
        sum_arr[idx] = ϕ0
        q_arr[idx] = ϕ0^2
        g_arr[idx] = (ϕ[NNp(x1), x2, x3] - ϕ0)^2 +
                     (ϕ[x1, NNp(x2), x3] - ϕ0)^2 +
                     (ϕ[x1, x2, NNp(x3)] - ϕ0)^2
    end
    return nothing
end

"""GPU implementation of `sufficient_statistics`, with one fused site kernel."""
function sufficient_statistics(ϕ)
    Ntot = L^3
    sum_arr = CuArray{FloatType}(undef, Ntot)
    q_arr = CuArray{FloatType}(undef, Ntot)
    g_arr = CuArray{FloatType}(undef, Ntot)
    stat_threads = 256
    stat_blocks = cld(Ntot, stat_threads)
    @cuda threads=stat_threads blocks=stat_blocks _statistics_kernel!(sum_arr, q_arr, g_arr, ϕ)
    return (M=Float64(sum(sum_arr)) / Ntot,
            Q=Float64(sum(q_arr)),
            G=Float64(sum(g_arr)))
end

"""Persistent storage for advancing every mass replica in one CUDA batch."""
mutable struct BatchedHMCWorkspace{A,V}
    proposal::A
    momentum::A
    force::A
    laplacian::A
    site_energy::V
    device_masses::V
    device_accepts::CuArray{Bool,1}
    swap_buffer::CuArray{FloatType,3}
    old_hamiltonians::Vector{Float64}
    new_hamiltonians::Vector{Float64}
end

function make_batched_workspace(fields::CuArray{FloatType,4}, masses)
    size(fields)[1:3] == (L, L, L) ||
        throw(ArgumentError("batched fields must have shape (L,L,L,replicas)"))
    nrep = size(fields, 4)
    length(masses) == nrep || throw(ArgumentError("one mass is required per replica"))
    return BatchedHMCWorkspace(
        similar(fields), similar(fields), similar(fields), similar(fields),
        CuArray{FloatType}(undef, length(fields)), CuArray(FloatType.(masses)),
        CuArray{Bool}(undef, nrep), CuArray{FloatType}(undef, L, L, L),
        zeros(Float64, nrep), zeros(Float64, nrep),
    )
end

function _batch_lap_kernel!(lapϕ, ϕ, sites_per_replica)
    idx = (blockIdx().x - 1) * blockDim().x + threadIdx().x
    if idx <= length(ϕ)
        zero_based = idx - 1
        site = zero_based % sites_per_replica
        replica = zero_based ÷ sites_per_replica + 1
        x1 = site % L + 1
        x2 = (site ÷ L) % L + 1
        x3 = site ÷ L^2 + 1
        lapϕ[x1,x2,x3,replica] = (
            ϕ[NNp(x1),x2,x3,replica] + ϕ[NNm(x1),x2,x3,replica] +
            ϕ[x1,NNp(x2),x3,replica] + ϕ[x1,NNm(x2),x3,replica] +
            ϕ[x1,x2,NNp(x3),replica] + ϕ[x1,x2,NNm(x3),replica] -
            6*ϕ[x1,x2,x3,replica]
        )
    end
    return nothing
end

function _batch_force_kernel!(F, lapϕ, ϕ, masses, Z_value, sites_per_replica)
    idx = (blockIdx().x - 1) * blockDim().x + threadIdx().x
    if idx <= length(ϕ)
        zero_based = idx - 1
        site = zero_based % sites_per_replica
        replica = zero_based ÷ sites_per_replica + 1
        x1 = site % L + 1
        x2 = (site ÷ L) % L + 1
        x3 = site ÷ L^2 + 1
        l0 = lapϕ[x1,x2,x3,replica]
        lap2 = (
            lapϕ[NNp(x1),x2,x3,replica] + lapϕ[NNm(x1),x2,x3,replica] +
            lapϕ[x1,NNp(x2),x3,replica] + lapϕ[x1,NNm(x2),x3,replica] +
            lapϕ[x1,x2,NNp(x3),replica] + lapϕ[x1,x2,NNm(x3),replica] - 6*l0
        )
        value = ϕ[x1,x2,x3,replica]
        F[x1,x2,x3,replica] = Z_value*l0 - lap2 - masses[replica]*value - λ*value^3
    end
    return nothing
end

function compute_force_batched!(F, lapϕ, ϕ, masses, Z_value)
    threads = BATCH_THREADS
    blocks = cld(length(ϕ), threads)
    @cuda threads=threads blocks=blocks _batch_lap_kernel!(lapϕ, ϕ, L^3)
    @cuda threads=threads blocks=blocks _batch_force_kernel!(
        F, lapϕ, ϕ, masses, Z_value, L^3
    )
    return nothing
end

function _batch_hamiltonian_kernel!(site_energy, ϕ, π_field, masses, Z_value,
                                    sites_per_replica)
    idx = (blockIdx().x - 1) * blockDim().x + threadIdx().x
    if idx <= length(ϕ)
        zero_based = idx - 1
        site = zero_based % sites_per_replica
        replica = zero_based ÷ sites_per_replica + 1
        x1 = site % L + 1
        x2 = (site ÷ L) % L + 1
        x3 = site ÷ L^2 + 1
        value = ϕ[x1,x2,x3,replica]
        lapl = (
            ϕ[NNp(x1),x2,x3,replica] + ϕ[NNm(x1),x2,x3,replica] +
            ϕ[x1,NNp(x2),x3,replica] + ϕ[x1,NNm(x2),x3,replica] +
            ϕ[x1,x2,NNp(x3),replica] + ϕ[x1,x2,NNm(x3),replica] - 6*value
        )
        grad2 = (ϕ[NNp(x1),x2,x3,replica] - value)^2 +
                (ϕ[x1,NNp(x2),x3,replica] - value)^2 +
                (ϕ[x1,x2,NNp(x3),replica] - value)^2
        momentum = π_field[x1,x2,x3,replica]
        site_energy[idx] = FloatType(0.5)*lapl^2 + FloatType(0.5)*Z_value*grad2 +
                           FloatType(0.5)*masses[replica]*value^2 +
                           FloatType(0.25)*λ*value^4 + FloatType(0.5)*momentum^2
    end
    return nothing
end

function batched_hamiltonians!(destination, site_energy, ϕ, π_field, masses, Z_value)
    threads = BATCH_THREADS
    blocks = cld(length(ϕ), threads)
    @cuda threads=threads blocks=blocks _batch_hamiltonian_kernel!(
        site_energy, ϕ, π_field, masses, Z_value, L^3
    )
    reduced = sum(reshape(site_energy, L^3, size(ϕ, 4)); dims=1)
    destination .= vec(Array(reduced))
    return destination
end

function leapfrog_batched!(ϕ, π_field, masses, Z_value, eps, leapfrog_steps, workspace)
    compute_force_batched!(workspace.force, workspace.laplacian, ϕ, masses, Z_value)
    π_field .+= (eps / 2) .* workspace.force
    for _ in 1:(leapfrog_steps - 1)
        ϕ .+= eps .* π_field
        compute_force_batched!(workspace.force, workspace.laplacian, ϕ, masses, Z_value)
        π_field .+= eps .* workspace.force
    end
    ϕ .+= eps .* π_field
    compute_force_batched!(workspace.force, workspace.laplacian, ϕ, masses, Z_value)
    π_field .+= (eps / 2) .* workspace.force
    return nothing
end

function _accept_batch_kernel!(fields, proposal, accepted, sites_per_replica)
    idx = (blockIdx().x - 1) * blockDim().x + threadIdx().x
    if idx <= length(fields)
        replica = (idx - 1) ÷ sites_per_replica + 1
        accepted[replica] && (fields[idx] = proposal[idx])
    end
    return nothing
end

"""Advance every field in a contiguous replica batch with one sequence of kernels."""
function hmc_step_batched!(fields, Z_value, eps, leapfrog_steps, workspace;
                           rng=Random.default_rng())
    randn!(workspace.momentum)
    batched_hamiltonians!(workspace.old_hamiltonians, workspace.site_energy, fields,
                          workspace.momentum, workspace.device_masses, Z_value)
    copyto!(workspace.proposal, fields)
    leapfrog_batched!(workspace.proposal, workspace.momentum, workspace.device_masses,
                      Z_value, eps, leapfrog_steps, workspace)
    batched_hamiltonians!(workspace.new_hamiltonians, workspace.site_energy,
                          workspace.proposal, workspace.momentum,
                          workspace.device_masses, Z_value)
    delta_h = workspace.new_hamiltonians .- workspace.old_hamiltonians
    accepted = [value < 0 || rand(rng) < exp(-value / Float64(T)) for value in delta_h]
    copyto!(workspace.device_accepts, accepted)
    threads = BATCH_THREADS
    blocks = cld(length(fields), threads)
    @cuda threads=threads blocks=blocks _accept_batch_kernel!(
        fields, workspace.proposal, workspace.device_accepts, L^3
    )
    return accepted, delta_h
end

end

##

function calc_hamiltonian(ϕ, π_field, m², Z)
    H_field = calc_total_energy(ϕ, m², Z)
    K = sum(π_field .^ 2) / 2
    return H_field + K
end

function leapfrog!(ϕ, π_field, m², Z, ε, n_lf)
    F = similar(ϕ)
    compute_force!(F, ϕ, m², Z)
    π_field .+= (ε / 2) .* F
    for _ in 1:(n_lf - 1)
        ϕ .+= ε .* π_field
        compute_force!(F, ϕ, m², Z)
        π_field .+= ε .* F
    end
    ϕ .+= ε .* π_field
    compute_force!(F, ϕ, m², Z)
    π_field .+= (ε / 2) .* F
end

function hmc_step!(ϕ, m², Z, ε, n_lf)
    if cpu
        π_field = Array{FloatType}(undef, L, L, L)
        randn!(π_field)
    else
        π_field = CUDA.randn(FloatType, L, L, L)
    end

    H_old = calc_hamiltonian(ϕ, π_field, m², Z)

    ϕ_prop = copy(ϕ)
    π_prop = copy(π_field)
    leapfrog!(ϕ_prop, π_prop, m², Z, ε, n_lf)

    H_new = calc_hamiltonian(ϕ_prop, π_prop, m², Z)
    ΔH    = H_new - H_old

    accepted = ΔH < 0 || rand() < exp(-ΔH / T)
    if accepted
        ϕ .= ϕ_prop
    end
    return accepted, Float64(ΔH)
end

function thermalize(ϕ, m², N)
    n_acc = 0
    for _ in 1:N
        accepted, _ = hmc_step!(ϕ, m², Z, ε, n_lf)
        n_acc += accepted
    end
    return n_acc / N
end
