# Simulation Campaigns and Repository Data Layout

Status date: **18 November 2026**

This document is the map of the numerical work in this repository. It explains
what was simulated, why each campaign exists, how raw tasks are stored, which
directories contain analysis rather than raw data, and how to determine whether
a campaign is actually complete.

The short version is:

- `runs/` contains raw or restartable simulation products.
- `reports/` contains reconstructed observables, diagnostics, tables, and
  campaign-specific interpretations.
- `plots/` contains cross-campaign plotting inputs and publication figures.
- `configs/` contains reusable source grids and umbrella profiles.
- `paper/` contains the current manuscript and its generated supporting data.
- A directory or checkpoint is **not** evidence of a completed run. Use the
  manifest, completion marker, final statistics file, and diagnostics together.

The physical model is

\[
H[\phi]=\sum_x\left[
\frac Z2(\nabla\phi_x)^2+\frac12(\nabla^2\phi_x)^2
+\frac{m^2}{2}\phi_x^2+\frac\lambda4\phi_x^4\right],
\qquad \lambda=4,\quad T=1.
\]

All production calculations sample `exp(-H/T)` with Hybrid Monte Carlo (HMC).
The principal scan coordinates are the quadratic-gradient coefficient `Z`, the
bare mass parameter `m2` (the code name for \(m^2\)), and the lattice size `L`.

---

## 1. Top-level layout

```text
LP_HMC/
├── src/                    HMC and replica-exchange implementation
├── scripts/                simulation, submission, reconstruction, and plotting tools
├── tests/                  Python regression tests
├── configs/                source grids and volume-dependent umbrella profiles
├── runs/                   raw simulation state and restartable task output
├── reports/                analyzed observables and campaign reports
├── plots/                  combined Binder tables, distributions, and figures
├── paper/                  manuscript, PDF, and generated phase-map tables
├── README.md               code and sampler overview
├── AGENTS.md               developer constraints and implementation notes
├── Project.toml            Julia dependencies
└── Manifest.toml           pinned Julia dependency versions
```

The historical `README.md` mentions `data/` as a generic output location. The
current production workflow instead uses `runs/` for raw outputs and `reports/`
for derived results.

### Source code

| Path | Role |
|---|---|
| `src/modelA.jl` | Module entry point and includes. |
| `src/initialize.jl` | CLI parsing and global constants such as `L`, `Z`, `m2`, `eps`, and `n_lf`. |
| `src/simulation.jl` | CPU/GPU HMC force, energy, leapfrog, accept/reject, and thermalization. |
| `src/replica_exchange.jl` | Exact mass-replica exchanges using `Q=sum(phi^2)`. |

The biharmonic force is evaluated in two passes: first \(\nabla^2\phi\), then
\(\nabla^2(\nabla^2\phi)\). The sampler APIs documented in `AGENTS.md` are the
authoritative interfaces.

---

## 2. Data lifecycle and evidence hierarchy

A typical calculation follows this path:

```text
configs/*.csv or campaign driver
        │
        ▼
runs/<campaign>/<volume>/manifest.csv
        │
        ├── checkpoints/*.jld2       restartable field and sampler state
        ├── diagnostics/*.csv        HMC, swaps, walkers, and transport checks
        ├── shards/<task>/*.csv      incremental measurement blocks
        ├── progress/*.json          current continuation state
        ├── statistics/*.csv         merged production measurements
        └── complete/*.complete      successful terminal marker
        │
        ▼
reports/<campaign>/                  reconstructed observables and diagnostics
        │
        ▼
plots/*.csv and plots/*.png          cross-volume/cross-Z summaries
        │
        ▼
paper/generated/ and paper/main.pdf  manuscript-level presentation
```

Use the following hierarchy when auditing a result:

1. **Manifest row:** exact requested parameters and expected output paths.
2. **Progress JSON:** last checkpoint and continuation state.
3. **Final statistics CSV:** actual production measurements.
4. **Completion marker:** task passed its workflow and wrote terminal output.
5. **Diagnostics:** HMC acceptance, swap acceptance, walker transport, overlap,
   effective sample size, and independent-start agreement.
6. **Analysis artifact:** reconstructed Binder cumulant, structure factor, or
   integrated free-energy result.
7. **Campaign README:** scientific interpretation and known limitations.

Do not infer completion from a `.jld2` checkpoint, a large directory, a lock
file, or a submitted task ID. Checkpoints are deliberately written before a
task is scientifically complete so that interrupted work can resume.

---

## 3. Naming conventions

### Coupling tags

Directory tags replace punctuation:

| Tag | Value |
|---|---:|
| `Z0p5` | \(Z=+0.5\) |
| `Zm0p5` | \(Z=-0.5\) |
| `Zm0p95625` | \(Z=-0.95625\) |
| `m2-2.52216` | \(m^2=-2.52216\) |

