#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
L=16
mass=-3.81

for i in {1..4}; do
    id=${RANDOM}
    TMPFILE=`mktemp`
    echo $id

    out="~/tmp/out.$id"
    err="~/tmp/err.$id"

    echo "echo \`date\` >> $out" >> $TMPFILE
    echo "julia \"${SCRIPT_DIR}/thermalize.jl\" --fp64 --mass=$mass --rng=$id $L 1>> $out 2> $err" >> $TMPFILE
    echo "echo \`date\` >> $out" >> $TMPFILE
    echo "rm $TMPFILE" >> $TMPFILE

    echo $TMPFILE

    chmod +x $TMPFILE
    echo $TMPFILE | batch
done
