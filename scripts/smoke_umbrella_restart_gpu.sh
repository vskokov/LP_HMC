#!/usr/bin/env bash
# CUDA process-restart smoke test. Run inside an allocated GPU job.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
artifact_dir="${UMBRELLA_SMOKE_DIR:-$(mktemp -d /tmp/umbrella-gpu-restart.XXXXXX)}"
julia_bin="${JULIA:-julia}"
common=(2 --fp64 --Z=-0.6 --mass=-1.86421 --eps=0.02 --n_lf=2
  --startup-eps=0.01 --startup-n-lf=2 --startup-sweeps=0
  --production-sweeps=1025 --max-production-sweeps=1025
  --min-round-trip-fraction=0 --min-swap-acceptance=0
  --umbrella-replicas=3 --umbrella-min=0 --umbrella-max=0.4
  --umbrella-kappa=10 --umbrella-power=1.3 --swap-every=1
  --rng=17 --task-id=0 --init-phase=disordered)

"$julia_bin" --startup-file=no --project="$repo_root" \
  "$repo_root/scripts/thermalize_umbrella.jl" "${common[@]}" \
  --checkpoint="$artifact_dir/full.jld2"
set +e
"$julia_bin" --startup-file=no --project="$repo_root" \
  "$repo_root/scripts/thermalize_umbrella.jl" "${common[@]}" \
  --checkpoint="$artifact_dir/segmented.jld2" --runtime-seconds=0.000000001
first_exit=$?
set -e
[[ "$first_exit" -eq 75 ]]
"$julia_bin" --startup-file=no --project="$repo_root" \
  "$repo_root/scripts/thermalize_umbrella.jl" "${common[@]}" \
  --checkpoint="$artifact_dir/segmented.jld2" --init="$artifact_dir/segmented.jld2"

collect=(2 --fp64 --Z=-0.6 --mass=-1.86421 --eps=0.02 --n_lf=2
  --production-sweeps=1025 --min-round-trip-fraction=0 --min-swap-acceptance=0
  --umbrella-replicas=3 --umbrella-min=0 --umbrella-max=0.4
  --umbrella-kappa=10 --umbrella-power=1.3 --swap-every=1
  --rng=19 --task-id=0 --init-phase=disordered --samples=3 --skip=1 --block-index=0)
for mode in full segmented
do
  "$julia_bin" --startup-file=no --project="$repo_root" \
    "$repo_root/scripts/collect_umbrella_shard.jl" "${collect[@]}" \
    --init="$artifact_dir/$mode.jld2" --output="$artifact_dir/$mode.csv" \
    --diagnostics="$artifact_dir/${mode}_diagnostics.csv" \
    --collection-checkpoint="$artifact_dir/${mode}_collection.jld2"
done
cmp "$artifact_dir/full.csv" "$artifact_dir/segmented.csv"
cmp "$artifact_dir/full_diagnostics.csv" "$artifact_dir/segmented_diagnostics.csv"
echo "gpu_restart_smoke=passed artifact_dir=$artifact_dir"
