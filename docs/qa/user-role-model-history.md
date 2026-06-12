# User Role Model — Codebase History & Current State (S3-OPS-USER-ROLE-MODEL-CONVERGE AC#1)

> 调研者: 魈 (架构师)
> 日期: 2026-06-12
> 触发: PR #232 ABAC-4LAYER-PART1 `get_current_companion` dual check 收敛 follow-up
> 配套 ADR: ADR-0055 (待写) — User Role Model Converge

---

## 1. 历史 migration 时间线

| Commit | 日期 | 变更 | 引入字段 |
|---|---|---|---|
| `b281265` | 2026-03-29 | Phase 1 OTP auth | `User.role: Enum(UserRole)` (单 role enum) |
| `c749c64` | 2026-04-03 | 双角色系统、自定义TabBar | `User.roles: String(50)` (multi-role string) |
| `a1b2c3d4e5f6_add_roles_field.py` | 2026-04-03 | alembic migration | `roles` 字段加 + 一次性 sync `UPDATE users SET roles = role WHERE role IS NOT NULL` |

**关键观察**:
- 双 role 字段并存 ~70 天 (至 2026-06-12), 但 migration **未做 phase 2**: 没 drop `role` enum 字段, 没改 auth 创建时自动 sync `roles`
- `a1b2c3d4e5f6` 只 sync 历史数据, 新建用户不会 sync (auth.py `User(phone=phone)` 0 role assignment)

## 2. 当前 codebase 用法占比

### 2.1 `user.role == UserRole.X` (enum 单 role 查询) — 11 处

| 文件 | 用法 | 风险 |
|---|---|---|
| `backend/app/services/order/query.py:19, 22, 71` | order 查询 patient/companion 过滤 | 🔴 新用户 role=NULL → 永不匹配, 查询返空 |
| `backend/app/services/order/cancel.py:19, 23, 76, 80` | order 取消 patient/companion 分流 | 🔴 新用户取消逻辑走死 |
| `backend/app/dependencies.py:94, 122` | `get_current_patient` / `get_current_companion` dual check 一半 | 🟡 dual or 后另一半补 |
| `backend/app/dependencies.py:112` | docstring 说明 legacy enum | 💭 注释 |

### 2.2 `user.has_role(UserRole.X)` (multi-role string 查询) — 5 处

| 文件 | 用法 |
|---|---|
| `backend/app/services/companion_profile.py:202` | companion 操作前 has_role guard |
| `backend/app/services/user.py:64` | user.set_role guard |
| `backend/app/dependencies.py:96, 124` | `get_current_patient` / `get_current_companion` dual check 另一半 |
| `backend/app/dependencies.py:113` | docstring 说明 newer multi-role |

### 2.3 `user.add_role(UserRole.X)` (multi-role 添加) — 2 处

| 文件 | 用法 |
|---|---|
| `backend/app/services/companion_profile.py:118` | 用户升级 companion 时 `add_role(UserRole.companion)` |
| `backend/app/services/user.py:54` | 通用 set_role 入口 |

### 2.4 关键发现: `User` 实例化时不设 role/roles

```python
# auth.py:132
user = User(phone=phone)
user = await self.user_repo.create(user)
```

3 处 (OTP/WeChat/Apple) 全是 `User(身份字段=值)`, 无 role/roles 赋值. 新用户默认 **role=NULL + roles=NULL**.

## 3. 核心问题: dual 字段语义不一致

### 3.1 `add_role` 只改 `roles`, 不改 `role`

```python
def add_role(self, r: UserRole) -> None:
    current = set(self.get_roles())
    current.add(r.value)
    self.roles = ",".join(sorted(current))
    # ❌ 不动 self.role enum 字段
```

后果: 用户 add_role(companion) 后:
- `user.roles == "companion"` ✅
- `user.role == None` ❌ (enum 字段仍 NULL)

### 3.2 `has_role` 只查 `roles`, 不查 `role`

```python
def has_role(self, r: "UserRole | str") -> bool:
    if not self.roles:
        return False
    val = r.value if isinstance(r, UserRole) else r
    return val in self.roles.split(",")
    # ❌ 不查 self.role enum
```

### 3.3 11 处 `user.role == UserRole.X` 是 latent bug

新用户 role 永远 NULL → order/cancel + order/query 11 处 enum 判断**永远 False**. 走死代码路径.

**实际现状**: 不出 bug 是因为 dependencies.py `get_current_patient/companion` 用 dual check (`or`) 覆盖. order service 只接受已通过 dependencies.py 的 user. 但**直接调 order/query.py 时(无 dependency injection)会漏判**.

## 4. 三方案

