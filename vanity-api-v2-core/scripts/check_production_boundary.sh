#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

forbidden='43\.207\.236\.210:1803[01]|/opt/vanity-address-api|RUNPOD_ENDPOINT_ID|RUNPOD_API_KEY|VAST_API_KEY'

if rg -n "$forbidden" "$ROOT" \
  --glob '!README.md' \
  --glob '!check_production_boundary.sh'; then
  echo "production boundary reference found" >&2
  exit 1
fi

echo "production boundary check passed"
