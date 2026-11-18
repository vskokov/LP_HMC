# Binder mass-derivative finite-size scaling

The reweighted crossing is primary; the legacy linear crossing is retained as a systematic check.
Reference exponents are conventional benchmarks only and are not imposed on the modified theory.

## Campaign status

- Z=-0.5: ready (L12=42/42 L16=42/42 L20=42/42 L24=42/42 binder_csv=present)
- Z=-0.25: ready (L12=38/38 L16=38/38 L20=38/38 L24=38/38 binder_csv=present)
- Z=0: ready (L12=42/42 L16=42/42 L20=42/42 L24=42/42 binder_csv=present)
- Z=0.5: ready (L12=40/40 L16=40/40 L20=40/40 L24=40/40 binder_csv=present)
- Z=1: ready (L12=36/36 L16=36/36 L20=36/36 L24=36/36 binder_csv=present)
- Z=1.25: ready (L12=38/38 L16=38/38 L20=38/38 L24=38/38 binder_csv=present)
- Z=2: ready (L12=40/40 L16=40/40 L20=40/40 L24=40/40 binder_csv=present)
- Z=-0.75: skipped (L12=30/30 L16=30/30 L20=28/30 L24=28/30 binder_csv=will_generate)
- Z=-1: skipped (L12=28/30 L16=27/30 L20=12/30 L24=0/30 binder_csv=will_generate)

## Largest-size-pair readout

- Z=-0.5: central y_eff=1.713, bootstrap [1.559, 1.559], warning=ok; interval contains none of the three exact benchmark values.
- Z=0: central y_eff=1.511, bootstrap [nan, nan], warning=unstable_crossing; interval contains none of the three exact benchmark values.
- Z=1: central y_eff=1.729, bootstrap [1.699, 1.699], warning=source_disagreement; interval contains none of the three exact benchmark values.
- Z=1.25: central y_eff=1.686, bootstrap [1.654, 1.654], warning=source_disagreement; interval contains none of the three exact benchmark values.
- Z=2: central y_eff=1.252, bootstrap [1.142, 1.142], warning=source_disagreement; interval contains none of the three exact benchmark values.

A benchmark match is not a singularity classification. Drift across the three size pairs,
mixed-moment tails, source agreement, and the possible failure of uniform M in the modulated regime
must be considered together. First-order identification additionally requires coexistence/barrier evidence.
