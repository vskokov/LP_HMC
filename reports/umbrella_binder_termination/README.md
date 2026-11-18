# Direct Binder termination scan

This campaign brackets where the uniform second-order line gives way to a
finite-wavevector instability.  Existing structure-factor results put the
change between `Z=-0.75` (selected shell `q*=0`) and `Z=-1` (nonzero lowest
shell for `L=16,20`).  The older apparent junction near `Z=-1.57` relied on an
extrapolated Binder line and is not used to position this scan.

The discovery grid is `Z=-0.80,-0.85,-0.90,-0.95`, with five masses at offsets
`-0.06,-0.03,0,+0.03,+0.06` around the quadratic Binder-line estimate.  Every
point has independent ordered and disordered starts.  `L=12,16,20` form the
initial finite-size comparison; `L=24` is prepared but held for confirmation.

The decisive analysis combines pairwise Binder crossings with a disordered-side
fit

```text
1/S(q) = r + c2 qhat^2 + c4 qhat^4.
```

On a continuous uniform critical line, `r=0` and `c2>0`; a continuous Lifshitz
termination additionally has `c2=0`.  Coexistence or a barrier appearing while
`c2` remains positive instead indicates first-order preemption.  Classification
will therefore use several sizes and both Binder and structure-factor evidence,
not a single shell jump or size pair.

## Central-pilot result (2026-11-08)

All 24 central pilots completed for `L=12,16,20`, with both ordered and
disordered starts at each `Z`.  Canonically weighted checkpoint censuses give:

| Z | L=12 | L=16 | L=20 |
|---:|:---:|:---:|:---:|
| -0.80 | q=0 | q=0 | q=0 |
| -0.85 | q=0 | q=0 | q=0 |
| -0.90 | q=0 | q=0 | q=0 |
| -0.95 | first nonzero shell | q=0 | first nonzero shell |

The two independent starts agree on the selected shell in every cell.  Thus
the onset is now bracketed to approximately `-0.95 < Z_termination < -0.90`,
subject to finite-size drift.  The disagreement between lattice sizes at
`Z=-0.95` is expected momentum-shell locking and is the reason not to quote a
sharper endpoint yet.

Quadratic low-momentum fits to `1/S(q)` at the single central mass are not
stable under changing the fit cutoff.  This is unsurprising because the
central point is nearly singular and the finite lattice has only a few low-q
shells.  The remaining four masses per `Z,L` were therefore released as jobs
215--310.  They supply disordered-side points with positive `r`, permitting a
controlled joint assessment of `r` and `c2`.  The prepared `L=24` stage remains
held until this scan narrows the bracket.

## Fine-Z refinement

Central two-start pilots are prepared at `Z=-0.91,-0.92,-0.93,-0.94` for
`L=12,16,20`, with Binder-line center masses `-2.378892`, `-2.396690`,
`-2.414601`, and `-2.432625`, respectively.  These 24 jobs are TSP IDs
311--334 and have priority over the broad mass scan.  After completion the
same canonically weighted checkpoint census will classify the selected shell.
This provides nominal `delta Z=0.01` resolution, although the final uncertainty
must also include lattice-size drift and shell locking rather than merely the
grid spacing.

### Fine-Z pilot readout (2026-11-11)

All 24 fine-Z pilots completed and their checkpoint census was reconstructed.
For `L=20`, both starts select the first nonzero shell at `Z=-0.91` and
`Z=-0.92`; finite-q power remains favored through `Z=-0.94` (the ordered start
at `Z=-0.94` is nearly tied).  Combined with the `q=0` result at `Z=-0.90`,
this brackets the finite-volume `L=20` onset to `-0.91 < Z_onset(L=20) < -0.90`.

The smaller lattices do not yield a monotone shell-selection sequence:
`L=12` and `L=16` exhibit allowed-shell locking, and some `L=16` points disagree
between ordered and disordered starts.  Consequently the `0.01` grid resolves
the `L=20` pseudocritical onset but does not yet establish a thermodynamic
endpoint with `0.01` uncertainty.  The mass-resolved scan and a targeted larger
lattice are needed to separate phase coexistence from momentum quantization.

### L=24 adaptive confirmation

The next stage uses only the central two-start points at `Z=-0.88,-0.90,-0.92`
for `L=24` (TSP jobs 335--340).  The wider spacing intentionally brackets the
`L=20` pseudocritical onset before any further bisection.  These runs change the
lowest allowed momentum from `qhat^2=0.097887` at `L=20` to about `0.068148` at
`L=24`, providing a direct test of momentum-shell locking.  A single additional
midpoint pair will be selected adaptively only after these six runs are read.

### Mass-resolved correction (2026-11-12)

The full five-mass Binder reconstruction changes the interpretation of the
single central-checkpoint shell census.  Resolved pairwise crossings are:

| Z | size pair | crossing m2 | Binder U4 |
|---:|:---:|---:|---:|
| -0.80 | 12x16 | -2.19054 | 0.5452 |
| -0.80 | 16x20 | -2.21932 | 0.6528 |
| -0.85 | 12x16 | -2.29830 | 0.5833 |
| -0.85 | 16x20 | -2.30434 | 0.6507 |
| -0.90 | 12x16 | -2.39021 | 0.5196 |
| -0.95 | 16x20 | -2.50974 | 0.6452 |

At these masses the checkpoint spectra are `q=0` dominated.  The first
nonzero shell becomes dominant only toward the higher-mass/disordered side of
each scan, with peak power growing much more slowly than the volume scaling of
the ordered `q=0` peak.  Therefore the earlier apparent onset near `Z=-0.90`
was a finite-q soft mode in the disordered regime, not by itself evidence that
the uniform critical line had terminated.

