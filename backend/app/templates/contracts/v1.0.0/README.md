# 合同模板 v1.0.0 — README（PM 业务边界口径）

> 产出：凝光（PM）@ 2026-06-08 10:05 UTC
> 触发：S3-DEV-001-CONTRACT-PDF-RENDER buffer 准备
> 文件：`backend/app/templates/contracts/v1.0.0/companion_service_contract.md.j2`

## 用途

胡桃 reportlab 渲染 `_render_pdf()` 时，将本 jinja2 模板 + ServiceContract 实例的 hash_inputs + 关联 Order/Companion/Patient 明文字段 swap 占位生成 PDF。

## 模板字段插槽清单

模板插槽分 3 类，对应数据来源：

### 类 1：来自 `service_contracts.hash_inputs` JSONB（ADR-0046 §3.2 7 字段）

| 插槽 | hash_inputs 字段 | 备注 |
|---|---|---|
| `{{ order_id_short }}` | `order_id`（取后 6 位）| 展示用，全 UUID 不放正文 |
| `{{ amount_yuan }}` | `amount_cny / 100` | 分→元转换，2 位小数 |
| `{{ scheduled_at_local }}` | `scheduled_at` | ISO-8601 UTC → Asia/Shanghai 友好格式 |
| `{{ service_type_label }}` | `service_package_id` | resolve 到 service_packages.name 中文 |
| `{{ companion_id_short }}` | `companion_id`（取后 6 位）| 展示用 |
| 不入模板 | `patient_pseudonym_hash` | hash 用，不入合同明文 |
| `{{ contract_hash }}` | hash 输出值 | 合同 hash 指纹，PDF 八.2 / 十 引用 |

### 类 2：来自关联 Order/Companion/Patient 明文（eager load via selectinload）

| 插槽 | 来源 | 备注 |
|---|---|---|
| `{{ patient_name }}` | `Patient.name`（NFKC normalized）| 真名展示在合同里（PIPL 第十三条履约必需）|
| `{{ patient_phone_masked }}` | `Patient.phone`（中间 4 位 mask）| 如 138****5678，不展示完整号 |
| `{{ patient_user_id_short }}` | `Patient.user_id`（后 6 位）| 展示用 |
| `{{ companion_name }}` | `Companion.name`（NFKC normalized）| 真名展示 |
| `{{ companion_cert_status }}` | `Companion.cert_status` | 三态：「已认证 / 临时证明补交中 / 未认证」中文 label |
| `{{ hospital_name }}` | `Order.hospital_name` | 展示完整医院名 |
| `{{ department_name }}` | `Order.department_name` | 可选，缺省"未指定" |
| `{{ insurance_policy_no }}` | `ServiceInsuranceRecord.vendor_policy_no` | 允许 PENDING 占位 |
| `{{ insurance_status_label }}` | `ServiceInsuranceRecord.status` | 中文 label |
| `{{ insurance_product_name }}` | `ServiceInsuranceRecord.product_name` | 缺省"陪诊责任险标准版" |
| `{{ insurance_coverage_label }}` | `ServiceInsuranceRecord.coverage_amount_cny` | 转人民币 + 文案如"保额 ¥100,000" |

### 类 3：来自生成时机的元数据

| 插槽 | 来源 | 备注 |
|---|---|---|
| `{{ generated_at_local }}` | `ServiceContract.generated_at` | Asia/Shanghai 友好格式（PDF 主体引用）|
| `{{ generated_at_utc }}` | `ServiceContract.generated_at` | ISO-8601 UTC（PDF 第十节技术引用）|
| `{{ companion_sop_version }}` | 平台常量 | 引用陪诊师服务规范版本号，缺省 "1.0" |

## 模板未填占位（待帝君确认主体信息）

| 插槽 | 占位 | 帝君拍板后 PM 补 |
|---|---|---|
| 平台运营主体 | `[由帝君注册主体后填入正式名称]` | 主体名称、注册号 |
| 客服电话 | `[由帝君注册客服号码后填入]` | 客服 400 / 公司座机 |
| 司法管辖地 | "平台运营主体所在地" | 具体到市级 |

## reportlab 渲染建议（PM 视角，不卡技术决策）

1. **字体**：reportlab 内置 `STSong-Light` CID font 解中文，胡桃已确认
2. **idempotent**：胡桃明示需 `setCreationDate(datetime(2026,1,1,UTC))` 写死 + `setProducer("")`，避免 PDF metadata 漂移破 hash 验证（AC#5）
3. **页眉/页脚**：建议每页页眉「医路安陪诊服务合同」+ 页脚「合同 hash: {{ contract_hash[:16] }}...」便司法取证
4. **分页**：合同主体长度约 4 页，reportlab Canvas 用 Frame 自动分页
5. **签名**：合同末尾不需要手写签名块（电子合同 §8.1 已说明勾选即生效）

## 业务边界守门点（PM 视角）

胡桃 swap 模板字段时，PM 关注：

1. **不要在 PDF 里展示** `patient_pseudonym_hash`（hash 用，不入合同明文，§ADR-0046 §3.2 注释明示）
2. **不要在 PDF 里展示完整** `companion_id` / `order_id` UUID（用后 6 位即可）
3. **不要在 PDF 里展示完整电话号**（手机号 mask 中间 4 位）
4. **不要展示** `companion_id` 对应的陪诊师证件号 / 身份证号 / 真实住址
5. **AC-F8-6 职业背书禁词** v1.0.0 已避开 PRD-001 v1.5 §F8 中所有 PO-001～PO-015 禁词措辞
6. **AC-2a admin pending_companion** 占位状态下，合同 row 还未 INSERT，不需要渲染 PDF（PM 业务边界守门：admin 看到「未生成 - 等待陪诊师接单」文案即可，不需要占位 PDF）

## 模板锁版时点

当前 v1.0.0-draft，PM 自留 amend 权。锁版条件：
1. 帝君 PRD-003 v0.5 Owner Accept 字到位
2. 帝君补齐 §九 平台运营主体名称、§五 客服电话、§八 司法管辖地
3. （可选）法务 review（如帝君指派法务顾问）

锁版后改 v1.0.1+ 需走 PM + 法务 + 帝君三签。

## 提示胡桃

- 当前 v1.0.0-draft，可直接 swap 占位起骨架，**未填占位 PM 后续 PR amend，不阻塞你 _render_pdf 主体逻辑**
- AC-2a 占位状态下 PDF 不渲染，admin 端走 admin 文案 fallback
- 如有字段插槽找不到对应数据来源，ping PM 业务边界澄清
