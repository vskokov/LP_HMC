# Modulation spatial-rank workflow

The modulation dimension is measured from the span of the dominant nonzero
Fourier wavevectors, not from the number of populated momentum pairs.  A
lamellar state has rank one even if its orientation changes between samples.

For every configuration, `modulation_rank_observables` in
`scripts/structure_factor_observables.jl` subtracts a neighboring-shell noise
estimate and constructs

\[
A_{ij}=\frac{\sum_a w_a\hat k_{a,i}\hat k_{a,j}}{\sum_a w_a},\qquad
d_\mathrm{eff}=\frac{1}{\mathrm{tr}(A^2)}.
\]

The eigenvalues are computed before ensemble averaging.  Rank 1, 2, and 3
correspond to one, two, or three active spatial directions.  Points without a
positive, statistically supported excess peak are `unmodulated`; ambiguous
points are `mixed/undetermined`.

## Umbrella checkpoints

New structure-factor shards automatically contain the tensor components,
eigenvalues, effective dimension, background, and signed excess power.  Use the
normal CPU campaign commands and analyze them with:

```bash
python3 scripts/structure_factor_campaign.py analyze \
  --manifest reports/structure_factor_cpu/preparation/production_manifest.csv \
  --output reports/structure_factor_cpu/rank_analysis
```

Do not append rank-aware shards to an old schema-1 production directory.  Use a
fresh production directory so every merged shard has the same columns.

The final fields retained by the old production campaign can be inspected
immediately, without new HMC trajectories:

```bash
python3 scripts/snapshot_modulation_rank.py \
  --manifest reports/structure_factor_cpu/preparation/production_manifest.csv \
  --output reports/structure_factor_cpu/rank_snapshots --workers 32 --resume
```

These results are explicitly marked as snapshot evidence and should guide the
adaptive scan; they do not replace blocked production uncertainties.

## Thermodynamic-integration branches

Set `TI_RANK_STARTS=true` when running
`scripts/thermodynamic_integration_multishell.jl` to add rank-2 and rank-3
initial conditions for each selected shell.  Existing runs are unchanged when
the variable is absent.  Analyze one or more independent replicas with:

```bash
python3 scripts/analyze_modulation_rank.py \
  --manifest reports/.../r1/manifest.csv \
  --manifest reports/.../r2/manifest.csv \
  --envelope reports/.../r1/integrated_multishell.csv \
  --envelope reports/.../r2/integrated_multishell.csv \
  --output reports/structure_factor_cpu/modulation_rank
```

The command writes separate metastable-branch and free-energy-envelope maps.
An envelope point is promoted to `equilibrium_supported` only when two
independent sources agree on the rank and differ by at most 0.25 in
`d_eff`.  It also emits adaptive midpoint suggestions where the label changes,
`d_eff` changes by more than 0.25, or the result remains unresolved.

The primary scan should use `L=16,20`; repeat representative interiors and all
apparent rank boundaries at `L=24`.  The exact selected shell is the primary
definition.  `include_adjacent=true` is available for the required radial-band
systematic check.

## GPU/TSP classification campaign

The first focused classification campaign is managed by
`scripts/modulation_rank_tsp_campaign.py`.  It was submitted to Task Spooler on
2026-11-18 as job IDs 413--440, with one concurrent job on the single RTX A6000.
HMC evolution runs on CUDA; configurations are transferred to the CPU only at
measurement times for the FFT and orientation-tensor analysis.

The campaign contains 28 jobs:

- lattice sizes `L=16,20`;
- two statistically independent replicas per `(L,Z)`;
- three mass anchors per `Z`, giving 42 distinct `(L,Z,m2)` points and 84
  replica-level mass measurements;
- one measured nonzero shell per point, chosen as the allowed finite-volume
  shell nearest the target `q` below;
