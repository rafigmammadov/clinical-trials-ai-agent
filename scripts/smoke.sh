#!/usr/bin/env bash
set -euo pipefail
BASE="${1:-http://127.0.0.1:8000}"
curl --fail-with-body --silent --show-error "$BASE/health" | python -m json.tool
curl --fail-with-body --silent --show-error \
  -H 'Content-Type: application/json' \
  -d '{"query":"How many trials for melanoma started each year since 2023?","condition":"melanoma","start_year":2023,"max_studies":50}' \
  "$BASE/api/v1/analyze" | python -m json.tool
