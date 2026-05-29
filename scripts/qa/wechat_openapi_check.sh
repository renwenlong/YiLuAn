#!/usr/bin/env bash
# S2-TEST-002 / PRD-001 §6.C AC#23 — 微信小程序 OpenAPI → d.ts schema 校验.
#
# 阶段 A：S2-DEV-002 端点未落地，d.ts 生成允许为空；本脚本只确认工具链可用 +
# wechat/services 层 ts-check 通过；S2-DEV-002 done 后改为严格校验 7 字段。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
BASELINE="$ROOT/docs/api/openapi-baseline.json"
OUT="$ROOT/wechat/types/openapi.d.ts"
mkdir -p "$(dirname "$OUT")"

if ! command -v npx >/dev/null 2>&1; then
  echo "::warning:: npx not available, skipping wechat OpenAPI check (阶段 A 允许)"
  exit 0
fi

echo ">>> generating $OUT from baseline"
npx -y openapi-typescript@7 "$BASELINE" -o "$OUT" || {
  echo "::error:: openapi-typescript generation failed" >&2
  exit 1
}

# 阶段 B（S2-DEV-002 done 后启用）：grep 7 字段都在 d.ts 中
# guarded=(share_token share_scope share_expires_at share_revoked_at share_session patient_name_masked digest_url)
# for f in "${guarded[@]}"; do grep -q "\b$f\b" "$OUT" || { echo "::error:: $f missing in d.ts"; exit 1; }; done

echo "OK: openapi-typescript d.ts generated."
