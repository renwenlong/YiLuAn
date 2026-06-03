#!/usr/bin/env bash
# S2-INT-005 admin-h5 联调冒烟脚本
# 用法：BASE=http://127.0.0.1:18080 TOKEN=staging-admin-token bash scripts/qa/s2_int_005_admin_smoke.sh
# 退出码：0 全 PASS / 非 0 任一 FAIL
set -uo pipefail
BASE="${BASE:-http://127.0.0.1:18080}"
TOKEN="${TOKEN:-staging-admin-token}"
PASS=0; FAIL=0
say() { printf '%-60s %s\n' "$1" "$2"; }
check() {  # check <name> <expected_http> <curl args...>
  local name="$1" want="$2"; shift 2
  local got
  got=$(curl -sL -o /dev/null -w '%{http_code}' "$@" || echo "ERR")
  if [[ "$got" == "$want" ]]; then say "✅ $name" "HTTP $got"; PASS=$((PASS+1));
  else say "❌ $name" "want=$want got=$got"; FAIL=$((FAIL+1)); fi
}

echo "==> §3-1 鉴权基线"
check "空 token → 401"           401 "$BASE/api/v1/admin/orders"
check "错 token → 401"           401 -H "X-Admin-Token: wrong-not-a-token" "$BASE/api/v1/admin/orders"
check "默认 dev-admin-token → 401" 401 -H "X-Admin-Token: dev-admin-token" "$BASE/api/v1/admin/orders"
check "合法 token → 200"          200 -H "X-Admin-Token: $TOKEN" "$BASE/api/v1/admin/orders"

echo "==> §3-2 订单查询"
check "订单列表 → 200"            200 -H "X-Admin-Token: $TOKEN" "$BASE/api/v1/admin/orders?limit=5"
check "不存在订单 → 404"          404 -H "X-Admin-Token: $TOKEN" "$BASE/api/v1/admin/orders/00000000-0000-0000-0000-000000000001"
check "非 UUID → 422"             422 -H "X-Admin-Token: $TOKEN" "$BASE/api/v1/admin/orders/not-a-uuid"

echo "==> §3-3 用户查询"
check "用户列表 → 200"            200 -H "X-Admin-Token: $TOKEN" "$BASE/api/v1/admin/users?limit=5"
# 字段脱敏校验：phone 必须 ******
phones=$(curl -sL -H "X-Admin-Token: $TOKEN" "$BASE/api/v1/admin/users?limit=10" \
  | python3 -c 'import json,sys;d=json.load(sys.stdin);print("|".join(str(u.get("phone")) for u in d["items"] if u.get("phone")))')
if [[ -z "$phones" ]]; then
  say "✅ 用户 phone 全空（无可校验）" "skip"; PASS=$((PASS+1))
elif [[ "$phones" =~ \*\*\*\*\*\* ]]; then
  say "✅ 用户 phone 默认脱敏（含 ******）" "OK"; PASS=$((PASS+1))
else
  say "❌ 用户 phone 未脱敏（含原文）" "$phones"; FAIL=$((FAIL+1))
fi

echo "==> §3-4 审计日志"
check "审计列表 → 200"            200 -H "X-Admin-Token: $TOKEN" "$BASE/api/v1/admin/audit-logs?limit=5"
# 检查 view_orders_list / view_users_list 留痕
actions=$(curl -sL -H "X-Admin-Token: $TOKEN" "$BASE/api/v1/admin/audit-logs?limit=20" \
  | python3 -c 'import json,sys;d=json.load(sys.stdin);print(",".join(sorted({i.get("action","") for i in d["items"]})))')
for need in view_orders_list view_users_list; do
  if [[ "$actions" == *"$need"* ]]; then
    say "✅ 审计含 $need" "OK"; PASS=$((PASS+1))
  else
    say "❌ 审计缺 $need" "actions=$actions"; FAIL=$((FAIL+1))
  fi
done

echo "==> §3-1+ 越权/边界负向"
check "GET /admin/dashboard 合法 → 200" 200 -H "X-Admin-Token: $TOKEN" "$BASE/api/v1/admin/dashboard/summary"
check "GET /admin/dashboard 空 token → 401" 401 "$BASE/api/v1/admin/dashboard/summary"
# 错 method
check "PUT /admin/orders 错 method → 405" 405 -X PUT -H "X-Admin-Token: $TOKEN" "$BASE/api/v1/admin/orders"

echo
echo "==============================="
echo " PASS=$PASS  FAIL=$FAIL"
echo "==============================="
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