The six `L=24` central runs completed, but their masses were based on the old
extrapolated line.  At `Z=-0.88` and `-0.92` the first nonzero shell dominates;
`Z=-0.90` is nearly tied.  Since the directly reconstructed smaller-size
crossings drift to more-negative mass by as much as about `0.05`, these L=24
central points do not determine the character of the mode at the actual
crossing.  A decisive L=24 continuation must add the `-0.03` and `-0.06` mass
offsets (both starts) and form direct `L=20 x L=24` crossings before further
refinement in Z.

The 12 required crossing-side runs were submitted as TSP jobs 341--352 on
2026-11-12.  They cover both starts at the `-0.06` and `-0.03` offsets for
`Z=-0.88,-0.90,-0.92`; the previously completed central pairs provide the
third mass at each Z.

### L=24 crossing-side result (2026-11-15)

All jobs 341--352 completed.  At `Z=-0.90`, the common three-mass grid gives a
direct `L=20 x L=24` crossing at

```text
m2_c = -2.41637
U4_c = 0.6608
```

Both starts are strongly `q=0` dominated at the two negative-offset masses,
including the crossing neighborhood.  The first nonzero shell becomes
competitive only at the higher extrapolated-center mass `m2=-2.361208`, after
the uniform crossing.  The analogous `L=24` spectra at `Z=-0.88` and `-0.92`
show the same pattern: negative-offset points are `q=0` ordered, while the
central/high-mass point has the soft finite-q mode.

Consequently the uniform line has not terminated near `Z=-0.90`.  Direct
smaller-size crossings remain `q=0` dominated through `Z=-0.95`, whereas the
existing `Z=-1` campaign has no robust `12x16` crossing and its `16x20`
candidate has negative Binder values, opposite-sign slopes, and source
disagreement.  The current evidence therefore places the termination in the
new bracket

```text
-1.00 < Z_termination < -0.95.
```

The efficient next calculation is an adaptive full mass scan at the midpoint
`Z=-0.975` for `L=16,20`, followed by bisection toward `-0.95` or `-1.00`
depending on whether a conventional q=0 crossing survives.

The midpoint scan was submitted on 2026-11-15 as TSP jobs 353--372.  Its five
masses are centered at `m2=-2.496604` with offsets `-0.06,-0.03,0,+0.03,+0.06`;
each mass has independent ordered and disordered starts for both `L=16` and
`L=20`.

### Z=-0.975 midpoint result (2026-11-16)

All 20 midpoint runs completed.  A formal linear `16x20` crossing occurs at
`m2=-2.55061`, `U4=0.4186`, but it is not a robust uniform critical crossing:
it interpolates between the only healthy mass and a point with enormous
ordered/disordered disagreement.  The mass-resolved spectra show:

- `m2=-2.556604`: clean q=0 order for both sizes;
- `m2=-2.526604`: q=0 still largest, but Binder source disagreement is severe;
- `m2>=-2.496604`: both sizes select their first nonzero momentum shell.

Thus `Z=-0.975` lies on the terminated/nonconventional side, while the robust
q=0 crossings at `Z=-0.95` lie on the uniform side.  The endpoint bracket is
now

```text
-0.975 < Z_termination < -0.95.
```

The next adaptive bisection point is `Z=-0.9625` using the same five-mass,
two-start protocol for `L=16,20`.

The `Z=-0.9625` bisection campaign was submitted as TSP jobs 373--392.  Its
five masses are centered at `m2=-2.473595` with offsets
`-0.06,-0.03,0,+0.03,+0.06`.

### Z=-0.9625 bisection result (2026-11-17)

All 20 runs completed.  The formal `16x20` crossing is
`m2=-2.52740`, `U4=0.5122`, but it again interpolates from the only healthy
q=0 mass into a point with extreme source disagreement.  Both sizes are q=0
at the two negative-offset masses and select their first nonzero shell from
the central mass upward.  This places `Z=-0.9625` on the terminated side and
tightens the bracket to

```text
-0.9625 < Z_termination < -0.95.
```

The next bisection point is `Z=-0.95625`.

The `Z=-0.95625` campaign was submitted as TSP jobs 393--412, centered at
`m2=-2.462157` with the same five offsets and two starts.

### Z=-0.95625 midpoint result (2026-11-18)

All 20 runs completed.  A formal linear `16x20` crossing occurs at

```text
m2_c = -2.52025
U4_c = 0.6256
```

but this does not cleanly assign the midpoint to either side of the endpoint.
The crossing lies only about `0.0019` above the lowest sampled mass
`m2=-2.522157`, where both sizes and both starts are strongly `q=0` dominated.
At the next mass, `m2=-2.492157`, `L=16` remains a consistent `q=0` state but
`L=20` develops severe ordered/disordered Binder disagreement; its disordered
start is almost tied between `q=0` and the first nonzero shell.  From the
central mass upward both sizes are predominantly finite-q, apart from the
source-dependent `L=16` central point.

Thus `Z=-0.95625` resolves the narrow crossover region itself rather than a
stable conventional Binder crossing.  Classifying it by the formal
interpolation would be dominated by one healthy endpoint and one contaminated
endpoint.  The defensible termination bracket therefore remains

```text
-0.9625 < Z_termination < -0.95,
```

with `Z=-0.95625` marked as ambiguous/coexistence-dominated inside that
interval.  This bracket is already narrower than the finite-size and
source-history systematics, so further bisection is not presently warranted.
