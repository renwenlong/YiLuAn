# ADR-0055 — User Role Model Converge: 弃 enum 收敛到 multi-role string (has_role 唯一 SoT)

> 状态: **Draft** · 作者: 魈 · 日期: 2026-06-12
> 关联: PR #232 (ABAC-4LAYER-PART1) 备注 #2 / `docs/qa/user-role-model-history.md` 调研报告
> 触发: PR #232 引入 `get_current_companion` dual check (`user.role == UserRole.companion or user.has_role(UserRole.companion)`), 收敛 follow-up
> Owner: 帝君 Accept 后 hutao implement

---

## 1. 背景

`User` 模型当前有 dual role 字段:
- `role: Mapped[UserRole | None]` — Enum 单 role (2026-03-29 引入 by `b281265`)
- `roles: Mapped[str | None]` — comma-separated multi-role string (2026-04-03 引入 by `c749c64`)

**migration `a1b2c3d4e5f6_add_roles_field.py` 一次性 sync** 历史数据 (`UPDATE users SET roles = role`), 但**没做 phase 2**:
- 没 drop `role` enum 字段
- auth.py 创建新用户时不设 role/roles (default NULL)
- `add_role` 只动 `roles`, 不动 `role` enum

**latent bug 现状** (`docs/qa/user-role-model-history.md` §3 详):
- 11 处 `user.role == UserRole.X` 查询 (order/cancel + order/query)
- 新用户 role=NULL → 这 11 处查询永远 False → 走死代码路径
- 不出 P0 bug 仅因 dependencies.py `get_current_patient/companion` 用 dual check 覆盖

PR #232 ABAC-4LAYER-PART1 review 时 (我 architect 6 项备注 #2) 立此 follow-up: 收敛 role-model 到单一表达, 移除 dual check.

---

## 2. 选型对比

### 2.1 候选

| 方案 | 单一 SoT | 复杂度 | 业务支持 multi-role | 数据迁移风险 |
|---|---|---|---|---|
| A. 弃 enum (multi-role 唯一) | ✅ has_role | 11 处 change | ✅ | 低 (不 drop 字段, 兼容) |
| B. 弃 multi-role (enum 唯一) | ✅ user.role | 5 处 change | 🔴 不支持 1 user 多 role | 高 (drop roles 字段) |
| C. 共存 + sync 强制 | ❌ 双字段 | 中 (加 sync) | ✅ | 中 (sync 漏一处=不一致) |

### 2.2 Owner 拍板: **A. 弃 enum (multi-role 唯一, has_role 作 SoT)**

理据 (4 点):
1. **业务需要 multi-role**: 家属帮患者下单时同人需 `patient + companion` 双角色, enum 单字段不支持
2. **enum 字段对新用户永远 NULL**: 11 处 query 是 latent 死路径, 不出 bug 仅因 dependencies.py dual check 兜底
3. **has_role 已是新业务默认入口**: companion_profile 5 处 + user 服务 1 处都用 has_role, 收敛方向符合演进
4. **enum 字段保留不 drop**: 向后兼容历史数据, alembic 不强制 schema 大改, 仅代码层不再读

否决 B: 业务不支持单 role.
否决 C: 不解决根本二意性, 双字段 sync 维护成本 + 漏 sync 风险.

---

## 3. 实施分阶段

### 3.1 P0: code 收敛 (hutao impl, ~45min)

#### 3.1.1 改 11 处 `user.role == UserRole.X` → `user.has_role(UserRole.X)`

文件清单:
```
backend/app/services/order/query.py:19, 22, 71
backend/app/services/order/cancel.py:19, 23, 76, 80
backend/app/dependencies.py:94, 122 (dual check 一半, 改后单一)
```

#### 3.1.2 改 dependencies.py dual check → 单 has_role

**before** (line 90-100):
```python
async def get_current_patient(...) -> User:
    if current_user.role == UserRole.patient:
        return current_user
    if current_user.has_role(UserRole.patient):
        return current_user
    raise HTTPException(status_code=403, detail="Patient role required")
```

**after**:
```python
async def get_current_patient(...) -> User:
    if current_user.has_role(UserRole.patient):
        return current_user
    raise HTTPException(status_code=403, detail="Patient role required")
```

同改 `get_current_companion`. docstring 删 "legacy single-role enum" / "newer multi-role string" 字面 (二者已统一).

#### 3.1.3 保留 enum 字段, 加 deprecation comment

`backend/app/models/user.py`:

```python
class User(Base):
    # ...
    # DEPRECATED (ADR-0055): use has_role() / add_role() instead. Kept
    # for backward compat with historical data. Do not read in new code.
    role: Mapped[UserRole | None] = mapped_column(Enum(UserRole), nullable=True)
    roles: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # ...
```