`m` immediately after `Z` means minus; `p` means decimal point. Mass values in
filenames retain a conventional leading minus sign.

### Replicas and starts

The production Binder campaigns normally use two independent starts:

- `r0_disordered`: disordered/hot start;
- `r1_ordered`: uniform ordered start.

Agreement is an equilibration diagnostic. A large discrepancy is not a larger
ordinary error bar; it signals incomplete mixing, phase coexistence, an
inappropriate umbrella coordinate, or another systematic problem.

### Volume directories

`L16`, `L20`, and similar names mean a periodic \(L^3\) cubic lattice. HMC has
no sublattice divisibility constraint.

---

## 4. Repeated umbrella-task directory structure

A production umbrella volume such as
`runs/umbrella_binder_Z0/L16/` or
`runs/umbrella_binder_termination/Zm0p95625/L16/` contains:

```text
L16/
├── manifest.csv
├── submission.json
├── checkpoints/
│   └── L16_Z..._m2..._r...jld2
├── statistics/
│   └── L16_Z..._m2..._r...csv
├── diagnostics/
│   └── L16_Z..._m2..._r...csv
├── complete/
│   └── L16_Z..._m2..._r...complete
├── progress/
│   └── L16_Z..._m2..._r...json
├── locks/
│   └── L16_Z..._m2..._r...lock
├── logs/
└── shards/
    └── L16_Z..._m2..._r.../
        ├── statistics_000000.csv
        ├── statistics_000001.csv
        ├── diagnostics_000000.csv
        ├── collection_checkpoint_0.jld2
        └── collection_checkpoint_1.jld2
```

### Meaning of the files

| File | Meaning |
|---|---|
| `manifest.csv` | One row per independent source task. It records physics parameters, HMC settings, umbrella settings, seeds, sampling targets, and all output paths. |
| `submission.json` | Submission metadata and command materialization. |
| `checkpoints/*.jld2` | Main restartable umbrella state after thermalization/production. |
| `statistics/*.csv` | Merged all-window production measurements used by WHAM/MBAR reconstruction. |
| `diagnostics/*.csv` | Acceptance, swaps, walker diffusion, round trips, and related health metrics. |
| `complete/*.complete` | Terminal success marker. Its absence is significant. |
| `progress/*.json` | Incremental collection state, last checkpoint, and shard bookkeeping. |
| `locks/*.lock` | Duplicate-run protection. This is not a completion marker. |
| `shards/<task>/statistics_*.csv` | Incremental collection blocks. |
| `shards/<task>/collection_checkpoint_[01].jld2` | Alternating restart checkpoints used during collection. |

The manifests currently contain absolute paths rooted at
`/home/vskokov/Binder/LP_HMC`. If the project is moved, regenerate manifests or
rewrite paths deliberately; do not assume they are portable.

---

## 5. Simulation families

### 5.1 Original direct and mass-tempering Binder tests at `Z=-0.6`

These campaigns predate the full `M2`-umbrella production program. They were
used to compare ordinary HMC and increasingly wide mass-tempering ladders near
the transition.

### Ordinary HMC/reweighting

```text
runs/binder_Zm06_L6/
runs/binder_Zm06_L8/
runs/binder_Zm06_L12/
runs/binder_Zm06_L16/
runs/binder_Zm06_L18/
runs/binder_Zm06_L20/
runs/binder_Zm06_L24/
runs/binder_Zm06_L32/
```

Each volume contains five masses, two replicas per mass, and ten completed
tasks. The common mass range is approximately `-1.95` to `-1.75`.

### Five-replica mass tempering

```text
runs/binder_Zm06_temp_L12/
runs/binder_Zm06_temp_L16/
runs/binder_Zm06_temp_L18/
runs/binder_Zm06_temp_L20/
runs/binder_Zm06_temp_L24/
runs/binder_Zm06_temp_L32/
```

These use `tempering_replicas=5` and `mass_span=0.2`, with ordered and
disordered starts. Each listed volume has ten completed tasks.

### Seventeen-replica mass tempering

```text
runs/binder_Zm06_temp17_L8/
runs/binder_Zm06_temp17_L12/
runs/binder_Zm06_temp17_L16/
runs/binder_Zm06_temp17_L18/
runs/binder_Zm06_temp17_L20/
runs/binder_Zm06_temp17_L24/
runs/binder_Zm06_temp17_L32/
```

These use `tempering_replicas=17` and `mass_span=0.6`. They demonstrated that
acceptable local mass-swap rates do not guarantee transport across the
ordered/disordered interface. That failure motivated the `M2` umbrella
coordinate.

These directories remain useful for method comparison, but the later umbrella
campaigns are the primary source for Binder results.

---

