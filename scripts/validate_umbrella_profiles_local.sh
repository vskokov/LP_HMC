#!/usr/bin/env bash
# Local A6000 driver for umbrella profile tuning (pilot -> nlf -> confirm -> promote).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE_DIR="$ROOT/configs/umbrella_profiles"
REPORT_DIR="$ROOT/reports/umbrella_tuning"
LOG_DIR="$REPORT_DIR/logs"
RUN_ROOT="$ROOT/runs/tuning"
CAMPAIGN_DIR="$ROOT/runs/umbrella_allL_production"
ALL_SIZES=(6 8 12 16 18 20 24 32)
TUNE_SIZES=("${ALL_SIZES[@]}")

JULIA="${JULIA:-$HOME/.julia/juliaup/julia-1.12.6+0.x64.linux.gnu/bin/julia}"
if [[ ! -x "$JULIA" ]]; then
  JULIA="${JULIA_FALLBACK:-julia}"
fi

FORCE="${FORCE:-0}"
DRY_RUN="${DRY_RUN:-0}"
FRESH_PILOT="${FRESH_PILOT:-1}"
CONTINUE_ON_ERROR="${CONTINUE_ON_ERROR:-1}"
STAGE="${STAGE:-all}"
# Optional overrides (also passable after `--`; see examples below):
#   CONFIRM_SAMPLES, PILOT_SAMPLES, NLF, RUNTIME_BUDGET_MINUTES

has_tune_flag() {
  local flag="$1"
  shift
  local arg
  for arg in "$@"; do
    case "$arg" in
      "$flag"|"$flag"=*)
        return 0
        ;;
    esac
  done
  return 1
}

