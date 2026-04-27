# ADR-0029 F-03 紧急呼叫的地理坐标 + PII 字段保留 180 天 + 加密落地策略

- 日期：2026-04-27
- 状态：Accepted
- 决议来源：D-043（DECISION_LOG，原晨会代号 D-042，与 OrderService 拆分撞号已改记 D-043）
- 关联：F-03 紧急呼叫（PR #32）、ADR-0026（outbound 可靠性，audit_event 同源）
- 参与角色：Arch / PM

## 背景

F-03 紧急呼叫功能（PR #32）已上线，三类高敏数据进入生产数据面：

1. **紧急联系人手机号**：`emergency_contacts.phone`（VARCHAR(20)，明文）。患者预设的 1-3 位亲属或监护人手机号，**强 PII**，且通常关联非用户本人。
2. **触发事件中的被呼号码**：`emergency_events.contact_called`（VARCHAR(50)）。命中 `contact_type='contact'` 时是亲属手机号，命中 `'hotline'` 时是平台客服号。
3. **触发地点**：`emergency_events.location`（VARCHAR(255)，目前后端实测以字符串形式落库，前端在「紧急呼叫」前会请求 `wx.getLocation` 拿到经纬度文本拼入）。**等同于地理坐标**，在《个保法》和 GB/T 35273 下属敏感个人信息。

合规约束：

- 《个人信息保护法》第 28 条：敏感个人信息（含医疗健康、行踪轨迹、不满 14 周岁未成年人）需「特定目的、充分必要、严格保护」。
- 《信息安全技术 个人信息安全规范》(GB/T 35273-2020) §6.1：保留期应「实现处理目的所必需的最短时间」。
- 医疗陪诊场景下，紧急呼叫数据的处理目的是「事件复盘 + 申诉举证 + 监管协查」，业内惯例是 6 个月内调用率即趋零。

现状问题：

1. `emergency_contacts.phone` / `emergency_events.contact_called` / `emergency_events.location` 全部明文落库，仅靠 ACL 兜底，没有应用层加密。
2. 没有任何后台 cron 在清理过期 emergency 数据，长期累积 = 长期暴露面。
3. 隐私政策（`docs/PRIVACY_POLICY.md` §5.2 / §8）只写了「账号注销 30 天内删除 + 敏感字段数据库加密」的通用口径，对紧急呼叫的「行踪轨迹」未单列保留期与告知方式。
4. 用户主动注销时，目前注销链路并未显式清理 `emergency_*` 两张表（依赖外键级联是不够的，因为 `order_id` 在事件中是 `nullable`，`patient_id` 才是关键 FK，需要单独 sweep）。

晨会决议把这些落到一条 ADR 一次说清，由 Arch 自审 + PM 补合规口径后归档。

## 决策

### 1. 保留期：180 天（地理坐标 + 触发事件 PII 同适用）

- `emergency_events.location`、`emergency_events.contact_called`：**触发后 180 天**清理。
- 清理策略 = **软删 + 字段置空**：
  - 第 90 天：触发后端 cron `cleanup_emergency_pii.py` 进入 *grace 阶段*，对到期事件**仅做告警与统计**（不动数据），避免误清。
  - 第 180 天：硬清理，把 `location` 置 `NULL`、`contact_called` 替换成「`***保留事件元数据***`」，保留 `id / patient_id / order_id / contact_type / triggered_at`，使审计与申诉举证仍可追溯到「谁在什么时间触发了什么类型的紧急呼叫」，但拿不到具体被呼号码与坐标。
- `emergency_contacts`（联系人本身）**不在 180 天清理范围**：联系人是配置数据（用户主动维护），跟随用户账号生命周期，由 §3「注销硬删」覆盖。

### 2. audit_event 中的 PII 字段同步处理

- 走 `app.services.admin_audit` 写入的「emergency.trigger」类事件，其 `payload` 字段中包含的 `phone` / `location` 同样在 180 天点位上**就地脱敏**（用 `app.core.pii.mask_phone` 把手机号改写成 `138****0001`，把 location 替换为 `"***pruned***"`）。
- 保留事件元数据：`event_type / actor_id / target_id / created_at / outcome`，确保安全审计链不断。

### 3. 用户主动注销 → 立即硬删，不等 180 天

- 注销链路（`/api/v1/users/me`，DELETE）需要**显式 sweep**：
  1. `DELETE FROM emergency_contacts WHERE user_id = :uid`
  2. `DELETE FROM emergency_events  WHERE patient_id = :uid`
  3. 走 audit_event 的 PII 脱敏分支（同 §2，但立即执行）。
- 这条与隐私政策 §5.2「账号注销 30 天内完成删除或匿名化」并不冲突：emergency 这一族被显式拉到「立即」。

