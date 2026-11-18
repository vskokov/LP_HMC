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
    make_cv(L, kind; shell_target=NaN, mix=1.0)

kind = "M2" (w = δ_{k0}), "shell" (w = 1 on the k̂² shell nearest `shell_target`),
or "mixed" (w = δ_{k0} − mix·shell).
"""
function make_cv(L::Int, kind::AbstractString; shell_target::Float64=NaN, mix::Float64=1.0)
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
    end
    if kind in ("M2", "mixed")
        w[1, 1, 1] = 1.0
    end
    kind in ("M2", "shell", "mixed") || throw(ArgumentError("unknown CV kind $kind"))
    label = kind == "M2" ? "M2" : kind == "shell" ? @sprintf("shell(q=%.10g)", q) :
            @sprintf("mixed(q=%.10g,c=%.6g)", q, mix)
    return QuadraticCV(_to_dev(FloatType.(w)), label, q, modes, pairs, dirs)
end

_fft3(x) = fft(x, (1, 2, 3))
_ifft3(x) = ifft(x, (1, 2, 3))

"""CV value for every replica of a (L,L,L,n) batch (or a single (L,L,L) field)."""
function cv_values(cv::QuadraticCV, batch)
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
"""Work buffers for CV-biased batched HMC (CPU or GPU)."""
mutable struct CVWorkspace{A}
    base::Any          # BatchedHMCWorkspace on GPU, nothing on CPU
    proposal::A
    momentum::A
    force::A
    laplacian::A
    grad::A
    masses::Vector{Float64}
end

function make_cv_workspace(batch, masses)
    nrep = size(batch, 4)
    length(masses) == nrep || throw(ArgumentError("one mass per replica"))
    base = cpu ? nothing : make_batched_workspace(batch, masses)
    return CVWorkspace(base, similar(batch), similar(batch), similar(batch), similar(batch),
                       similar(batch), Float64.(masses))
end

"""Physical + bias force for every replica; returns the CV values."""
function cv_force!(F, batch, ws::CVWorkspace, Z_value, cv, centers, kappas)
    if cpu
        for r in axes(batch, 4)
            compute_force!(view(F, :, :, :, r), view(batch, :, :, :, r), ws.masses[r], Z_value)
        end
    else
        compute_force_batched!(F, ws.laplacian, batch, ws.base.device_masses, Z_value, ws.base)
    end
    s = cv_values_and_gradient!(ws.grad, cv, batch)
    coef = FloatType.(-Float64.(kappas) .* (s .- Float64.(centers)))
    F .+= reshape(_to_dev(coef), 1, 1, 1, :) .* ws.grad
    return s
end

"""Total Hamiltonian (field + bias + kinetic) per replica."""
function cv_hamiltonians(batch, momentum, ws::CVWorkspace, Z_value, cv, centers, kappas)
    nrep = size(batch, 4)
    H = zeros(Float64, nrep)
    if cpu
        for r in 1:nrep
            H[r] = Float64(calc_total_energy(view(batch, :, :, :, r), ws.masses[r], Z_value)) +
                   0.5 * sum(abs2, Float64.(view(momentum, :, :, :, r)))
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
    for r in findall(accepted)
        copyto!(view(fields, :, :, :, r), view(proposal, :, :, :, r))
    end
end

"""One CV-biased HMC trajectory for every replica of the batch."""
function hmc_step_cv!(batch, Z_value, eps, nlf, ws::CVWorkspace, cv, centers, kappas;
                      rng=Random.default_rng())
    randn!(ws.momentum)
    H_old, _ = cv_hamiltonians(batch, ws.momentum, ws, Z_value, cv, centers, kappas)
    copyto!(ws.proposal, batch)
    ϕ, π_field, F = ws.proposal, ws.momentum, ws.force
    cv_force!(F, ϕ, ws, Z_value, cv, centers, kappas)
    π_field .+= FloatType(eps / 2) .* F
    for _ in 1:(nlf - 1)
        ϕ .+= FloatType(eps) .* π_field
        cv_force!(F, ϕ, ws, Z_value, cv, centers, kappas)
        π_field .+= FloatType(eps) .* F
    end
    ϕ .+= FloatType(eps) .* π_field
    cv_force!(F, ϕ, ws, Z_value, cv, centers, kappas)
    π_field .+= FloatType(eps / 2) .* F
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
