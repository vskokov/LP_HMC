using FFTW
using LinearAlgebra

"""Momentum-shell geometry for an L^3 periodic real field."""
struct MomentumShells
    L::Int
    q::Vector{Float64}
    members::Vector{Vector{CartesianIndex{3}}}
    pair_groups::Vector{Vector{Vector{CartesianIndex{3}}}}
end

function momentum_shells(L::Int; digits::Int=12)
    L >= 2 || throw(ArgumentError("L must be at least 2"))
    grouped = Dict{Float64,Vector{CartesianIndex{3}}}()
    for index in CartesianIndices((L, L, L))
        n = Tuple(index) .- 1
        q = round(sum(4sinpi(value / L)^2 for value in n); digits=digits)
        push!(get!(grouped, q, CartesianIndex{3}[]), index)
    end
    qvalues = sort!(collect(keys(grouped)))
    members = [grouped[q] for q in qvalues]
    pair_groups = [conjugate_pairs(shell, L) for shell in members]
    return MomentumShells(L, qvalues, members, pair_groups)
end

function conjugate_index(index::CartesianIndex{3}, L::Int)
    n = Tuple(index) .- 1
    return CartesianIndex(ntuple(axis -> mod(-n[axis], L) + 1, 3))
end

function conjugate_pairs(shell::Vector{CartesianIndex{3}}, L::Int)
    present = Set(shell)
    consumed = Set{CartesianIndex{3}}()
    groups = Vector{Vector{CartesianIndex{3}}}()
    for index in sort(shell; by=Tuple)
        index in consumed && continue
        partner = conjugate_index(index, L)
        partner in present || error("momentum shell is not closed under conjugation")
        group = partner == index ? [index] : sort([index, partner]; by=Tuple)
        union!(consumed, group)
        push!(groups, group)
    end
    return groups
end

"""Return total Fourier power per shell, normalized by V^2."""
function shell_powers(field, geometry::MomentumShells)
    size(field) == (geometry.L, geometry.L, geometry.L) ||
        throw(ArgumentError("field shape does not match shell geometry"))
    transformed = fft(field)
    volume2 = Float64(geometry.L^6)
    return [sum(abs2(transformed[index]) for index in shell) / volume2
            for shell in geometry.members]
end

function fourier_shell_observables(field, geometry::MomentumShells, shell_index::Int)
    size(field) == (geometry.L, geometry.L, geometry.L) ||
        throw(ArgumentError("field shape does not match shell geometry"))
    transformed = fft(field)
    volume2 = Float64(geometry.L^6)
    powers = [sum(abs2(transformed[index]) for index in shell) / volume2
              for shell in geometry.members]
    groups = geometry.pair_groups[shell_index]
    orientation = [sum(abs2(transformed[index]) for index in group) for group in groups]
    total = sum(orientation)
    if !(total > 0)
        return (powers=powers, maximum_fraction=0.0, participation=0.0)
    end
    return (
        powers=powers,
        maximum_fraction=maximum(orientation) / total,
        participation=total^2 / sum(abs2, orientation),
    )
end

function selected_shell_index(geometry::MomentumShells, selected_q::Real)
    index = argmin(abs.(geometry.q .- Float64(selected_q)))
    abs(geometry.q[index] - selected_q) <= 5e-11 ||
        throw(ArgumentError("selected q=$(selected_q) is not a lattice shell"))
    return index
end

"""Orientation diagnostics from the conjugate momentum pairs of one shell."""
function shell_orientation(field, geometry::MomentumShells, shell_index::Int)
    transformed = fft(field)
    groups = geometry.pair_groups[shell_index]
    values = [sum(abs2(transformed[index]) for index in group) for group in groups]
    total = sum(values)
    if !(total > 0)
        return (maximum_fraction=0.0, participation=0.0)
    end
    return (
        maximum_fraction=maximum(values) / total,
        participation=total^2 / sum(abs2, values),
    )
end

"""Signed lattice momentum and unit direction for one FFT array index."""
function lattice_momentum_direction(index::CartesianIndex{3}, L::Int)
    raw = Tuple(index) .- 1
    signed = ntuple(axis -> raw[axis] <= L ÷ 2 ? raw[axis] : raw[axis] - L, 3)
    momentum = Float64[2sinpi(value / L) for value in signed]
    norm2 = sum(abs2, momentum)
    norm2 > 0 || throw(ArgumentError("the zero mode has no modulation direction"))
    return momentum ./ sqrt(norm2)
end

