# L=16 exploratory branch thermodynamic integration

This campaign tests whether the extrapolated Binder-crossing line reaches a
finite-wavevector ordered phase.  It is an exploratory CPU calculation at
`L=16`, not a production phase-boundary determination.

## Method

At each of seven fixed values of `Z`, three HMC continuations were followed on
the same `m2` grid:

- a spatially uniform ordered start, continued from low to high `m2`;
- a single-mode finite-`q` start, continued from low to high `m2`;
- a disordered start, continued from high to low `m2`.

The measured conjugate density is `Q/V = sum(phi^2)/V`.  For any two restricted
branches `a` and `b`, their free-energy-density difference obeys

```text
d(f_a-f_b)/d(m2) = 0.5 * (Q_a/V - Q_b/V).
```

The three continuations are anchored to equal free energy at the largest mass,
where all have disordered observables, and integrated downward with the
trapezoid rule.  The reported statistical errors propagate the batch-MCSE of
`Q/V`; they do not include continuation or initialization systematics.

## Main result

The uniform branch is lower than both alternatives at every point on the
extrapolated Binder line from `Z=-0.75` through `Z=-1.5`.  A coherent finite-`q`
branch becomes lower at a less-negative mass for six of the seven scans:

| Z | extrapolated Binder m2 | q=0 to finite-q crossing | offset |
|---:|---:|---:|---:|
| -0.75 | -2.110 | -1.682 | 0.428 |
| -0.85 | -2.274 | unresolved | -- |
| -0.95 | -2.451 | -1.961 | 0.490 |
| -1.05 | -2.638 | -1.897 | 0.741 |
| -1.15 | -2.837 | -2.243 | 0.595 |
| -1.30 | -3.157 | -2.762 | 0.395 |
| -1.50 | -3.623 | -3.092 | 0.531 |

Here a crossing is retained only when `f_mod-f_uniform` changes from positive
to negative as `m2` increases and the continued modulated state still has
`S_peak >= 10`.  At `Z=-0.85`, the only raw free-energy root occurs after the
modulated continuation has become a noise-level disordered spectrum, so it is
not classified as a physical ordered-branch crossing.

The result therefore does **not** show the Binder-line transition changing to
nonzero momentum within this range.  It instead locates a separate finite-`q`
wedge above the extrapolated Binder line.  The quadratic extrapolation of the
Binder line, based only on `Z=-0.5,-0.25,0`, should not be trusted indefinitely
at more negative `Z`.

## Files

- `thermodynamic_integration.png`: free-energy curves and cleaned boundary plot.
- `crossing_summary.csv`: one-row-per-`Z` summary, including raw and selected roots.
- `pairwise_crossings.csv`: all linearly interpolated roots, including noise-region roots.
- `integrated_branches.csv`: pointwise observables, free-energy differences, MCSEs,
  and a conservative two-MCSE preferred-branch label.
- `manifest.csv`: exact scan inputs and raw statistics paths.

## Limitations and next check

Each branch currently has only one short continuation (`100` retained samples
per mass after settling), neighboring mass points are correlated through the
continued configuration, and metastable branches need not represent the full
canonical ensemble.  A production claim requires independent continuation
replicates and a finer `m2` grid around the selected crossings.  The most useful
next calculation is a focused replication at `Z=-0.75,-0.85,-0.95`, which tests
the anomalous missing crossing and determines whether the apparent onset is
smooth or affected by shell locking at finite `L`.
