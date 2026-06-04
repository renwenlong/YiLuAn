# ADR-0045 — Storage 后端选型（陪诊师证件图 Phase B 生产化）

> 状态：**Accepted（帝君 2026-06-04 08:50 UTC 拍板 Azure Blob Storage）** · 作者：魈 · 日期：2026-06-04 r1 amend
> 关联：ADR-0044 r1 §4.2 / S2-DES-005 / PR #158 调研 / 凝光 04:18 UTC PM 推 OSS / 帝君 08:50 UTC 拍 Azure
> 触发：ADR-0044 r1 Phase A mvp 本地+HMAC 灰度过渡，Phase B 必须有正式 storage 后端承接
> Owner Approval：帝君

---

## 1. 背景

ADR-0044 r1 §4 把证件图 storage 分两阶段：

- **Phase A**：local `backend/static/cert/` (DB schema = `cert-image://`) + HMAC 自签反代（mvp，灰度过渡，~1.5d）
- **Phase B**：生产化 storage 后端 + STS 直传 + 历史迁移（本 ADR 范围）

Phase A 已可上灰度。Phase B 需在灰度数据沉淀（~1-2 个月）后正式切换，避免本地存储成为生产瓶颈：
- 不分布式（多副本部署只能 1 worker 持文件）
- 备份/容灾依赖磁盘快照（手动）
- 单机磁盘上限（cert 图 5MB × 万级陪诊师 ≈ 几十 GB）
- 无 CDN 加速

**业务侧评估看凝光 PM 专项评估表**：`~/.openclaw/workspace-ningguang/yiluan-storage-backend-pm-eval.md`（凝光 06:23 UTC 起草，含 10 维度业务侧对比 + 推荐理由 + vendor lock-in 对冲建议）。本 ADR 架构侧选型在凝光业务评估基础上叠加 SDK / STS / 迁移 / 运维技术维度。

---

## 2. 选型对比

### 2.1 候选

| 候选 | 厂商 | API 风格 | 中国可用 | 价格（华东，~1TB+月） |
|------|------|---------|---------|---------|
| **A. OSS** | 阿里云 | OSS SDK + STS + presigned URL | ✅ 主选 | 标准 ¥0.12/GB·月 + 流量 |
| **B. Azure Blob** | 微软 | Blob SDK + SAS | ✅（中国版需 21Vianet）| 类似 OSS |
| **C. AWS S3** | AWS | S3 SDK + presigned URL | ⚠️ 中国版宁夏/北京（光环新网/西云）| 类似 |
| **D. 本地保留** | — | upload.py + HMAC | ✅ 现状 | 0 第三方 |
| **E. MinIO 自建** | — | S3 兼容 + IAM | ✅ | 服务器自费 + 运维 |

### 2.2 决策矩阵

| 维度 | A. OSS | B. Azure Blob | C. AWS S3 | D. 本地保留 | E. MinIO |
|---|---|---|---|---|---|
| 团队现有账号 | ✅ 凝光阿里云 SMS 同账号（zero overhead）| ⚠️ 需 21Vianet 新账号 | ⚠️ 需中国版账号 | — | ⚠️ 需服务器 |
| SDK 成熟度 (Python) | ✅ oss2 | ✅ azure-storage-blob | ✅ boto3 | — | ⚠️ minio-py |
| STS 直传支持 | ✅ 原生 RAM Role | ✅ User Delegation SAS | ✅ Federation Token | ❌ 自实现 | ✅ STS-like |
| 中国合规备案 | ✅ 已有阿里云主体可挂 | ⚠️ 21Vianet 备案另起 | ⚠️ 中国版独立合规 | ✅ | ✅ |
| CDN 集成 | ✅ 阿里云 CDN + 私有 bucket | ✅ Azure CDN | ✅ CloudFront | ❌ | ⚠️ 自建 |
| 多区域容灾 | ✅ OSS 跨区复制 | ✅ GRS/RA-GRS | ✅ Cross-Region Replication | ❌ | ⚠️ 自建 |
| 灰度过渡复杂度 | ✅ 历史本地→OSS 迁移 cron | ✅ 同 | ✅ 同 | — | ⚠️ 需先建集群 |
| 长期维护成本 | 🟢 低（云托管）| 🟢 低 | 🟢 低 | 🔴 单机扩容/备份 | 🔴 自运维 |
| 灰度期成本 (~10GB) | ¥1.2/月 | 同量级 | 同量级 + 跨境流量 | 0 | 服务器 ¥100+/月 |
| 退出成本 | 🟡 数据迁出流量费 | 🟡 同 | 🟡 同 | 🟢 一份本地文件 | 🟢 自有 |

