# ADR-0046 — 电子服务合同存储扩展（基于 ADR-0045 StorageBackend ABC）

> 状态：**Draft（待 review + Owner Accept）** · 作者：魈 · 日期：2026-06-05
> 关联：PRD-003 §3 S3-REQ-001 / ADR-0045 storage backend / ADR-0047 contract domain / PRD-003 v0.3 §8 Q1 架构评估 + 刻晴 tester review §1 强约束（双门契约 + 合同 hash 公式 + WORM）
> 触发：S3-REQ-001 陪诊责任险 + 电子服务合同 / 帝君 2026-06-05 09:52 UTC v0.3 Owner Accept
> Owner Approval：**Pending（待 v0.3 三签 + 凝光拆 task ready 后 Accept）**

---

## 1. 背景

PRD-003 S3-REQ-001 要求支付成功后异步生成电子服务合同，绑定订单 + 模板版本。架构层 PRD §8 Q1 已拍**必须复用 ADR-0045 StorageBackend ABC**，本 ADR 给出合同特化方案。

合同特性与 cert image 共性 + 差异：

| 维度 | cert image (ADR-0045) | contract PDF (本 ADR) |
|---|---|---|
| PII 等级 | 🔴 极敏感（陪诊师身份证） | 🔴 极敏感（订单含患者脱敏 hash + 价格 + 服务时间 + 陪诊师 id） |
| 数据持久性 | 长期保留（陪诊师生命周期）| 长期保留（合同 7+ 年依法定）|
| 修改语义 | 可重新上传覆盖 | **完全不可变**（已生效合同不允许修改，民法典/电子签名法要求）|
| 命名空间 | `cert/{companion_id}/{uuid4}.{ext}` | `contracts/{year}/{month}/{order_id}_{contract_hash}.pdf` |
| 访问方式 | admin + 陪诊师本人 | 用户 + 陪诊师 + admin（三端只读）|
| Storage 类型 | 标准 blob | **WORM（Write Once Read Many）immutable blob** |

---

## 2. 选型对比

### 2.1 候选

| 候选 | 描述 | 评估 |
|---|---|---|
| **A. 复用 ADR-0045 StorageBackend ABC + ContractStorageBackend 子类** | 抽象层延用，合同特化 namespace + WORM policy | ✅ 推荐 |
| B. 独立合同存储栈（新起 ContractStorage 不继承 StorageBackend）| 完全独立 SDK + namespace + factory | ❌ 重复造轮子，违反 ADR-0045 抽象意图 |
| C. 合同 PDF 存 PostgreSQL bytea | 合同直接入库，强一致 | ❌ DB 膨胀（每单 50-200KB × 万级）+ 备份成本爆炸 + 不利 CDN |
| D. 第三方 e-contract 平台（如法大大/e签宝）| 直接调 vendor API 出合同 | ❌ PRD §2.2 已排除真 CA 签章 vendor，S3 不做 |

**A 推荐理由**：
1. ADR-0045 已落 StorageBackend ABC + AzureBlobStorageBackend，本 ADR 仅加 ContractStorageBackend 子类 + WORM 配置 + namespace 隔离 = 增量最小
2. PIPL 红线统一遵守（cert image PII 跨境禁止已写入 ADR-0045 §7，contract PDF 同等 PII 自动继承）
3. vendor lock-in 对冲层（StorageBackend ABC factory）已存在，未来切 OSS / S3 同样适用合同存储

### 2.2 Owner 拍板：**A. 复用 ADR-0045 + ContractStorageBackend 子类**（架构推荐，待 Owner Accept）

---

## 3. 实施分阶段

### 3.1 P0：ContractStorageBackend ABC 子类（魈 design + 胡桃 impl，~0.5d）

```python
# backend/app/services/contract_storage.py
from app.services.storage_backend import StorageBackend, AzureBlobStorageBackend

class ContractStorageBackend(StorageBackend):
    """合同存储特化：WORM + 7 年保留 + 强制 namespace + hash 防篡改"""

    NAMESPACE_PREFIX = "contracts"  # 与 cert image 的 cert/ 隔离
    RETENTION_YEARS = 7              # 民法典合同存档要求

    def put_contract(
        self,
        order_id: str,
        contract_hash: str,
        pdf_bytes: bytes,
        template_version: str,
    ) -> ContractStorageRef:
        """WORM 写入：put_if_absent 防重复，blob immutable policy 防修改"""
        ...

    def get_contract_signed_url(
        self,
        blob_path: str,
        viewer_role: ViewerRole,  # user / companion / admin
    ) -> str:
        """根据 viewer_role 派生不同 TTL SAS URL"""
        ...
```