- uniform, disordered/high-mass, rank-1, rank-2, and rank-3 initial branches;
- 300 initial settling trajectories, 100 settling trajectories between masses,
  and 100 measurements separated by two HMC trajectories;
- `n_lf=15`, with `eps=0.010` for `L=16` and `eps=0.0085` for `L=20`.

| `Z` | mass anchors | target `q` |
|---:|:---|---:|
| -1.000 | -1.9431541794, -1.3431541794, -0.9431541794 | 0.38196601125 |
| -1.500 | -3.2230651515, -2.4230651515, -1.6230651515 | 0.824429495415 |
| -2.000 | -5.7866118766, -3.1866118766, -0.5866118766 | 0.824429495415 |
| -2.375 | -10.1954078833, -5.3954078833, -0.5954078833 | 1.38196601125 |
| -2.500 | -10.6337943546, -5.4337943546, -0.4337943546 | 1.38196601125 |
| -3.000 | -8.0, -4.5, -1.0 | 1.5 |
| -4.000 | -14.0, -8.0, -2.0 | 2.0 |

The anchors through `Z=-2.5` sample the previously measured finite-wavevector
envelope.  The `Z=-3` and `Z=-4` points are deep-modulated controls guided by
the mean-field stability interval.  Their role is to establish that the
classifier recognizes unambiguous morphology before resolving changes nearer
the phase boundaries.

Prepare, submit, and inspect the campaign with:

```bash
python3 scripts/modulation_rank_tsp_campaign.py prepare
python3 scripts/modulation_rank_tsp_campaign.py submit
python3 scripts/modulation_rank_tsp_campaign.py status
tsp
```

The manifest is
`reports/structure_factor_cpu/modulation_rank_gpu/manifest.csv`, and raw output
is stored under `runs/modulation_rank_gpu/L*/Z*/replica_*/statistics.csv`.
Submission is resumable: existing output files are skipped and only missing
tasks are enqueued.

This is primarily a morphology and initialization-dependence campaign.  If all
five starts converge to compatible eigenvalue spectra, the point has strong
branch-independent rank evidence.  Persistent start dependence is reported as
metastable or `mixed/undetermined`.  A point is not promoted to
`equilibrium_supported` solely from this scan; that designation still requires
the free-energy-envelope or canonical reconstruction checks described above.

### Completed classification result

All 28 jobs completed and passed the rank-schema checks.  They produced 42
distinct `(L,Z,m2)` classifications, with two replicas and five initial
morphologies at each point.  The aggregate result is:

| classification | points |
|:---|---:|
| `mixed/undetermined` | 33 |
| `rank1_metastable` | 9 |
| branch-independent/equilibrium-supported | 0 |

The minimum sample-level HMC acceptance was 0.93.  Independent replicas usually
reproduced one another, but the rank-1, rank-2, rank-3, uniform, and off-target
branches often retained their starting morphology.  The disagreement is
therefore initialization trapping between long-lived morphology sectors, not
an integration-acceptance failure.  In particular, several deep-modulated
points retain all three seeded ranks instead of converging to a unique rank.
Consequently, averaging `d_eff` across starts would not be an equilibrium rank
estimate.

Rank-one lamellar behavior is the only recurring candidate: all retained
modulated starts collapse to rank one for `L=16` at `Z=-2.5,-2.375` and for
`L=20` at `Z=-3`.  Uniform/disordered or off-target branches remain separate at
those points, however, so these are labeled `rank1_metastable`, not equilibrium
rank-one phases.

The analysis products are:

- `reports/structure_factor_cpu/modulation_rank_gpu/branch_rank_measurements.csv`;
- `reports/structure_factor_cpu/modulation_rank_gpu/classification_map.csv`;
- `reports/structure_factor_cpu/modulation_rank_gpu/classification_summary.json`;
- `reports/structure_factor_cpu/modulation_rank_gpu/figures/classification_map.png`;
- `reports/structure_factor_cpu/modulation_rank_gpu/figures/branch_convergence.png`.

