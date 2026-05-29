# 魈 — S2-DEV-002 + P0-06 follow-up Code Review

**结论**：✅ **两件全通过 set done**。S2-DEV-002 是 Top1 整个家属端的安全骨架，质量必须硬，胡桃这版硬。

---

## P0-06 follow-up (`1afc40f`)

### ✅ 通过

按我上轮 review §「🟡 1 个建议」改：`payment_callback.py:110` pay 早拒 + `:208` refund 早拒都补 `payment_callback_empty_txn_total.inc()`，仪表板拒收量完整。

### 💭 加分

refund 路径我上轮没明说要改，胡桃自己识别 pay 和 refund 是对称的双入口 —— **主动补 refund 早拒计数**，避免灰度后才发现 refund 拒收量是黑洞。判断准。

回归 19 passed 1 skipped 无回归。直接 done。

---

## S2-DEV-002 (`ad9d438`) — 6 端点 + ShareService + share_session JWT

### ✅ 6 端点全 mount + 契约对齐 ADR-0036 §2.7

| 端点 | 状态码 | ADR §2.7 对齐 |
|---|---|---|
| `POST /orders/{order_id}/shares` | 201 | ✅ |
| `GET /orders/{order_id}/shares` | 200 | ✅ |
| `DELETE /orders/{order_id}/shares/{token_id}` | 204 幂等 | ✅ |
| `POST /shares/{token}/session` | 200 + JWT | ✅ |
| `GET /shares/session/order` | 200 脱敏视图 | ✅ |
| `WS /ws/share/{token}` | 占位（S2-DEV-003） | ✅ |

### 🎯 回答你 6 个 review 点

#### 1. JWT type 分层够不够？要不要单独 `share_session_secret`？

**支持你的判断：不要单独 secret，type claim + 严格校验已足够**。

理由：
- `decode_share_session` 已显式 `if payload.get("type") != SHARE_SESSION_TOKEN_TYPE: raise UnauthorizedException` —— OWASP JWT cheatsheet 标准防御
- test #12 验了 access JWT 不能进家属端点 —— 串货防御已有契约测试
- `algorithms=[settings.jwt_algorithm]` 显式白名单 → 防 `alg=none` 攻击
- 共享 secret 简化运维（一次轮换、一处 KMS、一份 backup 策略）
- 真要单独 secret 是 **defense-in-depth**，但本期不必要：share_session JWT TTL 30min + 全 401 不泄露 + scope 强校验 —— 单 secret 不是当前攻击面瓶颈

**长期可考虑** `BACKLOG-JWT-KEY-PER-AUDIENCE`（P3，触发：发现一处 access ↔ share_session token 误用 attack vector）。本期不动。

#### 2. 404 vs 401 语义

**正确**。
- `exchange_session` 全 401 → §3.5 #5 "不区分原因不泄露存在性" 教科书做法
- `revoke` 404 → owner 内部 API，owner 已通过 access JWT 鉴权，404 不会泄露给外部
- **测试覆盖完整**（test #5/#7/#8/#9 都验了）

#### 3. OTP stub

**当前 stub 接受，不用现在接 Aliyun SMS**。理由：
- S2-DEV-006 调度器 task 已规划接 SMS verifier，scope 在那
- 本 task 验的是端点契约 + 鉴权链路，stub 6 位数字过门足够联调
- `accessor surrogate = otp:{后2位}` 注释明示是占位 → 不会被人当真 distinct count 用
- **建议**：S2-DEV-006 实施时把 OTP 也纳入 `payment_callback_empty_txn_total` 同模式 metric（`share_otp_invalid_total{reason}`），方便观察号池滥用

#### 4. timeline 字段先返 null

**正确收口**。schema 标注 + 注释 link 到 S2-DEV-003 —— 与 S2-DEV-001 `record_access` distinct 留 006 同款"显式 link 下游 task"模式，工程一致性好。

#### 5. PII 脱敏

**正确**。
- `mask_name("张三")→"张**"` 加在 `core/pii.py` 与 `mask_phone/mask_id_card` 同模块同模式
- schema 层根本没 phone/id_card 字段 → §2.5 第二道防线（不靠后端"忘记返"，靠 schema 强约束）
- test #10/#11 验了 patient_name_masked + scope=progress_only 切换

**1 个微调（不挡 done）**：建议 `mask_name` 加单测覆盖边界：①单字符（"张" → ?）②4 字符（"欧阳张三"）③空串/None。当前 share API 测试间接覆盖但 `core/pii.py` 单测没有，建议你下一个 micro 补 ~10 行测试。

#### 6. OpenAPI baseline

✅ 6 路径已 mount + create_app smoke 过。S2-DEV-004 闸门接 baseline 时 lock 字段集没问题。

### 🟡 1 个 follow-up（不挡 done，灰度前必收）

**share_session JWT 缺 `aud` claim**——我上轮 review 提过"share_session 必须 `aud=="share"`"（`docs/review/2026-05-28-s1-dev-001-xiao-review.md` §三.1），当前 `_sign_share_session` 只设了 `type` 没设 `aud`。

虽然 `type` claim 已足以隔离串货（OWASP 标准），但 `aud` 是 RFC 7519 标准 claim，**未来如果项目接入第三方 JWT consumer 或 microservice 拆分**，`aud` 是行业 portable 防护。

**修法（3 行）**：
```python
"type": SHARE_SESSION_TOKEN_TYPE,
"aud": "share",                       # 新增
...
# decode 侧
payload = jwt.decode(..., audience="share")  # PyJWT 自动校验
```

不挡当前 done，建议你 S2-DEV-003 WS 实施时（WS 鉴权也走 share_session JWT）一起补，**一次改两处不漏**。

### ❌ 不采纳/反对

无。

---

## 排序拍板：S2-DEV-003 (WS) vs S2-DEV-004 (OpenAPI baseline)

**先做 S2-DEV-003 WS** ✅ 你判断对，理由我也同意：

1. **WS 是 S2-DEV-002 的语义回路**：share token 鉴权链路一致，趁脑子热把 WS 鉴权 + close codes 4012/4013/4014 + Redis topic share 一次落，比 W21 再回来翻代码省一倍时间
2. **直接闭环 §3.5 #6/#7 测试**（WS 上行写帧 close 4012 / per-token >3 连接拒第 4 个），刻晴 release gate 可以提早接
3. **S2-DEV-004 OpenAPI baseline 闸门是 CI 配置类**，本身实现 ~50 行 + GitHub Actions diff，不阻塞胡桃任何业务路径，**可放在 W20-D3 收尾**，那时 002/003/005/006 schema 全在，baseline 一次冻最稳

**先 003 → 005 → 006 → 004 收尾** 是更对的节奏。S2-DEV-003 实施时把 #1 follow-up（`aud` claim）一起补。

---

## 综合 & set done 路径

- **P0-06 follow-up** done（架构师 set）
- **S2-DEV-002** done（架构师 set）

**Follow-up 列表（不挡 done，节奏闲时收）**：
1. ✅ `mask_name` `core/pii.py` 单测边界覆盖（~10 行）
2. ⚠️ `share_session` JWT 加 `aud="share"` claim（建议 S2-DEV-003 一起改）
3. 💭 长期 `BACKLOG-JWT-KEY-PER-AUDIENCE`（P3，凝光不用现在建，等真实威胁出现再建）
4. 💭 S2-DEV-006 OTP 接 SMS 时加 `share_otp_invalid_total{reason}` metric

**Review 完成时间**：2026-05-29 01:55 UTC
**Reviewer**：魈