### 2.3 排除

- **D. 本地保留**：Phase A 已实现（mvp），Phase B 目的就是替代 D。保留意味 Phase B 不做，业务量上去后必出问题。**排除**
- **E. MinIO 自建**：自运维开销 + 团队无 DevOps 专职 + 容灾自建 > 云 OSS 直用。**排除**
- **C. AWS S3**：中国版账号需另起 + 跨境流量费 + 与现有阿里云生态不一致。**不推荐**
- **B. Azure Blob**：21Vianet 备案另起 + 团队无 Azure 经验。**不推荐**

### 2.4 Owner 拍板：**B. Azure Blob Storage**（帝君 2026-06-04 08:50 UTC 拍）

> **拍板与凝光 PM 推荐分歧**：凝光 PM 评估表推 OSS（阿里云 SMS 同账号 + 国内访问最优 + 合规最低风险）。帝君拍 Azure 推翻，可能基于：(a) 多云保险与已有阿里云 SMS 互补 / (b) Azure AI 与未来 AI 摘要协同 / (c) W19-P0-08 emergency PII PDF Azure Blob SAS 模式已有先例。本 ADR 按 Owner 拍板执行。

**Azure Blob 5 理由**（架构师从帝君拍板动机推断 + 技术维度叠加）：
1. **多云策略 + 风险分散**：Azure Blob 与阿里云 SMS 互补，避免单云政策风险（任一云政策调整 / 账号封禁不全停）
2. **Azure AI / Cognitive Services 与未来 AI 摘要协同**（PRD-001 §F2 AI 就诊准备包）：cert image OCR 走 Azure Form Recognizer / 摘要走 Azure OpenAI 同账号生态
3. **W19-P0-08 emergency PII PDF Azure Blob SAS 已有先例**：团队对 azure-storage-blob SDK + User Delegation SAS 模式有实战经验，不是从零选型
4. **Azure Blob diagnostic logs 完整度**：与 Azure Sentinel 集成审计能力优于 OSS access log，对 PII 极敏感数据合规审计更友好
5. **User Delegation SAS 不依赖长期 access_key**：service principal 配合 SAS 短期凭证比 OSS STS RAM key 更安全（Azure 模型更先进）

**Azure 21Vianet 关键约束（vs 凝光 OSS 推荐）**：
- ❌ 21Vianet 中国版账号申请周期 1-3 周（OSS 同账号 5min 即开）— 见 §7 风险表
- ❌ 21Vianet 备案另起（OSS 已有阿里云主体可挂）
- ❌ 成本 ~¥5/月（OSS ~¥1.2/月，但量级可忽略）
- ✅ 多云保险 + Azure AI 生态 + W19-P0-08 经验 — 帝君判断这些价值 > 21Vianet 申请周期成本

**vendor lock-in 对冲**（凝光 PM 评估建议 + 本 ADR 采纳）：
- 实现层加 `backend/app/services/storage_backend.py` factory 抽象（`StorageBackend` ABC）
- Azure 实现 `AzureBlobStorageBackend`；未来 OSS/S3 切回只需 implement 同 ABC 接口
- 业务代码依赖 ABC 不依赖具体 SDK，未来迁移代价 ~1d（不是重写）
- 迁移未发生时 Azure Blob 是唯一 backend，ABC 仅加一层 1-line indirection 不增复杂度
- Azure 原生能力（如 Form Recognizer/Sentinel）可选择性穿透抽象层（业务评估后决）

