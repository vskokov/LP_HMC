#!/usr/bin/env bash
#BSUB -W 180
#BSUB -n 1
#BSUB -q gpu
#BSUB -R "select[h100]"
#BSUB -gpu "num=1:mode=shared:mps=no"
#BSUB -o tmp/out.%J
#BSUB -e tmp/err.%J
source /usr/share/Modules/init/bash
module load cuda/13.2
module load julia/1.12.6
export JULIA_DEPOT_PATH="/usr/local/usrapps/$GROUP/$USER/julia_depot"
export LD_LIBRARY_PATH=
