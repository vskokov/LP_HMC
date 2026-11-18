# Multi-shell L=20 phase-line map

This campaign removes the nearest-shell preselection that dominated the
earlier continuation maps.  At every `(Z,m2)`, five neighboring nonzero lattice
shells around the bare guide `-Z/2` are continued independently, together with
the uniform and high-mass branches.  All branches share the same high-mass
free-energy anchor.  The lowest coherent (`S_peak>=10`) nonzero-shell branch
defines the finite-q envelope.

## Coverage

- `L=20`.
- `Z=-0.5,-0.625,...,-2.5`.
- `m2` spacing `0.2`, including the exact extrapolated Binder-line mass.
- 17 Z slices, 626 mass points, and 4,382 seven-branch measurements.
- Minimum/mean HMC acceptance: `0.887/0.975`.

## Main result

The finite-q envelope is above the extrapolated Binder line through `Z=-1.5`
and below it for every sampled `Z<=-1.625`.  Unlike the false single-shell
onsets, the selected Binder-line shell is unchanged across this interval:

```text
q_selected = 0.824429495415.
```

The coarse free-energy differences are

```text
Z=-1.500: delta f = +0.01165
Z=-1.625: delta f = -0.01328
```

giving a coarse linear junction near `Z=-1.558`.  The `q=0`/finite-q equality
line crosses the negative-Z extrapolation of the Binder line at the same
location.  For less-negative Z it lies at higher mass, leaving a candidate
finite-q wedge between the equality line and the operational coherence limit.

The Binder line is directly measured only down to `Z=-0.5`; its continuation
to the junction is a quadratic extrapolation.  Therefore this is a candidate
connection to the Binder line, not yet a measured multicritical point.

## Outputs

- `phase_line_connection.png`: Binder data/extrapolation, uniform--finite-q
  equality line, coherence proxy, Binder-line free-energy difference, and
  selected shell.
- `multishell_envelopes.png`: five-shell free-energy envelopes versus mass.
- `multishell_summary.csv`: one-row-per-Z phase-line summary.
- `integrated_multishell.csv`: pointwise selected-envelope data.
- `manifest.csv`: exact parameters and raw-data paths.

The junction is independently refined in the adjacent
`thermodynamic_integration_multishell_join_L20` campaign.
