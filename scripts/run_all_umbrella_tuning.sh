#!/usr/bin/env bash
# Back-compat wrapper: batch local tuning + campaign prepare.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
bash "$ROOT/scripts/validate_umbrella_profiles_local.sh" tune-all
bash "$ROOT/scripts/validate_umbrella_profiles_local.sh" prepare-campaign
