# Wide L=16 modulation map

This exploratory CPU campaign extends the restricted-branch thermodynamic
integration over a broad `(Z,m2)` patch.  It follows uniform, initialized
finite-`q`, and high-mass continuations and compares their integrated free
energies using

```text
d(f_a-f_b)/d(m2) = 0.5 * (Q_a/V - Q_b/V).
```

## Coverage

- `Z=-0.5,...,-3.0` with coarse spacing `0.125`.
- A dense band `Z=-2.25,...,-2.50` with spacing `0.025`.
- `m2` spacing `0.25`, with the exact extrapolated Binder-line mass inserted.
- The high-mass endpoint is at least `Z^2/4 + 1`, so it remains above the bare
  finite-momentum instability.
- For `Z<=-2.3`, the low-mass endpoint is four units below the extrapolated
  Binder line to search for the return of the uniform phase.

The final manifest contains 29 `Z` slices, 1,142 mass points, and 3,426 branch
measurements.  The minimum HMC acceptance was `0.90` and the mean acceptance
was `0.974`.

## Main observations

1. From `Z=-0.5` through `Z=-2.275`, the extrapolated Binder-line point is on
   the `q=0` side of the restricted free-energy comparison.
2. At `Z=-2.300`, the lowest coherent finite-`q` continuation is already below
   the uniform continuation on the Binder line.  The onset is therefore
   bracketed by

   ```text
   -2.300 <= Z_onset(L=16) < -2.275.
   ```

   A linear interpolation would give approximately `Z=-2.279`, but this should
   not be interpreted as a continuous estimate.
3. The selected Binder-line shell changes from `q=1.17157287525` at `Z=-2.275`
   to `q=1.23463313527` at `Z=-2.300`.  The onset is therefore entangled with
   the discrete momentum grid at `L=16`.
4. At more-negative `Z`, different coherent finite-`q` continuations exchange
   stability.  In particular, the continuation initialized at high mass often
   settles into a different ordered shell than the branch initialized near the
   bare mean-field momentum.  The resulting jagged boundary is useful evidence
   of shell competition, but it is not a smooth thermodynamic phase boundary.
5. For several deep-`Z` slices, a finite-`q` branch remains favored even at the
   extended low-mass edge.  Those lower `q=0`/finite-`q` boundaries are reported
   as `finite_q_at_low_edge`, not extrapolated beyond the data.

## Output guide

- `wide_phase_map.png`: categorical preferred-phase map and selected momentum.
- `thermodynamic_integration.png`: all restricted free-energy curves and the
  bracketed ordered-branch boundary.
- `crossing_summary.csv`: boundaries, Binder-line free-energy differences,
  selected shell, and boundary status for every `Z`.
- `integrated_branches.csv`: all pointwise observables and free-energy results.
- `pairwise_crossings.csv`: raw pairwise roots, including roots in merged/noisy
  regions; use `crossing_summary.csv` for the filtered interpretation.
- `manifest.csv`: exact parameters and raw-data locations.

## Interpretation limits

These are short, single-continuation restricted free energies.  Their batch
MCSEs do not include initialization, continuation, or branch-selection
systematics.  The high-mass continuation must not be called “disordered” after
it enters an ordered basin at lower mass.  A controlled infinite-volume
boundary now requires repeating the onset band at another lattice size so the
allowed momentum shells change, plus independent continuation replicates near
`Z=-2.275` and `-2.300`.