### 4. 紧急联系人手机号的应用层加密（AES-256 + KMS 主密钥）

- `emergency_contacts.phone` 与 `emergency_events.contact_called`（仅 `contact_type='contact'` 时）**应用层加密**落库。
- 算法：**AES-256-GCM**（authenticated encryption），nonce 12B 随存随生成，存储格式 `base64(nonce || ciphertext || tag)`，**不依赖 DB 透明加密（TDE）**。
- 密钥层级：
  - **主密钥（KEK）** 托管在云厂商 KMS（阿里云 KMS / 腾讯云 KMS，二选一，取决于 B-03 落地结果）。
  - **数据密钥（DEK）** 走信封加密：每次启动时通过 KMS `Decrypt` 拿一次 DEK，缓存进进程内存（不落盘）。
  - 轮换：DEK 每 90 天一次；密文中携带 `key_version` 头，支持平滑切换。
- 配套查询：手机号查重需要可比性，新增 `phone_hash`（HMAC-SHA256(salt=PII_HASH_SALT, phone) → 16 字节十六进制）做唯一索引；手机号原文不进 WHERE 子句。这一步沿用 ADR-0026 已有 `app.core.pii::hash_phone()` 实现，零额外成本。
- **不加密**的字段：`name` / `relationship` / `contact_type` / `triggered_at` / `location`：
  - `name` / `relationship` 单独不可识别个人，且涉及搜索展示，加密性价比低。
  - `location` 性价比同上（且本身已在 180 天后清空），但**禁止**进入索引或日志。

### 5. 保留期实现位置

- 新增定时任务：`backend/app/cron/cleanup_emergency_pii.py`
  - 调度：每天 03:00 GMT+8（与 `outbound_call` retry 等其它 cron 错峰，避开 02:00 备份窗口）。
  - 执行：
    - 第 90 天阶段：`SELECT count(*) FROM emergency_events WHERE triggered_at < now() - interval '90 days' AND triggered_at >= now() - interval '180 days' AND location IS NOT NULL`，结果发企业微信群（同 D-040 的 Alertmanager webhook）。
    - 第 180 天阶段：`UPDATE emergency_events SET location = NULL, contact_called = '***pruned***' WHERE triggered_at < now() - interval '180 days' AND location IS NOT NULL`，并对 audit_event payload 做同等清理。
  - 单次跑完后写一行 `cron_run_log`（与现有运维表统一），出现非零失败时拉企业微信告警。

## PM 合规口径

> 本节由 PM 维护，研发只在结构变化时通知 PM 同步更新，不要直接改文案。

### 1. 隐私政策同步增补

`docs/PRIVACY_POLICY.md` 需在以下三处同步：

- **§5.2 存储期限**：在「客服与申诉记录：自纠纷解决之日起 3 年」之下追加一条：
  > 紧急呼叫事件相关数据（被呼号码、触发地点）：自触发之日起保留 **180 天**，到期后系统自动清理被呼号码与地点信息，仅保留事件元数据用于安全审计与监管协查；紧急联系人配置随账号生命周期保存。
- **§8 安全保护措施 / 存储安全**：把「敏感字段（手机号、身份证）数据库加密」明确成：
  > 敏感字段（手机号、身份证、紧急联系人手机号）采用应用层 **AES-256-GCM** 加密，密钥由云厂商 KMS 托管并定期轮换；数据库层无法直接读出明文。
- **第六节 您的权利 / 删除**：在 30 天注销保留期之外注明：
  > 紧急呼叫数据是例外：账号注销请求一旦确认，紧急联系人与紧急呼叫事件中的被呼号码、地点信息将**立即**硬删，不等 30 天保留期。

### 2. 用户告知方式

- **首次启用紧急呼叫**（首次进入「紧急呼叫」入口或首次添加紧急联系人）时，前端弹出 **强制确认弹窗**，文案最少包含：
  - 数据用途：仅用于紧急情况下联系您的亲属 / 客服热线，并保留事件证据。
  - 保留期：被呼号码 / 地点保留 180 天，到期自动清理。
  - 加密说明：手机号采用 AES-256 加密落库。
  - 链接：跳转 `docs/PRIVACY_POLICY.md` 的对应锚点。
- 弹窗仅一次，前端写本地 flag `emergency_pii_consent_v1`；版本字段允许我们将来文案有重大变更时强制重弹。
- 后端 audit：弹窗确认动作走 `admin_audit.log_event("emergency.consent_v1", ...)`，与本人签名同等留痕。

### 3. 数据导出 / 删除请求 SLA

