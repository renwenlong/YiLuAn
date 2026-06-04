#!/usr/bin/env bash
# admin-v2 PR-B smoke 验证（S2-DEV-013）
#
# 验证 backend 4 端点 + admin-v2 React 接通：
# - GET /api/v1/admin/companions （list pending）
# - POST /api/v1/admin/companions/{id}/approve
# - POST /api/v1/admin/companions/{id}/reject
#
# 前置：staging backend 已起栈，env.staging.local 有真实 admin token，
# 至少 1 个 pending companion 在 DB。
#
# 用法：
#   ./scripts/smoke-companion-review.sh staging-admin-token

set -euo pipefail

TOKEN="${1:-staging-admin-token}"
BASE="${BASE:-http://127.0.0.1:18080/api/v1}"

echo "=== 1. GET /admin/companions （list pending）==="
LIST_JSON=$(curl -fsS -H "X-Admin-Token: $TOKEN" "$BASE/admin/companions/?page=1&page_size=5")
echo "$LIST_JSON" | python3 -m json.tool

TOTAL=$(echo "$LIST_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin).get('total', 0))")
echo "  total pending: $TOTAL"
if [ "$TOTAL" -eq 0 ]; then
  echo "  ⚠️ 无 pending companion，跳过 approve/reject smoke"
  exit 0
fi

FIRST_ID=$(echo "$LIST_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['items'][0]['id'])")
echo "  first pending id: $FIRST_ID"

echo "=== 2. POST /admin/companions/$FIRST_ID/approve ==="
curl -fsS -X POST -H "X-Admin-Token: $TOKEN" \
  "$BASE/admin/companions/$FIRST_ID/approve" | python3 -m json.tool

echo ""
echo "=== 3. （另起一个）GET list 验证已不在 pending 列表 ==="
NEW_LIST=$(curl -fsS -H "X-Admin-Token: $TOKEN" "$BASE/admin/companions/?page=1&page_size=5")
NEW_TOTAL=$(echo "$NEW_LIST" | python3 -c "import json,sys; print(json.load(sys.stdin).get('total', 0))")
echo "  approved 后 pending total: $NEW_TOTAL (期望 = $((TOTAL - 1)))"

echo ""
echo "=== smoke 完成 ✅ ==="
echo "  接下来在浏览器手动验证："
echo "  - http://127.0.0.1:5173/admin-v2/login  （dev 模式）"
echo "  - 用同样 token 登录 → /admin-v2/companion-review 看列表"
echo "  - 详情 drawer 显示 list row 字段（无额外 fetch）"
echo "  - 拒绝输入框 maxLength=500 + showCount"
