# M² umbrella-exchange validation on NVIDIA RTX A6000

Validation point: `L=4`, `Z=1`, `m²=-2`, `ε=0.03`, `n_lf=4`.

The umbrella run used five centers from 0 to 0.4, common `κ=80`, 500 discarded
warmup sweeps, and 2,000 retained samples per window separated by two sweeps. The
unbiased reference used the existing single-HMC collector with the same physical and
HMC parameters, 500 warmup sweeps, and 2,000 retained samples separated by two
sweeps. Errors are synchronized moving-block bootstrap estimates with block size 20
and 200 draws.

| Quantity | Umbrella MBAR | Direct HMC | Combined-error difference |
|---|---:|---:|---:|
| `<M²>` | 0.390680 ± 0.007174 | 0.369874 ± 0.008111 | 1.92 σ |
| Binder | 0.647227 ± 0.001467 | 0.645197 ± 0.002530 | 0.69 σ |

Additional diagnostics:

- Neighboring `M²` histogram overlaps: 0.7645, 0.7390, 0.7835, 0.7535.
- Completed walker round trips: 392 during retained collection.
- Minimum cumulative swap acceptance at completion: 0.656.
- Canonical MBAR effective sample size: 4,347 of 10,000 biased samples.
- CUDA force and Hamiltonian equivalence tests passed on the A6000.

This validates the implementation and unbiasing on a volume where direct HMC is
reliable. It does not validate the default L24/L32 umbrella grid; those grids must be
accepted only after their own edge-overlap, round-trip, and phase-start checks.

Short A6000 probes were also used to define pilot—not production—profiles. After 200
conservative startup sweeps and 200 production sweeps, the power-spaced L24 grid had
minimum/median swap acceptance 0.41/0.65 and HMC acceptance 0.695–0.870. The L32 grid
had minimum/median swap acceptance 0.31/0.64 and HMC acceptance 0.630–0.835. Neither
probe was long enough for a round trip; the exact settings are recorded in
`large_L_probes.csv`.
