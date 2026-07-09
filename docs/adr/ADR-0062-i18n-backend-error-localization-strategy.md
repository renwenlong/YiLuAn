# ADR-0062 — i18n 后端错误文案本地化策略（方案 C：复用既有 error_code 基础设施）

> **状态：** Proposed（I18N-REQ-001 review 阶段架构决策，待帝君拍板 §6 方案）
> **作者：** 魈（架构师）
> **创建：** 2026-07-09
> **关联：** PRD-I18N-001 §2.2 / §6（FR-6）、I18N-REQ-001（requirement）
> **上游证据仓：** `/home/wenlongren/repo/YiLuAn` @ `bef9ea8`

---

## 1. 背景

PRD-I18N-001 §2.2 / §6 就"界面切英文时后端返回的中文错误消息如何本地化"给出两方案，并默认方案 A：

- **方案 A（PRD 默认）**：前端对已知错误场景做**客户端兜底翻译/映射**（前端持有 error message 文本 → i18n key 映射），后端不改。
- **方案 B（PRD 判为后续）**：后端从零引入 `error_code` 机制 + `Accept-Language`，工作量大，单独立项。

**Review 阶段 evidence-first 核查 main HEAD 物理事实，发现 PRD 对后端基础设施的描述与代码实况不符**，该差异直接改变方案取舍，故立本 ADR。

---

## 2. 关键物理事实（实测 @ `bef9ea8`，非印象）

| PRD §6 表述 | 代码实况（grep 证据） | 判定 |
|---|---|---|
| "后端**无** `error_code` 机制" | `backend/app/core/error_codes.py` **已存在**：机器可读 error_code 注册表（`PHONE_REQUIRED` / `ORDER_TRANSITION_INVALID` / `PAYMENT_REQUIRED` / `OTP_INVALID` … 数十个常量，按域分组） | ❌ PRD 表述错误 |
| （隐含）异常层不支持 error_code | `backend/app/exceptions.py:AppException(error_code=...)` **已支持** `error_code` 入参 + envelope `{"error_code": ..., "message": ...}`（`_build_detail`），全部子类 `NotFound/Unauthorized/Forbidden/BadRequest/...` 透传 | ❌ 基础设施已就位 |
| "后端 raise 约 20~30 条中文错误" | 生产代码（排除 tests/venv/支付回调内部）**用户可见中文 raise ≈ 16 条**，且有重复（"原订单未支付成功，无法退款" 出现 2 处） | ⚠️ 量级更小、可枚举 |
| error_code 已在被消费 | **iOS `APIClient.swift` 已有完整 dispatch**：decode `error_code` → `switch`（phoneRequired/paymentRequired/verificationRequired）→ fallback `detail`。**code-ready** | ✅ iOS 侧已就绪 |
| （error_codes.py docstring 声称）`wechat/services/request.js` 消费 code | **该文件不存在**（`wechat/services/` 有 `api.js` 等，无 `request.js`）。docstring 为 stale/aspirational | ⚠️ 微信侧 dispatcher 未建 |
| 已带 error_code 的 raise 数量 | **0**（注册表 + 异常入参齐备，但 raise 站点尚未 attach code） | ⚠️ infra 未在 raise 站点接线 |

**核心结论：** 后端不是"无机制"，而是"**机制已建 70%，仅 raise 站点未接线 + 微信侧 dispatcher 缺失**"。方案 B 的"从零建体系、工作量大"是**幻影成本**。

---

## 3. 方案对比

### 方案 A（前端按中文文本匹配翻译）
- **做法**：前端持 `"订单状态不允许请求开始服务" → i18n key` 的文本映射表，命中即替换。
- **优势**：后端零改动。
- **劣势（阻塞级）**：以**后端中文文案字符串**为匹配键 → **后端任何文案微调（改标点/措辞）都静默击穿映射**，回退显示中文且无告警。脆弱、反 DRY、跨端各维护一份中文表。与仓库**既有 error_code 方向背道而驰**（iOS 已按 code dispatch，方案 A 等于让前端同时维护 code 分支 + 中文文本分支两套）。

