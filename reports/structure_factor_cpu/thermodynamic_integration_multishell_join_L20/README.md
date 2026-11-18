# Replicated multi-shell junction with the Binder line

Two fresh multi-shell replicas refine the candidate junction over
`Z=-1.45...-1.65` with spacing `0.025`.  Each point includes uniform, five
neighboring finite-q shells, and high-mass continuations.

The campaign contains 590 mass points and 4,130 seven-branch measurements.
The minimum/mean HMC acceptance is `0.900/0.975`.

## Result

Both replicas find a sign change of the finite-q envelope on the extrapolated
Binder line:

```text
replica 1: bracket [-1.600,-1.575], linear root -1.58589
replica 2: bracket [-1.550,-1.525], linear root -1.54662
coarse scan: approximately -1.558
```

The branch-history spread is much larger than the pointwise MCSE, so a
conservative summary is

```text
Z_join(L=20) approximately -1.57
continuation-systematic bracket approximately [-1.60,-1.525].
```

The selected shell is exactly `q=0.824429495415` at every Z in both replicas.
Thus this crossing is not caused by a discrete shell switch, unlike the
single-shell artifacts near `Z=-2.35`.

This identifies where the restricted uniform--inhomogeneous equality line
meets the *extrapolated* uniform Binder line.  It does not by itself determine
whether the junction is a critical endpoint, Lifshitz point, tricritical point,
or a continuation artifact.  Direct Binder crossings below `Z=-0.5`, longer
independent branches, and finite-size repetition are required.

Files:

- `binder_line_junction.png`: replicated free-energy, line-offset, and shell
  comparison.
- `junction_roots.csv`: replica brackets and interpolated roots.
- `replica_summary.csv`: complete per-Z summaries.
- `r1/` and `r2/`: integrated replica outputs.
