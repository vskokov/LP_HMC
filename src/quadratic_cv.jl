# Quadratic-form umbrella collective variables in Fourier space.
#
#     s[φ] = Σ_k w(k) |φ̃_k|² / V²,      φ̃_k = Σ_x φ_x e^{-ik·x},  V = L³
#
# w = δ_{k,0} gives s = M² (the production umbrella coordinate); w = indicator of a
# lattice momentum shell gives the shell power P_*; w = δ_{k,0} - c·shell gives a
# mixed uniform/modulated coordinate.  Since φ is real,
#
#     ∂s/∂φ_x = (2/V) Re[ IFFT(w · φ̃) ]_x      (IFFT includes 1/V).
#
# This file is purely additive: it reuses the existing physical force/energy
# implementations (kernels receive κ = 0) and adds the bias on top.  It must be
# included after src/simulation.jl and scripts/structure_factor_observables.jl.

using FFTW
using LinearAlgebra
@static if !cpu
    using CUDA.CUFFT
end

_to_dev(x) = cpu ? x : CuArray(x)

"""Quadratic Fourier-space CV with optional shell modes for orientation tensors."""
struct QuadraticCV{W}
    weights::W                         # (L,L,L) FloatType, backend array
    label::String
    shell_q::Float64                   # k̂² of the selected shell (NaN if none)
    shell_modes::Vector{CartesianIndex{3}}
    shell_pairs::Vector{Vector{CartesianIndex{3}}}
    shell_dirs::Vector{Vector{Float64}}  # unit lattice-momentum direction per pair
end

"""Allowed finite-volume k̂² = Σ 4 sin²(π n/L) closest to `target`."""
function nearest_shell_q(L::Int, target::Float64)
    geometry = momentum_shells(L)
    nonzero = findall(>(1e-12), geometry.q)
    best = nonzero[argmin(abs.(geometry.q[nonzero] .- target))]
    return geometry.q[best], best, geometry
end

"""
    make_cv(L, kind; shell_target=NaN, mix=1.0, band=(NaN, NaN))

kind = "M2" (w = δ_{k0}), "shell" (w = 1 on the k̂² shell nearest `shell_target`),
"mixed" (w = δ_{k0} − mix·shell), "band" (w = 1 on every mode k ≠ 0 with
band[1] ≤ k̂² ≤ band[2]) or "mixedband" (w = δ_{k0} − mix·band).

The band coordinates do not fix the modulation wavevector in advance: fluctuations
renormalize Z, so the preferred k̂² differs from the bare −Z/2 that the single-shell
coordinate assumes.  For them `shell_target` only picks the shell used for the
lamellar initial fields (`shell_q`); shell observables run over the whole band.
"""
function make_cv(L::Int, kind::AbstractString; shell_target::Float64=NaN, mix::Float64=1.0,
                 band::Tuple{Float64,Float64}=(NaN, NaN))
    w = zeros(Float64, L, L, L)
    modes = CartesianIndex{3}[]
    pairs = Vector{CartesianIndex{3}}[]
    dirs = Vector{Float64}[]
    q = NaN
    if kind in ("shell", "mixed")
        isfinite(shell_target) || throw(ArgumentError("shell CV needs shell_target"))
        q, index, geometry = nearest_shell_q(L, shell_target)
        modes = geometry.members[index]
        pairs = geometry.pair_groups[index]
        dirs = [Float64.(lattice_momentum_direction(first(p), L)) for p in pairs]
        for m in modes
            w[m] = kind == "shell" ? 1.0 : -mix
        end
    elseif kind in ("band", "mixedband")
        lo, hi = band
        isfinite(lo) && isfinite(hi) && 0 < lo <= hi ||
            throw(ArgumentError("band CV needs 0 < band[1] <= band[2]"))
        geometry = momentum_shells(L)
        inband = findall(x -> lo - 1e-9 <= x <= hi + 1e-9, geometry.q)
        isempty(inband) && throw(ArgumentError("no lattice shell with $lo <= k̂² <= $hi at L=$L"))
        for index in inband
            append!(modes, geometry.members[index])
            append!(pairs, geometry.pair_groups[index])
        end
        dirs = [Float64.(lattice_momentum_direction(first(p), L)) for p in pairs]
        for m in modes
            w[m] = kind == "band" ? 1.0 : -mix
        end
        target = isfinite(shell_target) ? shell_target : (lo + hi) / 2
        q = geometry.q[inband[argmin(abs.(geometry.q[inband] .- target))]]
    end
    if kind in ("M2", "mixed", "mixedband")
        w[1, 1, 1] = 1.0
    end
    kind in ("M2", "shell", "mixed", "band", "mixedband") || throw(ArgumentError("unknown CV kind $kind"))
    label = kind == "M2" ? "M2" : kind == "shell" ? @sprintf("shell(q=%.10g)", q) :
            kind == "mixed" ? @sprintf("mixed(q=%.10g,c=%.6g)", q, mix) :
            kind == "band" ? @sprintf("band(%.6g,%.6g)", band...) :
            @sprintf("mixedband(%.6g,%.6g,c=%.6g)", band..., mix)
    return QuadraticCV(_to_dev(FloatType.(w)), label, q, modes, pairs, dirs)
