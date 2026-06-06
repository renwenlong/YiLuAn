# S3 信任前置 UI 设计文档

> 状态：**Draft（待胡桃 dev review + 刻晴 test review + Owner Accept）** · 作者：魈 · 日期：2026-06-06  
> 关联 PRD：PRD-003 v0.4 §S3-REQ-003 · 关联 ADR：ADR-0046 / ADR-0047 / ADR-0048 / ADR-0049  
> 关联 task：S3-DES-003 / S3-DEV-003-TRUST-UI-WX / S3-DEV-003-TRUST-UI-IOS / S3-DEV-003-ADMIN-COPY  
> Owner Approval：**Pending**

---

## 0. 设计目标（一句话）

用户**下单前**就能感知到「保险已就绪 / 合同已生成 / AI 准备包已就绪 / 陪诊师资质已核验」四张牌的实时状态，把信任建立**前置到付费前**，缩短决策链路。

不替代 S2 已有的订单详情页状态展示；这是**下单前的预检（precheck）状态卡片**，挂在订单创建流的最后一屏（点"立即支付"之前）。

---

## 1. 设计约束

| 约束 | 来源 |
|---|---|
| 不暴露陪诊师真实身份信息（姓 + 工号 + 资质类型） | ADR-0046 §3.5 ABAC + PRD-001 v1.4 §F8 |
| 4 张牌字段全 positive list（`companion_cert_*` / `contract_*` / `insurance_*` / `preparation_*`） | ADR-0046 §3.5 S3_NEW_FIELD_PREFIXES |
| 不在用户端返回 `raw_content` / `attachment_urls` / `user_contact` 等高敏字段 | ADR-0048 §7.0 4 层 ABAC |
| 反馈入口只露给「订单 done 后 30 天内的用户」 | ADR-0049 + PRD-004 |
| WebSocket 推送时延 SLO ≤5s（含 1 次自动重连） | 胡桃 review amend（与 HOT-RELOAD 对齐）|
| 微信小程序后台/锁屏 WS 会断，需 polling fallback 30s | 胡桃 review amend |
| iOS 端 implement 以 CI E2E 为准（WSL 工具栈约束） | 胡桃 review amend |

---

## 2. 用户旅程

```
[选服务] → [填基本信息] → [选陪诊师] → [信任前置卡片] → [付款] → [订单详情]
                                          ↑
                                    本文档覆盖
```

信任前置卡片 = 订单创建流的第 4 屏，**所有牌就绪才允许付款**。任一牌未就绪 → 付款 CTA 灰显 + 显示原因（管理员介入中 / 资料补全中 / 系统处理中）。

---

## 3. 4 张牌设计

### 3.1 卡片整体结构

```
┌────────────────────────────────────────┐
│ 即将开始服务 · 已为您准备：               │
│                                        │
│ ✅ 服务合同已生成                        │
│    [查看合同 PDF →]                      │
│                                        │
│ ✅ 履约保险已生效                        │
│    保单号 BX2026****1234                │
│    [查看保单 →]                          │
│                                        │
│ ✅ AI 就诊准备包已就绪                   │
│    含检查须知 / 注意事项 / 流程说明       │
│    [查看准备包 →]                        │
│                                        │
│ ✅ 陪诊师资质已核验                      │
│    陈师傅 · 工号 PC0042                 │
│    持证：康复治疗师 + 健康管理师           │
│    [查看资质详情 →]                      │
│                                        │
│ ─────────────────────────────────────  │
│              [确认付款 ¥xxx]              │
└────────────────────────────────────────┘
```

### 3.2 4 张牌字段契约

**用户端 ResponseView：`OrderPrecheckSummaryView`**

```python
class OrderPrecheckSummaryView(BaseModel):
    order_id: str
    
    # Card 1: 合同
    contract_status: ContractStatusView  # 子对象
    
    # Card 2: 保险
    insurance_status: InsuranceStatusView
    
    # Card 3: AI 准备包
    preparation_status: PreparationStatusView
    
    # Card 4: 陪诊师资质
    companion_cert_status: CompanionCertStatusView
    
    # 总开关
    all_ready: bool
    payment_enabled: bool
    blocked_reason: str | None  # 任一未就绪时填
```

每个子对象**只**含 positive list 字段：

