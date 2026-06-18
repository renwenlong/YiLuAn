# TASK_CREATION_AUTHORITY.md

立 task 时的优先级 / severity 措辞约定.

> **背景**: dev 角色立 task 时, 若随手标 P0 / "security" / "漏洞", 会挤占真正
> 高优先级 task 的带宽 + 触发不必要的 PM 守门 escalation. 同源 alarm fatigue
> 风险见 docs/dev/PR_SEVERITY_LEXICON.md.
>
> **目标**: 给 dev 立 task 的优先级一个**建议默认值**, 避免优先级通胀.

> ⚠️ **本文档当前为建议表述 (降级)**. 等 S2-OPS-017 的 PR review-approve 后,
> 按 reviewer 决定升回硬约束. 在此之前, 下列为**建议默认值**, 非强制门禁.

---

## 1. dev 立 task 优先级建议默认值 (AC#9, 建议表述)

dev 角色 (胡桃) 自主立 task 时, **建议**:

- **默认 priority = P2-P3**. dev 自起手的改进 / 加固 / 清理类, 默认走 P2-P3.
- **P0/P1 需上呈**: 若 dev 认为某 task 该 P0/P1, **不自己直接标 P0/P1**, 而是
  立为 P2 + 在 description 写明 "建议升 P0/P1, 理由: …", 交 PM (凝光) / 架构师
  (魈) ratify 后再升.
- **含 security fix / 漏洞 / vulnerability 字样的 task**: 必须在 description
  附 attack chain 5 项 (见 PR_SEVERITY_LEXICON.md §2); 给不出真链路的, 改用
  "defense-in-depth hardening" 措辞, priority 默认 P2-P3.

---

## 2. 为什么 (优先级通胀的危害)

1. 优先级是稀缺信号. 人人 P0, 等于没有 P0.
2. dev 自标 P0 会触发 PM 守门 escalation (反案 #38), 消耗团队带宽.
3. severity 措辞通胀 = alarm fatigue, 真 incident 时反应迟钝.

---

## 3. 与 PM 守门 (反案 #38) 的关系

- 本文档管 **dev 立 task 时的自律默认值** (源头降通胀).
- 反案 #38 管 **dev 自起手 task 时的 PM ratify 门禁** (执行端守门).
- 两者互补: 源头少标 P0 → 守门压力小; 守门兜底 → 即使误标也有 PM 拦截.

---

## 4. 修订历史

- 2026-06-18, 胡桃 (程序员): v1 初版 (建议表述), S2-OPS-017 AC#9.
  待本 task PR review-approve 后按 reviewer 决定升硬约束.