### 5.2 Broad production Binder-cumulant campaigns

These are the main uniform-order scans. They use harmonic umbrellas in
`M2`, adjacent-window replica exchange, two independent starts, and canonical
WHAM/MBAR reconstruction.

| Raw campaign | Z | L values | Mass range | Unique masses | Tasks | Complete |
|---|---:|---|---:|---:|---:|---:|
| `runs/umbrella_binder_Zm0p5/` | -0.5 | 8, 12, 16, 20, 24 | -2.1 to -1.4 | 21 | 198 | 198 |
| `runs/umbrella_binder_Zm0p25/` | -0.25 | 8, 12, 16, 20, 24 | -1.8 to -1.1 | 19 | 182 | 182 |
| `runs/umbrella_binder_Z0/` | 0 | 8, 12, 16, 20, 24 | -1.5 to -0.8 | 21 | 198 | 198 |
| `runs/umbrella_binder_Z0p5/` | 0.5 | 8, 12, 16, 20, 24 | -1.4 to -0.7 | 20 | 190 | 190 |
| `runs/umbrella_binder_Z1/` | 1 | 8, 12, 16, 20, 24 | -1.1 to -0.5 | 18 | 170 | 170 |
| `runs/umbrella_binder_Z1p25/` | 1.25 | 8, 12, 16, 20, 24 | -1.1 to -0.4 | 19 | 182 | 182 |
| `runs/umbrella_binder_Z2/` | 2 | 8, 12, 16, 20, 24 | -1.0 to -0.3 | 20 | 190 | 190 |
| `runs/umbrella_binder_Zm06/` | -0.6 | 12, 16, 18, 20, 24, 32 | -1.95 to -1.75 | 5 | 60 | 60 |

The corresponding reconstructed per-source JSON files are in matching report
directories, for example `reports/umbrella_binder_Z0/L16/`.

Cross-volume plot inputs and figures are in `plots/`:

- `plots/umbrella_binder_mZ*.csv` and `*_overlay.png`;
- `plots/binder_crossings_vs_Z.csv` and `.png`;
- `plots/umbrella_PM2_*.csv` and `.png` for reconstructed distributions.

The primary cross-Z crossing table is `plots/binder_crossings_vs_Z.csv`. It
contains the `12x16`, `16x20`, and `20x24` pairwise crossings.

---

### 5.3 Lower-Z exploratory Binder campaigns

| Campaign | Z | L values | Tasks | Complete | Interpretation |
|---|---:|---|---:|---:|---|
| `runs/umbrella_binder_Zm0p75/` | -0.75 | 12, 16, 20, 24 | 120 | 116 | Mostly complete lower-Z scan; finite-q effects begin to matter. |
| `runs/umbrella_binder_Zm1/` | -1.0 | 12, 16, 20, 24 | 120 | 105 | Partially complete; uniform Binder crossings are not robust and the finite-q mode dominates important points. |

These campaigns supplied source checkpoints for the CPU structure-factor work.
Their incomplete counts must be considered when reusing a mass or volume.

---

### 5.4 Direct termination scan of the uniform critical line

Raw data live under:

```text
runs/umbrella_binder_termination/Z<tag>/L<size>/
```

The scan was adaptive. Some manifests contain five masses for all four sizes,
but only central pilots or crossing-side points were intentionally released.
Therefore `complete < manifest rows` does not automatically mean a failed
campaign; consult `reports/umbrella_binder_termination/README.md` for the
stage actually requested.

| Tag | Z | Sizes in manifest | Mass range | Tasks | Complete |
|---|---:|---|---:|---:|---:|
| `Zm0p8` | -0.80 | 12, 16, 20, 24 | -2.25061 to -2.13061 | 40 | 30 |
| `Zm0p85` | -0.85 | 12, 16, 20, 24 | -2.33449 to -2.21449 | 40 | 30 |
| `Zm0p88` | -0.88 | 24 | -2.38618 to -2.26618 | 10 | 6 |
| `Zm0p9` | -0.90 | 12, 16, 20, 24 | -2.42121 to -2.30121 | 40 | 36 |
| `Zm0p91` | -0.91 | 12, 16, 20 | -2.43889 to -2.31889 | 30 | 6 |
| `Zm0p92` | -0.92 | 12, 16, 20, 24 | -2.45669 to -2.33669 | 40 | 12 |
| `Zm0p93` | -0.93 | 12, 16, 20 | -2.47460 to -2.35460 | 30 | 6 |
| `Zm0p94` | -0.94 | 12, 16, 20 | -2.49262 to -2.37263 | 30 | 6 |
| `Zm0p95` | -0.95 | 12, 16, 20, 24 | -2.51076 to -2.39076 | 40 | 30 |
| `Zm0p95625` | -0.95625 | 16, 20 | -2.52216 to -2.40216 | 20 | 20 |
| `Zm0p9625` | -0.9625 | 16, 20 | -2.53360 to -2.41359 | 20 | 20 |
| `Zm0p975` | -0.975 | 16, 20 | -2.55660 to -2.43660 | 20 | 20 |

