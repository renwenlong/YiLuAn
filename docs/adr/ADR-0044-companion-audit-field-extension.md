# ADR-0044 — 陪诊师审核字段扩展 + detail endpoint + 三件套模板

> 状态：**Draft（D+0）** · 作者：魈 · 日期：2026-06-04
> 关联：S2-DES-004 / S2-DEV-013（admin-v2 Phase 1）/ ADR-0036（family-share）/ ADR-0042（admin-v2 选型）/ S2-TEST-009 acceptance A-6
> 触发：刻晴 review PR-B 指出 "drawer 复用 list row 5 字段 = 盲签" + 胡桃 PR-A follow-up "feature 标准动作 = list+detail+mutation 三件套"
> 灰度门：**灰度推全前必合**（admin 真审核能力是 §6 四方签字硬门）

---

## 1. 背景

S2-DEV-013 PR-A/B 实施过程发现 backend `CompanionItem` 5 字段（id / real_name / id_number_masked / certifications / created_at）不足以支撑真审核业务。admin 看不到证件原件 / 申请人 bio / 联系方式 → 实质 rubber-stamp，不能上线。

---

## 2. 关键发现：模型字段已有，仅 API 未暴露

实测 `backend/app/models/companion_profile.py::CompanionProfile`**已含**审核所需字段：

| 字段 | DB 字段 | API 暴露 | 备注 |
|---|---|---|---|
| id | ✅ | ✅ list | — |
| real_name | ✅ | ✅ list | — |
| id_number | ✅ | ✅ list (masked) | reveal 需独立端点 |
| certifications | ✅ | ✅ list (str) | 持证信息文本串 |
| created_at | ✅ | ✅ list | — |
| **bio** | ✅ | ❌ | 申请人自述，审核重要 |
| **certification_image_url** | ✅ | ❌ | 证件照片 URL（单个）|
| **certification_type** | ✅ | ❌ | 证件类型 |
| **certification_no** | ✅ | ❌ | 证件编号 |
| **service_area / service_city / service_hospitals / service_types** | ✅ | ❌ | 服务范围 |
| **avg_rating / total_orders** | ✅ | ❌ | 历史指标 |
| **verification_status** | ✅ | ❌（list 强制 pending）| detail 应可见 |
| **certified_at** | ✅ | ❌ | 已认证陪诊师时间戳 |

User.phone（关联 `user_id`）：已通过 `/api/v1/admin/users` 的 `?reveal=true` query param 暴露（list/detail 默认 `phone_masked`，?reveal=true 返明文 + 写 admin_audit_log action=reveal_pii，实证 `backend/app/api/v1/admin/users.py` L62-180）。**不重复建 companion 专用 endpoint**（胡桃 review 关切 #2 落实）。

**结论**：不需要 alembic 迁移 + 不需要新数据库字段。仅扩 API schema 暴露已有字段。工作量大幅降低。

---

## 3. 设计

### 3.1 新增 detail endpoint

```
GET /api/v1/admin/companions/{id}
  → CompanionDetail (扩展 schema，含上述新字段)
  鉴权: Depends(require_admin)
  审计: write admin_audit_log action=view_companion_detail target_id=companion_id
```

### 3.2 `CompanionDetail` schema（新增，独立于 list `CompanionItem`）

```python
class CompanionDetail(BaseModel):
    # 与 list 重叠（保持字段名一致避免前端两套 type）
    id: str
    real_name: str
    id_number: str | None  # masked
    certifications: str | None  # 持证文本串
    created_at: str | None

    # 新增：审核必要字段
    bio: str | None
    verification_status: str  # pending / verified / rejected
    certified_at: str | None

    # 新增：证件三件
    certification_type: str | None
    certification_no: str | None
    certification_image_signed_url: str | None  # ⚠️ signed URL，详 §4

    # 新增：服务范围（参考）
    service_area: str | None
    service_city: str | None
    service_hospitals: str | None
    service_types: str | None

    # 新增：历史指标（参考）
    avg_rating: float
    total_orders: int

    # 新增：关联用户联系方式（masked，reveal 单独端点）
    user_phone_masked: str | None
```

### 3.3 list `CompanionItem` 保持精简

不动现有 5 字段。detail 才返扩展字段。理由：列表分页性能 + 减少不必要数据传输。

### 3.4 三件套模板（ADR-0042 §3 Phase 2-9 复粘模板补附录）

> **admin-v2 feature page 标准动作 = list + detail + mutation 三件套，缺一不可**
> - **list**：分页 + 过滤 + 跳页 + 排序，row 字段**仅含表格列**（精简）
> - **detail**：drawer / 独立页，**展开 row 不可见的所有审核/编辑必要字段**
> - **mutation**：approve / reject / patch / delete 等，**触发后必有 audit_log 留痕**

任何新 feature page（订单管理 / 用户管理 / 审计 / 退款审批 / 仪表盘等 Phase 2-9）必须三件套齐全，PR review checklist 加一项："是否 list+detail+mutation 三件套齐"。

