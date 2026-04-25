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

else

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
