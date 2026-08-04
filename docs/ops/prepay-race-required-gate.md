# Prepay 并发 race — CI required gate 收口

> Task: `S3-PAY-PREPAY-RACE-CI-REQUIRED-GATE` (P1)
> 关联: `backend/tests/smoke/test_pg_prepay_race.py` · `backend/tests/test_payment_concurrent.py`

## 背景（隐性资损坑）

`OrderService.pay_order` 通过 `_get_order_for_update_or_404` →
`order_repo.get_by_id_for_update`（`.with_for_update()`，见
`backend/app/repositories/order.py`）用 `SELECT ... FOR UPDATE` 行锁串行化并发
`POST /orders/{id}/pay`。**该锁在 SQLite 单测里是 no-op**，主套（`Backend
Tests`，required）从未真正验证并发重复支付串行化。

真实覆盖在 `pg_prepay_race` smoke（`-m smoke`），跑在 `ci-smoke.yml` 的
`smoke-pg` job（check 名 **`Smoke tests (real Postgres + alembic)`**）。契约：
5 并发 pay → 恰 1×2xx winner + 4×400 rejects，0×5xx，无 IntegrityError/UNIQUE
泄漏到客户端。

**但该 check 不在 branch protection required 列表**（实测 required=4：`Backend
Tests` / `Docker Build Verification` / `WeChat Mini Program Tests` / `Build &
Test (iOS Simulator)`）——即 smoke 挂了也不阻塞合并。本 gate 让并发锁契约进
required。

## 已完成（developer 侧，本 PR）

- ✅ AC-2/AC-4：清除两处误导性 `TODO: Fix the race condition before production
  deployment`。race 已修复（SELECT FOR UPDATE 到位），改为指向 smoke 覆盖的说明
  + SQLite `with_for_update` no-op 局限标注 + 交叉引用。
- ✅ AC-3：`test_pg_prepay_race` 在真 PG 下 **PASS**（非 xfail/skip），本地
  `pytest -m smoke` 留证（1 passed）。
- ✅ AC-5：`ci-smoke.yml` 触发无 path-filter（`on: push/pull_request →
  branches:[main]`，无 `paths:`/`paths-ignore:`），backend 变更 PR 必跑
  `smoke-pg`，不被误跳。

## 待帝君/admin apply（AC-1，需 admin 权限）

把 `smoke-pg` check 加进 main branch protection 的
`required_status_checks.contexts`。**精确 check 名**：

```
Smoke tests (real Postgres + alembic)
```

### 改法（gh CLI，admin 身份）

```bash
# 1. 读当前 protection（确认 4 个 required）
gh api repos/renwenlong/YiLuAn/branches/main/protection \
  --jq '.required_status_checks.contexts'

# 2. 追加 smoke check（保留原 4 个，共 5 个）
gh api -X PATCH repos/renwenlong/YiLuAn/branches/main/protection/required_status_checks \
  -f 'contexts[]=Backend Tests' \
  -f 'contexts[]=Docker Build Verification' \
  -f 'contexts[]=WeChat Mini Program Tests' \
  -f 'contexts[]=Build & Test (iOS Simulator)' \
  -f 'contexts[]=Smoke tests (real Postgres + alembic)'

# 3. 验证已进 required（应打印 5 个，含 smoke）
gh api repos/renwenlong/YiLuAn/branches/main/protection \
  --jq '.required_status_checks.contexts'
```

> 或在 GitHub Web UI：Settings → Branches → `main` → Edit → Require status
> checks → 搜 `Smoke tests (real Postgres + alembic)` 勾选 → Save。

apply 后 required=5，prepay 并发锁契约正式成为合并前置闸。
