#!/bin/bash
#BSUB -W 60
#BSUB -n 1
#BSUB -q gpu
#BSUB -R "select[l40s]"
#BSUB -gpu "num=1:mode=shared:mps=no"
#BSUB -o tmp/out.%J
#BSUB -e tmp/err.%J
source /usr/share/Modules/init/bash
module load julia/1.8.0
module load cuda/12.0