function _adjacent_background_per_mode(transformed, geometry::MomentumShells,
                                       shell_indices::Vector{Int})
    selected = Set(shell_indices)
    lower = minimum(shell_indices) - 1
    while lower >= 1 && (lower in selected || geometry.q[lower] <= 1e-12)
        lower -= 1
    end
    upper = maximum(shell_indices) + 1
    while upper <= length(geometry.q) && upper in selected
        upper += 1
    end
    samples = Tuple{Float64,Float64}[]
    if lower >= 1
        power = sum(abs2(transformed[index]) for index in geometry.members[lower])
        push!(samples, (geometry.q[lower], power / length(geometry.members[lower])))
    end
    if upper <= length(geometry.q)
        power = sum(abs2(transformed[index]) for index in geometry.members[upper])
        push!(samples, (geometry.q[upper], power / length(geometry.members[upper])))
    end
    isempty(samples) && return 0.0
    length(samples) == 1 && return samples[1][2]
    target_q = sum(geometry.q[shell_indices]) / length(shell_indices)
    (q0, p0), (q1, p1) = samples
    fraction = clamp((target_q - q0) / (q1 - q0), 0.0, 1.0)
    return (1 - fraction) * p0 + fraction * p1
end

"""
    modulation_rank_observables(field, geometry, shell_index; include_adjacent=false)

Return the per-configuration orientation tensor of the excess Fourier power.
The eigenvalues are computed before any ensemble average, so a rotating
lamellar state remains rank one.  `raw_excess_power` is deliberately not
clipped and is the quantity to use for deciding whether modulation is present.
"""
function modulation_rank_observables(field, geometry::MomentumShells, shell_index::Int;
                                      include_adjacent::Bool=false)
    size(field) == (geometry.L, geometry.L, geometry.L) ||
        throw(ArgumentError("field shape does not match shell geometry"))
    geometry.q[shell_index] > 1e-12 ||
        throw(ArgumentError("modulation rank requires a nonzero momentum shell"))
    transformed = fft(field)
    shell_indices = include_adjacent ?
        collect(max(2, shell_index - 1):min(length(geometry.q), shell_index + 1)) :
        [shell_index]
    background_raw = _adjacent_background_per_mode(transformed, geometry, shell_indices)
    volume2 = Float64(geometry.L^6)
    tensor = zeros(Float64, 3, 3)
    raw_power = 0.0
    raw_excess = 0.0
    clipped_excess = 0.0
    for selected in shell_indices
        for group in geometry.pair_groups[selected]
            pair_power = sum(abs2(transformed[index]) for index in group)
            pair_excess = pair_power - background_raw * length(group)
            weight = max(pair_excess, 0.0)
            direction = lattice_momentum_direction(first(group), geometry.L)
            tensor .+= weight .* (direction * direction')
            raw_power += pair_power
            raw_excess += pair_excess
            clipped_excess += weight
        end
    end
    if clipped_excess > 0
        tensor ./= clipped_excess
        eigenvalues = sort!(eigvals(Symmetric(tensor)); rev=true)
        eigenvalues .= clamp.(eigenvalues, 0.0, 1.0)
        eigenvalues ./= sum(eigenvalues)
        effective_dimension = inv(sum(abs2, eigenvalues))
    else
        eigenvalues = zeros(Float64, 3)
        effective_dimension = 0.0
    end
    return (
        tensor_xx=tensor[1, 1], tensor_yy=tensor[2, 2], tensor_zz=tensor[3, 3],
        tensor_xy=tensor[1, 2], tensor_xz=tensor[1, 3], tensor_yz=tensor[2, 3],
        lambda1=eigenvalues[1], lambda2=eigenvalues[2], lambda3=eigenvalues[3],
        effective_dimension=effective_dimension,
        background_per_mode=background_raw / volume2,
        raw_power=raw_power / volume2,
        raw_excess_power=raw_excess / volume2,
        excess_power=clipped_excess / volume2,
    )
end

function field_statistics(field)
    L = size(field, 1)
    size(field) == (L, L, L) || throw(ArgumentError("field must be cubic"))
    total = 0.0
    quadratic = 0.0
    gradient = 0.0
    for z in 1:L, y in 1:L, x in 1:L
        value = Float64(field[x, y, z])
        total += value
        quadratic += value^2
        gradient += (Float64(field[mod1(x + 1, L), y, z]) - value)^2
        gradient += (Float64(field[x, mod1(y + 1, L), z]) - value)^2
        gradient += (Float64(field[x, y, mod1(z + 1, L)]) - value)^2
    end
    magnetization = total / L^3
    return (M=magnetization, M2=magnetization^2, Q=quadratic, G=gradient)
end
