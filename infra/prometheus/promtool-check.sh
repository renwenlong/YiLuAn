#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

exec docker run --rm \
  -v "${ROOT_DIR}:/work:ro" \
  -w /work \
  --entrypoint /bin/promtool \
  prom/prometheus:v2.51.0 \
  check rules infra/prometheus/rules/precheck_abac.yml