Analysis products are split between:

- `reports/umbrella_binder_termination/` for the narrative status;
- `reports/umbrella_binder_termination/Z<tag>/` for per-source reconstructions;
- `plots/binder_termination/` for combined Binder CSVs and overlays;
- `reports/structure_factor_cpu/termination_*_census/` for Fourier censuses;
- `reports/structure_factor_cpu/termination_*_preparation/` for canonically
  weighted shell summaries.

Current conclusion: robust uniform behavior survives through `Z=-0.95`; the
terminated/nonconventional side is established by `Z=-0.9625`. The midpoint
`Z=-0.95625` is itself source-history/coexistence dominated. The defensible
finite-size bracket is

```text
-0.9625 < Z_termination < -0.95.
```

The formal `Z=-0.95625` crossing is `m2=-2.52025`, `U4=0.6256`, but it is not
used to tighten the bracket because it interpolates from a healthy `q=0` point
into a contaminated point.

Driver: `scripts/direct_binder_termination_campaign.py`.

---

### 5.5 Prepared direct junction campaign

```text
runs/umbrella_binder_junction/
├── Zm1p5/
├── Zm1p55/
├── Zm1p6/
└── Zm1p65/
```

Each `Z` has manifests for `L=12,16,20,24`, 13 masses over a `0.6` interval,
and two starts. The full design contains 416 tasks.

**Status:** this is not a completed campaign. There are no final statistics
files or completion markers. Each `Z` directory currently contains six pilot
checkpoints, reflecting interrupted/preliminary work. Do not use this campaign
as a measured phase boundary.

The scientific motivation and staged submission commands are documented in
`reports/umbrella_binder_junction/README.md`. The newer direct termination
scan near `Z≈-0.956` supersedes the old extrapolated `Z≈-1.57` junction as the
best estimate of where the conventional uniform line ceases to be reliable.

Driver: `scripts/direct_binder_junction_campaign.py`.

---

### 5.6 Umbrella and HMC tuning campaigns

### Umbrella trajectory-length tuning

Raw tuning results are under `runs/umbrella_tuning_tsp/`, organized by lattice
size and by pilot/confirmation stage. Volumes `L=6,8,12,16,18,20,24,32` were
tested. The campaign contains 32 completed manifest tasks, but each task stores
large window-level diagnostic output; the directory is about 3.2 GB.

Analyzed recommendations are under `reports/umbrella_tuning/`:

```text
reports/umbrella_tuning/
├── L6_nlf/{sweep_manifest.csv,results.csv,recommendations.csv}
├── L6_selected_nlf.json
├── L6_validation.json
├── ...
└── L32_validation.json
```

Relevant tools:

- `scripts/umbrella_tuning_campaign.py`;
- `scripts/explore_umbrella_nlf.py`;
- `scripts/tune_umbrella_profile.py`;
- `scripts/validate_umbrella_profile.py`;
- `scripts/audit_umbrella_transport.jl`.

### Profile configuration

`configs/umbrella_profiles/L*.json` contains the volume-specific window count,
range, force constant, nonlinear center spacing, HMC settings, transport gates,
and sampling defaults. These files are inputs, not results.

---

### 5.7 CPU structure-factor campaign

The structure-factor workflow reuses equilibrated umbrella configurations. It
does not simply Fourier transform an arithmetic average field. It measures
translation- and rotation-safe shell power from each configuration and then
reconstructs the canonical ensemble with the umbrella bias removed.

### Main raw production

```text
runs/structure_factor_cpu/
├── Zm1p0/L12|L16|L20/task_*/
├── Zm0p75/L12|L16|L20|L24/task_*/
├── Zm0p5/L12|L16|L20|L24/task_*/
├── Z0p0/L12|L16|L20|L24/task_*/
└── Z0p5/L12|L16|L20|L24/task_*/
```

This is one of the largest raw trees, approximately 5.6 GB. A typical task
contains:

```text
task_000000/
├── progress.json
├── statistics.csv
├── checkpoint_0.jld2
├── checkpoint_1.jld2
└── shards/ or incrementally numbered collection files
```

The governing manifest is
`reports/structure_factor_cpu/preparation/production_manifest.csv`, because
these tasks are derived from multiple Binder campaigns rather than created
under one ordinary raw-run manifest.

### Observables

For the shell \(\mathcal S_n\),

\[
P_n=\frac{1}{V^2}\sum_{k\in\mathcal S_n}|\widetilde\phi_k|^2,
\qquad S_n=\frac{V\langle P_n\rangle}{g_n},
\]