```python
class ContractStatusView(BaseModel):
    ready: bool                          # True | False
    contract_id: str | None              # ready 时填
    contract_template_version: str | None
    contract_pdf_url: str | None         # signed URL TTL ≤15min
    generated_at: datetime | None
    # 不返回：contract_hash / hash_inputs / storage_blob_path / template_key

class InsuranceStatusView(BaseModel):
    ready: bool
    insurance_order_id: str | None
    policy_no_masked: str | None         # BX2026****1234 中间脱敏
    policy_pdf_url: str | None
    effective_from: date | None
    # 不返回：carrier_internal_id / actual_premium / underwriter_meta

class PreparationStatusView(BaseModel):
    ready: bool
    preparation_id: str | None
    prep_summary: str | None             # 已过 ABAC + 关键词过滤
    sections_count: int | None
    generated_at: datetime | None
    # 不返回：prompt_version / model_used / raw_llm_output / cost_yuan

class CompanionCertStatusView(BaseModel):
    ready: bool
    companion_cert_pseudonym_name: str | None    # "陈师傅"
    companion_cert_work_id: str | None           # "PC0042"
    companion_cert_qualifications: list[str] | None  # ["康复治疗师", "健康管理师"]
    companion_cert_proof_image_urls: list[str] | None  # signed URL TTL ≤15min
    companion_cert_verified_at: datetime | None
    # 不返回：companion_real_name / companion_id_card_hash / companion_phone / companion_user_id
```

### 3.3 4 张牌"未就绪"文案统一表

| 牌 | not ready 原因 | UI 文案 |
|---|---|---|
| 合同 | 合同生成 worker 排队中 | 服务合同生成中（通常 ≤30s） |
| 合同 | 合同生成失败重试中 | 系统正在处理（已自动重试 X 次） |
| 合同 | 合同已失效（admin invalidate） | 合同需重新生成，客服正在处理 |
| 保险 | 保险下单中 | 保险投保中（通常 ≤60s） |
| 保险 | 保险下单失败 | 保险出单异常，客服正在处理 |
| 保险 | circuit breaker open | 保险服务暂时不可用，预计 X 分钟恢复 |
| AI 准备包 | 生成中 | 准备包生成中（通常 ≤120s） |
| AI 准备包 | budget breach fallback | 已使用基础版准备包 |
| AI 准备包 | 关键词命中 | 内容审核中，客服正在处理 |
| 陪诊师资质 | 核验未通过 | 该陪诊师资质待核验，请选择其他陪诊师 |
| 陪诊师资质 | 核验过期 | 资质需重新核验，请稍后再试 |

**文案 lint 规则**（admin-v2 文案配置同步 + 刻晴 review gap）：

- `DENY_KEYWORDS = ["失败", "错误", "异常堆栈", "exception", "error", "failed"]`：任何文案动态加载后含以上关键词 → lint fail。
- `DENY_WORKER_NAMES`：动态加载 `app.workers.__all__` 名单；任何文案出现 worker 名 → lint fail。
- `DENY_HARDCODE_TIME = /\d+\s*(秒|分钟|s|min)/`：硬时限承诺 → lint warn，需 PM ack 后才能发布。
- CI script：`backend/scripts/lint_precheck_copy.py`，GitHub Actions job `precheck-copy-lint` 必跑。
- 本地 lint：admin-v2 client-side onChange + server-side onSave 双拦截。

## 4. 实时推送设计

### 4.1 推送通道选择

**首选 WebSocket，断连后 polling fallback。**

| 通道 | 用途 | 时延 SLO |
|---|---|---|
| WebSocket `/ws/v1/orders/{order_id}/precheck` | 在线推送 4 张牌状态变化 | ≤5s：backend WS broadcast → client onMessage ≤5s，含 1 次自动重连窗口 |
| Polling GET `/api/v1/users/orders/{order_id}/precheck-status` | WS 断连 30s 未重连成功 fallback | 每 5s 1 次 |

**断连切换规则**：

```
WS 断 → 立即尝试重连（间隔 1s/3s/5s 共 3 次）
  ├─ 重连成功 → 继续 WS（UI 视觉无感）
  └─ 重连失败（30s 内未成功） → 切 polling 每 5s 1 次
      └─ WS 恢复 → 立即切回 WS + 停 polling
```

**SLO 量化验证**（刻晴 review gap）：

- mock backend WS broadcast 事件时间戳 + client onMessage 时间戳 → p95(client - backend) ≤5s。
- mock 断连 1 次后重连成功 → p95(reconnect) ≤1s、p99 ≤5s。
- mock 3 次重连失败 → polling fallback 在 30±2s 内生效，不能提前刷接口，也不能超过 32s。

