#!/usr/bin/env julia
# CPU correctness tests for src/quadratic_cv.jl (no ArgParse; L=6, Float64).
#   julia --project=. scripts/test_quadratic_cv.jl
# Set QCV_GPU=true to run the GPU batched-vs-CPU comparison instead (needs CUDA).

cd(@__DIR__)
using Printf
using Random
using Statistics

const L = 6
const FloatType = Float64
const cpu = !(lowercase(get(ENV, "QCV_GPU", "false")) in ("1", "true", "yes"))
const λ = FloatType(4.0)
const T = FloatType(1.0)
const Z = FloatType(-2.0)
const ε = FloatType(0.01)
const n_lf = 20

include("../src/simulation.jl")
include("structure_factor_observables.jl")
include("../src/quadratic_cv.jl")

failures = 0
function check(name, ok, detail)
    global failures
    @printf("%-4s  %-40s %s\n", ok ? "PASS" : "FAIL", name, detail)
    ok || (failures += 1)
end

Random.seed!(7)
m2 = -1.2
host_field() = 0.3 .* randn(L, L, L) .+ 0.2 .* [cos(2π * (x - 1) / L) for x in 1:L, y in 1:L, z in 1:L]

function total_energy(ϕ, m2, cv, c, k)
    return Float64(calc_total_energy(ϕ, m2, Z)) + cv_energy(cv_values(cv, ϕ)[1], c, k)
end

if cpu
    ϕ = host_field()
    # 1. M2 CV reproduces the legacy umbrella coordinate and force.
    cvM = make_cv(L, "M2")
    s = cv_values(cvM, ϕ)[1]
    check("M2 value == umbrella_coordinate", abs(s - umbrella_coordinate(ϕ)) < 1e-12,
          @sprintf("diff=%.2e", s - umbrella_coordinate(ϕ)))
    batch = reshape(copy(ϕ), L, L, L, 1)
    ws = make_cv_workspace(batch, [m2])
    F1 = similar(batch)
    cv_force!(F1, batch, ws, Z, cvM, [0.05], [3000.0])
    F2 = similar(ϕ)
    compute_force_umbrella!(F2, ϕ, m2, Z, 0.05, 3000.0)
    check("M2 force == legacy umbrella force", maximum(abs.(F1[:, :, :, 1] .- F2)) < 1e-10,
          @sprintf("max=%.2e", maximum(abs.(F1[:, :, :, 1] .- F2))))

    # 2. Finite-difference force for shell and mixed CVs (physical + bias).
    for (kind, kw) in (("shell", (shell_target=1.0,)), ("mixed", (shell_target=1.0, mix=0.7)),
                       ("band", (band=(0.5, 2.1),)), ("mixedband", (band=(0.5, 2.1), mix=0.7)))
        cv = make_cv(L, kind; kw...)
        c, k = 0.02, 5000.0
        Fb = similar(batch)
        cv_force!(Fb, batch, ws, Z, cv, [c], [k])
        h = 1e-6
        errs = Float64[]
        for site in (CartesianIndex(1, 1, 1), CartesianIndex(2, 3, 4), CartesianIndex(6, 5, 1),
                     CartesianIndex(4, 4, 4))
            p = copy(ϕ); p[site] += h
            mns = copy(ϕ); mns[site] -= h
            fd = -(total_energy(p, m2, cv, c, k) - total_energy(mns, m2, cv, c, k)) / (2h)
            push!(errs, abs(fd - Fb[site, 1]) / max(abs(fd), 1e-8))
        end
        check("FD force ($kind)", maximum(errs) < 1e-5, @sprintf("max_rel=%.2e  q=%.4f", maximum(errs), cv.shell_q))
        if kind == "band"
            # band value == sum of the single-shell values over the shells in the band
            g = momentum_shells(L)
            parts = sum(cv_values(make_cv(L, "shell"; shell_target=q), ϕ)[1]
                        for q in g.q if 0.5 - 1e-9 <= q <= 2.1 + 1e-9)
            check("band value == sum of shell values", abs(cv_values(cv, ϕ)[1] - parts) < 1e-12,
                  @sprintf("diff=%.2e", cv_values(cv, ϕ)[1] - parts))
        end
    end

    # 3. Energy conservation and reversibility for a biased trajectory (3 replicas).
    cv = make_cv(L, "shell"; shell_target=1.0)
    nrep = 3
    b = cat((host_field() for _ in 1:nrep)...; dims=4)
    ws3 = make_cv_workspace(b, fill(m2, nrep))
    centers, kappas = [0.0, 0.02, 0.05], fill(4000.0, nrep)
    randn!(ws3.momentum)
    H0, _ = cv_hamiltonians(b, ws3.momentum, ws3, Z, cv, centers, kappas)
    ϕp = copy(b); πp = copy(ws3.momentum)
    function traj!(ϕx, πx, eps, steps)
        F = similar(ϕx)
        cv_force!(F, ϕx, ws3, Z, cv, centers, kappas); πx .+= eps / 2 .* F
        for _ in 1:steps-1
            ϕx .+= eps .* πx; cv_force!(F, ϕx, ws3, Z, cv, centers, kappas); πx .+= eps .* F
        end
        ϕx .+= eps .* πx; cv_force!(F, ϕx, ws3, Z, cv, centers, kappas); πx .+= eps / 2 .* F
    end
    traj!(ϕp, πp, 0.002, 100)
    H1, _ = cv_hamiltonians(ϕp, πp, ws3, Z, cv, centers, kappas)
    rel = maximum(abs.(H1 .- H0) ./ abs.(H0))
    check("energy conservation (eps=0.002)", rel < 1e-4, @sprintf("max|dH|/|H|=%.2e", rel))
    πp .*= -1
    traj!(ϕp, πp, 0.002, 100)
    check("reversibility", maximum(abs.(ϕp .- b)) < 1e-9, @sprintf("max|dphi|=%.2e", maximum(abs.(ϕp .- b))))

    # 4. Exact swap action.
    s = cv_values(cv, b)
    Hs = [total_energy(b[:, :, :, r], m2, cv, centers[r], kappas[r]) for r in 1:2]
    Hx = total_energy(b[:, :, :, 2], m2, cv, centers[1], kappas[1]) +
         total_energy(b[:, :, :, 1], m2, cv, centers[2], kappas[2])
    d = cv_swap_delta(s[1], s[2], centers[1], centers[2], kappas[1], kappas[2])
    check("exact CV swap action", abs((Hx - sum(Hs)) - d) < 1e-8, @sprintf("err=%.2e", (Hx - sum(Hs)) - d))

    # 5. Lamellar field: P_shell = A^2/2 and rank one.
    A = 0.7
    lam = [A * cos(2π * (y - 1) / L) for x in 1:L, y in 1:L, z in 1:L]
    cvl = make_cv(L, "shell"; shell_target=4sinpi(1 / L)^2)
    o = shell_observables(cvl, reshape(lam, L, L, L, 1))[1]
    check("lamellar P_shell = A^2/2", abs(o.P_shell - A^2 / 2) < 1e-12, @sprintf("P=%.6f", o.P_shell))
    check("lamellar d_eff = 1", abs(o.d_eff - 1) < 1e-12, @sprintf("d_eff=%.6f", o.d_eff))
    cube = [A * (cos(2π * (x - 1) / L) + cos(2π * (y - 1) / L) + cos(2π * (z - 1) / L))
            for x in 1:L, y in 1:L, z in 1:L]
    o3 = shell_observables(cvl, reshape(cube, L, L, L, 1))[1]
    check("cubic field d_eff = 3", abs(o3.d_eff - 3) < 1e-10, @sprintf("d_eff=%.6f", o3.d_eff))

    # 6. Short biased sampling: HMC acceptance sane.
    acc = sum(sum(hmc_step_cv!(b, Z, 0.01, 20, ws3, cv, centers, kappas)[1]) for _ in 1:100)
    rate = acc / 300
    check("biased HMC acceptance", 0.5 < rate <= 1.0, @sprintf("rate=%.3f", rate))
