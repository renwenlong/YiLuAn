# 陪诊师 carry_items_summary 分类规则（PM 调研稿）

> Task: `S3-DEV-002-COMPANION-CARRY-ITEMS-SUMMARY`
> Owner: 凝光（PM）
> Reviewer: 魈（architect）
> Scope: PR #233 follow-up；补齐 ADR-0048 §7.0.1 `CarryItemsSummary {total_count, categories}` 的业务字典。

## 1. 结论

陪诊师端只看**条数 + 脱敏类别**，不看具体携带物品名称。

```json
{
  "total_count": 3,
  "categories": ["证件凭证", "医疗设备"]
}
```

- `total_count`: 原始 `carry_items` 条目数。
- `categories`: 去重后的安全分类展示名，按固定优先级排序。
- 不返回原始物品名称、不返回单类数量、不返回疾病/科室/症状/药名/设备名。

## 2. 业务原则

1. **陪诊师需要知道“准备协助方向”，不需要知道“病情细节”。**
   - 好：`医疗设备`
   - 坏：`糖尿病相关物品`、`胰岛素笔`、`血糖监测用品`
2. **类别只表达服务动作，不表达医学判断。**
   - 好：`就医资料`
   - 坏：`肿瘤复查资料`、`产检材料`
3. **可测试优先于智能推断。**
   - MVP 使用确定性映射表，不调用 LLM 做分类。
   - 理由：LLM 可能把“胰岛素笔”推断成“糖尿病”，违反 ABAC 红线；确定性映射可被单测锁死。

## 3. 安全分类字典（v1）

| 固定顺序 | category | 典型映射词（仅服务端内部使用，不返给陪诊师） | 隐私说明 |
|---:|---|---|---|
| 1 | `证件凭证` | 身份证、医保卡、社保卡、就诊卡、挂号单、预约凭证 | 身份/就诊流程信息，必要且不含病情 |
| 2 | `支付材料` | 现金、银行卡、支付码、押金、发票 | 支付协助方向，不含病情 |
| 3 | `就医资料` | 病历本、检查报告、检验单、影像片、转诊单、处方单 | 只提示“有资料”，不暴露资料内容/科室/诊断 |
| 4 | `药品用品` | 常用药、备用药、药盒、给药用品、吸入器、胰岛素笔 | 不返药名/适应症；统一归为药品用品 |
| 5 | `医疗设备` | 血压计、血糖仪、雾化器、助听器、制氧机、体温计 | 不返设备名；避免推断疾病 |
| 6 | `日常用品` | 纸巾、湿巾、口罩、外套、雨具、充电器 | 通用生活协助 |
| 7 | `饮食补给` | 水杯、饮用水、零食、餐食、糖果 | 不推断低血糖/饮食禁忌 |
| 8 | `出行辅助` | 轮椅、拐杖、护具、陪护椅、便携凳 | 只表达出行协助，不描述行动能力原因 |
| 9 | `其他` | 未命中映射表或不确定项 | 安全兜底；不做智能猜测 |

## 4. 映射与展示规则

### 4.1 输入

`PreparationPackage.carry_items: list[str] | None`

### 4.2 输出

```python
class CarryItemsSummary(BaseModel):
    total_count: int
    categories: list[str]
```

### 4.3 规则

1. `carry_items is None` 或空数组：`{total_count: 0, categories: []}`。
2. `total_count = len(carry_items)`，不去重；这是用户端原始清单数量。
3. 每个 item 仅用于服务端分类，不出现在 companion response。
4. 多个 item 命中同一类别时，`categories` 只保留一次。
5. 单个 item 命中多类时，按第 3 节固定顺序取第一个安全类别，避免自由推断。
6. `categories` 按第 3 节固定顺序输出，保证测试稳定。
7. 不确定、不应推断、含敏感病情词的 item：归 `其他` 或其安全父类，不生成疾病类目。

## 5. 明确禁止

陪诊师 response 中禁止出现：

- 原始 item 文本：如 `胰岛素笔`、`血糖仪`、`产检报告`。
- 疾病/症状/科室推断：如 `糖尿病`、`肿瘤`、`孕产`、`精神科`。
- 药名/器械名/检查名：如具体药品名、设备名、检查项目名。
- 单类别计数：如 `医疗设备 2 件`（可能辅助反推病情）。
- 目的解释：如 `用于控制血糖`。

## 6. 验收样例

| 原始 `carry_items` | `carry_items_summary` |
|---|---|
| `[]` | `{total_count: 0, categories: []}` |
| `["身份证", "医保卡", "银行卡"]` | `{total_count: 3, categories: ["证件凭证", "支付材料"]}` |
| `["胰岛素笔", "血糖仪", "身份证"]` | `{total_count: 3, categories: ["证件凭证", "药品用品", "医疗设备"]}` |
| `["产检报告", "水杯", "纸巾"]` | `{total_count: 3, categories: ["就医资料", "日常用品", "饮食补给"]}` |
| `["不确定的私人物品"]` | `{total_count: 1, categories: ["其他"]}` |

## 7. 实施交接给 hutao

PM 决策：**MVP 用确定性映射表，不调用 LLM。**

