#!/usr/bin/env bash
# S2-TEST-002 / PRD-001 §6.C AC#22 — OpenAPI cross-end contract diff gate.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
cd "$ROOT/backend"
PY="${PYTHON:-python3}"
if [ -x "$ROOT/backend/.venv/bin/python" ]; then
  PY="$ROOT/backend/.venv/bin/python"
fi
exec "$PY" "$ROOT/scripts/qa/openapi_contract_diff.py" "$@"