UI 不弹"连接失败"错（用户感知差），全程视觉无感。

### 4.2 WebSocket 事件 schema

```json
{
  "event": "precheck.status.updated",
  "order_id": "ord_xxx",
  "card": "contract",   // contract | insurance | preparation | companion_cert
  "status": {           // 同 OrderPrecheckSummaryView.contract_status 结构
    "ready": true,
    "contract_id": "ct_xxx",
    "...": "..."
  },
  "all_ready": false,
  "ts": "2026-06-06T03:30:00Z"
}
```

**事件类型**：

- `precheck.status.updated` — 单张牌状态变化
- `precheck.all_ready` — 所有牌就绪（payment_enabled = true）
- `precheck.blocked` — 任一牌不可恢复阻塞（payment 永远不可用，需重新下单）

### 4.3 后端推送时机

| 事件 | 触发点 | 后端动作 |
|---|---|---|
| `precheck.status.updated{card: contract}` | ContractStateMachine 转 done | `ContractService.transition` after_commit hook → `OrderPrecheckAggregator.evaluate(order_id)` → WS broadcast |
| `precheck.status.updated{card: insurance}` | InsuranceOrderStateMachine 转 active | `InsuranceService.transition` after_commit hook → 同上 |
| `precheck.status.updated{card: preparation}` | preparation_status 表 status=ready | AI prep worker after_commit hook → 同上 |
| `precheck.status.updated{card: companion_cert}` | companion_cert_verifications 表 status=verified | admin verify endpoint after_commit → 同上 |
| `precheck.all_ready` | 4 张牌全 ready 的最后一张触发 | `aggregator.evaluate` 检测 all_ready=True → 附加该事件 broadcast |
| `precheck.blocked` | 任一牌不可恢复阻塞 | `aggregator.evaluate` 检测 permanent_blocked → broadcast |

**OrderPrecheckAggregator** = 新建 service（`backend/app/services/order_precheck_aggregator.py`），订阅以上 4 个事件源，每次 evaluate 后：

- 写 redis cache `precheck:order:{order_id}` TTL 5min。
- WS broadcast 推送给订阅该 `order_id` 的 connection。
- 不写 DB（4 张牌状态已在各自表，aggregator 只读）。

**cert event ≤3s 拆解**（胡桃 review gap）：

```
admin verify endpoint commit
  ├─ after_commit hook 触发 ≤100ms
  ├─ aggregator.evaluate 读 4 表 + redis cache write ≤300ms
  └─ WS broadcast → client onMessage（含 1 次自动重连）≤2600ms
  ---
  总计 ≤3000ms = 3s SLO
```

## 5. 后端 API 契约

### 5.1 endpoint 列表

| Method | Path | 用途 | 鉴权 |
|---|---|---|---|
| `GET` | `/api/v1/users/orders/{order_id}/precheck-status` | 同步取 precheck 状态（polling fallback / 首屏） | `get_current_user` + 订单 owner 校验 |
| `WS` | `/ws/v1/orders/{order_id}/precheck` | 订阅实时推送 | WS handshake 时校验 user token + order owner |

**WS handshake 鉴权细节**（胡桃 review gap）：

- WS upgrade header `Authorization: Bearer <user_token>`；微信小程序 WS API 不支持自定义 header 时允许 `?token=<user_token>` fallback。
- handler 验证 token → 提取 user_id。
- 查询 `orders` 表 `order_id` 的 user_id，不等 → WS 4401 close（语义等价 HTTP 401）。
- token 过期期间服务侧主动推送 `precheck.session.expired` 事件后 4401 close。

### 5.2 GET endpoint 行为

```python
@router.get("/users/orders/{order_id}/precheck-status", response_model=OrderPrecheckSummaryView)
async def get_precheck_status(
    order_id: str,
    user: User = Depends(get_current_user),
    aggregator: OrderPrecheckAggregator = Depends(),
) -> OrderPrecheckSummaryView:
    # 1) 校验订单 owner（user.id == order.user_id），否则 403
    # 2) aggregator.evaluate(order_id) → OrderPrecheckSummaryView
    # 3) 拒绝任何 admin / companion 角色访问（独立 endpoint，不复用 admin endpoint）
    ...
```

**SLO**（胡桃 review gap）：