**关键约束**：
- ABC 继承 `StorageBackend`（ADR-0045 同款抽象层）
- backend 实例 `AzureBlobStorageBackend` 直接复用，无需新起 Azure 账号
- container 复用 `yiluan-cert-{env}` (省一次 RBAC + 21Vianet 配置)，blob path 用 `contracts/{year}/{month}/{order_id}_{contract_hash}.pdf` namespace 隔离

### 3.2 P1：合同 hash 公式 + 防篡改（魈 spec + 胡桃 impl，~0.25d）

**合同 hash 公式（刻晴 tester review §1 强约束）**：

```python
contract_hash = SHA-256(
  template_version    # 如 "v1.0.0"
  + "|"
  + json.dumps(canonical_order_snapshot, sort_keys=True, ensure_ascii=False)
)
```

`canonical_order_snapshot` 必含字段（按 key 排序避免序列化漂移）：

| 字段 | 来源 | 备注 |
|---|---|---|
| `order_id` | Order.id | UUID |
| `amount_cny` | Order.price_snapshot | 分单位整数 |
| `service_package_id` | OrderItem.service_package_id | UUID |
| `scheduled_at` | Order.scheduled_at | ISO-8601 UTC |
| `patient_pseudonym_hash` | SHA-256(患者姓名+身份证后4 + salt) | **不入合同明文**，只入 hash 计算防篡改 |
| `companion_id` | Order.companion_id | UUID（接单后 immutable）|
| `template_version` | ContractTemplate.version | semver |

**约束**：
- 任何字段缺失 / 类型不一致 → `ContractHashGenerationError` (合同生成失败状态)
- canonical JSON 必须 `sort_keys=True` + `ensure_ascii=False` + `separators=(',', ':')` 三参数固定（防漂移）
- patient_pseudonym_hash 计算盐独立 env `CONTRACT_PSEUDONYM_SALT`（不与 cert image 共用 salt）

### 3.3 P2：WORM 语义实施（魈 spec + 胡桃 impl，~0.25d）

**Azure Blob Immutable Storage Policy**：

```python
# 合同 blob 创建时设置 immutability policy
container.set_immutability_policy(
    blob_name=blob_path,
    period_since_creation_in_days=365 * 7,  # 7 年保留
    policy_mode="Locked",                    # Locked 不可解除（vs Unlocked 可解锁）
)
```

**WORM 防御层级**：

| 层 | 防御 |
|---|---|
| 1. 存储层 | Azure immutable policy Locked 7 年（即使有 owner key 也不能 delete/overwrite）|
| 2. 应用层 | `put_contract` 用 `put_if_absent` (Azure `If-None-Match: *`)，文件已存在则 reject |
| 3. DB 层 | `service_contracts.contract_hash` UNIQUE constraint + `service_contracts.is_immutable` 默认 TRUE，更新 trigger reject |
| 4. API 层 | `PUT /admin/contracts/{id}` 不存在；admin 仅可 `GET` 已生效合同 |

### 3.4 P3：合同生成失败补偿（魈 spec + 胡桃 impl，~0.25d）

**刻晴 tester review §1 AC#5 强约束**：合同生成失败不阻塞支付 + 补偿 cron + 3 次失败 admin alert。

```
events:
  payment.succeeded
    -> contract.generate.requested (异步 Celery / RQ task)
       -> ContractStorageBackend.put_contract()
          -> 成功 → service_contracts.status = active
          -> 失败 → service_contracts.status = generation_failed + retry_count += 1

contract_generate_retry_cron (每 5min):
  SELECT contracts WHERE status=generation_failed AND retry_count < 3
  -> retry put_contract with exponential backoff:
     1st retry: 支付后 5min
     2nd retry: 1st 失败后 30min
     3rd retry: 2nd 失败后 2h
  -> 3 次全失败 → status = generation_permanently_failed + admin alert (alertmanager)
```

