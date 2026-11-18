# Replicated L=20 shell-change refinement

Two fresh continuation replicas were run at
`Z=-2.350,-2.355,...,-2.375`, using the same full mass paths as the wide scan.
The campaign contains 624 mass points and 1,872 branch measurements.

Both replicas independently find:

- positive `f_finite-q-f_uniform` at `Z=-2.350`;
- negative values at every `Z<=-2.355`;
- a simultaneous shell jump from `q=1.14589803375` to `q=1.20639550666`.

Linear interpolation gives roots

```text
replica 1: Z=-2.3520763157
replica 2: Z=-2.3520853557
```

The nearest-shell switch predicted from the midpoint of the two lattice shells
is

```text
Z_shell = -(1.14589803375 + 1.20639550666) = -2.35229354041.
```

The numerical roots track this shell-selection threshold to about `2.1e-4`.
Accordingly, the sharp crossing is not evidence for a smoothly resolved
thermodynamic onset; it is controlled by the discrete L=20 momentum grid and
the branch initialization/selection rule.  The wide map still demonstrates a
finite-q favored region at sufficiently negative Z, but a physical boundary
must be extracted with a method that samples competing shells together and is
compared across volumes.

Files:

- `replicated_onset.png`: the three independent scans and shell jump.
- `onset_summary.csv`: interpolated roots.
- `replica_crossing_summary.csv`: full per-Z summaries.
- `r1/` and `r2/`: integrated branch tables and diagnostic plots.