- P95 cache hit ≤200ms（redis hit 路径）。
- P95 cache miss ≤800ms（4 表 union 查询 + write cache）。
- k6 perf test：`backend/perf/precheck_status.k6.js`，VU=50、duration=2min、thresholds：
  - `http_req_duration{cache:hit}: p(95)<200`
  - `http_req_duration{cache:miss}: p(95)<800`
- prometheus metric：`precheck_status_request_duration_seconds_bucket{path,cache_hit}`。

### 5.3 ABAC 4 层防御（复用 ADR-0048 §7.0 模板）

| 层 | 合同牌 | 保险牌 | AI 准备包牌 | 陪诊师资质牌 |
|---|---|---|---|---|
| Schema | `ContractStatusView` 不定义 `contract_hash/hash_inputs/storage_blob_path/template_key` | `InsuranceStatusView` 不定义 `carrier_internal_id/actual_premium/underwriter_meta` | `PreparationStatusView` 不定义 `prompt_version/model_used/raw_llm_output/cost_yuan` | `CompanionCertStatusView` 不定义 `companion_real_name/companion_id_card_hash/companion_phone/companion_user_id` |
| Endpoint | `/users/...` owner-only | `/users/...` owner-only | `/users/...` owner-only | `/users/...` owner-only |
| Service | SELECT 显式列裁剪 | SELECT 显式列裁剪 | SELECT 显式列裁剪 | SELECT 显式列裁剪 |
| Test | schema + integration + schemathesis | schema + integration + schemathesis | schema + integration + schemathesis | schema + integration + schemathesis |

**17 字段 negative list**：

`contract_hash`, `hash_inputs`, `storage_blob_path`, `template_key`, `carrier_internal_id`, `actual_premium`, `underwriter_meta`, `prompt_version`, `model_used`, `raw_llm_output`, `cost_yuan`, `companion_real_name`, `companion_id_card_hash`, `companion_phone`, `companion_user_id`, `companion_real_*`, `*_id_card_*`。

**positive list 哨兵**：`ORDER_PRECHECK_RESPONSE_POSITIVE_LIST` 加字段必须 PR + reviewer ack；任何 response 字段不在 positive list 内 → CI 失败。

1. **Schema 层**：`OrderPrecheckSummaryView` 物理上不定义敏感字段。
2. **Endpoint 层**：`/users/...` endpoint 强 `get_current_user` 依赖；admin / companion 永不复用该 endpoint。
3. **Service 层**：`aggregator.evaluate` 内 SQL `SELECT` 显式列裁剪，不依赖 schema 兜底。
4. **测试层**：
   - 单元：`assert "contract_hash" not in OrderPrecheckSummaryView.model_json_schema()["$defs"]["ContractStatusView"]["properties"]`。
   - 集成：mock user token 请求，response json grep `contract_hash` 必须 0 命中。
   - Schemathesis：negative list 17 字段 + positive list 双哨兵。

## 6. 前端实现要点

### 6.1 微信小程序（WX）

| 项 | 实现 |
|---|---|
| 卡片组件 | `components/PrecheckCard/index.wxml` 4 张牌共享组件，props: `card, status` |
| WS 客户端 | `services/precheck-ws.ts` 自动重连 1s/3s/5s × 3，failover 切 polling |
| Polling 客户端 | `services/precheck-poll.ts` setInterval 5s + AbortController 切换控制 |
| 文案配置 | `config/precheck-copy.ts` 从 admin-v2 `S3-DEV-003-ADMIN-COPY` 同步导出（CI 校验一致性） |
| 后台/锁屏处理 | `onHide` 立即停 WS + 停 polling；`onShow` 重连 WS / 拉一次 GET |
| 支付 CTA | `OrderPrecheckSummaryView.payment_enabled === true` 才启用，否则 disabled + 灰显 + 显示 blocked_reason |

### 6.2 iOS（H5 内嵌 + 原生壳）

| 项 | 实现 |
|---|---|
| H5 部分 | 与 WX 共享 React 组件库（`packages/precheck-card`），独立 H5 build |
| 原生壳 | iOS WKWebView 包装，JSBridge 暴露 `applicationState` 转发到 H5（前后台切换感知）|
| 推送通道 | 同 WX：WS first，polling fallback |
| dev 实施 | WSL 无 Xcode，dev 本机只跑 H5 部分；iOS 原生壳与 H5↔native bridge 必须 CI E2E（macOS runner）验证 |

**iOS CI E2E round-trip**（刻晴 review gap）：