where `g_n` is the shell degeneracy. The collector also retains `M2`, `M4`,
`Q`, the gradient observable `G`, total energy `H`, selected-shell power, and
orientation participation diagnostics.

### Structure-factor report directories

| Directory | Purpose |
|---|---|
| `reports/structure_factor_cpu/census/` | Quick shell census from source checkpoints. |
| `reports/structure_factor_cpu/preparation/` | Canonical census summaries, frozen shell choices, and production manifest. |
| `reports/structure_factor_cpu/analysis/` | Combined observables, reweighting grids, precision status, equal-weight candidates, and figures. |
| `reports/structure_factor_cpu/deep_modulated_validation/` | Strong-modulation test at approximately `(Z,m2,L)=(-4,-1,16)`; verifies that orientation/phase averaging does not erase the peak. |
| `reports/structure_factor_cpu/modulation_onset_L16/` | Early `L=16` onset exploration. |
| `reports/structure_factor_cpu/termination_census/` | Census for the broad direct termination grid. |
| `reports/structure_factor_cpu/termination_refinement_census/` | Census for the `Z=-0.91...-0.94` refinement. |
| `reports/structure_factor_cpu/termination_L24_census/` | `L=24` termination confirmation census. |
| `reports/structure_factor_cpu/termination_Zm0p975_census/` | Census at `Z=-0.975`. |
| `reports/structure_factor_cpu/termination_Zm0p9625_census/` | Census at `Z=-0.9625`. |
| `reports/structure_factor_cpu/termination_Zm0p95625_census/` | Census at `Z=-0.95625`. |
| Matching `*_preparation/` folders | Canonical weights, shell summaries, and any selected production tasks. |

Core implementation:

- `scripts/structure_factor_observables.jl`: shell geometry and per-field observables;
- `scripts/census_structure_factor.jl`: checkpoint census;
- `scripts/collect_structure_factor_shard.jl`: extended measurements;
- `scripts/structure_factor_analysis.py`: WHAM weights, reweighting, bootstrap, and bimodality diagnostics;
- `scripts/structure_factor_campaign.py`: census/prepare/run/analyze orchestration.

### Early direct `L=16` onset scan

`runs/modulation_onset_L16/` is a separate 36-task exploratory scan generated
before the production census workflow. It covers
`Z=-0.75,-0.80,-0.85,-0.90,-0.95,-1.0,-1.05,-1.1,-1.2,-1.3,-1.4,-1.5`,
with one mass on the then-extrapolated Binder line and three starts at each
point: uniform, modulated, and disordered. Each task writes `summary.csv` and
`spectrum.csv` under `task_###/`.

The governing and combined files are in
`reports/structure_factor_cpu/modulation_onset_L16/`:

- `manifest.csv` maps the 36 tasks to raw directories;
- `summary.csv` combines peak shell, magnetization, energy, orientation, and
  acceptance information;
- `crossing_fit.csv` records the Binder-line guide used by the scan;
- `onset_scan.png` visualizes the result.

This scan demonstrated strong start dependence and motivated thermodynamic
integration. It is exploratory branch information, not an equilibrium phase
boundary.

---

### 5.8 Restricted-branch thermodynamic-integration campaigns

These CPU campaigns follow separately initialized uniform, modulated, and
high-mass branches. They integrate

```text
d(f_a-f_b)/d(m2) = 0.5 * ( <Q>/V |_a - <Q>/V |_b )
```

along mass. They are valuable for finding candidate scan windows, but they do
not automatically sample transitions among branches. Their equality points
are therefore exploratory unless confirmed by an unbiased finite-size method.

Raw data are in `runs/thermodynamic_integration_*`; analyzed tables, figures,
manifests, and interpretation are in matching subdirectories of
`reports/structure_factor_cpu/`.

| Campaign | L | Z coverage | Design and result |
|---|---:|---|---|
| `thermodynamic_integration_L16` | 16 | -1.5 to -0.75, 7 slices | First three-branch exploration near the extrapolated Binder line. |
| `thermodynamic_integration_L16_wide` | 16 | -3.0 to -0.5, 29 slices | Wide phase map; apparent onset near `Z=-2.275...-2.300` coincides with an allowed-shell change. |
| `thermodynamic_integration_L20_onset` | 20 | -2.325 to -2.25, 7 slices, 2 replicas | Finite-size check: no sign change in the `L=16` onset interval; shows the `L=16` feature is shell-locking dominated. |
| `thermodynamic_integration_L20_wide` | 20 | -3.0 to -0.5, 37 slices | Wide continuation map; first sign change appears near a discrete momentum-shell switch. |
| `thermodynamic_integration_L20_refine` | 20 | -2.375 to -2.35, 6 slices, 2 fresh replicas | Roots near `Z=-2.35208` track the deterministic shell midpoint to about `2.1e-4`; not a physical smooth onset. |
| `thermodynamic_integration_multishell_L20` | 20 | -2.5 to -0.5, 17 slices | Uniform plus five finite-q shells plus high-mass branch; 626 mass points and 4,382 branch measurements. Candidate connection near `Z≈-1.558`. |
| `thermodynamic_integration_multishell_join_L20` | 20 | -1.65 to -1.45, 9 slices, 2 replicas | Refines the restricted-branch junction: roots `-1.58589` and `-1.54662`, with a continuation-history bracket `[-1.60,-1.525]`. |