- 一般个人信息：维持隐私政策第六节「15 个工作日」口径不变。
- **紧急呼叫数据**例外：导出 / 删除请求 **72 小时内**响应（与隐私政策 §8「安全事件 72 小时通知」对齐节拍），原因是行踪轨迹时效性强、申诉窗口短。
- 操作通道：邮件 `legal@yiluan.example`；后台运营有专门工单类型「F-03 / emergency」，单走 PM + 法务双签流程。

### 4. 监管备案

- **不需要单独备案**，纳入医路安平台医疗陪诊业务的总体合规框架（已走过的网信办 App 备案 + 即将走的 ICP 备案 B-04）。
- 若未来法规口径变化（特别是「行踪轨迹 + 医疗 + 未成年人」三者叠加被特殊认定），由 PM 在每月合规盘点会上重新评估，必要时升级为「敏感个人信息处理活动事前评估（PIA）」并补本 ADR 的修订条目。

## 后果

### 正面

- **合规对齐**：满足《个保法》第 28 条「最小必要 + 严格保护」与 GB/T 35273 §6.1「最短保留时间」的硬要求。
- **数据最小化**：到期后即使数据库泄漏，攻击者也拿不到 180 天前的被呼号码与坐标。
- **用户可控**：注销即立即硬删 emergency 数据，让用户对最敏感的字段拥有「立即可执行的删除权」。
- **审计可追溯**：保留事件元数据，监管协查与内部申诉链路不被破坏。

### 负面

- **新增 cron 维护成本**：`cleanup_emergency_pii.py` 是新增的有状态任务，必须监控（FOLLOW-UP-1）。
- **依赖 KMS 接入**：B-03（ACR + 服务器）落地之前，KMS 客户端 SDK 没法在生产环境真用，过渡期采用 `app.core.pii::EnvelopeKey` 的 *本地 KEK fallback*（KEK 走环境变量），**这条本身是技术债**，必须随 B-03 一起切到云 KMS（FOLLOW-UP-2）。
- **现存数据回填**：上线前已有的 emergency_contacts / emergency_events 是明文，需要一次性迁移脚本 `migrations/2026_04_27_encrypt_emergency_pii.py`，跑期间需要短暂只读。

### 中性

- emergency 表查询性能：日均触发量在内测期 < 10 / day，180 天累积 < 2k 行；加密改造对查询无可见影响。
- `phone_hash` 唯一索引会让「修改联系人手机号」这一动作走「先 verify hash → 再覆写密文」两步，比当前的「直接 UPDATE」多一次 SELECT，可忽略。

## 备选方案

| 方案 | 否决理由 |
| --- | --- |
| **永久保留**（不清理） | 直接违反 GB/T 35273 §6.1「最短保留时间」；攻击面随时间线性扩大；极端场景下监管检查会要求当场拉警报。 |
| **30 天保留**（更激进） | 与「客服与申诉记录 3 年」的口径反差过大，纠纷申诉窗口（医疗类纠纷常常超过 30 天才浮出水面）会因证据丢失而无法举证；运营复盘窗口也不够。 |
| **不加密、只 ACL** | DBA / 运维 / 备份介质三个口都能直接读出手机号；与隐私政策 §8「敏感字段数据库加密」承诺直接矛盾；KMS 接入成本可控（约 0.5 人周），不应省。 |
| **DB 透明加密（TDE）替代应用层加密** | TDE 保护的是「磁盘 / 备份介质」，对持有数据库连接的内部人员零防护；本场景的威胁模型恰恰是内部人员误用 + SQL 注入，TDE 不解决。 |
| **整段表级别加密** | 把 `name / relationship / triggered_at` 也加密会破坏排序、分页与展示，性价比极差。 |

## Follow-ups

- **F-1 (FOLLOW-UP-1)**：研发实现 `backend/app/cron/cleanup_emergency_pii.py`，含 90 天 grace 告警 + 180 天硬清理；负责人：Backend；目标：本周内完成 + 灰度跑一周。
- **F-2 (FOLLOW-UP-2)**：KMS 接入（依赖 B-03 ACR / 服务器到位）。临时走 `EnvelopeKey` 本地 KEK fallback，必须在 B-03 完成后 1 周内切到云 KMS；负责人：Arch + DevOps。
- **F-3 (FOLLOW-UP-3)**：PM 同步更新 `docs/PRIVACY_POLICY.md` §5.2 / §6 / §8 三处文案（见 PM 合规口径 §1），并在前端「紧急呼叫」入口接入 `emergency_pii_consent_v1` 弹窗；负责人：PM + 前端。
- **F-4 (FOLLOW-UP-4)**：一次性迁移脚本 `migrations/2026_04_27_encrypt_emergency_pii.py` 把存量明文回填为密文 + 写入 `phone_hash`；负责人：Backend；上线窗口：F-2 之后第一个发版窗口。