usage() {
  cat <<'EOF'
Local umbrella profile validation on the A6000.

Usage:
  validate_umbrella_profiles_local.sh status
  validate_umbrella_profiles_local.sh tune <L> [<L> ...] [-- <tune_umbrella_profile.py options>]
  validate_umbrella_profiles_local.sh tune-all [-- <tune_umbrella_profile.py options>]
  validate_umbrella_profiles_local.sh reset-tuning
  validate_umbrella_profiles_local.sh prepare-campaign

Commands:
  status            Show validated / pending profiles for all supported L.
  reset-tuning      Delete tuning runs/reports and reset all profiles to unvalidated.
  tune              Run tuning stages for each listed L (default: all stages).
  tune-all          Tune every profile (skips validated unless FORCE=1).
  prepare-campaign  Refresh runs/umbrella_allL_production manifests after tuning.

Environment:
  JULIA                   Julia binary (default: juliaup 1.12.6 if present)
  FORCE=1                 Re-tune even when a profile is already validated
  DRY_RUN=1               Print commands only (passed through to tune_umbrella_profile.py)
  FRESH_PILOT=1           Delete stale tune_L{L}_pilot runs before pilot (default: on)
  CONTINUE_ON_ERROR=1     Keep going after a failed L in tune-all (default: on)
  STAGE=all               Stage(s) to run: pilot, nlf, confirm, promote, or all
  CONFIRM_SAMPLES=3000    Confirmation samples per window (first attempt)
  CONFIRM_SAMPLE_SCHEDULE=1000,3000,6000
  CONFIRM_ATTEMPTS=3      Escalating confirm attempts if canonical gate fails
  PILOT_SAMPLES=200       Pilot collection samples per window
  NLF=26                  Override selected n_lf for confirm/promote
  RUNTIME_BUDGET_MINUTES  Override per-task runtime budget (default: size-dependent)

Examples:
  bash scripts/validate_umbrella_profiles_local.sh status
  bash scripts/validate_umbrella_profiles_local.sh tune 12
  bash scripts/validate_umbrella_profiles_local.sh tune 12 -- --stage=confirm --n-lf=26 --confirm-samples=3000
  STAGE=confirm NLF=26 CONFIRM_SAMPLES=3000 bash scripts/validate_umbrella_profiles_local.sh tune 12
  bash scripts/validate_umbrella_profiles_local.sh tune 12 -- --stage=promote --n-lf=26
  bash scripts/validate_umbrella_profiles_local.sh tune-all
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

cmd_status() {
  printf "%-4s %-10s %s\n" "L" "validated" "profile"
  for L in "${ALL_SIZES[@]}"; do
    local profile="$PROFILE_DIR/L${L}.json"
    if [[ ! -f "$profile" ]]; then
      printf "%-4s %-10s %s\n" "$L" "missing" "$profile"
      continue
    fi
    if profile_is_validated "$L"; then
      printf "%-4s %-10s %s\n" "$L" "yes" "$profile"
    else
      printf "%-4s %-10s %s\n" "$L" "no" "$profile"
    fi
  done
}

tune_one() {
  local L="$1"
  shift
  local -a extra=("$@")
  local profile="$PROFILE_DIR/L${L}.json"
  if [[ ! -f "$profile" ]]; then
    echo "missing profile for L=$L: $profile" >&2
    return 1
  fi
  if [[ "$FORCE" != "1" ]] && profile_is_validated "$L"; then
    echo "=== L=$L already validated; skipping (set FORCE=1 to re-tune) ==="
    return 0
  fi

  local budget="${RUNTIME_BUDGET_MINUTES:-$(runtime_budget_minutes "$L")}"
  local stage="$STAGE"
  has_tune_flag --stage "${extra[@]}" && stage="(custom)"

  local log_file
  mkdir -p "$LOG_DIR"
  log_file="$LOG_DIR/tune_L${L}_$(date +%Y%m%d_%H%M%S).log"

  echo "=== tuning L=$L (stage=${stage} budget=${budget}m fresh_pilot=${FRESH_PILOT}) ==="
  echo "log: $log_file"

  local -a cmd=(
    python3 "$ROOT/scripts/tune_umbrella_profile.py"
    --L="$L"
    --scheduler=local
    --slots=1
    --julia="$JULIA"
    --run-root="$RUN_ROOT"
    --report-dir="$REPORT_DIR"
    --runtime-budget-minutes="$budget"
    --pilot-max-thermalization-sweeps=0
    --pilot-continuations=12
  )
  if ! has_tune_flag --stage "${extra[@]}"; then
    cmd+=(--stage="$STAGE")
  fi
  if ! has_tune_flag --confirm-samples "${extra[@]}" && [[ -n "${CONFIRM_SAMPLES:-}" ]]; then
    cmd+=(--confirm-samples="$CONFIRM_SAMPLES")
  fi
  if ! has_tune_flag --confirm-sample-schedule "${extra[@]}" && [[ -n "${CONFIRM_SAMPLE_SCHEDULE:-}" ]]; then
    cmd+=(--confirm-sample-schedule="$CONFIRM_SAMPLE_SCHEDULE")
  fi
  if ! has_tune_flag --confirm-attempts "${extra[@]}" && [[ -n "${CONFIRM_ATTEMPTS:-}" ]]; then
    cmd+=(--confirm-attempts="$CONFIRM_ATTEMPTS")
  fi
  if ! has_tune_flag --pilot-samples "${extra[@]}" && [[ -n "${PILOT_SAMPLES:-}" ]]; then
    cmd+=(--pilot-samples="$PILOT_SAMPLES")
  fi
  if ! has_tune_flag --n-lf "${extra[@]}" && [[ -n "${NLF:-}" ]]; then
    cmd+=(--n-lf="$NLF")
  fi
  if [[ "$FRESH_PILOT" == "1" ]]; then
    cmd+=(--fresh-pilot)
  fi
  if [[ "$DRY_RUN" == "1" ]]; then
    cmd+=(--dry-run)
  fi
  if ((${#extra[@]})); then
    cmd+=("${extra[@]}")
  fi

  if [[ "$DRY_RUN" == "1" ]]; then
    "${cmd[@]}"
  else
    if ! "${cmd[@]}" 2>&1 | tee "$log_file"; then
      echo "=== L=$L tuning failed; see $log_file ===" >&2
      return 1
    fi
  fi

  if profile_is_validated "$L"; then
    echo "=== L=$L validated ==="
    return 0
  fi
  echo "=== L=$L finished but profile is still not validated ===" >&2
  return 1
}

split_tune_args() {
  TUNE_SIZES_ARGS=()
  TUNE_EXTRA_ARGS=()
  local parsing_extras=0
  local arg
  for arg in "$@"; do
    if [[ "$arg" == "--" ]]; then
      parsing_extras=1
      continue
    fi
    if (( parsing_extras )); then
      TUNE_EXTRA_ARGS+=("$arg")
    else
      TUNE_SIZES_ARGS+=("$arg")
    fi
  done
}

cmd_tune() {
  split_tune_args "$@"
  if ((${#TUNE_SIZES_ARGS[@]} == 0)); then
    echo "tune requires at least one L value" >&2
    usage >&2
    return 2
  fi
  local rc=0
  local L
  for L in "${TUNE_SIZES_ARGS[@]}"; do
    if ! tune_one "$L" "${TUNE_EXTRA_ARGS[@]}"; then
      rc=1
      if [[ "$CONTINUE_ON_ERROR" != "1" ]]; then
        return "$rc"
      fi
    fi
  done
  return "$rc"
}

cmd_tune_all() {
  split_tune_args "$@"
  local -a pending=()
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
  cmd_tune "${pending[@]}" -- "${TUNE_EXTRA_ARGS[@]}"
}

cmd_prepare_campaign() {
  python3 "$ROOT/scripts/umbrella_campaign.py" prepare \
    --sizes "6,8,12,16,18,20,24,32" \
    --campaign-dir "$CAMPAIGN_DIR"
}

cmd_reset_tuning() {
  echo "Removing tuning runs: $RUN_ROOT"
  rm -rf "$RUN_ROOT"
  echo "Removing tuning reports: $REPORT_DIR"
  rm -rf "$REPORT_DIR"
  mkdir -p "$LOG_DIR"
  for artifact in \
    "$ROOT/reports/umbrella_binder_L6.csv" \
    "$ROOT"/reports/umbrella_L6_*.json; do
    if [[ -e "$artifact" ]]; then
      echo "Removing $artifact"
      rm -f "$artifact"
    fi
  done
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

main() {
  local cmd="${1:-status}"
  shift || true
  case "$cmd" in
    -h|--help|help)
      usage
      ;;
    status)
      cmd_status
      ;;
    tune)
      cmd_tune "$@"
      ;;
    tune-all)
      cmd_tune_all
      ;;
    prepare-campaign)
      cmd_prepare_campaign
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