else
    # GPU: batched CV force/Hamiltonian must match the CPU-style per-replica evaluation.
    CUDA.functional() || error("CUDA not functional")
    nrep = 4
    hb = cat((host_field() for _ in 1:nrep)...; dims=4)
    b = CuArray(hb)
    masses = [-1.2, -1.1, -1.0, -0.9]
    ws = make_cv_workspace(b, masses)
    cv = make_cv(L, "shell"; shell_target=1.0)
    centers, kappas = [0.0, 0.01, 0.02, 0.03], fill(4000.0, nrep)
    F = similar(b)
    s = cv_force!(F, b, ws, Z, cv, centers, kappas)
    Fh = Array(F)
    errs = Float64[]
    for r in 1:nrep
        ϕ = hb[:, :, :, r]
        h = 1e-6
        for site in (CartesianIndex(1, 1, 1), CartesianIndex(3, 2, 5))
            p = copy(ϕ); p[site] += h; mns = copy(ϕ); mns[site] -= h
            e(x) = total_energy(CuArray(x), masses[r], cv, centers[r], kappas[r])
            fd = -(e(p) - e(mns)) / (2h)
            push!(errs, abs(fd - Fh[site, r]) / max(abs(fd), 1e-8))
        end
    end
    check("GPU batched FD force", maximum(errs) < 1e-5, @sprintf("max_rel=%.2e", maximum(errs)))
    mom = CUDA.randn(FloatType, L, L, L, nrep)
    H, _ = cv_hamiltonians(b, mom, ws, Z, cv, centers, kappas)
    Href = [total_energy(CuArray(hb[:, :, :, r]), masses[r], cv, centers[r], kappas[r]) +
            0.5 * sum(abs2, Array(mom)[:, :, :, r]) for r in 1:nrep]
    check("GPU batched Hamiltonian", maximum(abs.(H .- Href) ./ abs.(Href)) < 1e-10,
          @sprintf("max_rel=%.2e", maximum(abs.(H .- Href) ./ abs.(Href))))
    acc = sum(sum(hmc_step_cv!(b, Z, 0.01, 20, ws, cv, centers, kappas)[1]) for _ in 1:50)
    check("GPU biased HMC acceptance", acc / (50nrep) > 0.5, @sprintf("rate=%.3f", acc / (50nrep)))
end

println(failures == 0 ? "ALL PASS" : "$(failures) FAILURE(S)")
exit(failures == 0 ? 0 : 1)
