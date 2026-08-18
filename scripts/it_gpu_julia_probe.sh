#!/usr/bin/env bash
# Compute-node body for the IT GPU/Julia probe.
# Submitted as: bsub ... bash /absolute/path/to/it_gpu_julia_probe.sh
# (same pattern as umbrella jobs: scalar bsub + bash on GPFS, not a job array,
# not `bsub < script`.)
set -euo pipefail

echo "=== LSF / host ==="
echo "date=$(date -Is)"
echo "hostname=$(hostname -s)"
echo "LSB_JOBID=${LSB_JOBID:-unset}"
echo "LSB_JOBNAME=${LSB_JOBNAME:-unset}"
echo "LSB_QUEUE=${LSB_QUEUE:-unset}"
echo "LSB_HOSTS=${LSB_HOSTS:-unset}"
echo "USER=${USER:-unset}"
echo "PWD=$(pwd)"
echo "env_HOME=${HOME:-unset}"
echo "passwd=$(getent passwd "${USER}" || true)"

echo "=== home / .lsbatch visibility (this is what fails on some gpu nodes) ==="
PASSWD_HOME="$(getent passwd "${USER}" | awk -F: '{print $6}')"
echo "passwd_HOME=${PASSWD_HOME:-unset}"
ls -ld "${PASSWD_HOME}" 2>&1 || true
ls -ld "${PASSWD_HOME}/.lsbatch" 2>&1 || true
ls -ld "${HOME}" 2>&1 || true
ls -ld "${HOME}/.lsbatch" 2>&1 || true

echo "=== modules / Julia / CUDA (same as production umbrella jobs) ==="
# shellcheck source=/dev/null
source /usr/share/Modules/init/bash
module load cuda/13.2
module load julia/1.12.6
if [[ -z "${GROUP:-}" ]]; then
  GROUP="$(id -gn 2>/dev/null || printf '%s' "$USER")"
fi
export GROUP
export JULIA_DEPOT_PATH="/usr/local/usrapps/${GROUP}/${USER}/julia_depot"
echo "GROUP=${GROUP}"
echo "JULIA_DEPOT_PATH=${JULIA_DEPOT_PATH}"
echo "julia=$(command -v julia)"
julia --version
echo "checking CUDA runtime and device"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
julia --startup-file=no --project="${ROOT}" -e '
VERSION >= v"1.12" || error("Julia 1.12 or newer is required; got $(VERSION)")
using CUDA
CUDA.functional(true) || error("CUDA is not functional")
println("preflight Julia=", VERSION, " GPU=", CUDA.name(CUDA.device()))
CUDA.versioninfo()
'

echo "=== probe ok on $(hostname -s) ==="
