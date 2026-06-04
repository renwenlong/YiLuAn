# PR-E2 storage 后端调研报告（S2-DEV-013 / ADR-0044 §4.1 路径 B）

> 状态：**Draft（D+1）** · 作者：胡桃 · 日期：2026-06-04
> 关联：ADR-0044 §4 / PR-E1 #155 / PR-E3 #157 / 我 ADR-0044 review 关切 #1

---

## 1. 调研范围

ADR-0044 §4.1 写 "实测：若当前 DB cert_image_url 是 SAS/presigned → wrapper 重签；若是 public URL → backend 必须重新生成"。本调研**实证**当前仓库 `certification_image_url` 字段实际写入路径 + storage 后端类型 + 选型路径。

---

## 2. 实证结果

### 2.1 字段写入路径

`grep -rn "certification_image_url" backend/`：

| 入口 | 写入方式 |
|---|---|
| `backend/app/services/admin_audit.py:150` certify_companion service | admin 调 `POST /admin/companions/{id}/certify` 手填 URL 字符串 |
| `backend/app/api/v1/admin/companions.py:218` API 端点 | body.certification_image_url（admin 提交的字符串）|
| alembic migration | String(500) nullable，**无任何上传 service 写入** |

**结论 1**：**没有任何"上传图片"的 API**。`certification_image_url` 是 admin 在 certify 时填入的**任意 URL 字符串**，backend 不做存储管理。

### 2.2 测试 fixture URL 来源

`backend/tests/test_companion_certification.py`：
- `https://oss.example.com/cert/abc.jpg`
- `https://oss.example.com/cert/hm-001.jpg`
- 任意 https URL placeholder

**结论 2**：设计期就**没确定 storage 后端**——测试用占位 URL，业务从未真上线过证件图功能。

### 2.3 现有 storage 设施

`backend/app/services/upload.py`：

```python
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/jpg"}
MAX_SIZE = 5 * 1024 * 1024  # 5MB
STATIC_DIR = backend/static/avatars  # 本地文件系统
```

**结论 3**：现有 storage = **本地静态文件**，**仅 avatar 用**。无 OSS / Azure Blob / S3 SDK 依赖（grep "presigned/sas/oss_bucket/azure_blob" 0 命中）。

### 2.4 当前 admin 流程实际状态

- admin 在 certify 时手填**任意 URL**（如运营把证件图传公司 OSS / 微信群截图，拿到 URL 贴进 admin UI）
- backend 不验证 URL 是否可达 + 不验证是否安全
- frontend admin-v2 drawer **无证件图预览**（PR-E3 已留警示提示 PR-E2 实施）
- 业务方上线后大概率**没真用证件图**，或运营有外部存储约定（需 PM 凝光确认）

---

## 3. 三条 storage 路径

| 路径 | 实施量 | 优点 | 缺点 |
|---|---|---|---|
| **A. wrapper 重签**（不引 storage 后端） | ~150 行 + 中等复杂度 | 不引新依赖 / 兼容当前 admin 手填模式 | backend 充当反向代理 — 流量打 backend / 必须 admin 填的源 URL 已是 public 可访问 / signed token 验证逻辑要自己写 |
| **B. 引 storage 后端**（Phase 2 完整化）| ~3-5 工作日 + ADR-0044 r1 + 迁移 | 标准方案 / OSS/Azure Blob 自带 SAS / 上传链路完整 / signed URL TTL/篡改/双闸 SDK 提供 | 工作量大 + 跨多 task / 需 PM/帝君拍 storage 选型（OSS vs Azure Blob vs S3）+ 账号资源 + 历史 URL 迁移 cron |
| **C. mvp 兜底**（本地 storage + 自签 token）| ~1.5 工作日 | 复用 upload.py 模式 / 不引新依赖 / 端到端可控 | 不分布式 / 备份难 / 灰度规模上不去 / signed token 自实现易出 PII bug |

---

## 4. 推荐：B+C 阶段化

**Phase A（紧急 mvp，灰度推全前必合）= C**：
- 加 `POST /admin/companions/{id}/certify-image-upload` 端点 — 复用 upload.py 模式，存 `backend/static/cert/{companion_id}.jpg`
- `certification_image_url` 字段写 `/static/cert/{id}.jpg`
- backend signed URL = backend 自签 query token（HMAC + TTL 15min）+ 反代路由 `GET /admin/cert-image/{token}` 验证后 serve 文件
- admin-v2 drawer fetchDetail 时 backend 实时生成 signed URL 返回
- **范围**：~1.5 工作日，可作为 PR-E2

**Phase B（生产化，下一迭代）= B**：
- 起独立 task `S2-DES-005 storage 后端选型 + 上传链路`
- 需 PM/帝君拍 OSS / Azure Blob / S3
- 实施上传 SDK + signed URL service + 历史数据迁移
- 不阻塞 S2 灰度

---

## 5. 关键依赖待 PM/凝光/帝君确认

1. **业务上证件图功能现在真用了吗？** 如果灰度阶段 admin 不需要审核证件图（依赖外部材料 + 人工审核），Phase A mvp 也可不做，直接 acceptance 降级 + PR-E1/E3 已覆盖即合 §6 签字
2. **storage 后端 future 选型偏好**：OSS / Azure Blob / S3 / 本地？需 PM/帝君前置拍
3. **历史已存 cert URL 处理**：实测 `SELECT certification_image_url FROM companion_profiles WHERE certification_image_url IS NOT NULL` 看 staging/prod 有多少行 → 迁移成本评估

---

## 6. 我的实施建议

**PR-E2 范围**：
1. 本调研报告落 docs/research/ 入库（本 PR）
2. **不实施 storage 选型 + signed URL**——这是 ADR-0044 r1 + storage 后端 ADR 应该拍的事
3. **ping 魈 + 凝光确认**：Phase A mvp（C 方案）vs 直接做 Phase B（独立 task）vs cert image 不进灰度直接 acceptance 降级
4. 等定调后下一刀真做实施

**深夜决策**：本 PR-E2 作为**调研报告 + ADR-0044 r1 输入** 提交，由魈接 ADR-0044 r1 amend 拍方向。等 r1 Accept 后再起 PR-E2-impl (mvp C 方案) 或独立 task (B 方案)。

---

## 7. 反向引用

- ADR-0044 §4.1 signed URL 改造路径
- PR-E1 #155 backend detail endpoint（占位 cert_image_signed_url None）
- PR-E3 #157 frontend drawer 占位 + PR-E2 提示
- 我 ADR-0044 review 关切 #1 "cert_image_url 存储调研 P1 起手做"
- `backend/app/services/upload.py` avatar 模式参考
- `backend/app/services/admin_audit.py::certify_companion` 当前 admin 手填 URL 路径
