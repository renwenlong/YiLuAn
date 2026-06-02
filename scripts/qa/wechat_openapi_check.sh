#!/usr/bin/env bash
# S2-INT-002 / PRD-001 §6.C AC#23 — 微信小程序 OpenAPI → d.ts schema 严格校验（阶段 B）.
#
# 阶段 B（S2-DEV-002 share 端点已 done）：严格校验 9 字段都在生成的 d.ts 中。
# 源文件用真 OpenAPI 文档 docs/api/openapi.json（不是签名指纹 baseline），
# 且先重导保新鲜，避免 json 滞后于 backend schema 导致漏守。
# 字段集对齐 S2-INT-002 权威表（魈拍板）：digest_url 是幽灵字段，已剔除。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
OPENAPI="$ROOT/docs/api/openapi.json"
OUT="$ROOT/wechat/types/openapi.d.ts"
mkdir -p "$(dirname "$OUT")"

if ! command -v npx >/dev/null 2>&1; then
  echo "::error:: npx not available, cannot run wechat OpenAPI check (阶段 B 必须)" >&2
  exit 1
fi

# 重导 openapi.json，保证它跟 backend live schema 一致（防过时漏守 share 端点）。
PYBIN="$ROOT/backend/.venv/bin/python"
[ -x "$PYBIN" ] || PYBIN="python3"
echo ">>> regenerating $OPENAPI from backend live schema"
( cd "$ROOT/backend" && "$PYBIN" scripts/dump_openapi.py ) || {
  echo "::error:: dump_openapi.py failed" >&2
  exit 1
}

echo ">>> generating $OUT from $OPENAPI"
npx -y openapi-typescript@7 "$OPENAPI" -o "$OUT" || {
  echo "::error:: openapi-typescript generation failed" >&2
  exit 1
}

# 阶段 B 严格校验：S2-INT-002 权威表 9 字段必须都出现在 d.ts 中（digest_url 已剔除）。
guarded=(
  share_token
  share_url
  share_scope
  share_expires_at
  share_revoked_at
  share_active_count
  share_session
  share_session_expires_at
  patient_name_masked
)
missing=()
for f in "${guarded[@]}"; do
  grep -q "\b$f\b" "$OUT" || missing+=("$f")
done
if [ "${#missing[@]}" -gt 0 ]; then
  echo "::error:: 微信 d.ts 缺跨端契约字段（漂移/未导出）：${missing[*]}" >&2
  echo "处理：三端任一漂移→直接打回 develop（ADR-0039 §4.4）；先核 backend schema 与 ADR。" >&2
  exit 1
fi

echo "OK: wechat d.ts 覆盖 S2-INT-002 权威表 ${#guarded[@]} 字段。"
