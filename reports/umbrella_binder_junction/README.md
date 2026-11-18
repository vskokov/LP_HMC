# Direct Binder scan at the candidate inhomogeneous junction

This campaign directly tests the extrapolated Binder line near the multi-shell
free-energy junction.  It scans

- `Z = -1.50, -1.55, -1.60, -1.65`;
- `L = 12, 16, 20`, with `L=24` manifests prepared as a confirmation stage;
- 13 source masses per `Z`, centered on the previous quadratic Binder-line
  estimate and extending by `+/-0.30` in `m2`;
- two independent starts per point, one ordered and one disordered.

The sampler, umbrella profiles, transport gates, reconstruction, and bootstrap
analysis are unchanged.  The source observable remains the zero-mode Binder
cumulant, while the existing structure-factor analysis is needed to flag points
where a finite-q mode rather than the zero mode is the appropriate order
parameter.

The complete campaign comprises 416 tasks including `L=24`, or 312 tasks in the
initial `L=12,16,20` stage.  Production is staged: task IDs 12 and 13 in each
initial-stage manifest are central-mass transport pilots.  These 24 pilots were
queued first.  The other tasks should be released only after both phase starts
pass the round-trip, edge-swap, overlap, and agreement checks at negative `Z`.

Driver:

```text
python3 scripts/direct_binder_junction_campaign.py status
python3 scripts/direct_binder_junction_campaign.py submit --pilot-only
python3 scripts/direct_binder_junction_campaign.py submit
python3 scripts/direct_binder_junction_campaign.py analyze
```

The final analysis produces one Binder curve per `Z` and the pairwise `12x16`
and `16x20` crossings versus `Z`.  The `20x24` crossing is added after the
confirmation stage is explicitly submitted with `--include-L24`.