The next decisive calculation is a rank-resolved free-energy comparison.  Each
rank-1, rank-2, and rank-3 branch should be continued along a denser mass ladder
to a verified common disordered anchor, and the branch free-energy differences
obtained by integrating the conjugate observable `Q/2`.  This can select the
thermodynamically favored morphology without requiring local HMC to tunnel
between morphology sectors.

## Rank-resolved free-energy campaign

The follow-up GPU campaign is managed by
`scripts/rank_free_energy_tsp_campaign.py`.  It continues rank-1, rank-2, and
rank-3 starts upward in `m2`, while an independently initialized disordered
branch is continued downward.  Its high-mass endpoint satisfies
`m2 > Z^2/4`, where the bare quadratic kernel is positive at every lattice
momentum.  Agreement of all branches there is checked before using that point
as their common free-energy normalization.

The first production grid uses `L=16,20`, two replicas, `Z=-1.5,-2,-2.5,-3,-4`,
mass spacing no larger than 0.5, and includes the three mass anchors from the
classification campaign exactly.  Each task uses one target momentum shell
and five continuations: uniform, rank-1, rank-2, rank-3, and high-mass.
The 20 tasks were submitted on 2026-11-18 as TSP jobs 441--460, with one
concurrent task on the RTX A6000.

```bash
python3 scripts/rank_free_energy_tsp_campaign.py prepare
python3 scripts/rank_free_energy_tsp_campaign.py submit
python3 scripts/rank_free_energy_tsp_campaign.py status
```

Outputs are kept separate from the exploratory scan under
`runs/modulation_rank_free_energy_gpu/`; its manifest is
`reports/structure_factor_cpu/modulation_rank_free_energy_gpu/manifest.csv`.

### Completed free-energy result

All TSP jobs 441--460 completed with exit level zero.  The 20 outputs contain
all 2,780 expected branch--mass rows; the minimum HMC sample acceptance is
0.9367.  At every one of the 20 high-mass endpoints, all five branches have
`peak_S < 10`, so the common normalization point is unmodulated.  The endpoint
spread in `Q/L^3` is nevertheless about 0.001--0.003, and the final uncertainty
therefore conservatively includes the two-replica spread as well as propagated
within-run MCSE.

The integrated restricted-branch comparison gives 143 mass points with a
greater than two-standard-error morphology preference.  Every one of those
points has an observed rank-one orientation tensor.  There are no significant
observed rank-two or rank-three winners.  Thus the current finite-volume
evidence favors a lamellar, one-dimensional modulation throughout the sampled
modulated region.

The seed label must not be confused with the measured morphology.  At
`L=16, Z=-2.5` and at the deepest `L=20, Z=-3` points, the continuation that
started from rank two has the lowest integrated restricted-branch free energy,
but it has already relaxed to a rank-one-dominated tensor (`d_eff` roughly
1.2--1.3).  These cases indicate distinct lamellar histories or defects, not a
thermodynamically selected rank-two phase.  Near the disordered boundary, 128
grid points remain unresolved at the two-standard-error level, as expected
when all branch differences collapse toward zero.

Reproduce the analysis with:

```bash
python3 scripts/analyze_rank_free_energy.py
```

The main products are
`integrated_rank_free_energy.csv`, `anchor_convergence.csv`,
`rank_crossings.csv`, `analysis_summary.json`, and
`rank_free_energy_comparison.png` in
`reports/structure_factor_cpu/modulation_rank_free_energy_gpu/`.

This is strong evidence against stable rank-two or rank-three modulation on
`L=16,20`, but the result remains a restricted-continuation comparison rather
than a proof of global equilibration.  The most useful next validation is an
`L=24` check at a small number of representative interior points, together
with longer continuations at the anomalous `L=16, Z=-2.5` and `L=20, Z=-3`
locations to test whether their lamellar histories merge.