开发侧建议（不强绑实现）：
- 新增 `CarryItemsSummary` Pydantic model。
- `CompanionPrepPackageView.carry_items_summary` 从 `str | None` 改为 `CarryItemsSummary`。
- `get_prep_for_companion` SELECT `carry_items`，服务层映射为 summary，但 response 不含 raw `carry_items`。
- 加红线测试：`胰岛素笔 + 血糖仪 + 身份证` 不得在 companion response 中出现 `胰岛素` / `血糖` / `糖尿病` 等字面。

## 8. 映射表物理存储 + 维护职责（PR #294 review 建议 #2/#3 补补）

### 8.1 存储位置（yaml + py loader 双轨）

- **真源**：`docs/medical-content/carry-items-category-mapping.yml`
  - PM 维护、可独立走 PR、改动 diff 清晰、不依赖 py 代码
  - 同目录与 `prohibited-keywords.yml` 并列，保持一致体验
- **loader**：`backend/app/services/carry_items_categorizer.py`（hutao impl）
  - 启动加载到模块级 `_MAPPING: dict[str, str] = {...}`（一次 import、cache 住，性能等价 hardcode）
  - 提供 `categorize(item: str) -> Category` API、denylist 守门（疾病/药名 → raise / log 但不入映射 value）
  - 启动时字典未加载成功 → fail-fast（不走 fail-open，反面学 ADR-0051 反案 #24 blocklist fail-open 锅）
- **asset-presence test**：`backend/tests/integration/test_carry_items_mapping_yml_present.py`（hutao impl）
  - assert `yml_path.exists() == True`、不 mock
  - assert 加载后 `len(_MAPPING) >= 50`（防空 yml 上线）
  - `backend/Dockerfile` `COPY docs/medical-content/` 需包含本 yml（同 ADR-0051 反案 #24 纠正路径）

### 8.2 维护职责

| 变更类型 | 维护方 | 审批路径 |
|---|---|---|
| 初版词条（v0） | 凝光（PM） | 已随本 PR #294 交付（§3 + §4） |
| 后续扩词（同现有17 类） | PM 主导 | PM 提 PR → dev/architect 1 人 review approve → PM 合并（不需 ADR amend） |
| 调整已有词条映射目标类 | PM 主导 | 同上，但需 changelog 标「映射调整」+ 启动旧 fixture diff |
| 加新分类（第 10 类及以上）/ 改顺序 / 拆分既有分类 | PM + 架构师 + Owner 三签 | ADR-0048 r2 amend，项目重点变更 |
| 删词（缩窄映射） | PM 单签可推 | changelog 标「删词」，不影响 ABAC 红线不需 ADR amend |
| denylist 红线（疾病/药名/科室推断） | PM + 架构师双签 | 触红线词永久不进映射 value，只进 denylist set |

### 8.3 为什么不接魈 review 建议 #3（hardcode in Python）

魈建议「hardcode in Python (`carry_items_categorizer.py`)」以拿加载性能 + 单测覆盖 + git 历史。PM 反驳：

- 加载性能：yaml import 后 cache 为模块级 dict，运行时访问与 hardcode 等价（无反复解析）
- 单测覆盖：yaml 同样可 `yaml.safe_load` 走 fixture，覆盖率与存储格式无关
- git 历史：yaml diff 比 py dict literal 更易 review，PM 可独立提 PR 不劳烦 dev
- **核心理由**：PM 是维护方，yaml 让 PM 独立扩词（不动 py 代码 = 不踩越权红线）；hardcode py 则每次扩词都要 dev 改源码，与「初版 PM own」表中的职责划分矛盾

同时不完全拒 hardcode 优点：py loader 里允许额外加 hardcoded `denylist`（疾病词）作为代码层守门、与 yaml 映射双重护绑。

## 9. Schema 变更兼容性（OpenAPI breaking change disclose，PR #294 review 建议 #1）

本设计把陪诊师 `prep-package` response 的 `carry_items_summary` 字段类型从 `str | None`（PR #233 临时 placeholder）改为 `CarryItemsSummary | None`。这是 OpenAPI schema 上的 **breaking change**（type discriminator string → object）。

### 9.1 三端同步 PR 起手准入条件（PM 守门）

- **iOS**：`CompanionPrepPackage` model 添加 `CarryItemsSummary` struct；MoshiCodable/JSON Decoder 调试
- **wxapp**：陪诊师订单详情 page data 解构更；wxml 渲染拆为 `{{summary.total_count}}` + `{{summary.categories.join('、')}}`
- **admin-h5**：admin 调试视图（若有）同步改
- **后端 PR**：必同一 sprint 出三端跟进 PR（可分仓，但需引用同一 task ID）
- **schemathesis CI gate**：`scripts/qa/openapi_contract_diff.py` 会 diff 出 type 变化并标红，PR description 需显式 disclose `BREAKING: carry_items_summary type str|None → object`
- **灰度开关**：任一端 PR 未合 → 后端 PR 不解锁陪诊师访问

### 9.2 为什么可接受这个 breaking change

- PR #233 临时 placeholder `str | None` 本就不是正式 schema（ADR-0048 §7.0.1 始终要求 `CarryItemsSummary` object）
- 由于陪诊师 prep-package 端没有外部 partner，全部 first-party client（iOS/wxapp/admin）可控 + 合 sprint 同步发版
- ADR-0048 r1 amend 明列三端同步为准入条件，不会出现后端领先、前端脱后的漂移