**admin alert 触发**（ADR-0040 alertmanager 体系内）：
- alert name: `contract_generation_permanently_failed`
- severity: `warning`（不是 critical，因为不阻塞订单）
- target: 企微告警群 + admin 后台显示 banner
- 包含信息：order_id / failure_reason / retry_count / last_error_trace

### 3.5 P4：双门契约检查（魈 spec + 胡桃/刻晴 impl，~0.5d）

**刻晴 tester review §1 强约束**：

```python
# scripts/qa/openapi_contract_diff.py

GUARDED_FIELDS = {  # negative list (ADR-0045 已锁，本 ADR 沿用)
    "share_token", "share_url", "share_scope", "share_active_count",
    "share_expires_at", "share_revoked_at", "share_session", "share_jwt",
    "share_verified",
}

S3_NEW_FIELD_PREFIXES = {  # positive list (本 ADR 新加 + r2 加 companion_cert_*)
    "contract_",
    "insurance_",
    "preparation_",
    "companion_cert_",   # r2: PRD-001 v1.2 §F8 资质透明度 ¨ AC-F8-7 要求强制前缀
    "feedback_",         # r2: PRD-004 反馈采集 AC-8 要求强制前缀
}

def check_share_namespace_locked(openapi_spec: dict) -> list[str]:
    """negative list: 拒任何新 share_* 字段进 share endpoint"""
    violations = []
    for endpoint in openapi_spec.get("paths", {}):
        if "/share" in endpoint:
            fields = extract_response_fields(openapi_spec, endpoint)
            new_share = {f for f in fields if f.startswith("share_")} - GUARDED_FIELDS
            if new_share:
                violations.append(
                    f"{endpoint}: forbidden new share_* fields: {new_share}"
                )
    return violations

def check_s3_prefix_enforced(openapi_spec: dict) -> list[str]:
    """positive list: S3 endpoint 新字段必须用域前缀"""
    violations = []
    for endpoint, methods in openapi_spec.get("paths", {}).items():
        # S3 endpoint 范围：/contracts, /insurance, /preparation 路径
        if any(x in endpoint for x in ["/contracts", "/insurance", "/preparation"]):
            fields = extract_response_fields(openapi_spec, endpoint)
            for f in fields:
                if f in COMMON_FIELDS_WHITELIST:  # id, created_at 等通用字段
                    continue
                if not any(f.startswith(p) for p in S3_NEW_FIELD_PREFIXES):
                    violations.append(
                        f"{endpoint}.{f}: missing required S3 prefix "
                        f"({', '.join(S3_NEW_FIELD_PREFIXES)})"
                    )
    return violations
```

**CI required gate**（`.github/workflows/openapi-contract.yml`）：

```yaml
jobs:
  openapi-contract:
    name: OpenAPI 契约双门校验
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python scripts/qa/openapi_contract_diff.py
      # PR 含违规 → exit 1 → CI fail → branch protection block merge
```

**branch protection rule**: `main` 分支 required status check 加 `OpenAPI 契约双门校验`，S3 时代后所有 PR 必须 pass。

**unit test 覆盖**（刻晴 review 阶段硬核 3 case）：

```python
# tests/qa/test_openapi_contract_diff.py

def test_negative_share_xxx_rejected():
    spec = build_spec_with_field("/v1/share/order", "share_insurance")
    violations = check_share_namespace_locked(spec)
    assert "share_insurance" in str(violations)

def test_positive_no_prefix_rejected():
    spec = build_spec_with_field("/v1/contracts/{id}", "policy_no")  # 无前缀
    violations = check_s3_prefix_enforced(spec)
    assert "policy_no" in str(violations)
    assert "missing required S3 prefix" in str(violations)

def test_positive_with_prefix_accepted():
    spec = build_spec_with_field("/v1/contracts/{id}", "contract_hash")
    violations = check_s3_prefix_enforced(spec)
    assert violations == []
```

**code-review-checklist.md §7 加可复现 grep 命令**（刻晴 review 阶段硬核）：

```bash
# 行人复核命令（PR review 时手动跑）
# 1. 检查新字段未污染 share_* 命名空间
grep -rn "^\s*share_" backend/app/schemas/ | \
  grep -v -E "share_(token|url|scope|active_count|expires_at|revoked_at|session|jwt|verified)"

# 2. 检查 openapi.json 中 share endpoint 不引入新 share_* 字段
grep -E '"share_[a-z_]+"' docs/api/openapi.json | sort -u

# 3. S3 endpoint 字段前缀检查
python scripts/qa/openapi_contract_diff.py --json-summary
```

