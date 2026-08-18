#!/usr/bin/env bash
# LSF driver for umbrella profile tuning (pilot -> nlf -> confirm -> promote).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE_DIR="$ROOT/configs/umbrella_profiles"
REPORT_DIR="$ROOT/reports/umbrella_tuning"
LOG_DIR="$REPORT_DIR/logs"
CAMPAIGN_DIR="$ROOT/runs/umbrella_tuning_lsf"
ALL_SIZES=(6 8 12 16 18 20 24 32)
TUNE_SIZES=("${ALL_SIZES[@]}")

JULIA="${JULIA:-julia}"

cluster_env() {
  if [[ -f /usr/share/Modules/init/bash ]]; then
    # shellcheck source=/dev/null
    source /usr/share/Modules/init/bash
    module load cuda/13.2
    module load julia/1.12.6
    export JULIA_DEPOT_PATH="/usr/local/usrapps/${GROUP:?GROUP must be set on LSF}/${USER}/julia_depot"
  fi
  JULIA="${JULIA:-julia}"
}

FORCE="${FORCE:-0}"
DRY_RUN="${DRY_RUN:-0}"
FRESH_PILOT="${FRESH_PILOT:-1}"
CONTINUE_ON_ERROR="${CONTINUE_ON_ERROR:-1}"
STAGE="${STAGE:-}"
CONFIRM_SAMPLES="${CONFIRM_SAMPLES:-}"
CONFIRM_SAMPLE_SCHEDULE="${CONFIRM_SAMPLE_SCHEDULE:-}"
CONFIRM_ATTEMPTS="${CONFIRM_ATTEMPTS:-}"
PILOT_SAMPLES="${PILOT_SAMPLES:-}"
NLF="${NLF:-}"
QUEUE="${QUEUE:-short_gpu}"
GPU_SELECT="${GPU_SELECT:-h200 || h100 || l40s}"
EXCLUDE_HOSTS="${EXCLUDE_HOSTS:-gpu31}"

usage() {
  cat <<'EOF'
LSF umbrella profile validation on H100 (2-hour resumable jobs).

Usage:
  validate_umbrella_profiles_lsf.sh [options] status
  validate_umbrella_profiles_lsf.sh [options] prepare [--sizes 16,18,20,24]
  validate_umbrella_profiles_lsf.sh preflight <L>
  validate_umbrella_profiles_lsf.sh [options] submit [<L> ...]
  validate_umbrella_profiles_lsf.sh [options] repair
  validate_umbrella_profiles_lsf.sh [options] tune <L> [<L> ...]
  validate_umbrella_profiles_lsf.sh [options] tune-all
  validate_umbrella_profiles_lsf.sh reset-tuning

Options:
  --force                   Re-tune even when a profile is already validated
  --dry-run                 Print commands only
  --confirm-samples N       Confirmation samples per window (first attempt)
  --confirm-sample-schedule LIST
                            Comma-separated confirm sample counts, e.g. 1000,3000,6000
  --confirm-attempts N      Escalating confirm attempts if canonical gate fails
  --pilot-samples N         Pilot collection samples per window
  --n-lf N                  Override selected n_lf for confirm/promote

Commands:
  status         Show per-L stage and validated flag.
  prepare        Create campaign tree, manifests, and state files.
  preflight      Run self-resubmit preflight for L's active pilot/confirm stage.
  submit         bsub initial jobs for listed L (or all pending).
  repair         Advance state: resubmit incomplete jobs, summarize nlf, promote.
  tune           prepare + preflight + submit for listed sizes.
  tune-all       Tune every unvalidated profile.
  reset-tuning   Clear runs/umbrella_tuning_lsf and reset profiles.

Environment:
  Same options are available via FORCE, DRY_RUN, CONFIRM_SAMPLES,
  CONFIRM_SAMPLE_SCHEDULE, CONFIRM_ATTEMPTS, PILOT_SAMPLES, NLF, QUEUE, GPU_SELECT
  EXCLUDE_HOSTS (default: gpu31)
  (export the variable or pass the matching --flag).

Examples:
  bash scripts/validate_umbrella_profiles_lsf.sh --force \
    --confirm-sample-schedule=1000,3000,6000 tune 16 18 20 24
  bash scripts/validate_umbrella_profiles_lsf.sh --confirm-samples=3000 tune 32

Operational loop:
  bash scripts/validate_umbrella_profiles_lsf.sh tune 16 18 20 24
  bash scripts/validate_umbrella_profiles_lsf.sh repair
  bash scripts/validate_umbrella_profiles_lsf.sh status
EOF
}