ADR-0042 §3 我会单独发 r1 修订 PR 补本附录（小改），不在本 ADR 内并入。

---

## 4. 安全设计：certification_image_url → signed URL（r1 2026-06-04 重写）

> **r1 修订动因**：PR-E2 调研 (PR #158) 实证发现原 §4 假设错误：backend **无任何上传 API + storage 后端零选型**（cert_image_url 是 admin 手填的任意 URL 字符串，业务从未真上线证件图功能）。原路径 A/B 不适用。重写为 Phase A mvp + Phase B 生产化两阶段。

**刻晴 review 关切（不可妥协）仍然有效**：PII 极敏感，上传、存储、分发三环节必须双闸鉴权 + TTL 限制 + 审计。

### 4.0 现状（PR #158 调研结论）

- `certification_image_url` 是 admin 手填的任意 URL 字符串（不是 storage URL）
- backend 零 storage SDK 依赖（grep oss/azure/s3 0 命中）
- 现有 `backend/app/services/upload.py` 仅 avatar 用：本地 `STATIC_DIR=backend/static/avatars`，5MB 限，仅 image/jpeg、image/png
- 业务侧 PM 凝光确认：**证件图是陪诊师审核合规硬要求**（本 ADR §1 钉死），火度推全前必须可用

### 4.1 Phase A：mbvp 本地 storage + HMAC 自签反代（**火度推全前必合**）

**范围**：复用 `upload.py` 本地静态文件模式，加 HMAC 自签 signed token + backend 反代路由验证后 serve。不引 OSS/Azure/S3 SDK。

**实现要点**：
1. 新增 `POST /api/v1/admin/companions/{id}/certify-image-upload`（multipart/form-data）—— 复用 upload.py 模式但独立 STATIC_DIR=`backend/static/cert`，限 5MB，仅 image/jpeg/png/pdf（增 pdf 支持资格证扫件）
2. 上传后写 `CompanionProfile.certification_image_url = /static/cert/{companion_id}.{ext}`（内部路径，不外露）
3. detail endpoint 返回时：service 实时生成 HMAC 签名 token = HMAC_SHA256(secret, f"{path}:{exp}") + 拼接 `certification_image_signed_url = /api/v1/admin/cert-image/{token}?path=...&exp=...`
4. 新增 `GET /api/v1/admin/cert-image/{token}` 反代路由：verify_admin_token + verify HMAC + 检 exp < now 后读本地文件 stream 返 (Content-Type 推断不信任外部) + 写 audit action=view_cert_image
5. TTL = 15min（与 ADR-0036 share_session 30min 同量级）
6. nginx 不暴露 `/static/cert/` 路径（仅反代走 `/api/v1/admin/cert-image/`）—— 双闸防裸 GET

**估时**：~1.5 工作日（PR-E2-impl）

**限制**：不分布式 / 备份难 / 单机督场路 / 适合火度期。Phase B 上线后迁移。

### 4.2 Phase B：生产化 storage 后端（**独立后续 ADR**）

**范围**：拆独立 design task **S2-DES-005 storage 后端选型 + 上传链路 + 历史迁移**，下一迭代。

**需 PM 凝光 + Owner 帝君拍**：
- storage 后端选型：OSS（凝光推，与阿里云 SMS 同账号）/ Azure Blob / AWS S3 / 本地 (Phase A 保留)
- 企业账号 + 子账号权限
- 账单 vs 点击金额预估

**实现**（S2-DES-005 安排）：
- 上传链路改成直传 OSS（不走 backend）使用 STS 临时证书
- detail endpoint 返 OSS signed URL (SAS / presigned)，TTL 15min
- 历史 cert URL 迁移 cron：扫 Phase A 本地 `/static/cert/*` + 上传 OSS + 更新 DB
- Phase A 反代路由废弃，切 OSS 原生 signed URL

**不阻塞 S2 火度**。帝君拍后拆低优先级独立表。

### 4.3 双闸鉴权（Phase A + Phase B 同适用）

| 闸 | 拦截点 | 失败码 |
|---|---|---|
| 1 | admin token 验证（detail endpoint 返回 signed URL）| 401 |
| 2 | signed URL TTL 验证（反代路由 / OSS 原生）| 403 / SAS 过期 |
| 3 | signed URL 签名验证（防篡改）| 403 |
| 4 | nginx 不暴露 cert 资源 host 裸 GET | 404 |

### 4.4 admin-v2 drawer 行为（不变）

- 每次 open drawer **重新 fetch detail endpoint 获新 signed URL**（不 cache URL）—— PR-E3 #157 已实现 `staleTime=0 + gcTime=0`
- 关 drawer 即丢弃 URL
- 图片预览加载失败（URL 过期）显示「链接已过期，请重新打开」，不静默 fail

### 4.5 单测/E2E 必须覆盖（Phase A）

- 上传 endpoint：非 admin token 拒 401 / 超 5MB 拒 413 / 错 MIME 拒 415 / 完整上传后 DB cert_url 写入检
- signed token 生成：HMAC 可重入验证 / exp 正确计算
- 反代路由：signed URL 过期后 GET 拒 403 / 缺 admin token 拒 401 / 签名篡改 1 byte 拒 403 / TTL 内重复 GET 通
- nginx 裸 GET `/static/cert/*` 拒 404（staging 集成测验）

### 4.6 Phase A 限制 → Phase B 迁移检清单

Phase B Accept 后，S2-DES-005 实施 PR 顺手迁移：
- `backend/static/cert/*` 本地文件 → OSS bucket
- DB `certification_image_url` 路径重写
- 反代路由废弃
- HMAC 签名 service 可保留（本地 stub 用）或废弃

---

## 5. user_phone reveal-on-demand

User.phone 走 `/api/v1/admin/users/{id}?reveal=true` query param（复用已有机制，不新建 companion 专用，胡桃 review 关切 #2）。

- list / detail 默认返 `phone_masked` (如 `138******03`)
- query param `?reveal=true` 与后返明文 + `admin_audit_log` action=`reveal_pii` target_id=user_id 留痕
- admin-v2 drawer 响应“显示完整手机号”点击 → 调 `/api/v1/admin/users/{companion.user_id}?reveal=true`
- 多次 reveal 写多条 audit 行（高频 reveal 可起 alert）

实证代码：`backend/app/api/v1/admin/users.py` L62-180。

---

## 6. 实施步骤（S2-DEV-013 PR-E 由胡桃做）

| Phase | 内容 | 估时 |
|---|---|---|
| **P1** | backend `CompanionDetail` Pydantic schema + `GET /admin/companions/{id}` endpoint + 审计留痕 | 0.5d |
| **P2** | service 层 signed URL 生成（评估当前 cert_image_url 存储后端 / 接 SAS 或 presigned） | 0.5d |
| **P3** | admin-v2 drawer 改 fetchDetail + signed URL 图片预览 + reveal-on-demand phone | 0.5d |
| **P4** | 单测 + E2E（cert_url 过期 / 篡改 / 双闸）+ openapi schema diff | 0.5d |
| **P5** | ADR-0042 r1 amend 补三件套模板附录（小） | 0.5d（魈做）|

总计 ~2 工作日（前端后端串行），灰度前完成。

---

## 7. 验收（ADR-0044）

- [ ] 本 ADR 落盘 + Accept
- [ ] backend CompanionDetail schema + GET /admin/companions/{id} endpoint
- [ ] 审计 view_companion_detail 留痕
- [ ] signed URL service 实现（TTL ≤ 15min + 重签 + 双闸）
- [ ] admin-v2 drawer fetchDetail + 图片预览 + reveal phone
- [ ] 单测：signed URL 过期 / 篡改 / 双闸 / TTL 内复用全覆盖
- [ ] ADR-0042 r1 补三件套模板附录
- [ ] S2-TEST-009 A-6 第二版 acceptance 满足（drawer 显示完整审核字段 + reveal phone + 通过/拒绝 + audit）
- [ ] **灰度推全前必合**（与 admin 真审核启用同步）

---

## 8. 风险

| 风险 | 概率 | 缓解 |
|---|---|---|
| 当前 cert_image_url 是 public URL → 历史数据风险 | 高 | 调研当前存储后端；若是 public，加迁移 cron 把已存 URL 替换为 signed wrapper；过渡期 admin 浏览仍走 signed wrapper |
| signed URL 生成开销 / 存储后端 SDK 依赖 | 低 | Azure Blob SAS 本地签名，无外部 RTT；S3 presigned 同样 |
| reveal phone 滥用 | 中 | reveal 端点单独 rate-limit + 审计 + 异常告警（高频 reveal 触发 alert） |
| 三件套模板硬性约束阻碍快速 prototype | 低 | mutation 类型小 feature（如开关切换）可省 detail；模板说明清楚 |

---

## 9. 不在范围

- 陪诊师 self-service 编辑（patch 自己字段）—— 走 patient app / 陪诊师 app，不是 admin 范畴
- 多张证件照片（cert_image_urls[]）—— DB 当前是单字段 string；若业务真需要，下一迭代独立 ADR 改成关联表
- 证件图 OCR 自动审核 —— 业务方向，下一迭代

---

## 10. 决定

**Draft → 待 review**

- Reviewer：胡桃（developer，PR-E 实施者）+ 刻晴（tester，签 §6 四方签字硬门）
- Owner Approval：帝君
- 凝光知会：A-6 措辞修订（第一版 → 第二版）

Accept 后立刻起 PR-E。

---

## 11. 反向引用

- ADR-0036 r1 §8.1：错误码分层（admin token 401 走 FastAPI handshake 层）
- ADR-0038：admin-h5 默认 token 加固（admin-v2 沿用）
- ADR-0042：admin-v2 选型；**§3 Phase 2-9 模板需 r1 amend 补三件套附录**
- S2-DES-004：本 ADR 是其设计产出
- S2-TEST-009 A-6：第二版 acceptance 由本 ADR 满足
- W19-P0-08：emergency PII PDF SAS 模式参考