### 方案 A: 弃 enum (multi-role 唯一 SoT)

**改动**:
- `User.role` 字段 deprecate, 加 `@property def role` 兜底返 `roles.split(",")[0]` (向后兼容旧 query)
- 11 处 `user.role == UserRole.X` 全改 `user.has_role(UserRole.X)`
- `has_role` / `add_role` / `get_roles` / `roles` 唯一 SoT
- migration: 不 drop 列 (向后兼容), 新代码不用

**优点**:
1. 业务表达自然 (1 user 多 role, e.g. patient + companion 同人)
2. 移除 dual check 二意性
3. add_role / has_role 已是新业务默认入口

**缺点**:
1. 11 处 change (order service 集中)
2. `User.role` 字段保留但不用 = 死列 (alembic 不 drop 防破历史)
3. PR review 改动量中等

### 方案 B: 弃 multi-role (enum 唯一 SoT)

**改动**:
- 删除 `User.roles` 字段 (drop column)
- 删除 `has_role` / `add_role` / `get_roles` 方法
- companion_profile / user.py 改用 `user.role = UserRole.companion` 直接 assign
- 5 处 has_role 改 `user.role == UserRole.X`

**优点**:
1. enum 类型安全, 编译时检查
2. 单字段, schema 简洁

**缺点**:
1. 🔴 enum 只能 1 role — **不支持** patient + companion 双角色 (家属帮患者下单时同人需要 2 role)
2. 业务模型退化 (反产品需求)
3. 删 roles 字段 = 数据丢失风险 (历史用户 multi-role 数据)

**否决**: 业务模型不支持. 单 role 是错的设计.

### 方案 C: 共存 + 单一 SoT 强制

**改动**:
- 保留两字段
- 添加 trigger / event listener: `add_role` 调用时同步 `self.role = r` (最后加的 role 作 enum)
- auth.py 创建 user 时设默认 role=patient + roles="patient"
- 11 处 enum 查询保留, 5 处 has_role 保留, 但保证 sync

**优点**:
1. 0 break 现有 query
2. 渐进迁移

**缺点**:
1. 双字段语义还是混乱 (which is SoT?)
2. add_role(companion) 后 user.role == companion (覆盖 patient) — 不直观
3. sync 逻辑加复杂度, 容易漏

**否决**: 不解决根本二意性, 只是糊裱.

---

## 5. 拍板: 方案 A (弃 enum)

**理由**:
1. 业务需要 multi-role (patient + companion 同人)
2. enum 字段对新用户永远 NULL → 11 处查询是 latent 死路径
3. has_role 已是新业务默认入口, 收敛到它符合 codebase 演进方向
4. enum 字段保留不 drop (向后兼容历史数据 + alembic 不强制 schema 大改)

## 6. 实施 phase

### Phase 1 (本调研报告 + ADR-0055 设计) — 架构师 own (~30min)
- ✅ 调研报告 `docs/qa/user-role-model-history.md` (本 file)
- ⏳ ADR-0055 `docs/adr/ADR-0055-user-role-model-converge.md` 拍 A + 实施 spec
- handoff → hutao

### Phase 2 (hutao 实施) — developer own (~60min)
- AC#3: 11 处 `user.role == UserRole.X` → `user.has_role(UserRole.X)` 全改
- `get_current_patient` / `get_current_companion` dual check → 单一 `has_role`
- AC#4: pytest 现有 auth + role 全 green + 加 1 regression (`test_role_model_single_sot_via_has_role`)
- AC#5: ABAC PART1 兼容 (dependencies.py 调整不破 PR #232 行为)

### Phase 3 (回归) — tester own (~30min)
- E2E auth 流验证

---

## 7. 风险

| 风险 | 缓解 |
|---|---|
| 11 处 change 漏一处 → enum 查询继续走死 | grep -rn `role == UserRole` PR review 必查 0 hit |
| has_role 查询性能 (String split) vs enum 直查 | 用户表 has_role 调用每 request 不超 10 次, 性能可接受; 后续如热点可 cache in User 实例 |
| 历史用户 roles 字段 NULL (auth 一次性 sync 之后没 backfill) | migration alembic upgrade: `UPDATE users SET roles = role WHERE role IS NOT NULL AND roles IS NULL` (idempotent backfill) |

## 8. 后续 follow-up (不在本 task)

- enum 字段长期 drop (3 月后 cool-down 期, 确认 0 use 后 drop column)
- ABAC PART2 (S3-DEV-002-ABAC-4LAYER-PART2) 用 has_role 重写 (PR #233 待评)
- admin role 加 (e.g. `add_role(UserRole.admin)`) 扩展 enum 值