end

_fft3(x) = fft(x, (1, 2, 3))
_ifft3(x) = ifft(x, (1, 2, 3))

"""CV value for every replica of a (L,L,L,n) batch (or a single (L,L,L) field)."""
function cv_values(cv::QuadraticCV, batch)
    if !cpu && cv.label == "M2" && ndims(batch) == 4      # s = M²: no FFT needed
        M = Float64.(vec(Array(sum(batch; dims=(1, 2, 3))))) ./ Float64(L)^3
        return M .^ 2
    end
    φk = _fft3(batch)
    V = Float64(L)^3
    s = sum(cv.weights .* abs2.(φk); dims=(1, 2, 3))
    return Float64.(vec(Array(s))) ./ V^2
end

"""Values s and gradient ∂s/∂φ (written into `G`, same shape as `batch`)."""
function cv_values_and_gradient!(G, cv::QuadraticCV, batch)
    φk = _fft3(batch)
    V = Float64(L)^3
    s = Float64.(vec(Array(sum(cv.weights .* abs2.(φk); dims=(1, 2, 3))))) ./ V^2
    G .= FloatType(2 / V) .* real.(_ifft3(cv.weights .* φk))
    return s
end

cv_energy(s, center, kappa) = 0.5 * Float64(kappa) * (Float64(s) - Float64(center))^2

# ------------------------------------------------------------------ batched HMC
"""
Bias-force buffers, built once per workspace: cached in-place FFT plans (cuFFT on GPU,
FFTW on CPU) and per-replica (1,1,1,n) vectors.  On the GPU the bias force then needs
no host round-trip (no synchronisation, no allocation) inside the leapfrog loop.
"""
mutable struct BiasBuffers
    φk::Any            # (L,L,L,n) complex work array
    forward::Any       # plan_fft!(φk)
    inverse::Any       # plan_ifft!(φk)  (normalised)
    s::Any             # (1,1,1,n) CV values
    coef::Any          # (1,1,1,n) -κ (s - c)
    centers::Any       # (1,1,1,n)
    kappas::Any        # (1,1,1,n)
    host_centers::Vector{Float64}
    host_kappas::Vector{Float64}
    label::String      # CV the buffers were built for (M² needs no FFT buffers)
end

"""Work buffers for CV-biased batched HMC (CPU or GPU)."""
mutable struct CVWorkspace{A}
    base::Any          # BatchedHMCWorkspace on GPU, nothing on CPU
    proposal::A
    momentum::A
    force::A
    laplacian::A
    grad::A
    masses::Vector{Float64}
    bias::Any          # BiasBuffers (built lazily on first use)
end

function make_cv_workspace(batch, masses)
    nrep = size(batch, 4)
    length(masses) == nrep || throw(ArgumentError("one mass per replica"))
    base = cpu ? nothing : make_batched_workspace(batch, masses)
    return CVWorkspace(base, similar(batch), similar(batch), similar(batch), similar(batch),
                       similar(batch), Float64.(masses), nothing)
