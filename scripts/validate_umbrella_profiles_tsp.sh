#!/usr/bin/env bash
# Local TSP driver for umbrella profile tuning (pilot -> nlf -> confirm -> promote).
# Same commands as validate_umbrella_profiles_lsf.sh; jobs go to task-spooler.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE_DIR="$ROOT/configs/umbrella_profiles"
REPORT_DIR="$ROOT/reports/umbrella_tuning"
CAMPAIGN_DIR="$ROOT/runs/umbrella_tuning_tsp"
ALL_SIZES=(6 8 12 16 18 20 24 32)
TUNE_SIZES=("${ALL_SIZES[@]}")

JULIA="${JULIA:-$HOME/.julia/juliaup/julia-1.12.6+0.x64.linux.gnu/bin/julia}"
if [[ ! -x "$JULIA" ]]; then
  JULIA="${JULIA_FALLBACK:-julia}"
fi

FORCE="${FORCE:-0}"
DRY_RUN="${DRY_RUN:-0}"
FRESH_PILOT="${FRESH_PILOT:-0}"
CONTINUE_ON_ERROR="${CONTINUE_ON_ERROR:-1}"
CONFIRM_SAMPLES="${CONFIRM_SAMPLES:-}"
CONFIRM_SAMPLE_SCHEDULE="${CONFIRM_SAMPLE_SCHEDULE:-}"
CONFIRM_ATTEMPTS="${CONFIRM_ATTEMPTS:-}"
PILOT_SAMPLES="${PILOT_SAMPLES:-}"
NLF="${NLF:-}"
SLOTS="${SLOTS:-1}"
TSP="${TSP:-tsp}"

usage() {
  cat <<'EOF'
Local umbrella profile validation via task-spooler (same stages as the LSF driver).

Usage:
  validate_umbrella_profiles_tsp.sh [options] status
  validate_umbrella_profiles_tsp.sh [options] prepare [--sizes 16,18,20,24]
  validate_umbrella_profiles_tsp.sh preflight <L>
  validate_umbrella_profiles_tsp.sh [options] submit [<L> ...]
  validate_umbrella_profiles_tsp.sh [options] repair
  validate_umbrella_profiles_tsp.sh [options] tune <L> [<L> ...]
  validate_umbrella_profiles_tsp.sh [options] tune-all
  validate_umbrella_profiles_tsp.sh reset-tuning

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
  preflight      Local Julia/CUDA check (no LSF).
  submit         Enqueue incomplete tasks with tsp.
  repair         Advance state, enqueue next-stage jobs, resubmit incomplete tasks.
  tune           prepare + preflight + submit for listed sizes.
  tune-all       Tune every unvalidated profile.
  reset-tuning   Clear runs/umbrella_tuning_tsp. Does not reset profile JSON.

Environment:
  JULIA, FORCE, DRY_RUN, FRESH_PILOT, CONFIRM_SAMPLES,
  CONFIRM_SAMPLE_SCHEDULE, CONFIRM_ATTEMPTS, PILOT_SAMPLES, NLF,
  SLOTS (tsp concurrency, default 1), TSP

Examples:
  bash scripts/validate_umbrella_profiles_tsp.sh --force \
    --confirm-sample-schedule=2000,4000,8000 tune 6
  tsp
  bash scripts/validate_umbrella_profiles_tsp.sh repair
  bash scripts/validate_umbrella_profiles_tsp.sh status
EOF
}

profile_is_validated() {
  local profile="$PROFILE_DIR/L${1}.json"
  python3 - "$profile" <<'PY'
import json, sys
raise SystemExit(0 if json.load(open(sys.argv[1])).get("validated") is True else 1)
PY
}

runtime_budget_minutes() {
  local L="$1"
  if (( L <= 8 )); then
    echo 60
  elif (( L <= 12 )); then
    echo 180
  elif (( L <= 16 )); then
    echo 240
  elif (( L <= 20 )); then
    echo 300
  else
    echo 360
  fi
}

campaign_args() {
  local L_budget="${1:-}"
  local budget="${RUNTIME_BUDGET_MINUTES:-}"
  if [[ -z "$budget" && -n "$L_budget" ]]; then
    budget="$(runtime_budget_minutes "$L_budget")"
  fi
  if [[ -z "$budget" ]]; then
    budget="360"
  fi
  local -a args=(
    --scheduler tsp
    --campaign-dir "$CAMPAIGN_DIR"
    --profile-dir "$PROFILE_DIR"
    --report-dir "$REPORT_DIR"
    --julia "$JULIA"
    --tsp "$TSP"
    --slots "$SLOTS"
    --runtime-budget-minutes "$budget"
  )
  if [[ "$FORCE" == "1" || "$FRESH_PILOT" == "1" ]]; then
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
  local L_for_budget=""
  if [[ "$subcommand" == "preflight" || "$subcommand" == "submit" ]]; then
    local arg
    for arg in "$@"; do
      if [[ "$arg" == "--L" ]]; then
        continue
      fi
      if [[ "$arg" =~ ^[0-9]+$ ]]; then
        L_for_budget="$arg"
      fi
    done
  fi
  local -a cmd=(python3 "$ROOT/scripts/umbrella_tuning_campaign.py" "$subcommand")
  local arg
  while IFS= read -r arg; do
    cmd+=("$arg")
  done < <(campaign_args "$L_for_budget")
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
    echo "=== TSP tuning L=$L ==="
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
  echo "Removing TSP tuning campaign: $CAMPAIGN_DIR"
  rm -rf "$CAMPAIGN_DIR"
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
