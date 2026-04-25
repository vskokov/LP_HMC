#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
for L in 8; do
for i in {1..32}; do
    id=${RANDOM}
    TMPFILE=`mktemp`
    cp "${SCRIPT_DIR}/run_l40s.sh" $TMPFILE

    echo "julia \"${SCRIPT_DIR}/thermalize.jl\" --fp64 --rng=$id $L" >> $TMPFILE
    echo "rm $TMPFILE" >> $TMPFILE

    echo $TMPFILE

    chmod +x $TMPFILE
    bsub < $TMPFILE
done
done