end

_is_m2(cv::QuadraticCV) = cv.label == "M2"

function _bias_buffers!(ws::CVWorkspace, cv, batch, centers, kappas)
    n = size(batch, 4)
    b = ws.bias
    if b === nothing || size(b.s, 4) != n || b.label != cv.label
        φk = _is_m2(cv) ? nothing : similar(batch, Complex{FloatType})
        fwd = φk === nothing ? nothing : plan_fft!(φk, (1, 2, 3))
        inv = φk === nothing ? nothing : plan_ifft!(φk, (1, 2, 3))
        z() = similar(batch, FloatType, 1, 1, 1, n)
        b = BiasBuffers(φk, fwd, inv, z(), z(), z(), z(), Float64[], Float64[], cv.label)
        ws.bias = b
    end
    if b.host_centers != centers || b.host_kappas != kappas
        copyto!(b.centers, reshape(FloatType.(centers), 1, 1, 1, n))
        copyto!(b.kappas, reshape(FloatType.(kappas), 1, 1, 1, n))
        b.host_centers = Float64.(centers); b.host_kappas = Float64.(kappas)
    end
    return b
end

"""
Bias force F += -κ (s - c) ∂s/∂φ for every replica; leaves s in `b.s` (1,1,1,n).
M²:     s = M², ∂s/∂φ_x = 2M/V (no FFT).
shell:  s = Σ w|φ̃|²/V², ∂s/∂φ = (2/V) Re IFFT(w φ̃), with cached in-place plans.
GPU: whole-batch broadcasts on the device.  CPU: threaded over replicas.
"""
function _add_bias_force!(F, batch, ws::CVWorkspace, cv, centers, kappas)
    b = _bias_buffers!(ws, cv, batch, centers, kappas)
    V = FloatType(L)^3
    n = size(batch, 4)
    if _is_m2(cv)
        if cpu
            Threads.@threads for r in 1:n
                @views b.s[1, 1, 1, r] = sum(batch[:, :, :, r]) / V     # M
            end
        else
            sum!(b.s, batch); b.s ./= V                                  # M
        end
        b.coef .= -b.kappas .* (b.s .^ 2 .- b.centers) .* (FloatType(2) / V) .* b.s
        if cpu
            Threads.@threads for r in 1:n
                @views F[:, :, :, r] .+= b.coef[1, 1, 1, r]
            end
        else
            F .+= b.coef                                                 # constant per replica
        end
        b.s .= b.s .^ 2                                                  # s = M²
        return b
    end
    if cpu
        Threads.@threads for r in 1:n
            @views b.φk[:, :, :, r] .= batch[:, :, :, r]
        end
    else
        b.φk .= batch
    end
    b.forward * b.φk
    if cpu
        w = cv.weights
        Threads.@threads for r in 1:n
            acc = zero(FloatType)
            @inbounds for I in CartesianIndices(w)
                acc += w[I] * abs2(b.φk[I, r])
            end
            b.s[1, 1, 1, r] = acc / V^2
            @views b.φk[:, :, :, r] .*= w
        end
    else
        b.s .= sum(cv.weights .* abs2.(b.φk); dims=(1, 2, 3)) ./ V^2
        b.φk .*= cv.weights
    end
    b.coef .= -b.kappas .* (b.s .- b.centers)
    b.inverse * b.φk
    if cpu
        Threads.@threads for r in 1:n
            c = b.coef[1, 1, 1, r] * FloatType(2) / V
            @views F[:, :, :, r] .+= c .* real.(b.φk[:, :, :, r])
        end
    else
        F .+= b.coef .* (FloatType(2) / V) .* real.(b.φk)
    end
    return b
end