The multi-shell campaign removes the worst nearest-shell preselection artifact,
but it remains a restricted continuation. The direct Binder termination study
near `Z≈-0.956` is the controlling evidence for where the conventional uniform
line terminates.

Each integration report typically contains:

```text
README.md                    campaign design and interpretation
manifest.csv                 exact Z/mass grids and raw output paths
integrated_branches.csv      pointwise branch free energies
crossing_summary.csv         one-row-per-Z crossing summary
pairwise_crossings.csv       branch-pair equality points
thermodynamic_integration.png
wide_phase_map.png           where applicable
```

Multi-shell reports use `integrated_multishell.csv`, `multishell_summary.csv`,
`multishell_envelopes.png`, and `phase_line_connection.png`.

---

## 6. Analysis-only directories

### 6.1 Binder mass derivative and finite-size scaling

`reports/binder_slope_fss/` contains analytic derivatives of the Binder
cumulant with respect to `m2`, finite-difference validation, crossing-based
effective exponents, and bootstrap products.

Important subdirectories:

| Path | Meaning |
|---|---|
| `preliminary/` | Central production analysis across `Z=-0.5,-0.25,0,0.5,1,1.25,2`. |
| `exploratory/` | Earlier settings and sensitivity checks. |
| `Zm1_partial/` | Partial `Z=-1` analysis, where the uniform order parameter is already problematic. |
| `Zm1_partial_L12_L20/` | Generated central reports for selected `Z=-1` sizes. |

Typical files are:

- `slope_curves.csv` and `slope_curves_Z*.png`;
- `crossing_exponents.csv`;
- `bootstrap_draws.csv`;
- `effective_exponents_vs_Z.png`;
- `crossing_method_shift.png`;
- `campaign_status.csv`.

Implementation: `scripts/analyze_binder_slopes.py`, with tests in
`tests/test_binder_slopes.py`.

### 6.2 Progress report

`reports/current_results_2026-10-30/` contains the historical long-form
progress report:

- `binder_progress_report.tex`;
- `binder_progress_report.pdf`.

It records the evolution of the analysis and is useful provenance, but the
current manuscript and campaign READMEs contain later conclusions.

### 6.3 Paper

```text
paper/
├── main.tex
├── main.pdf
├── README.md
└── generated/
    ├── mean_field_phase_diagram.{png,pdf}
    ├── phase_diagram_status.{png,pdf}
    ├── phase_boundary_catalog.csv
    └── proposed_transition_campaign.csv
```

`paper/generated/phase_boundary_catalog.csv` explicitly distinguishes:

- direct finite-size Binder measurements;
- restricted-branch equal-free-energy estimates;
- operational finite-q coherence proxies.

Regenerate manuscript figures with:

```bash
MPLCONFIGDIR=/tmp/lp_hmc_matplotlib \
  python3 scripts/build_paper_figures.py
latexmk -pdf -interaction=nonstopmode -halt-on-error -cd paper/main.tex
```

---

## 7. Configuration files

### Reweighting source grids

```text
configs/reweight_sources_Zm1.csv
configs/reweight_sources_Zm0p75.csv
configs/reweight_sources_Zm0p6.csv
configs/reweight_sources_Zm0p5.csv
configs/reweight_sources_Zm0p25.csv
configs/reweight_sources_Z0.csv
configs/reweight_sources_Z0p5.csv
configs/reweight_sources_Z1.csv
configs/reweight_sources_Z1p25.csv
configs/reweight_sources_Z2.csv
```

These define the mass/source points used to build broad Binder campaigns.

### Direct termination and junction grids

- `configs/binder_termination/sources_Z*.csv` contains five-mass adaptive
  grids for the endpoint scan.
- `configs/binder_junction/sources_Z*.csv` contains 13-mass grids for the
  prepared older junction campaign.

### Umbrella profiles

`configs/umbrella_profiles/L6.json` through `L32.json` contain volume-specific
production defaults. Profile validation is performed by the
`validate_umbrella_profile*` scripts.

---

## 8. Script map

### Core simulation and measurement

