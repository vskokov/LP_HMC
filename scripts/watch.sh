#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="${SCRIPT_DIR}/../data"

n16=`ls "${DATA_DIR}/magnetization_L_16_"*"_id_17663.dat" 2>/dev/null | wc -l`
n24=`ls "${DATA_DIR}/magnetization_L_24_"*.dat 2>/dev/null | wc -l`

echo "16 progress: $n16"
echo "24 progress: $n24"