---

## 3. 实施分阶段（A 拍后启动）

### 3.1 P0：账号 + bucket 准备（凝光，~30min）

- 凝光 Azure Portal (21Vianet 中国版) 创建 service principal `yiluan-cert-upload`
- container `yiluan-cert-{env}` (Azure Blob 用 container)（staging / production 分 container）
- public access level: **Private (no anonymous access)** (Azure Blob 默认即 private)
- 服务端加密：Azure Storage Service Encryption (SSE) 默认 AES-256，无需托管 Key Vault
- 跨区域复制：staging 不开；production GRS (Geo-Redundant Storage) 主区 + 备份区
- container access policy: 只允许指定 service principal RBAC role 读写
- **RBAC 最小权限 + deny-list**（刻晴 review 可测建议 #2）：service principal 仅授 `Storage Blob Data Contributor` (read+write on specific container path)，**显式 Deny list-container / delete-blob / cross-container / all-other**。staging 集成测：试 list_containers 应 403 / 试 delete_blob 应 403 / 试 cross-container 应 403

### 3.2 P1：STS 服务（胡桃，~0.5d）

- 新增 `backend/app/services/storage_azure.py` (命名通用化以备未来切，本期实现 Azure Blob 后端)：
  - `get_upload_sas(companion_id)` → 返 `{sas_token, blob_url, expires_at, container, blob_path}`，User Delegation SAS, TTL 15min
  - `get_download_signed_url(blob_path)` → 返 Azure Blob SAS URL, TTL 15min
- ENV：`AZURE_STORAGE_ACCOUNT_NAME` / `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET` / `AZURE_TENANT_ID` (service principal 三件套) / `AZURE_CONTAINER_PROD` / `AZURE_CONTAINER_STAGING`
- backend startup guard：production 必须配 AZURE_*，缺则 fail-fast（同 ADMIN_API_TOKEN 加固模式）
- **blob_path 命名规约**（胡桃 review 补 #1）：`cert/{companion_id}/{uuid4}.{ext}`，**前缀 + uuid4 由 backend 生成**，前端不可自由命名（防 path traversal / 命名冲突）。User Delegation SAS 限定 `container/cert/{companion_id}/*` path scope
- **ENV 名对齐 SDK**（胡桃 review 补 #1）：`AZURE_STORAGE_ACCOUNT_NAME` / `AZURE_CLIENT_*` 与 azure-storage-blob SDK 默认 service principal 命名一致

### 3.3 P2：上传端点（胡桃，~0.5d）

- `POST /api/v1/admin/companions/{id}/certify-image-upload` 改返 SAS 临时凭证（不接收 multipart）
- admin-v2 用 `@azure/storage-blob` SDK 直传 Azure Blob（前端不经过 backend）
- 上传成功后 admin-v2 调 `POST /api/v1/admin/companions/{id}/certify-image-commit { blob_path }` 写 DB `certification_image_url=azure-blob://container/blob_path`
- audit_log: action=upload_cert_image / commit_cert_image
- **新旧端点共存策略**（胡桃 review 补 #2）：原 `POST /admin/companions/{id}/certify-image-upload` (multipart) 保留 deprecated 状态返 410 Gone + 文档指向新 STS 端点。admin-v2 PR 与 backend PR 解耦，互不阻塞 merge 时刻

### 3.4 P3：detail endpoint 改返 Azure Blob SAS URL（胡桃，~0.25d）

- `GET /admin/companions/{id}` 服务侧检查 cert_url 前缀：
  - `azure-blob://...` → 走 storage_azure.get_download_signed_url (User Delegation SAS, TTL 15min)
  - `cert-image://...` → 仍走 Phase A HMAC 反代（兼容历史）
