#!/usr/bin/env bash
# Submit from the LP_HMC repository root with:
#   mkdir -p runs/reweight_binder_lsf/logs plots
#   bsub < scripts/reweight_binder_bsub.sh

#BSUB -J "reweight_binder[1-18]%4"
#BSUB -W 120
#BSUB -n 1
#BSUB -q short_gpu
#BSUB -R "select[h200 || h100 || l40s]"
#BSUB -R "select[hname!='gpu16' && hname!='gpu33']"
#BSUB -R "rusage[mem=32]"
#BSUB -gpu "num=1:mode=shared:mps=no"
#BSUB -o "runs/reweight_binder_lsf/logs/%J_%I.out"
#BSUB -e "runs/reweight_binder_lsf/logs/%J_%I.err"

set -euo pipefail

source /usr/share/Modules/init/bash
export JULIA_DEPOT_PATH=/rsstu/users/v/vskokov/gluon/jd
export JULIAUP_DEPOT_PATH=/rsstu/users/v/vskokov/gluon/.julia
export PATH=/rsstu/users/v/vskokov/gluon/juliaup/bin:"$PATH"
export MPLBACKEND=Agg
export PYTHONUNBUFFERED=1
module load cuda/12.3

project_dir="${LS_SUBCWD:-$PWD}"
cd "$project_dir"
mkdir -p plots

lattice_sizes=(6 8 12 16 24 32)
z_values=(-0.6 -0.77 -0.9)
m2_starts=(-1.95 -2.25 -2.45)
m2_ends=(-1.75 -2.0 -2.2)
output_labels=(mZ0.6 mZ0.77 mZ0.9)

array_offset=$((LSB_JOBINDEX - 1))
lattice_index=$((array_offset / 3))
scan_index=$((array_offset % 3))

L="${lattice_sizes[$lattice_index]}"
Z="${z_values[$scan_index]}"
m2_start="${m2_starts[$scan_index]}"
m2_end="${m2_ends[$scan_index]}"
label="${output_labels[$scan_index]}"

# The LSF analysis runs where the simulations were produced, so the original
# manifest contains the correct absolute HPC paths.  manifest.local.csv is
# only for data copied to another machine.
manifest="runs/binder_lsf_L${L}/manifest.csv"
output="plots/binder_lsf_${label}_L${L}"

[[ -f "$manifest" ]] || {
    echo "missing manifest: $manifest" >&2
    exit 1
}

echo "host=$(hostname)"
echo "task_index=$LSB_JOBINDEX L=$L Z=$Z m2_start=$m2_start m2_end=$m2_end"
echo "manifest=$manifest output=$output"
echo "julia=$(command -v julia)"
julia --version
julia --project=. --startup-file=no -e \
    'using CUDA; CUDA.functional(true) || error("CUDA is not functional"); CUDA.versioninfo()'

python3 reweight_binder.py \
    --manifest "$manifest" \
    --start "$Z" "$m2_start" \
    --end "$Z" "$m2_end" \
    --num 301 \
    --source-mode mbar \
    --bootstrap 1000 \
    --block-size auto \
    --backend cuda \
    --cuda-batch-size 32 \
    --output "$output"
