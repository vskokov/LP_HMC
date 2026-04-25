#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

id=${RANDOM}
TMPFILE=`mktemp`
cp "${SCRIPT_DIR}/run_cpu.sh" $TMPFILE

echo "julia -t 16 \"${SCRIPT_DIR}/reweighted_binder.jl\"" >> $TMPFILE
echo "rm $TMPFILE" >> $TMPFILE

echo $TMPFILE

chmod +x $TMPFILE
bsub < $TMPFILE