| Script | Role |
|---|---|
| `scripts/thermalize.jl` | Ordinary HMC thermalization and checkpoint output. |
| `scripts/thermalize_replicas.jl` | Mass-tempering thermalization. |
| `scripts/thermalize_umbrella.jl` | `M2` umbrella thermalization with replica exchange. |
| `scripts/collect_reweight_stats.jl` | Ordinary reweighting measurements. |
| `scripts/collect_reweight_stats_replicas.jl` | Mass-tempering measurements. |
| `scripts/collect_umbrella_stats.jl` | Monolithic umbrella collection. |
| `scripts/collect_umbrella_shard.jl` | Restartable incremental umbrella collection. |
| `scripts/measure.jl` | Legacy mass scan. |
| `scripts/measure_single.jl` | Single-mass measurement. |
| `scripts/snap.jl` | Field snapshots. |

### Campaign submission and orchestration

| Script | Role |
|---|---|
| `scripts/submit_umbrella.py` | Common umbrella manifest/command construction. |
| `scripts/submit_umbrella_tsp.py` | Local GPU task-spooler submission. |
| `scripts/submit_umbrella_bsub.py` | LSF umbrella submission. |
| `scripts/umbrella_binder_campaign.py` | Prepare, submit, monitor, and analyze Binder source grids. |
| `scripts/direct_binder_termination_campaign.py` | Adaptive endpoint campaign. |
| `scripts/direct_binder_junction_campaign.py` | Prepared direct scan near the older extrapolated junction. |
| `scripts/run_reweight_task.py` | Execute one ordinary/reweighting task. |
| `scripts/run_umbrella_task.py` | Execute/resume one umbrella task. |

### Analysis and plotting

| Script | Role |
|---|---|
| `scripts/analyze_umbrella.py` | Canonical WHAM/MBAR reconstruction and bootstrap. |
| `scripts/aggregate_umbrella_binder.py` | Combine per-source Binder results. |
| `scripts/analyze_binder_m2.py` | Binder analysis from retained moments. |
| `scripts/analyze_binder_slopes.py` | Analytic mass derivatives and effective exponents. |
| `scripts/find_binder_crossings.py` | Pairwise crossing extraction. |
| `scripts/plot_binder_crossings_vs_z.py` | Cross-Z crossing figures and CSV. |
| `scripts/plot_umbrella_pm2.py` | Reconstructed `P(M2)` figures. |
| `scripts/plot_reweight_csv.py` | Generic curve overlays. |

### Structure factor and phase mapping

| Script | Role |
|---|---|
| `scripts/structure_factor_campaign.py` | Main census/prepare/run/analyze driver. |
| `scripts/structure_factor_analysis.py` | Canonical weights, observables, bootstrap, and bimodality. |
| `scripts/structure_factor_observables.jl` | Fourier shell geometry and measurements. |
| `scripts/validate_deep_modulated.jl` | Strong-modulation validation. |
| `scripts/explore_modulation_L16.py` | Early onset scan. |
| `scripts/thermodynamic_integration_L16.jl` | Three-branch integration engine. |
| `scripts/thermodynamic_integration_multishell.jl` | Multi-shell branch engine. |
| `scripts/run_thermodynamic_integration_*.py` | Campaign-specific grids and analysis. |
| `scripts/run_multishell_phase_map_L20.py` | Five-shell `L=20` phase map. |
| `scripts/run_multishell_join_refine_L20.py` | Replicated junction refinement. |

### Validation and tests

At minimum, run:

```bash
julia --project=. scripts/test_hmc.jl
julia --project=. scripts/test_replica_exchange.jl
julia --project=. scripts/test_structure_factor.jl
python3 -m unittest discover -s tests -v
```

GPU-specific validation additionally uses `scripts/test_umbrella_gpu.jl` and
`scripts/test_reweight_stats_gpu.jl`.

---

## 9. Important file formats

### JLD2 checkpoints

`.jld2` files contain fields and sampler state. Umbrella checkpoints also
retain window fields, centers, biases, walker labels, swap counters, transport
state, and RNG information needed for exact continuation. Use the project
validation scripts before trusting a checkpoint created by an older schema.

### Manifest CSVs

Manifests are the exact task contracts. Common fields include:

```text
task_id, L, Z, m2, replica, seed, eps, n_lf,
startup_eps, startup_n_lf, startup_sweeps,
production_sweeps, max_production_sweeps,
min_round_trip_fraction, min_swap_acceptance,
samples, skip, umbrella_replicas, umbrella_min, umbrella_max,
umbrella_kappa, umbrella_power, init_phase,
checkpoint_path, stats_path, diagnostics_path,
completion_marker, progress_marker, shard_dir
```

### Statistics CSVs

