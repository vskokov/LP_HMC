# Wide L=20 scan in Z and m2

This campaign extends the replicated `L=20` onset check into a broad
two-dimensional map.

## Coverage

- `Z=-0.5,...,-2.25` with spacing `0.125`.
- `Z=-2.25,...,-2.60` with spacing `0.025`.
- `Z=-2.65,...,-3.00` with spacing `0.05`.
- `m2` spacing `0.25`, with the exact extrapolated Binder-line mass inserted.
- The low endpoint is four units below that line; the high endpoint is above
  `Z^2/4+1`.
- 37 Z slices, 1,640 mass points, and 4,920 branch measurements.
- Minimum/mean HMC acceptance: `0.890/0.9757`.

## Result

The finite-`q` restricted free-energy envelope is above the uniform branch on
the extrapolated Binder line through `Z=-2.350`, where
`delta f=+0.0288`.  It is below the uniform branch at `Z=-2.375`, where
`delta f=-0.0496`.

The sign change coincides exactly with a selected-shell jump:

```text
Z=-2.350: q=1.14589803375
Z=-2.375: q=1.20639550666
```

At more-negative Z the Binder-line finite-`q` branch remains favored, with
additional shell changes near `Z=-2.525`, `-2.700`, and `-2.900`.  Many deep-Z
slices remain finite-q favored at the low edge, so no lower boundary is
extrapolated there.

In the added `Z=-0.5...-2.25` region, the Binder-line point is on the uniform
side throughout `Z=-0.5...-1.5`.  Isolated negative differences occur at
`Z=-1.625`, `-1.875`, and `-2.125`, but positive differences return at the
interleaved points `Z=-1.75`, `-2.0`, and `-2.25`.  These alternating signs
track changes among discrete selected shells and do not define a monotone
physical onset.  They reinforce the conclusion that single-shell branch
selection is the limiting systematic of this exploratory map.

The sharp first sign change required a replicated refinement because it occurs
at a discrete shell switch.  See the adjacent
`thermodynamic_integration_L20_refine` report.

## Files

- `wide_phase_map.png`: preferred-phase and selected-momentum map.
- `thermodynamic_integration.png`: branch free-energy curves and boundaries.
- `crossing_summary.csv`: one-row-per-Z summary.
- `integrated_branches.csv`: full pointwise analysis.
- `manifest.csv`: exact parameters and raw-data paths.
