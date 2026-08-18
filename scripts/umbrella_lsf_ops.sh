#!/usr/bin/env bash
# Operational helpers for restartable LSF umbrella production.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CAMPAIGN="${CAMPAIGN:-$ROOT/runs/umbrella_allL_production}"
INDEX="$CAMPAIGN/campaign.json"

case "${1:-status}" in
  prepare)
    python3 "$ROOT/scripts/umbrella_campaign.py" prepare \
      --campaign-dir "$CAMPAIGN" --sizes "6,8,12,16,18,20,24,32"
    ;;
  preflight)
    shift
    python3 "$ROOT/scripts/umbrella_campaign.py" preflight \
      --manifest "${1:-$CAMPAIGN/L24/manifest.csv}"
    ;;
  status)
    python3 "$ROOT/scripts/umbrella_campaign.py" status --campaign-index "$INDEX"
    ;;
  repair)
    python3 "$ROOT/scripts/umbrella_campaign.py" repair --campaign-index "$INDEX"
    ;;
  submit)
    python3 "$ROOT/scripts/umbrella_campaign.py" prepare \
      --campaign-dir "$CAMPAIGN" --sizes "6,8,12,16,18,20,24,32" --submit
    ;;
  *)
    echo "usage: $0 {prepare|preflight|status|repair|submit} [manifest]" >&2
    exit 2
    ;;
esac