Umbrella statistics contain measurements from all biased windows and the
metadata needed to remove the bias. Depending on collector generation, fields
include `slot`, umbrella center and kappa, `M2`, `M4`, `Q`, `G`, energy, and
trajectory identifiers. Structure-factor statistics additionally contain
shell powers `P_q*`, selected power, and orientation observables.

### Report JSONs

Per-source JSON files under `reports/umbrella_binder_*` contain reconstructed
canonical moments, Binder values, uncertainty estimates, overlap/ESS
diagnostics, and source metadata. They are derived artifacts; the manifest and
statistics CSV remain the reproducibility basis.

### Completion markers

`.complete` files are intentionally small. Their presence means the task
workflow reached its successful terminal state. Scientific acceptance still
requires diagnostics and independent-start agreement.

---

## 10. How to audit or resume work

### Audit a campaign

1. Open its `manifest.csv`.
2. Count rows and expected replicas.
3. Verify every intended row has a final statistics file and completion marker.
4. Inspect progress JSONs for interrupted continuations.
5. Inspect diagnostics for HMC acceptance, minimum edge-swap acceptance,
   walker endpoint coverage, and round trips.
6. Reconstruct ordered and disordered starts independently.
7. Check overlap/ESS and source agreement before combining.
8. For negative `Z`, inspect shell-resolved structure factors before treating
   the zero-mode Binder cumulant as the correct order parameter.

### Resume an umbrella task

Use the original submitter with `--resume`; do not manually copy a random
checkpoint over the manifest path. The runner reads the progress marker and
continues from the last compatible checkpoint. The thermalization transport
gate and collection state are preserved.

### Regenerate Binder analysis

The high-level campaign drivers expose an `analyze` command. For example:

```bash
python3 scripts/direct_binder_termination_campaign.py \
  analyze --Z=-0.95625 --L 16 20
```

### Rebuild a structure-factor census

```bash
python3 scripts/structure_factor_campaign.py census \
  --campaign -0.95625 runs/umbrella_binder_termination/Zm0p95625 \
  --sizes 16 20 --workers 20 \
  --output reports/structure_factor_cpu/termination_Zm0p95625_census

python3 scripts/structure_factor_campaign.py prepare \
  --index reports/structure_factor_cpu/termination_Zm0p95625_census/census_index.csv \
  --output reports/structure_factor_cpu/termination_Zm0p95625_preparation \
  --production-root runs/structure_factor_cpu/termination_Zm0p95625 \
  --workers 20
```

---

## 11. Storage notes

The largest current directories are approximately:

| Directory family | Approximate size |
|---|---:|
| `runs/umbrella_binder_Zm06/` | 58 GB |
| `runs/umbrella_binder_termination/` | 36 GB |
| Individual broad `runs/umbrella_binder_Z*/` campaigns | 24–29 GB each |
| `runs/structure_factor_cpu/` | 5.6 GB |
| `runs/umbrella_tuning_tsp/` | 3.2 GB |
| `reports/structure_factor_cpu/` | 524 MB |

Raw statistics and checkpoints dominate storage. Do not delete shards merely
because a merged CSV exists unless restartability and audit requirements have
been reviewed. In particular, shards carry block structure used for correlated
uncertainty estimates.

---

## 12. Current scientific status encoded by the folders

As of the status date:

- The uniform broken–symmetric line has direct Binder data for
  `Z=-0.5,-0.25,0,0.5,1,1.25,2`, plus targeted negative-Z endpoint scans.
- The conventional uniform line terminates within the finite-size bracket
  `-0.9625 < Z < -0.95`; `Z=-0.95625` is ambiguous/coexistence dominated.
- The structure-factor estimator is validated in a deep modulated regime and
  detects finite-q dominance near and below `Z≈-1`.
- Single-shell thermodynamic-integration onsets at `L=16` and `L=20` were shown
  to track discrete shell switches and are not accepted physical critical
  points.
- The multi-shell `L=20` restricted continuation gives useful candidate
  uniform–modulated and modulated-coherence windows, but not final
  thermodynamic boundaries.
- The old direct junction campaign near `Z=-1.5...-1.65` is prepared but not
  completed and should not be cited as production evidence.
- The paper deliberately marks unresolved transition-order results as
  placeholders. Establishing the nature of the modulated–symmetric and
  modulated–uniform transitions requires unbiased joint-order-parameter
  sampling and finite-size barrier/response scaling.

For the current interpretation, read these in order:

1. `reports/umbrella_binder_termination/README.md`;
2. `reports/structure_factor_cpu/thermodynamic_integration_multishell_L20/README.md`;
3. `reports/structure_factor_cpu/thermodynamic_integration_multishell_join_L20/README.md`;
4. `paper/main.pdf` or `paper/main.tex`.

This ordering separates direct measurements from exploratory restricted-branch
estimates and prevents obsolete extrapolations from being treated as final
phase boundaries.
