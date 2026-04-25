#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
L=16

id=${RANDOM}
echo $id
TMPFILE=`mktemp`

out="~/tmp/out.$id"
err="~/tmp/err.$id"

echo "echo \`date\` >> $out" >> $TMPFILE
echo "julia \"${SCRIPT_DIR}/measure.jl\" --fp64 --rng=$id $L 1>> $out 2> $err" >> $TMPFILE
echo "echo \`date\` >> $out" >> $TMPFILE
echo "rm $TMPFILE" >> $TMPFILE

echo $TMPFILE

chmod +x $TMPFILE
echo $TMPFILE | batch