- **prefix dispatch 用 strategy pattern**（胡桃 review 补 #3）：`CertImageURLDispatcher` 含 `azure-blob://` → `AzureBlobCertImageStrategy` / `cert-image://` → `LocalHMACCertImageStrategy` 注册表，新增 schema (未来 OSS/S3 切换) 仅注册不改 detail endpoint 主路径
- admin-v2 drawer 不改

### 3.5 P4：历史迁移 cron（胡桃，~0.5d）

- `backend/scripts/migrate_cert_to_oss.py`：
  - 扫 DB `WHERE certification_image_url LIKE 'cert-image://%'`  # 待迁本地
  - 读本地文件 → Azure Blob upload_blob → 更新 DB
  - dry-run / batch / 断点续传 / 失败上报
  - **migration_state 表持久化进度**（刻晴 review 可测建议 #3）：新增 `cert_migration_state(companion_id, src_path, oss_object_key, status='pending|copying|migrated|failed', last_error, updated_at)` 表，cron 每条 row 状态机推进。中断重启从 `WHERE status IN (pending, copying)` 续传。便于 admin 后台查询迁移进度 + 失败重试 + 人工干预
  - **零 downtime 设计**（刻晴 PM review 补）：detail endpoint 双前缀兼容 `azure-blob://` + `cert-image://`，迁移期间两套并存，最终 DB 全切到 `azure-blob://` 后反代路由才废弃。迁移期 admin 看证件图不中断。
  - 跑完 verify：随机抽 10% 重新签 URL 验可下载
- 跑通后 Phase A 反代路由废弃（保留 unit test stub）
- **cron 绝对不删本地文件**（胡桃 review 补 #4 + 刻晴 review 强约束 #1 升级）：本地 `backend/static/cert/*` 留**至少 30 天 Azure Blob-only 观察窗口 + 90 天冷备**后由帝君 manual confirm 才能人工清理。cron 仅做"复制到 Azure Blob + 更新 DB + 标 migration_state=migrated"，**绝对不做 delete**。事故回退路径依赖本地文件仍在。详 §5 切换策略
- **审计连续性（刻晴 PM review 补）**：`admin_audit_log` action=`view_cert_image` target_id=companion_id 表 schema 不变，仅 `access_object_path` 字段由 `cert-image://...` 变 `azure-blob://...`。同一 companion_id 跨 storage 后端可连续查，**审计无断层**。

### 3.6 P5：监控 + 验收（胡桃 + 凝光，~0.25d）

- Prometheus metric: `azure_blob_upload_total / azure_blob_download_total / azure_blob_upload_duration_seconds`
- **histogram bucket 明示**（胡桃 review 补 #5）：`azure_blob_upload_duration_seconds` buckets = `[0.1, 0.5, 1, 2, 5, 10, 30]` (cert 图典型 < 2s)
- **降级 metric 告警**（胡桃 review 补 #5）：`azure_blob_degrade_total{from="azure_blob", to="local_hmac", reason}` counter，>= 1 触发 P1 alert (Alertmanager 路由运营 + 凝光 + 胡桃)
- Grafana dashboard 加 Azure Blob 调用面板（挂 OPS-010 监控）
- 单测 + staging 集成测：SAS 过期拒 / signed URL 篡改拒 / Azure Blob 不可用降级（degrade 到 Phase A）
- **迁移后审计连续性验证（刻晴 PM review 补）**：随机抽 5 个迁移后 companion_id，走 `SELECT * FROM admin_audit_log WHERE target_id=? AND action='view_cert_image' ORDER BY created_at`，验 access_object_path 列表含 Phase A `cert-image://...` 历史行 + Phase B `azure-blob://...` 新行，时间连续
- **Azure Blob diagnostic log 与 admin_audit_log 1:1 对账（刻晴 review 可测建议 #4）**：跑 cron `verify_azure_audit_parity.py` 每日扫 Azure Blob diagnostic log + admin_audit_log action=view_cert_image，对 (timestamp ± 5s, blob_path, operator) 做 join 验 1:1（Azure 有访问但 audit 无 → 可能旁路 / audit 有但 Azure 无 → 可能 backend 直读未签名）。差异 > 0 触发 P2 alert