#### 3.1.4 ORM init event listener — 自动 mirror role→roles (反案 #18 amend @ 2026-06-15 14:00Z)

**Edge case (反案 #18 触发)**: PR #317 phase 2 IMPL 首次 push 后 CI 抓 2 ABAC test fail (`tests/test_coverage_boost_w18.py::test_get_order_patient_not_owner_forbidden` + `test_get_order_companion_other_after_accept_forbidden`):

```python
# 17 处 test fixture (grep verified):
owner = User(phone="...", role=UserRole.patient, is_active=True)
# 只设 role enum, roles 字段 NULL

# query.py:19 改后:
if user.has_role(UserRole.patient):  # 读 roles → NULL → False → skip
    raise ForbiddenException(...)    # 不 raise → ABAC 失效
```

**不只 test fail** — production legacy path 同款洞: `auth.py` token issue / admin 创 user / 任何 ORM 层 `User(role=X)` 不带 `roles` 的 path. backfill migration `<rev>_backfill_roles_from_role.py` 只 fix 历史 row (alembic upgrade 时), **不 fix ORM 层新建 user**.

**修法**: SQLAlchemy `init` event listener, 自动 mirror enum role → roles string:

```python
# backend/app/models/user.py
from sqlalchemy import event

@event.listens_for(User, 'init')
def _mirror_role_to_roles_on_init(target, args, kwargs):
    """ADR-0055 §3.1.4: ORM 创建 user 时自动 mirror enum role 到 roles string.
    保证 has_role() 在 fixture + production legacy path 都一致.
    
    与 backfill migration §3.2 互补:
    - 历史 row → migration (alembic upgrade 一次性)
    - 新 row → event listener (每次 ORM 创建自动 mirror)
    
    幂等: 显式传 roles 时不覆盖 (caller intent 优先)."""
    if 'role' in kwargs and kwargs['role'] is not None and 'roles' not in kwargs:
        kwargs['roles'] = kwargs['role'].value
```

**Test 增加** (反案 #18 SOP — asset-presence sentinel 模式语义版):

```python
# backend/tests/models/test_user_role_model_single_sot.py

def test_orm_init_event_listener_mirrors_role_to_roles():
    """反案 #18 regression: ORM 创建 user 仅传 role enum, roles 自动 mirror."""
    u = User(phone="13800000001", role=UserRole.patient, is_active=True)
    assert u.roles == "patient"
    assert u.has_role(UserRole.patient)

def test_orm_init_event_listener_respects_explicit_roles():
    """显式 roles 不被 event listener 覆盖."""
    u = User(phone="...", role=UserRole.patient, roles="patient,companion")
    assert u.roles == "patient,companion"  # caller intent 优先
```

**反案 #18 教训** (architect 责任):

1. **r1 APPROVE 不是越快越好** — 11:10Z r1 APPROVE 时 CI Backend Tests 还在跑, 11:15Z CI 跑完抓 fail, 我兜底失败
2. **ADR-0055 spec 自身漏 §3.1.4** — phase 2 IMPL 按 spec 没错, 我 review 应 mental simulate fixture 状态
3. **SOP 升级**: r1 APPROVE 必须在 CI 4 required check 全绿之后 (反案 #16 v2)

### 3.2 P1: backfill migration (hutao, ~10min)

`backend/alembic/versions/<auto>_backfill_roles_from_role.py`:

```python
def upgrade() -> None:
    # idempotent backfill: 历史用户如有 role enum 但 roles NULL, sync
    op.execute(
        "UPDATE users SET roles = role WHERE role IS NOT NULL AND roles IS NULL"
    )

def downgrade() -> None:
    pass  # no-op, backfill 不可回滚 (roles 已 sync, 还原会丢)
```

注意:
- 不 drop `role` 字段 (cool-down 3 月后再独立 ADR 评估)
- migration idempotent (重复 run 不破)

### 3.3 P2: 测试 (hutao, ~30min)

#### 3.3.1 现有测试 green

`pytest backend/tests/services/auth backend/tests/test_dependencies* backend/tests/services/order` 全过.

#### 3.3.2 regression test

`backend/tests/models/test_user_role_model_single_sot.py`:

```python
"""Regression: ADR-0055 user role model converge.

verify:
1. add_role(X) 调用后 has_role(X) is True
2. 即使 user.role enum 字段 NULL, has_role 仍正确
3. dependencies.get_current_patient/companion 单 has_role 不 dual check
"""
import pytest
from app.models.user import User, UserRole

class TestUserRoleSingleSoT:
    def test_add_role_updates_roles_field_only(self, db_session):
        user = User(phone="+8613800000001")
        db_session.add(user)
        db_session.commit()

        assert user.role is None
        assert user.roles is None
        assert user.has_role(UserRole.patient) is False

        user.add_role(UserRole.patient)
        db_session.commit()

        assert user.role is None  # ADR-0055: enum 字段不动
        assert user.roles == "patient"
        assert user.has_role(UserRole.patient) is True

    def test_dual_role_supported(self, db_session):
        user = User(phone="+8613800000002")
        user.add_role(UserRole.patient)
        user.add_role(UserRole.companion)
        db_session.add(user)
        db_session.commit()

        assert user.has_role(UserRole.patient) is True
        assert user.has_role(UserRole.companion) is True
        assert set(user.get_roles()) == {"patient", "companion"}

    @pytest.mark.parametrize("role_enum_val, roles_str", [
        (UserRole.patient, None),  # legacy: enum set but roles NULL
        (None, "patient"),  # new: enum NULL but roles set
        (UserRole.companion, "patient,companion"),  # mixed: both set
    ])
    def test_get_current_patient_only_via_has_role(
        self, db_session, role_enum_val, roles_str
    ):
        from app.dependencies import get_current_patient
        user = User(phone="+8613800000003", role=role_enum_val, roles=roles_str)
        db_session.add(user)
        db_session.commit()

        # legacy case (role=patient, roles=NULL):
        # ADR-0055 收敛后 has_role 不查 enum → False → get_current_patient raise
        # 这是 expected behavior change (隔离 enum 死字段)
        # backfill migration 解决历史数据
        if not user.has_role(UserRole.patient):
            with pytest.raises(HTTPException) as exc:
                await get_current_patient(current_user=user)
            assert exc.value.status_code == 403
        else:
            result = await get_current_patient(current_user=user)
            assert result is user
```

### 3.4 P3: ABAC PART1 兼容验证 (hutao + tester, ~15min)

PR #232 ABAC-4LAYER-PART1 已 merge, 不能破其行为. verify:
- 已通过 dependencies.py 的 `current_companion` 用 has_role 通过
- 不引入新 dual check 死路径
- PR #232 加的所有 fixture / test 全过

---

## 4. 实施 Acceptance (魈 review 阶段硬核 4 项)

| AC | 内容 | 验证 |
|---|---|---|
| AC-1 | 11 处 `user.role == UserRole.X` 全改 `user.has_role(UserRole.X)` (含 order service + dependencies dual 一半) | `grep -rn "role == UserRole" backend/app/ \| grep -v __pycache__` 返 0 hit |
| AC-2 | dependencies.py `get_current_patient/companion` 移除 dual check, 仅用 has_role | docstring 删 "legacy single-role enum" / "newer multi-role string" 字面 |
| AC-3 | regression test `test_user_role_model_single_sot.py` 通过 | pytest 3 case 全 green |
| AC-4 | 现有 auth + dependencies + order test 全 green; ABAC PART1 fixture 无回归 | full backend test suite green |

---

## 5. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 历史用户 roles=NULL (auth 一次性 sync 之后没 backfill 的 user) → has_role 永 False → 403 | P1 backfill migration idempotent `UPDATE users SET roles = role WHERE role IS NOT NULL AND roles IS NULL` |
| has_role 性能 (string split) vs enum 直查 | 每 request 调用 ≤10 次, 性能可接受; 后续如热点可在 User 实例 cache |
| 11 处 change 漏一处 → enum 查询继续走死 | PR review grep 0 hit + AC-1 自动化 verify |
| enum 字段保留 = 死列 schema noise | 3 月 cool-down 后独立 ADR 评估 drop column |

---

## 6. 相关 ADR

- ADR-0049 (User Feedback Domain): 用 has_role 判 companion → 与本 ADR 一致
- ADR-0050 (Worktree Owner Metadata): 不相关
- PR #232 (ABAC-4LAYER-PART1) 备注 #2: 本 ADR 触发源

---

## 7. 实施授权

- 架构师 (魈) Draft → 帝君 Accept → 凝光 (PM) sanity check (业务不变) → hutao implement
- 配套 task: `S3-OPS-USER-ROLE-MODEL-CONVERGE` (P2, develop)
- assignee swap: 架构师 → developer (本 ADR merge 后)

---

## 8. 变更记录

- **r1 (2026-06-12)**: Draft 初版, 调研报告 `docs/qa/user-role-model-history.md` 配套. 拍 A (弃 enum). 4 AC + P0-P3 实施 phase.
