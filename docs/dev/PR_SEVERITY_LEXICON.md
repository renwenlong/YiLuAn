# PR_SEVERITY_LEXICON.md

PR description 严重度词汇表 + attack chain 强制模板.

> **背景**: 2026-06-06 07:43 UTC 胡桃 PR #196 在 description / title 写
> "sign_read_url _safe_key bypass + 5 项防御加固", PR comment 进一步称
> "🚨 安全漏洞修复 + 优先 merge 建议: PR #196 是 security fix". 经 grep main
> 实证: `verify_sig` 5 重防御已守住 fs 真访问入口, `sign_read_url` 不调
> `_safe_key` 是 by design (签名 URL 不落 fs 路径) —— 实际是
> **defense-in-depth hardening, 不是 security fix**.
>
> **问题**: severity 表述夸大 = alarm fatigue 风险. 未来真有 security
> incident 时, reviewer 因长期被 "security fix" 狼来了麻木, 漏掉真漏洞.
>
> **目标**: 统一 PR 严重度词汇 + 对 security 类强制 attack chain 举证, 让
> "security fix" 这个词回归它该有的分量. 文档约束 + reviewer 自律, 不上 CI
> check (见 §6 理由, 与 DRAFT_PR_PROTOCOL.md §6 同源).

---

## 1. 严重度词汇表 (AC#1 强约束)

PR description 的 "Severity" 必须从下表选**恰好一类**, 不夸大、不模糊:

| 类别 | 定义 | 判定门槛 | 举证要求 |
|------|------|---------|---------|
| **security fix** | 修复一个**真实存在的 attack path**, 且在 production 配置下**可被利用** (exploitable) | 必须能画出从 attacker 起点到受影响数据/权限的**完整链路**, 且链路上**无既有防御阻断** | **强制** attack chain 5 项 (见 §2) |
| **defense-in-depth hardening** | 在**已有防御已经守住**的前提下, 额外加一层防御 (纵深防御) | 既有防御**已经**阻断了 attack path; 本 PR 是 "万一某层失效" 的冗余加固 | 说明既有防御为何已足够 + 本层加固防的是哪种"假设失效" |
| **feat** | 新增功能 | 无 security 含义 | 无 |
| **refactor** | 行为不变的结构调整 | 无 security 含义 | 无 (但需单向性/无破坏证明) |
| **cleanup** | 删死代码 / 清注释 / 去重 | 无 security 含义 | 无 |
| **docs** | 仅文档 | 无 security 含义 | 无 |

### 关键区分: security fix vs defense-in-depth

这两个最容易被混用 (PR #196 即误用). 判定口诀:

> **改之前, attack path 是否真的可走通?**
> - 可走通 (无防御阻断) → 你修的是真洞 → **security fix**
> - 走不通 (已有防御挡住) → 你加的是冗余层 → **defense-in-depth**

**反例 (PR #196)**: `sign_read_url` 不调 `_safe_key`, 看似 "路径遍历 bypass".
但 `sign_read_url` 产出的是**签名 URL**, 不直接落 fs 路径; 真正的 fs 访问入口
`verify_sig` 有 5 重校验已挡住遍历. 改之前 attack path **走不通** → 这是
defense-in-depth, **不是** security fix. 写成 "bypass 修复" = 夸大.

---

## 2. security 类强制 attack chain 5 项 (AC#3 强约束)

PR "Severity" 勾选 **security fix** 时, description 必须填写完整 attack chain,
**缺任一项视为举证不足, reviewer 应拒绝 approve**:

```markdown
### Attack Chain (security fix 必填)

1. **Attacker 起点**: 谁能发起? (匿名外网 / 已登录普通用户 / 越权 admin / 内部网络…)
2. **控制点**: attacker 能控制哪个输入? (URL param / body 字段 / header / 上传文件名…)
3. **攻击 payload**: 具体构造什么? (贴出真实 payload 示例, 如 `../../etc/passwd`)
4. **真实访问入口**: payload 经过哪条代码路径**真正**触达受保护资源?
   (要求: 链路上**无**既有防御阻断; 若有防御, 说明为何被绕过)
5. **受影响数据/权限**: 成功后 attacker 拿到什么? (读任意文件 / 越权改单 / 提权…)
```

**举证标准**: 第 4 项是核心 —— 必须证明**链路真能走通**, 不能只说 "理论上可能".
若给不出无防御阻断的真链路, 说明这是 defense-in-depth, 改 Severity 分类.

---

## 3. PR template 集成 (AC#2 已落地, 本节说明)

`.github/PULL_REQUEST_TEMPLATE.md` 的 "Severity" section 已含三选 checklist
(由 S2-OPS-018 引入). 本 task 补强:

- security 类后追加 "Attack Chain (security fix 必填)" 子模板 (§2 内容).
- 词汇表正式落地为本文件, template 的 "见 docs/dev/PR_SEVERITY_LEXICON.md
  词汇表 (when exists)" 中 "when exists" 限定可移除 —— 文件现已 exists.

---

## 4. 历史夸大表述归档 (AC#7)

存量案例集中归档于本节, 供 reviewer 校准"什么叫夸大":

| PR | 原表述 | 实际类别 | 夸大点 |
|----|--------|---------|--------|
| #196 | "_safe_key bypass + 安全漏洞修复 + security fix" | defense-in-depth | `sign_read_url` 不落 fs 路径, `verify_sig` 5 重防御已挡, attack path 改前走不通 |
| #195 | (同期 storage 安全契约系列, 表述偏重) | refactor/hardening | 安全契约拆分属结构调整 + 冗余加固, 非修真洞 |

> 后续发现新的夸大案例, 追加到本表, 不另起 task (轻量归档原则, 同
> DRAFT_PR_PROTOCOL.md §7).

---

## 5. Reviewer 用法 (与 REVIEWER_VERIFY_PROTOCOL.md 配合)

reviewer review 含 security/P0/critical 关键词的 PR 时:

1. 看 "Severity" 勾的是不是 security fix.
2. 若是, 检查 attack chain 5 项是否填全 + 第 4 项链路是否真能走通.
3. 自己 grep main 实证: 既有防御是否已挡住该 attack path (走不通 = 应改归
   defense-in-depth).
4. 举证不足 → 不 approve, 要求 author 补 attack chain 或改分类.

详细 reviewer SOP 见 `docs/dev/REVIEWER_VERIFY_PROTOCOL.md`.

---

## 6. 为什么不上 CI check (AC#8)

与 `DRAFT_PR_PROTOCOL.md` §6 同源理由:

1. severity 分类是语义判断, CI 无法机械验证 "attack path 是否真能走通".
2. 强上 CI 会逼 author 为过 check 而乱填, 反而稀释举证质量.
3. 目标是 reviewer 教育 + 文档约定, 非流程枷锁.

**正解**: 词汇表 (本文件) + PR template checklist + reviewer 自律
(REVIEWER_VERIFY_PROTOCOL.md), 三层非强制约束.

---

## 7. 修订历史

- 2026-06-18, 胡桃 (程序员): v1 初版, S2-OPS-017-PR-DESCRIPTION-SEVERITY-LEXICON.
  起因 PR #196 自夸 security fix, 第一手教训立此词汇表.
