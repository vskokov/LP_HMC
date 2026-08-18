#!/usr/bin/env bash
# Submit N independent scalar GPU jobs (not an LSF array) so they can land
# on different gpu* hosts. Flags match umbrella tuning: short_gpu, 24 GB,
# one shared GPU, h200|h100|l40s, 10 minute walltime.
#
# Usage (from a Hazel login node, in the repo):
#   bash scripts/submit_it_gpu_julia_probes.sh          # 8 jobs
#   bash scripts/submit_it_gpu_julia_probes.sh 16       # 16 jobs
#
# Do not exclude gpu21: IT needs jobs to hit the hosts that die with
#   Cannot open your job file: /home/$USER/.lsbatch/...
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROBE="${ROOT}/scripts/it_gpu_julia_probe.sh"
LOG_DIR="${ROOT}/runs/lsf_gpu_julia_probe/logs"
N="${1:-8}"
QUEUE="${QUEUE:-short_gpu}"
GPU_SELECT="${GPU_SELECT:-h200 || h100 || l40s}"
EXCLUDE="${EXCLUDE_HOSTS:-}"   # empty on purpose; set e.g. gpu31 if needed

if [[ ! -f /usr/share/Modules/init/bash ]]; then
  echo "submit this on a Hazel login node" >&2
  exit 1
fi
if [[ ! -f "$PROBE" ]]; then
  echo "missing probe: $PROBE" >&2
  exit 1
fi

mkdir -p "$LOG_DIR"
PROBE="$(readlink -f "$PROBE")"

select_expr="(${GPU_SELECT})"
if [[ -n "$EXCLUDE" ]]; then
  IFS=',' read -ra _hosts <<< "$EXCLUDE"
  for host in "${_hosts[@]}"; do
    host="${host// /}"
    [[ -n "$host" ]] && select_expr+=" && hname!='${host}'"
  done
fi

echo "probe=${PROBE}"
echo "logs=${LOG_DIR}"
echo "jobs=${N}"
echo "select=${select_expr}"

for i in $(seq 1 "$N"); do
  name="it_gpu_julia_${i}"
  echo "+ bsub -J ${name} ..."
  bsub \
    -J "$name" \
    -q "$QUEUE" \
    -W 10 \
    -n 1 \
    -R "select[${select_expr}] rusage[mem=24]" \
    -gpu "num=1:mode=shared:mps=no" \
    -o "${LOG_DIR}/%J.out" \
    -e "${LOG_DIR}/%J.err" \
    bash "$PROBE"
done

echo
echo "Watch with:  bjobs -w"
echo "Logs in:     ${LOG_DIR}"
echo "After they finish:"
echo "  grep -H 'executed on host' ${LOG_DIR}/*.out"
echo "  grep -H 'Cannot open your job file\\|probe ok' ${LOG_DIR}/*.out"
