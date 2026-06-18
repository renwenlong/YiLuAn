# COORDINATOR_HYGIENE.md

协调者 (甘雨) 转传消息 / 纠偏 ping 的卫生规则.

> **背景**: 2026-06-06 07:43 UTC 胡桃 PR #196 自称 "security fix + 优先 merge",
> 协调者若不加核验直接转传 "🚨 安全漏洞" 给 reviewer / Owner, 会放大夸大表述,
> 制造 alarm fatigue. 同源事件见 docs/dev/PR_SEVERITY_LEXICON.md.
>
> **目标**: 协调者作为消息中枢, 对 severity 类措辞负 "转传前核验" 之责, 不做
> 夸大表述的无脑放大器; 同时纠偏时给原发起方回执, 避免无效二次转传.

---

## 1. severity 措辞转传前必核验 (AC#4 强约束)

协调者转传任何含以下措辞的消息前, **必须先要求来源方 (dev) 给出 verification
来源**:

- "security fix" / "安全漏洞" / "漏洞修复"
- "优先 merge" / "紧急" / "critical" / "P0"
- "bypass" / "提权" / "越权" / "数据泄露"

**verification 来源** 至少其一:

- attack chain 5 项 (见 PR_SEVERITY_LEXICON.md §2)
- grep main 实证输出 (证明既有防御存在/缺失)
- POC / 复现步骤

**处理规则**:

1. dev 给得出 verification → 正常转传, 可附 "已核验" 标注.
2. dev 给不出 → **拒绝转传**, 或转传时显式标注 `[dev 声称未 verify]`, 让下游
   自行判断分量.
3. 协调者**不替 dev 编造** verification, 也不替 dev 拔高/降低 severity.

---

## 2. 纠偏 alarm 类 ping 时给原发起方回执 (AC#5 强约束)

当协调者发现某条 ping 是夸大 alarm (如 dev 称 security fix 实为
defense-in-depth), 做纠偏后:

1. **主动给原 ping 发起方回执**: `你那条 X 我核验后归类为 defense-in-depth
   (理由: …), 已按此转传/未转传给 Y. 如有异议给 attack chain.`
2. 目的: 让原发起方知道纠偏结果, 避免他**重复发同样 alarm** 给别人 (协调者做
   无效二次转传).
3. 回执要给**理由** (为何降级), 不只是结论, 便于 dev 学习校准.

---

## 3. 与其他文档的关系

- severity 词汇表判定标准: `docs/dev/PR_SEVERITY_LEXICON.md`
- reviewer 端核验 SOP: `docs/dev/REVIEWER_VERIFY_PROTOCOL.md`
- 本文件管 **协调者 (转传中枢)** 这一环, 三者形成 dev→协调者→reviewer 全链路
  severity 把关.

---

## 4. 为什么不上 CI / 不强制 (AC#8 同源)

协调者 hygiene 是人工判断 + 自律, 无法机械化. 与 PR_SEVERITY_LEXICON.md §6 /
DRAFT_PR_PROTOCOL.md §6 同源: 文档约定 + 角色教育, 不上流程枷锁.

---

## 5. 修订历史

- 2026-06-18, 胡桃 (程序员): v1 初版, S2-OPS-017 AC#4/#5.
  owner 侧 scope 属甘雨, 本文档由 hutao 起草, 甘雨可后续 amend.
