# ADR-0043 — 陪诊服务类型 + 价格后台可配（去硬编码）

> 状态：**Draft（D+0）** · 作者：魈 · 日期：2026-06-04
> 关联：S2-REQ-003（PM 凝光）/ ADR-0030（金额 Decimal）/ ADR-0041（状态机解耦）/ ADR-0042（admin-v2）/ S2-INT-001 v2 验收口径 §1.1.1（U-1 摘要模板互锁）
> 业务方案：凝光拍 B（服务类型 + 价格全部后台可配，非仅价格）
> Owner Approval：帝君

---

## 1. 背景

`backend/app/models/order.py` 当前硬编码：
- `ServiceType` Enum（`full_accompany / half_accompany / errand`）
- `SERVICE_PRICES` 常量（299 / 199 / 149）
- `SERVICE_TYPE_LABELS` 在 `backend/app/services/notification.py:14`

三端硬编码联动：
- iOS / 微信端 U-1 服务选项 + 摘要模板（"全程陪诊 ¥299" 等）
- admin-h5 无服务/价格管理模块
- 联调期 S2-INT-001 v2 §1.1.1 摘要模板钉死表逐字符互锁（建立在固定三档上）

业务需要新增/删除服务档位、改价格不发版。

---

## 2. 决策

### 2.1 数据模型：Enum → 表

新增表 `service_packages`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID PK | 服务档位主键 |
| `code` | str (UNIQUE, NOT NULL) | 业务编码（如 `full_accompany`），用于历史订单兼容 |
| `name` | str (NOT NULL) | 中文显示名（如 "全程陪诊"） |
| `price` | Decimal(10,2) NOT NULL | 价格（元） |
| `is_active` | bool NOT NULL default true | 启用状态 |
| `sort_order` | int NOT NULL default 0 | 排序权重（升序） |
| `description` | str nullable | 详情说明（可选） |
| `created_at` / `updated_at` | timestamp | 标准时间戳 |
| `created_by` / `updated_by` | UUID (admin_user_id) nullable | 审计字段 |

**约束**：`code` 全局唯一（migration 时把 enum 三值 `full_accompany / half_accompany / errand` seed 进表 + sort_order=10/20/30）。

### 2.2 兼容旧数据：保留 `Order.service_type` 字段

`Order.service_type` **类型不变**（仍是 string，旧 enum 值），但**含义升级为 service_packages.code 引用**（弱外键，不加 FK 约束避免 cascade 复杂度）。

- 旧订单：`service_type='full_accompany'` 仍指向 seed 后的 `service_packages` 行
- 新订单：admin 新建档位时 code 自定义（如 `vip_full`），写入 Order.service_type 即可
- 兜底：读 Order 时若 service_type 在 service_packages 表中查不到（极端：被硬删了），用 `Order.service_name_snapshot` + `Order.service_price_snapshot` 渲染

### 2.3 价格快照（acceptance #4 硬要求）

`Order` 表新增 2 字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `service_name_snapshot` | str NOT NULL | 下单时档位名快照 |
| `service_price_snapshot` | Decimal(10,2) NOT NULL | 下单时价格快照 |

下单时（OrderService.create_order）从 service_packages 取当前 active 档位，把 name + price 快照到 Order；后续 admin 改价不影响历史订单（acceptance #4）。

**支付/退款金额** 一律读 `service_price_snapshot`，**不再** 读 `SERVICE_PRICES`。

### 2.4 admin CRUD API

新增 `backend/app/api/v1/admin/service_packages.py`：

| 端点 | 方法 | 鉴权 | 功能 |
|---|---|---|---|
| `/api/v1/admin/service-packages` | GET | require_admin | 列表（含已停用），分页 |
| `/api/v1/admin/service-packages` | POST | require_admin | 新建档位（code/name/price/sort_order/description） |
| `/api/v1/admin/service-packages/{id}` | PATCH | require_admin | 改价/改名/启停/改排序 |
| `/api/v1/admin/service-packages/{id}` | DELETE | require_admin | **软删**（is_active=false），不真删避免历史订单引用断裂 |
| `/api/v1/public/service-packages` | GET | 公开 | 三端动态拉**启用中**档位 (按 sort_order 升序) |

**audit_logs 留痕**：CREATE / UPDATE / SOFT_DELETE 三 action 全写 admin_audit_logs。

### 2.5 三端动态读取

| 端 | 改动 |
|---|---|
| **iOS** | U-1 下单页启动时 `GET /api/v1/public/service-packages` 拉档位列表渲染；摘要模板 `summaryService(serviceName, price)` 参数已是字符串 + Decimal，**无需改函数签名**；测试 fixture 改为读 API mock 数据 |
| **微信端** | 同上，`wechat/utils/orderSummary.js` 函数签名不变；createOrder 页拉接口 |
| **admin-h5（v1）** | 应急 v1 加"服务管理"模块（vanilla JS，与现有 9 项能力同款）；admin-v2 Phase 2-9 中迁移（依 ADR-0042 顺序，建议作为 Phase 1.5 紧随陪诊师审核样板后做） |

### 2.6 S2-INT-001 v2 §1.1.1 互锁口径修订

**关键**：U-1 摘要模板原约定"逐字符匹配钉死表"是基于固定三档。改成动态档位后，互锁口径必须修订：

> **新口径**：服务选项 + 摘要模板互锁对象从「写死文案」改为「后端档位数据源逐字段一致」——
> - iOS / 微信端从 `/api/v1/public/service-packages` 拉同一份 JSON
> - `summaryService(name, price)` 函数实现逐字符等价（这部分仍是 AC#13 / AC#25 互锁范围）
> - 文案随后端档位变动，不再是字面常量