- GitHub Actions matrix 增加 macOS runner job：`ios-precheck-e2e`。
- 验证 WKWebView 首屏加载 + H5 调 `window.webkit.messageHandlers.precheck.postMessage` 到 native。
- 验证 native 回调 `window.__PRECHECK_NATIVE_EVENT__` 到 H5。
- 验证前后台切换：native `applicationState` → H5 停 WS / 恢复后重连 WS + 拉一次 GET。
- WSL 本机不要求 Xcode；CI E2E 是唯一通过口径。

### 6.3 跨端一致性 lint

- 共享字段映射：`packages/precheck-card/src/field-mapping.ts` 定义 4 张牌的 ResponseView ↔ UI 字段 1:1 映射
- 文案 lint：`packages/precheck-card/src/copy-lint.ts` enforce §3.3 文案表 + admin-v2 同步源
- 单测：`packages/precheck-card/__tests__/abac.test.ts` 三端共享，校验组件永不渲染敏感字段（即使误传也不显示）

---

## 7. admin-v2 文案管理（S3-DEV-003-ADMIN-COPY）

### 7.1 路径

`/admin-v2/system/precheck-copywriting`

### 7.2 功能

| 功能 | 说明 |
|---|---|
| 文案列表 | §3.3 11 条文案 key + value 可编辑 |
| lint 校验 | 保存前 client-side + server-side 双 lint：不含"失败"、不含错误码、不含 worker 名 |
| 版本管理 | 每次保存写 `admin_audit_logs` + 文案版本号自增 |
| 灰度发布 | 编辑后默认 staging only，super_admin 批准后 prod 生效 |

### 7.3 鉴权

普通 admin 可读 + 可起草；super_admin 才能批准 prod 生效。

---

## 8. 灰度发布策略

| 阶段 | 流量 | 时长 | 监控指标 |
|---|---|---|---|
| Phase 1 | 内测 5 用户 | 24h | WS 连接成功率 ≥99% / API P95 ≤200ms / 0 ABAC 失血 |
| Phase 2 | 5% 真实用户 | 48h | + 付款转化率不下降 |
| Phase 3 | 30% | 72h | 同上 + 文案 NPS 调研 |
| Phase 4 | 100% | — | 持续观察 7 天 |

**回滚触发（刻晴 review gap）**：任一 phase 满足以下条件立即回滚：

- ABAC 失血 > 0（任何敏感字段命中 negative list）。
- WS 连接成功率 <95%。
- GET `/precheck-status` P95 >500ms 连续 10min。
- 支付转化率相对上一 phase 下降 ≥3%。
- cert event ≤3s SLO 失败率 >1%。

回滚方式：关闭 `feature_flags.s3_precheck_ui`，保留后端 endpoint dark launch，不触发 DB downgrade。

## 9. 验收清单（与 S3-TEST-003 对齐）

- [ ] AC#1 设计文档 `docs/design/S3-trust-precheck-ui.md` 落盘 ✅ **本文档**
- [ ] AC#2 三端共享字段映射 + ResponseView schema 落盘
- [ ] AC#3 WX/iOS/admin-v2 UI 4 张牌渲染正确，字段映射一致
- [ ] AC#4 WS 推送时延 ≤5s（含 1 次自动重连）+ polling fallback 30±2s 切换正确
- [ ] AC#5 cert event ≤3s 端到端（admin verify → after_commit hook → aggregator.evaluate → WS broadcast → 用户端 UI 更新）
- [ ] AC#6 文案 lint 校验通过 + admin-v2 三端文案一致
- [ ] AC#7 a11y 通过（刻晴 review gap）：
  - 色盲：deuteranopia / protanopia / tritanopia 3 型模拟截图通过
  - screen reader：VoiceOver/NVDA 能读出 4 张牌状态 + blocked_reason
  - 键盘焦点：Tab 顺序为 4 张牌 → 4 个详情链接 → 付款 CTA；disabled CTA 不吞焦点
  - 图标不能只靠颜色表达状态，必须有文字/aria-label
- [ ] AC#8 ABAC 4 层防御全过：schema / endpoint / service / 测试哨兵
- [ ] AC#9 PRECHECK-BACKEND task 存在且 UI task depends_on 指向 `S3-DEV-003-PRECHECK-BACKEND`，不能再依赖 `S3-DEV-001-CONTRACT-API`

## 10. 不做的事（防范围蔓延）

- ❌ 不做下单后的精装信任卡片（S2 订单详情页已有，不重复）
- ❌ 不做用户主动触发"重新核验"按钮（admin 流程，用户端不暴露）
- ❌ 不做"推荐其他陪诊师"算法（PRD-005 范围）
- ❌ 不做反馈入口（PRD-004 + ADR-0049 范围，订单 done 后才露）