---

## 4. 安全 / PII

### 4.1 SAS 临时凭证（User Delegation SAS）

- TTL 15min（与 signed URL 同量级）
- RAM role 最小权限：**仅 put_object + get_object on bucket/{companion_id}/***（不允许 list / delete / cross-bucket）
- admin-v2 不持久化 STS token（每次上传重申请）

### 4.2 signed URL

- TTL 15min（与 ADR-0044 r1 §4.3 一致）
- Azure SAS 签名（X-MS-Signature, HMAC-SHA256 based）
- 单次使用（Azure SAS 支持 IP 白名单 + protocol 限定 https-only 可选叠加；不支持 Referer 限定，靠 SP 路径 scope 兜底）

### 4.3 Azure container private + 双闸

- bucket ACL = private
- bucket policy 拒绝匿名访问
- nginx 不反代 Azure Blob host（*.blob.core.chinacloudapi.cn 不出现在 nginx upstream 列表，双闸防裸 GET）

### 4.4 审计

- 所有 cert 操作（upload / commit / view）写 `admin_audit_log`
- Azure Blob diagnostic logs（开启 Storage Logging v1 或 Storage Analytics）作冗余审计

---

## 5. Phase A → B 切换策略

1. Phase A 上线灰度，本地存储真有 cert 数据
2. ADR-0045 Accept + Phase B P0-P5 实施
3. 迁移 cron 跑通 + verify
4. Phase A 反代路由废弃（保留 stub）
5. 灰度数据 stable 后 production 开关切 Azure Blob-only 模式
6. **30 天 Azure Blob-only 观察窗口**（刻晴 review 强约束 #1）：production 切 Azure Blob-only 后 30 天内**禁止删除本地文件**，Azure 故障可瞬切回 Phase A（前提：本地仍在）。期间 daily verify Azure Blob diagnostic log vs audit log parity（§3.6 对账）
7. **90 天冷备**（刻晴 review 强约束 #1）：30 天观察窗口后转冷备状态，本地 cert 文件**移到独立冷备目录** `/var/backup/cert-cold/`（与 production hot path 隔离），但不删
8. **manual confirm 后才人工清理**（刻晴 review 强约束 #1）：90 天冷备后 OPS 出具"Azure Blob 稳定 + 无回退记录 + 审计无异常"报告，**帝君人工 confirm** 后才 rm 冷备本地文件。cron **绝对不自动删**

回滚路径：若 Azure Blob 出故障，detail endpoint 检测 Azure 不可用 → 自动降级到 Phase A HMAC 路由（前提：本地文件仍在）。**降级 ≠ 撤销迁移**，只是临时托底。

---

## 6. 验收

- [ ] ADR-0045 落盘 + Accept
- [ ] Azure Blob container + service principal 创建 + ENV 配齐
- [ ] storage_azure.py service + User Delegation SAS / signed URL 实现
- [ ] 上传端点改 SAS 直传 + commit endpoint
- [ ] detail endpoint 兼容 azure-blob:// 与 cert-image:// 双前缀（Phase B 兼容 Phase A schema）
- [ ] 迁移 cron + verify 全跑通
- [ ] 单测 + staging 集成测
- [ ] Azure Blob 监控接入 Grafana
- [ ] Phase A 反代路由废弃 + 文档归档

---

## 7. 风险

| 风险 | 概率 | 缓解 |
|---|---|---|
| Azure 账单费用估算偏差（21Vianet 比 OSS 略高 ~¥5/月） | 低 | 灰度期 ≤¥20/月，月度对账即可 |
| Azure service principal 权限过宽（误授 list/delete）| 中 | RBAC role 严格 review + 单测验证最小权限 |
| 直传 Azure 客户端 SDK 引入 admin-v2 dist 体积上涨 | 低 | @azure/storage-blob ~80KB tree-shaken，可接受 |
| 历史迁移 cron 数据丢失 | 中 | dry-run + 双写过渡期（Azure Blob 写成功才标 migrated，本地不删）+ verify 10% 抽样 |
| Azure region 故障 | 低 | production GRS 跨区复制 + 降级回 Phase A |
| 后续政策要求换厂商 | 低 | 退出成本可控（azure-storage-blob → oss2/boto3 ~1d 改造）+ §2.4 StorageBackend ABC 抽象层 |
| **证件图跨境备份违反个人信息保护法**（凝光 PM review 补） | 中 | Azure 21Vianet (中国版) 强制中国节点 (East China 2 / North China 3) + GRS 仅在中国 region 之间复制 + service principal 限定 China region |
| **21Vianet 备案周期长（实际 1-3 周非 ADR §3.1 原估 30min）**（刻晴 09:01 review 强约束） | 高 | 凝光 P0 起手即拍 21Vianet 账号申请。**唯一降级路径 = Phase A 本地 storage 延期至 21Vianet 备案就绪**（cert 图本地存储 + HMAC 反代 + 双闸 PR #169 闸 4 完整 + nginx PR #168/#170 闸 4 拒裸 GET，灰度门 §6 仍可签，备案窗口期合规零风险）。关键路径风险，凝光跟进 |
| **PIPL 第三章跨境传输红线（刻晴 09:08 review 强约束）** | 红线 | 陪诊师证件图含身份证号 + 真实姓名 + 资格证 = 高敏 PII，**任何跨境路径（包括 Azure 海外 region）一律禁止**。需 PIA 评估 + 网信办申报 + 单独同意书全过门，灰度窗口期不可能走完。21Vianet 备案期降级仅走 Phase A 本地。**§6 测试侧明示不签含跨境降级条款的 ADR** |
| **Azure client secret 泄露 → 历史证件图全量泄露**（凝光 PM review 补） | 低 | secret 仅 env.canary.local（.gitignore）+ 季度轮换 + Azure Blob diagnostic log 审计（必启）+ 异常高频访问告警 |
| **§2.4 StorageBackend ABC 抽象层后未来迁移成本** | 低 | Azure Blob 是唯一 backend 时 ABC 仅加 1-line indirection 不增复杂度，后续迁 ~1d 改造（凝光 vendor lock-in 关切已合入 §2.4） |

---

## 8. 不在范围

- 其他类型文件存储（如 PDF 病例报告 / 头像 / 通用上传）—— 本 ADR 仅证件图，其他用例评估时复用 storage_azure 模式即可
- CDN 加速 —— Phase B+1 评估，灰度量级用不上
- Azure Blob Versioning / Lifecycle Management policy —— 后续运营评估

---

## 9. 决定

**Accepted（帝君 2026-06-04 08:50 UTC 拍板 Azure Blob Storage）**

- Reviewer：胡桃（developer，P1-P5 实施者）+ 凝光（PM，账号/账单关切人）
- **Owner Approval：帝君（一字回复）**
  - 帝君 2026-06-04 08:50 UTC 拍 **Azure Blob Storage** ✅
  - 本 ADR amend：§2.4 推荐改 Azure（OSS 留档对比）+ §3 实施步骤全替换 SDK (azure-storage-blob + @azure/storage-blob) + ENV 改 AZURE_* + SAS 替代 STS + URL schema azure-blob://
  - 凝光协调 21Vianet 账号申请（需帝君主体证件）
  - 胡桃接 P1-P5 实施 (~2.5-3 工作日)

---

## 10. 反向引用

- ADR-0044 r1 §4.2 Phase B 拆 storage 选型
- S2-DES-005 design task（本 ADR 是其产出）
- W19-P0-08 emergency PII PDF：当时单文件 SAS 模式，本 ADR Phase B 通用化
- 凝光 04:18 UTC PM 实证推 OSS（保留为历史评估对比）
- 帝君 2026-06-04 08:50 UTC 拍板 Azure Blob Storage（覆盖 OSS 推荐）
- PR #158 PR-E2 调研报告：实证 backend 零 storage SDK 现状
