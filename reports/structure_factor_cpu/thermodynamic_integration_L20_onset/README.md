# L=20 finite-size check of the L=16 modulation onset

This campaign tests whether the sharp restricted-branch sign change observed at
`L=16` near `Z=-2.275...-2.300` persists when the allowed momentum shells are
changed.

## Design

- Lattice size: `L=20`.
- `Z=-2.25,-2.2625,...,-2.325`.
- Two statistically independent continuation replicas at every `Z`.
- Three continuations per replica: uniform low-mass start, finite-`q` start,
  and high-mass start continued downward.
- `m2` spacing `0.25`, including the exact extrapolated Binder-line mass.
- The mass interval extends four units below the Binder line and above
  `Z^2/4+1`.
- HMC parameters: `eps=0.0085`, `n_lf=15`.
- Each mass uses 100 settling trajectories (300 at the initial endpoint), then
  100 retained measurements separated by two trajectories.

The final campaign contains 712 mass points and 2,136 branch measurements.
The minimum HMC acceptance is `0.897` and the mean is `0.975`.

## Result

The finite-`q` restricted free-energy envelope remains above the uniform branch
at the extrapolated Binder-line mass for every scanned `Z` in both replicas.
The full range is

```text
replica 0: delta f = +0.0282 ... +0.0392
replica 1: delta f = +0.0318 ... +0.0363
```

No sign change occurs.  Both replicas select the same coherent shell,
`q=1.14589803375`, throughout the interval.  Their `q=0`/finite-`q` branch
crossings lie at less-negative masses, approximately `m2=-5.27...-5.62`, while
the extrapolated Binder line lies near `m2=-5.77...-6.03`.

This differs qualitatively from `L=16`, where the finite-`q` envelope changes
sign and the selected shell jumps between `q=1.171573` and `q=1.234633` in the
same `Z` interval.  The putative `L=16` onset near `Z=-2.29` therefore does not
survive this finite-size check and is likely dominated by momentum-shell
locking and/or metastable continuation selection.

The result does not exclude a finite-`q` transition at more-negative `Z` for
`L=20`; it shows that the `L=16` onset bracket is not volume-stable.

## Files

- `L16_L20_onset_comparison.png`: direct finite-size and replica comparison.
- `finite_size_onset_summary.csv`: sign-change audit for both replicas.
- `replica_crossing_summary.csv`: pointwise crossing summaries.
- `r0/` and `r1/`: full integrated tables and diagnostic figures.
- `manifest.csv`: exact simulation parameters and raw-data paths.
