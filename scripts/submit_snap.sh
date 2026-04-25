#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="${SCRIPT_DIR}/../data"
L=8
N=4

for file in `ls "${DATA_DIR}/thermalized_L_${L}_id_"*.jld2 | sort -R | head -$N`; do

    id=${RANDOM}
    TMPFILE=`mktemp`
    cp "${SCRIPT_DIR}/run_l40s.sh" $TMPFILE

    echo "julia \"${SCRIPT_DIR}/snap.jl\" --fp64 --rng=$id $L" >> $TMPFILE

    echo "rm $TMPFILE" >> $TMPFILE

    echo $TMPFILE

    chmod +x $TMPFILE
    bsub < $TMPFILE

done