profile_is_validated() {
  local profile="$PROFILE_DIR/L${1}.json"
  python3 - "$profile" <<'PY'
import json, sys
raise SystemExit(0 if json.load(open(sys.argv[1])).get("validated") is True else 1)
PY
}

campaign_args() {
  local -a args=(
    --campaign-dir "$CAMPAIGN_DIR"
    --profile-dir "$PROFILE_DIR"
    --report-dir "$REPORT_DIR"
    --julia "$JULIA"
    --queue "$QUEUE"
    --gpu-select "$GPU_SELECT"
  )
  local host
  IFS=',' read -ra _exclude_hosts <<< "$EXCLUDE_HOSTS"
  for host in "${_exclude_hosts[@]}"; do
    host="${host#"${host%%[![:space:]]*}"}"
    host="${host%"${host##*[![:space:]]}"}"
    [[ -n "$host" ]] && args+=(--exclude-host="$host")
  done
  if [[ "$FRESH_PILOT" == "1" ]]; then
    args+=(--fresh-pilot)
  fi
  if [[ -n "${CONFIRM_SAMPLES:-}" ]]; then
    args+=(--confirm-samples="$CONFIRM_SAMPLES")
  fi
  if [[ -n "${CONFIRM_SAMPLE_SCHEDULE:-}" ]]; then
    args+=(--confirm-sample-schedule="$CONFIRM_SAMPLE_SCHEDULE")
  fi
  if [[ -n "${CONFIRM_ATTEMPTS:-}" ]]; then
    args+=(--confirm-attempts="$CONFIRM_ATTEMPTS")
  fi
  if [[ -n "${PILOT_SAMPLES:-}" ]]; then
    args+=(--pilot-samples="$PILOT_SAMPLES")
  fi
  if [[ -n "${NLF:-}" ]]; then
    args+=(--n-lf="$NLF")
  fi
  if [[ "$DRY_RUN" == "1" ]]; then
    args+=(--dry-run)
  fi
  if [[ "$FORCE" == "1" ]]; then
    args+=(--force-revalidate)
  fi
  printf '%s\n' "${args[@]}"
}

run_campaign() {
  local subcommand="$1"
  shift
  cluster_env
  local -a cmd=(python3 "$ROOT/scripts/umbrella_tuning_campaign.py" "$subcommand")
  local arg
  while IFS= read -r arg; do
    cmd+=("$arg")
  done < <(campaign_args)
  "${cmd[@]}" "$@"
}

cmd_status() {
  run_campaign status
}

cmd_prepare() {
  local sizes=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --sizes)
        sizes="$2"
        shift 2
        ;;
      *)
        echo "unknown prepare argument: $1" >&2
        return 2
        ;;
    esac
  done
  if [[ -z "$sizes" ]]; then
    sizes="$(IFS=,; echo "${TUNE_SIZES[*]}")"
  fi
  run_campaign prepare --sizes "$sizes"
}

cmd_preflight() {
  local L="${1:?preflight requires L}"
  run_campaign preflight --L "$L"
}

cmd_submit() {
  if (("$#")); then
    local L
    for L in "$@"; do
      run_campaign submit --L "$L"
    done
  else
    run_campaign submit
  fi
}

cmd_repair() {
  run_campaign repair
}