---

## 11. 拆分

本设计文档对应 **4 个** develop task（凝光 PM 04:30 UTC 拦截 amend：原 3 task 全前端遗漏后端实施，补 PRECHECK-BACKEND root）：

| Task | 范围 | 依赖 |
|---|---|---|
| **S3-DEV-003-PRECHECK-BACKEND** （root） | OrderPrecheckAggregator + GET precheck-status + WS handler + 4 hook + ABAC 4 层 + 17 字段哨兵 + Schemathesis positive list | S3-DES-003 / S3-DEV-001-CONTRACT-DOMAIN / S3-DEV-001-INSURANCE-DOMAIN / S3-DEV-002-PREP-API / S3-DEV-005-CACHE-INVALIDATE |
| S3-DEV-003-TRUST-UI-WX | 微信小程序 4 张牌组件 + WS 客户端 + polling fallback 30s | S3-DES-003 / S3-DEV-003-PRECHECK-BACKEND |
| S3-DEV-003-TRUST-UI-IOS | iOS H5 + 原生壳 + JSBridge + CI E2E | S3-DES-003 / S3-DEV-003-PRECHECK-BACKEND |
| S3-DEV-003-ADMIN-COPY | admin-v2 文案配置 + lint + 版本管理（含 COPY-LINT 合并） | S3-DES-003 |

---

## 12. Owner Approval Trail

| 角色 | 状态 | 备注 |
|---|---|---|
| 魈（架构师） | 起草 r1 amend | 2026-06-06；凝光 PM 04:30 UTC 拦截后补 PRECHECK-BACKEND task |
| 胡桃（dev review） | Pending r1 | 5 gap 全采纳（PRECHECK-BACKEND task + design doc §11 粒度 + 4 task 并行性）|
| 刻晴（test review） | Pending r1 | 6 gap 全采纳（详§13）|
| 帝君（Owner Accept） | Pending | r1 闭环后 re-set S3-DES-003 awaiting-approval |

---

## 13. r1 amend（胡桃 5 gap + 刻晴 6 gap）

凝光 PM 04:30 UTC 拦截 → design doc 与 task 拆分必须物理一致才能 awaiting-approval。

### 13.1 胡桃 dev review 5 gap

| Gap | 处置位置 |
|---|---|
| 1. PRECHECK-BACKEND task 缺失（critical）| board 新建 S3-DEV-003-PRECHECK-BACKEND + §11 拆分表补 |
| 2. 4 hook 触发点未说明 | §4.3 表 4 事件源 + after_commit hook + AC#4 |
| 3. WS handshake auth 未说明 | §5.1 / AC#3 补 「handshake 时校验 user token + order owner」 |
| 4. P95 SLO 未说明 | §5.2 补 「P95 cache hit ≤200ms / miss ≤800ms」 + AC#2 k6 perf test |
| 5. cert event ≤3s SLO 未拆 alg | AC#5 / §event-flow 表补 admin verify → aggregator.evaluate → WS broadcast 三段时限 |

### 13.2 刻晴 test review 6 gap

| Gap | 处置位置 |
|---|---|
| 1. WS ≤5s SLO 测试方法 | §4.1 补 「WS broadcast → 前端 onMessage ≤5s，含 1 次重连重试 1s/3s/5s」 + AC#4 量化 |
| 2. 4 张牌 ABAC 4 层 endpoint 对应 | §5.3 表补 「4 张牌 × 4 层 = 16 哨兵点」逐点拆 |
| 3. 文案 lint 规则可测试 | §3.3 补 「lint 规则列表：DENY_KEYWORDS=["失败","错误","异常堆栈"，worker 名列表动态加载]，CI script 跳脸」 |
| 4. iOS CI E2E 覆盖 round-trip | §6.2 补「macOS runner GitHub Actions matrix：H5↔native bridge 逐调用 + WKWebView 打开 + JSBridge 双向消息验证」 |
| 5. 灰度回滚触发指标量化 | §8 表补「触发上下限：ABAC 失血 >0 / WS 成功率 <95% / P95 >500ms / 转化率 -3%」 |
| 6. a11y 验收具体项 | AC#7 补「色盲 deuteranopia/protanopia/tritanopia 3 型模拟截图 + VoiceOver/NVDA + 键盘焦点」逐项验证 |