### 3.6 P5：迁移与回滚（魈 spec + 凝光协调，~0.25d）

**迁移**：
- S3 启动前历史订单（S2 完结订单）**不补生成合同**（PM 拍：合同从 S3 启动后新订单开始）
- 灰度期：S3-REQ-001 灰度 10 单（PRD-003 §7 指标），灰度通过后全量开

**回滚**：
- 灰度期发现严重问题：
  1. 关 `contract_generation_enabled` feature flag → 新订单不生成合同
  2. 已生成合同保留（WORM 不可删，但 status 可改为 `manually_invalidated`）
  3. admin 后台显示 banner 通知用户/陪诊师
- 永久回滚：依赖 ADR-0045 storage backend factory，切换合同存储后端不影响 cert image

---

## 4. 实施 Acceptance（魈 review 阶段硬核 3 项）

| AC | 标准 | 验证方式 |
|---|---|---|
| AC-1 | ContractStorageBackend 子类正确继承 StorageBackend ABC + 复用 AzureBlobStorageBackend 实例 | 单元测试 + ABC 接口 check |
| AC-2 | 合同 hash 公式产出稳定（同输入恒等输出）+ canonical JSON 三参数固定 | hash repro test + 字段漂移 fuzz |
| AC-3 | WORM 4 层防御全部生效（storage / app / DB / API）| 集成测：试 delete blob 应 403 / 试 PUT API 应 404 / 试 hash collision insert 应 UNIQUE violation |
| AC-4 | 合同生成失败 3 次补偿（5min/30min/2h 指数退避）+ admin alert | cron 模拟测 + alertmanager fire 模拟 |
| AC-5 | 双门契约 check 函数 3 unit test case 全 pass + CI required gate 哨兵 PR 验证 | 故意造违规 PR 验 CI fail |

---

## 5. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| Azure Blob immutable policy lock 后 7 年内无法清除（测试数据污染）| 中 | 测试 container 永久占用 | staging 用单独 container `yiluan-cert-staging` 不开 immutable policy；只 production container 开 |
| 合同 hash 公式后续变更导致历史合同 hash 失效 | 低 | 已生成合同 hash 不可验证 | hash 公式版本化（`contract_hash_version` 字段），历史合同保留原版本 hash |
| 合同 PDF 模板更新影响历史合同 | 低 | 历史合同应保留原模板 | DB `service_contracts.template_version` 记录 + WORM 防覆盖 |
| 21Vianet 备案延期导致 S3-REQ-001 阻塞 | 高 | S3 推迟 1-3 周 | 复用 ADR-0045 cert image 同 container（同一 21Vianet 主体）;不需独立申请 |
| 双门 check 误伤 legacy 字段 | 低 | CI 全红 | COMMON_FIELDS_WHITELIST 维护通用字段列表（id, created_at, updated_at 等）|

---

## 6. 相关 ADR

- **ADR-0045 storage backend selection**（父）：StorageBackend ABC + AzureBlobStorageBackend 实例
- **ADR-0047 service contract & insurance domain models**（兄弟）：合同状态机 + 事件流
- **ADR-0048 AI assistant budget guard**（兄弟）：AI 准备包独立成本控件
- **ADR-0044 r1 §4.3** PIPL 红线：本 ADR 合同 PDF PII 等级同 cert image，PIPL 跨境禁止规则继承

---

## 7. 实施授权

待 v0.3 三签（PM/架构/测试）+ 帝君 Owner Accept → 凝光拆 S3-REQ-001 develop task → 本 ADR Accept → 胡桃 implement。

---

## 8. 变更记录

- **r1（2026-06-05）**：Draft 初版，吸收刻晴 tester review §1 3 强约束 + 5 可测建议（合同 hash 公式 + WORM + 双门契约 + 补偿 cron + admin alert）
- **r2（2026-06-05）**：双门 positive list 加 `companion_cert_*`（PRD-001 v1.2 §F8 AC-F8-7）+ `feedback_*`（PRD-004 AC-8），填补后续 S3-REQ-004/005 实施需要的域前缀，避免 CI gate 误伤