### 方案 B（从零建 error_code 体系）
- **做法**：PRD 设想的新建 error_code + Accept-Language。
- **判定**：**伪命题**。error_code 注册表 + AppException 入参 + iOS dispatcher 已存在，无需"从零"。若指"后端按 Accept-Language 返回已翻译文本"，则把翻译职责放后端，与 iOS 现有"前端按 code 决定 UX/文案"架构冲突，且需后端引入译文资源，反而更重。

### 方案 C（推荐）— 复用既有 error_code 基础设施，前端按 code 映射译文
- **做法**：
  1. **后端**：给 §2 那 ≈16 条用户可见 `raise` **attach 既有 error_code**（`raise BadRequestException("订单状态不允许请求开始服务", error_code=error_codes.ORDER_TRANSITION_INVALID)`）。补齐 `error_codes.py` 缺的常量。**不新建机制**，只接线。
  2. **前端**：iOS 扩展现有 `switch`（加 case + 用 i18n 按 code 取译文，替代硬编码中文 fallback）；微信**新建 dispatcher**（对齐 iOS，`error_code → t(key)`）。
  3. 前端把 error_code → i18n key 纳入统一术语表/字典（与 PRD §7 同源），中英一致。
- **优势**：以**稳定的机器码**为契约（后端改文案不击穿前端）；顺着仓库既有架构（iOS 已如此）；跨端一致；后端改动小（16 处 + 常量补齐）；未覆盖码可回退 detail 文本并登记。
- **劣势**：需后端配合改 16 处 raise（但成本远低于 PRD 对方案 B 的估计）；微信侧要补 dispatcher（本就是 i18n 工程一部分）。

---

## 4. 决定

**推荐方案 C。** 理由：方案 A 以中文文本为键**脆弱**且与既有 error_code 架构相悖；方案 B 的"从零建体系"是幻影成本（基础设施已存在）。方案 C 复用已建 70% 的 error_code 通路，以机器码为契约，跨端一致、后端改动小、抗后端文案漂移。

> **最终 §6 采纳哪个方案属帝君拍板项**（PRD §8 开放问题 1）。本 ADR 提供 evidence 修正 PRD 的方案取舍前提：真正的选择不是"A 兜底 vs B 重建"，而是"**A 脆弱兜底 vs C 复用既有 code 通路**"。

---

## 5. 后果

- **PRD §2.2 / §6 / §8-1 需据实修正**：删除"后端无 error_code 机制"表述；方案改列为 A vs C；标注 error_code 基础设施现状（infra 就位、raise 未接线、微信 dispatcher 缺失）。
- **design 阶段拆分新增两项**（原 PRD §6 建议基础上）：
  - `后端 error_code 接线`（≈16 处 raise attach code + 补常量）— develop
  - `微信 error_code dispatcher`（对齐 iOS `APIClient` 现有 dispatch）— develop
- **error_codes.py docstring 需更正**：`wechat/services/request.js` 路径不存在，改指向实际将建的微信 dispatcher 位置。
- **术语表（PRD §7）扩展**：纳入 error_code → 中/英 文案映射，作为前端字典 SSoT。
- 未被 code 覆盖的低频错误：前端回退显示 `detail`（中文），测试报告登记未覆盖清单（沿用 FR-6）。

---

## 6. 附：证据命令（可复现）

```bash
cd /home/wenlongren/repo/YiLuAn   # @ bef9ea8
# error_code 注册表存在
cat backend/app/core/error_codes.py
# AppException 支持 error_code + envelope
sed -n '1,30p' backend/app/exceptions.py
# 用户可见中文 raise ≈16（排除 tests/venv/支付回调内部）
grep -rnP 'raise \w+.*[\x{4e00}-\x{9fff}]' backend/app --include=*.py \
  | grep -vP 'wechat\.py|callback|precheck_abac_metrics|probes/__init__|config\.py|git_blame'
# 已 attach code 的 raise = 0（infra 未接线）
grep -rnP 'raise \w+Exception\([^)]*error_code' backend/app --include=*.py | grep -v test | wc -l
# iOS 已有 dispatch
sed -n '150,175p' ios/YiLuAn/Core/Networking/APIClient.swift
# 微信 dispatcher 不存在
ls wechat/services/request.js   # -> No such file
```