# Physical force of one replica on the CPU: the same two-pass stencil as
# compute_force! (∇²φ, then ∇²(∇²φ)), but serial and allocation-free, so that replicas
# can run in parallel threads.
function _force_replica_cpu!(F, lap, ϕ, m², Z)
    @inbounds for x3 in 1:L, x2 in 1:L, x1 in 1:L
        lap[x1,x2,x3] = (ϕ[NNp(x1),x2,x3] + ϕ[NNm(x1),x2,x3] +
                         ϕ[x1,NNp(x2),x3] + ϕ[x1,NNm(x2),x3] +
                         ϕ[x1,x2,NNp(x3)] + ϕ[x1,x2,NNm(x3)] - 6*ϕ[x1,x2,x3])
    end
    @inbounds for x3 in 1:L, x2 in 1:L, x1 in 1:L
        l0 = lap[x1,x2,x3]
        lap2 = (lap[NNp(x1),x2,x3] + lap[NNm(x1),x2,x3] +
                lap[x1,NNp(x2),x3] + lap[x1,NNm(x2),x3] +
                lap[x1,x2,NNp(x3)] + lap[x1,x2,NNm(x3)] - 6*l0)
        v = ϕ[x1,x2,x3]
        F[x1,x2,x3] = Z*l0 - lap2 - m²*v - λ*v^3
    end
    return nothing
end

"""
Physical + bias force for every replica.  CPU: returns the CV values.  GPU: returns
`nothing` (the values stay on the device; use `cv_values` when they are needed).
"""
function cv_force!(F, batch, ws::CVWorkspace, Z_value, cv, centers, kappas)
    if cpu
        Zt = FloatType(Z_value)
        Threads.@threads for r in axes(batch, 4)
            @views _force_replica_cpu!(F[:, :, :, r], ws.laplacian[:, :, :, r],
                                       batch[:, :, :, r], FloatType(ws.masses[r]), Zt)
        end
        b = _add_bias_force!(F, batch, ws, cv, centers, kappas)
        return Float64.(vec(b.s))
    end
    compute_force_batched!(F, ws.laplacian, batch, ws.base.device_masses, Z_value, ws.base)
    _add_bias_force!(F, batch, ws, cv, centers, kappas)
    return nothing
end

"""Total Hamiltonian (field + bias + kinetic) per replica."""
function cv_hamiltonians(batch, momentum, ws::CVWorkspace, Z_value, cv, centers, kappas)
    nrep = size(batch, 4)
    H = zeros(Float64, nrep)
    if cpu
        Threads.@threads for r in 1:nrep
            H[r] = Float64(calc_total_energy(view(batch, :, :, :, r), ws.masses[r], Z_value)) +
                   0.5 * sum(x -> Float64(x)^2, view(momentum, :, :, :, r))
        end
    else
        batched_hamiltonians!(H, ws.base.site_energy, batch, momentum,
                              ws.base.device_masses, Z_value, ws.base)
    end
    s = cv_values(cv, batch)
    for r in 1:nrep
        H[r] += cv_energy(s[r], centers[r], kappas[r])
    end
    return H, s
end

function _accept_copy!(fields, proposal, accepted::Vector{Bool})
    if cpu
        Threads.@threads for r in findall(accepted)
            copyto!(view(fields, :, :, :, r), view(proposal, :, :, :, r))
        end
    else                                   # one masked kernel instead of one copy per replica
        mask = reshape(CuArray(accepted), 1, 1, 1, length(accepted))
        fields .= ifelse.(mask, proposal, fields)
    end
end

"""y .+= a .* x with a scalar or per-replica (1,1,1,n) `a`; threaded over replicas on CPU."""
function _axpy!(y, a, x)
    if cpu
        Threads.@threads for r in axes(y, 4)
            ar = a isa Real ? a : a[1, 1, 1, r]
            @views y[:, :, :, r] .+= ar .* x[:, :, :, r]
        end
    else
        y .+= a .* x
    end
    return y
end

"""Step size as a broadcastable value: a scalar, or one ε per replica shaped (1,1,1,n)."""
_step(eps::Real, ::Int) = FloatType(eps)
_step(eps::AbstractVector, nrep::Int) =
    (length(eps) == nrep || throw(ArgumentError("one step size per replica"));
     reshape(_to_dev(FloatType.(eps)), 1, 1, 1, nrep))

