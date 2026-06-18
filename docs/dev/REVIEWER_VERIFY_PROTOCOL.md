# REVIEWER_VERIFY_PROTOCOL.md

Reviewer 审 security / P0 / critical 类 PR 的实证 SOP.

> **背景**: 2026-06-06 07:43 UTC 胡桃 PR #196 自称 security fix, 若 reviewer
> 不 grep main 实证 attack chain 就 approve, 等于背书夸大表述. 刻晴 07:49 拍:
> reviewer 对 security 类 PR 必须先实证. 同源 docs/dev/PR_SEVERITY_LEXICON.md.
>
> **目标**: reviewer 审含 security/P0/critical 关键词的 PR 时, 有一套必做的
> 实证动作, 不被 author 的措辞牵着走.

---

## 1. 触发条件

PR 命中以下任一时, reviewer 走本 SOP:

- "Severity" 勾了 security fix
- title / description / comment 含 "security" / "漏洞" / "vulnerability" /
  "bypass" / "提权" / "越权"
- priority = P0 / P1 且理由涉及 security

---

## 2. Reviewer 必做实证动作 (AC#10 强约束)

1. **grep main 实证 attack chain 完整链路**:
   - 对 author 给的 attack chain 第 4 项 (真实访问入口), 自己 `grep` /
     读 main 上的代码, 确认该链路**真能走通**.
   - 重点验: 链路上是否有**既有防御**已经阻断. 若有 → 改前 attack path 走不通
     → 应归 defense-in-depth, 要求 author 改 Severity.
2. **缺 attack chain 不 approve**:
   - security fix 而 attack chain 5 项不全 → 退回要求补, 不 approve.
3. **链路走不通则要求改分类**:
   - 实证发现既有防御已挡 → 这是 defense-in-depth, 要求 author 修正措辞 +
     priority (通常 security fix 的 P0/P1 → defense-in-depth 的 P2-P3).
4. **实证结论留痕**:
   - 在 PR review comment 写明实证过程 (grep 了哪个文件 / 哪几行防御挡住),
     不只写 "LGTM" / "看着像真洞".

---

## 3. 实证示例 (以 PR #196 为镜)

reviewer 若当时走本 SOP:

```
# author 称 sign_read_url _safe_key bypass 是 path traversal 洞
# reviewer 实证:
grep -n "_safe_key\|verify_sig" backend/app/.../storage_backend.py
# 发现: 真 fs 访问入口 verify_sig 有 5 重校验 (含 path 规范化 + 前缀锁定)
# sign_read_url 产出签名 URL, 不直接落 fs 路径
# 结论: attack path 改前走不通 → defense-in-depth, 非 security fix
# 动作: 要求 author 把 Severity 从 security fix 改为 defense-in-depth hardening
```

---

## 4. 与其他文档的关系

- severity 判定标准 + attack chain 模板: `docs/dev/PR_SEVERITY_LEXICON.md`
- 协调者转传端把关: `docs/dev/COORDINATOR_HYGIENE.md`
- 本文件管 **reviewer 端实证**, 三者形成 dev→协调者→reviewer 全链路把关.

---

## 5. 为什么不上 CI (AC#8 同源)

attack chain 真假是语义判断 + 代码实证, CI 无法机械验证. 与
PR_SEVERITY_LEXICON.md §6 同源: reviewer 教育 + SOP, 不上 CI check.

---

## 6. 修订历史

- 2026-06-18, 胡桃 (程序员): v1 初版, S2-OPS-017 AC#10 (刻晴 07:49 拍).