cmd_tune() {
  if (("$#" == 0)); then
    echo "tune requires at least one L value" >&2
    usage >&2
    return 2
  fi
  local rc=0
  local -a pending=()
  local L
  for L in "$@"; do
    if [[ "$FORCE" != "1" ]] && profile_is_validated "$L"; then
      echo "=== L=$L already validated; skipping (use --force or FORCE=1 bash ... to re-tune) ==="
      continue
    fi
    pending+=("$L")
  done
  if ((${#pending[@]} == 0)); then
    return 0
  fi
  local sizes
  sizes="$(IFS=,; echo "${pending[*]}")"
  if ! run_campaign prepare --sizes "$sizes"; then
    return 1
  fi
  for L in "${pending[@]}"; do
    echo "=== LSF tuning L=$L ==="
    if ! run_campaign preflight --L "$L"; then
      rc=1
      [[ "$CONTINUE_ON_ERROR" == "1" ]] || return "$rc"
      continue
    fi
    if ! run_campaign submit --L "$L"; then
      rc=1
      [[ "$CONTINUE_ON_ERROR" == "1" ]] || return "$rc"
    fi
  done
  return "$rc"
}

cmd_tune_all() {
  local -a pending=()
  local L
  for L in "${TUNE_SIZES[@]}"; do
    if [[ "$FORCE" == "1" ]] || ! profile_is_validated "$L"; then
      pending+=("$L")
    fi
  done
  if ((${#pending[@]} == 0)); then
    echo "All profiles are already validated."
    return 0
  fi
  echo "Pending sizes: ${pending[*]}"
  cmd_tune "${pending[@]}"
}

cmd_reset_tuning() {
  echo "Removing LSF tuning campaign: $CAMPAIGN_DIR"
  rm -rf "$CAMPAIGN_DIR"
  echo "Resetting umbrella profiles to unvalidated scaling proposals"
  python3 - "$PROFILE_DIR" "$ROOT" <<'PY'
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[2]) / "scripts"))
from umbrella_profiles import SUPPORTED_SIZES, proposed_profile

profile_dir = Path(sys.argv[1])
for L in SUPPORTED_SIZES:
    path = profile_dir / f"L{L}.json"
    path.write_text(json.dumps(proposed_profile(L), indent=2) + "\n", encoding="utf-8")
    print(f"reset {path}")
PY
}

parse_global_opts() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --force)
        FORCE=1
        shift
        ;;
      --dry-run)
        DRY_RUN=1
        shift
        ;;
      --confirm-samples)
        CONFIRM_SAMPLES="${2:?--confirm-samples requires a value}"
        shift 2
        ;;
      --confirm-samples=*)
        CONFIRM_SAMPLES="${1#*=}"
        shift
        ;;
      --confirm-sample-schedule)
        CONFIRM_SAMPLE_SCHEDULE="${2:?--confirm-sample-schedule requires a value}"
        shift 2
        ;;
      --confirm-sample-schedule=*)
        CONFIRM_SAMPLE_SCHEDULE="${1#*=}"
        shift
        ;;
      --confirm-attempts)
        CONFIRM_ATTEMPTS="${2:?--confirm-attempts requires a value}"
        shift 2
        ;;
      --confirm-attempts=*)
        CONFIRM_ATTEMPTS="${1#*=}"
        shift
        ;;
      --pilot-samples)
        PILOT_SAMPLES="${2:?--pilot-samples requires a value}"
        shift 2
        ;;
      --pilot-samples=*)
        PILOT_SAMPLES="${1#*=}"
        shift
        ;;
      --n-lf)
        NLF="${2:?--n-lf requires a value}"
        shift 2
        ;;
      --n-lf=*)
        NLF="${1#*=}"
        shift
        ;;
      -h|--help|help)
        usage
        exit 0
        ;;
      -*)
        echo "unknown option: $1" >&2
        usage >&2
        exit 2
        ;;
      *)
        break
        ;;
    esac
  done
  GLOBAL_REMAINING=("$@")
}

main() {
  parse_global_opts "$@"
  set -- "${GLOBAL_REMAINING[@]}"
  local cmd="${1:-status}"
  shift || true
  case "$cmd" in
    -h|--help|help)
      usage
      ;;
    status)
      cmd_status
      ;;
    prepare)
      cmd_prepare "$@"
      ;;
    preflight)
      cmd_preflight "$@"
      ;;
    submit)
      cmd_submit "$@"
      ;;
    repair)
      cmd_repair
      ;;
    tune)
      cmd_tune "$@"
      ;;
    tune-all)
      cmd_tune_all
      ;;
    reset-tuning)
      cmd_reset_tuning
      ;;
    *)
      echo "unknown command: $cmd" >&2
      usage >&2
      return 2
      ;;
  esac
}

main "$@"
