#!/bin/bash
#BSUB -W 60
#BSUB -n 16
#BSUB -R span[hosts=1] 
#BSUB -o tmp/out.%J
#BSUB -e tmp/err.%J

export JULIA_DEPOT_PATH=~/perm/.julia
module load julia/1.8.0
