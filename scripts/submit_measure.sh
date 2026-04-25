#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="${SCRIPT_DIR}/../data"
mass=-3.81

#for L in 64 48 12 8; do
for L in 64 48 32 24 16 12 8; do
for file in `ls "${DATA_DIR}/thermalized_L_${L}_mass_${mass}_id_"*.jld2`; do
for id in {1..4}; do

    id=${RANDOM}
    TMPFILE=`mktemp`
    cp "${SCRIPT_DIR}/run_cpu.sh" $TMPFILE

    echo "julia -t 16 \"${SCRIPT_DIR}/measure_single.jl\" --cpu --fp64 --init=$file --mass=$mass --rng=$id $L" >> $TMPFILE
    echo "rm $TMPFILE" >> $TMPFILE

    echo $TMPFILE

    chmod +x $TMPFILE
    bsub < $TMPFILE

done
done
    sleep 10
done
