#!/usr/bin/env bash
# Worker for submit_binder_analysis_bsub.py. Run it through that submitter so
# LSB_JOBINDEX and the matching dynamic LSF array are configured together.

set -euo pipefail

data_prefix="binder_lsf_"
output_prefix=""
lattice_csv="6,8,12,16,24,32"
run_root="runs"
output_root="plots"
num=301
bootstrap=1000
block_size="auto"
cuda_batch_size=32
scans=()

while (($#)); do
    case "$1" in
        --data-prefix) data_prefix="$2"; shift 2 ;;
        --output-prefix) output_prefix="$2"; shift 2 ;;
        --lattice-sizes) lattice_csv="$2"; shift 2 ;;
        --run-root) run_root="$2"; shift 2 ;;
        --output-root) output_root="$2"; shift 2 ;;
        --num) num="$2"; shift 2 ;;
        --bootstrap) bootstrap="$2"; shift 2 ;;
        --block-size) block_size="$2"; shift 2 ;;
        --cuda-batch-size) cuda_batch_size="$2"; shift 2 ;;
        --scan) scans+=("$2"); shift 2 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

if ((${#scans[@]} == 0)); then
    scans=(
        "-0.6,-1.95,-1.75,mZ0.6"
        "-0.77,-2.25,-2.0,mZ0.77"
        "-0.9,-2.45,-2.2,mZ0.9"
    )
fi
[[ -n "$output_prefix" ]] || output_prefix="$data_prefix"

IFS=',' read -r -a lattice_sizes <<< "$lattice_csv"
scan_count=${#scans[@]}
task_count=$((${#lattice_sizes[@]} * scan_count))
task_index=${LSB_JOBINDEX:?LSB_JOBINDEX is not set}
if ((task_index < 1 || task_index > task_count)); then
    echo "LSB_JOBINDEX=$task_index is outside 1-$task_count" >&2
    exit 2
fi

array_offset=$((task_index - 1))
lattice_index=$((array_offset / scan_count))
scan_index=$((array_offset % scan_count))
L="${lattice_sizes[$lattice_index]}"
IFS=',' read -r Z m2_start m2_end label <<< "${scans[$scan_index]}"

source /usr/share/Modules/init/bash
export JULIA_DEPOT_PATH=/rsstu/users/v/vskokov/gluon/jd
export JULIAUP_DEPOT_PATH=/rsstu/users/v/vskokov/gluon/.julia
export PATH=/rsstu/users/v/vskokov/gluon/juliaup/bin:"$PATH"
export MPLBACKEND=Agg
export PYTHONUNBUFFERED=1
module load cuda/12.3

project_dir="${LS_SUBCWD:-$PWD}"
cd "$project_dir"
mkdir -p "$output_root"

manifest="${run_root}/${data_prefix}L${L}/manifest.csv"
output="${output_root}/${output_prefix}${label}_L${L}"

[[ -f "$manifest" ]] || {
    echo "missing manifest: $manifest" >&2
    exit 1
}

echo "host=$(hostname)"
echo "task_index=$task_index/$task_count L=$L Z=$Z m2_start=$m2_start m2_end=$m2_end"
echo "manifest=$manifest output=$output"
echo "julia=$(command -v julia)"
julia --version
julia --project=. --startup-file=no -e \
    'using CUDA; CUDA.functional(true) || error("CUDA is not functional"); CUDA.versioninfo()'

python3 reweight_binder.py \
    --manifest "$manifest" \
    --start "$Z" "$m2_start" \
    --end "$Z" "$m2_end" \
    --num "$num" \
    --source-mode mbar \
    --bootstrap "$bootstrap" \
    --block-size "$block_size" \
    --backend cuda \
    --cuda-batch-size "$cuda_batch_size" \
    --output "$output"
