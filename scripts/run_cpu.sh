#!/bin/bash
#BSUB -W 60
#BSUB -n 16
#BSUB -R span[hosts=1] 
#BSUB -o tmp/out.%J
#BSUB -e tmp/err.%J

source /usr/share/Modules/init/bash
module load cuda/13.2
module load julia/1.12.6
export JULIA_DEPOT_PATH="/usr/local/usrapps/$GROUP/$USER/julia_depot"