"""
One CV-biased HMC trajectory for every replica of the batch.

`eps` is a scalar or a vector with one step size per replica (window).  Each replica
is an independent HMC chain, so a per-replica ε that is held fixed while sampling
keeps every window's kernel exact.
"""
function hmc_step_cv!(batch, Z_value, eps, nlf, ws::CVWorkspace, cv, centers, kappas;
                      rng=Random.default_rng())
    randn!(ws.momentum)
    H_old, _ = cv_hamiltonians(batch, ws.momentum, ws, Z_value, cv, centers, kappas)
    copyto!(ws.proposal, batch)
    ϕ, π_field, F = ws.proposal, ws.momentum, ws.force
    e = _step(eps, size(batch, 4))
    h = e isa Real ? e / 2 : e ./ 2
    cv_force!(F, ϕ, ws, Z_value, cv, centers, kappas)
    _axpy!(π_field, h, F)
    for _ in 1:(nlf - 1)
        _axpy!(ϕ, e, π_field)
        cv_force!(F, ϕ, ws, Z_value, cv, centers, kappas)
        _axpy!(π_field, e, F)
    end
    _axpy!(ϕ, e, π_field)
    cv_force!(F, ϕ, ws, Z_value, cv, centers, kappas)
    _axpy!(π_field, h, F)
    H_new, _ = cv_hamiltonians(ϕ, π_field, ws, Z_value, cv, centers, kappas)
    ΔH = H_new .- H_old
    accepted = [d < 0 || rand(rng) < exp(-d / Float64(T)) for d in ΔH]
    _accept_copy!(batch, ws.proposal, accepted)
    return accepted, ΔH
end

"""Exact crossed-action swap test between adjacent CV windows at equal mass."""
function cv_swap_delta(s_i, s_j, c_i, c_j, k_i, k_j)
    return cv_energy(s_j, c_i, k_i) + cv_energy(s_i, c_j, k_j) -
           cv_energy(s_i, c_i, k_i) - cv_energy(s_j, c_j, k_j)
end

function swap_slices!(batch, i, j, buffer)
    copyto!(buffer, view(batch, :, :, :, i))
    copyto!(view(batch, :, :, :, i), view(batch, :, :, :, j))
    copyto!(view(batch, :, :, :, j), buffer)
end

# ------------------------------------------------------------- shell observables
"""
Per-replica shell observables from one FFT of the batch: shell power P_shell,
orientation-tensor eigenvalues (pair-power weighted) and d_eff = 1/tr(A²).
"""
function shell_observables(cv::QuadraticCV, batch)
    isempty(cv.shell_pairs) && return nothing
    φk = _fft3(batch)
    nrep = size(batch, 4)
    V2 = Float64(L)^6
    out = Vector{NamedTuple}(undef, nrep)
    # Gather only the shell entries to the host.
    lin = LinearIndices((L, L, L))
    idx = [lin[m] for m in cv.shell_modes]
    flat = reshape(φk, L^3, nrep)
    host = Array(flat[_to_dev(idx), :])          # (nmodes, nrep)
    pos = Dict(m => i for (i, m) in enumerate(cv.shell_modes))
    for r in 1:nrep
        A = zeros(3, 3)
        total = 0.0
        pmax = 0.0
        for (p, d) in zip(cv.shell_pairs, cv.shell_dirs)
            w = sum(abs2(host[pos[m], r]) for m in p)
            A .+= w .* (d * d')
            total += w
            pmax = max(pmax, w)
        end
        if total > 0
            A ./= total
            ev = sort!(eigvals(Symmetric(A)); rev=true)
            ev .= clamp.(ev, 0.0, 1.0)
            ev ./= sum(ev)
            deff = 1 / sum(abs2, ev)
        else
            ev = zeros(3); deff = 0.0
        end
        out[r] = (P_shell=total / V2, P_maxpair=pmax / V2, lambda1=ev[1], lambda2=ev[2],
                  lambda3=ev[3], d_eff=deff)
    end
    return out
end