凝光更新 PRD-001 §F7 + S2-INT-001 v2 §1.1.1 + 通知刻晴 test-plan 增量对齐（凝光已在群里 ack）。

---

## 3. 实施步骤（建议拆 develop sub-task）

| Phase | 内容 | 估时 |
|---|---|---|
| **P1 数据建模 + 迁移** | service_packages 表 + Order 加 2 snapshot 字段 + alembic migration + seed 三档 + 单测 | 0.5d |
| **P2 admin CRUD API** | 5 端点 + audit 留痕 + 单测 + OpenAPI doc | 0.5d |
| **P3 public 端点 + lifecycle 改造** | GET /public/service-packages + OrderService.create_order 改读 service_packages + 写快照 | 0.5d |
| **P4 SERVICE_PRICES / SERVICE_TYPE_LABELS 去硬编码** | lifecycle.py / notification.py 调用点全改读 service_packages + 兜底 snapshot | 0.5d |
| **P5 三端动态读取** | iOS / 微信 createOrder 页接 public 端点 + admin-h5 v1 服务管理模块 | 1d（三端并行） |
| **P6 S2-INT-001 v2 §1.1.1 互锁口径修订 + test-plan 同步** | docs/qa 修订 + 刻晴 test-plan I-1/W-1 修订 | 0.5d（凝光主导） |
| **P7 历史订单数据迁移兜底** | alembic 升级把存量 Order.service_type 值用 SERVICE_PRICES + SERVICE_TYPE_LABELS 回填 snapshot + 验数据完整 | 0.5d |

总计 ~4 工作日（三端并行后），实施 owner = 胡桃，reviewer = 魈。

---

## 4. 与 S2-INT-001 关系

S2-INT-001 联调主线已 done（基于固定三档跑通）。本 ADR 不破联调成果——
- 后端 OrderItem 9 字段契约**不变**（service_type 字段名 + 类型 string 不变）
- 新增 `service_name_snapshot / service_price_snapshot` 是 **additive**（向后兼容，老客户端不读不报错）
- 互锁口径修订（§2.6）是**升级**不是 break

灰度门 S2-TEST-004 不受本 ADR 影响（本 ADR 实施排在灰度通过后，与 admin-v2 Phase 2-9 同期）。

---

## 5. 风险

| 风险 | 概率 | 缓解 |
|---|---|---|
| 历史订单 service_type='full_accompany' 在 service_packages 软删后渲染失效 | 中 | snapshot 字段兜底；DELETE 是软删不真删 |
| admin 改价瞬间下单的订单价格不一致（race） | 低 | 下单事务内 SELECT 价格 + UPDATE Order，单事务原子；前端可加"价格已变更，请确认"弱提示 |
| 三端发版节奏不同步导致部分端仍硬编码 | 中 | 后端 public 端点先上 + 三端按各自节奏接，过渡期前端读不到 API 时回退到旧三档兜底 |
| 资金线回归 | 高 | pytest -m money_safety 全绿门 + 灰度沙箱真跑（S2-TEST-004）+ 与 SERVICE_PRICES 调用点改动一起跑 |
| admin-v2 Phase 1 还没落，新模块只能进 v1 | 中 | v1 加服务管理模块（小模块 ~200 行 JS），admin-v2 Phase 2-9 时迁移；不阻塞业务 |

---

## 6. 不在范围

- **服务档位的多语言**（i18n）下迭代
- **服务档位的 SKU 维度**（如同档位多医院差价）下迭代
- **价格历史曲线**（不做时间序列价格表，admin 改价直接覆盖）
- **服务档位与 companion 资质绑定**（如 vip 档位只允许某些陪诊师接）下迭代

---

## 7. 验收

- [ ] ADR-0043 落盘
- [ ] `service_packages` 表 + alembic 迁移 + seed 三档 + 单测
- [ ] admin CRUD API 5 端点 + 审计 + 单测
- [ ] public 端点 + lifecycle 改造 + 价格快照
- [ ] SERVICE_PRICES / SERVICE_TYPE_LABELS 调用点零硬编码（grep 验证）
- [ ] 三端动态读取 + admin-h5 v1 服务管理模块
- [ ] S2-INT-001 v2 §1.1.1 互锁口径修订（凝光主导）
- [ ] 历史订单 service_type 数据迁移兜底
- [ ] pytest -m money_safety 全绿
- [ ] U-1 端到端契约测试（iOS + 微信）改读 API mock fixture
- [ ] OpenAPI schema diff CI gate 含新端点

---

## 8. 决定

**Draft → 待 review**

- Reviewer：胡桃（developer，实施者）+ 刻晴（tester，回归视角）
- Owner Approval：帝君（业务方案 B 已拍，本 ADR 是技术拆解细化）
- 凝光（PM）作为 PRD-001 / S2-INT-001 口径同步关切人，需要在 §2.6 修订前 confirm

Accept 后 hutao 拆 P1-P7 sub-task 实施。

---

## 9. 反向引用

- ADR-0030 金额 Decimal：本 ADR price 字段类型遵从
- ADR-0041 状态机解耦：本 ADR 不动 OrderStatus，仅动 Order 字段
- ADR-0042 admin-v2 选型：v1 服务管理模块作为应急方案 + admin-v2 Phase 1.5（陪诊师审核样板后）迁移
- S2-INT-001 v2 验收口径 §1.1.1：互锁口径修订承接 §2.6
- S2-REQ-003 PM 任务 §7：本 ADR 是其技术拆解产出
