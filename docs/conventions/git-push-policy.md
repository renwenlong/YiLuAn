# Git / PR 流程规矩（YiLuAn 项目）

> 生效：2026-05-29（D4-D10 三端前端阶段起）
> 触发背景：W20 后端骨架阶段 23 commit 直推 main（既往不咎），帝君拍板从此走 PR 流程。
> 机制层保障：魈已开 main branch protection。

## 一、硬规矩（全员，机制层强制）

main 分支已启用 branch protection：

- ❌ **禁止直接 push main**
- ✅ **合并必须经 PR + ≥1 approval**（code review 落 GitHub PR，不再只在群里）
- ✅ **PR 上的 review comment 必须 resolve 才能合**
- ❌ **禁 force push / 禁删 main**

## 二、标准流程（每个 develop / bug task）

1. **开分支**：`git checkout -b feature/<TASK-ID>-<简述>`
   - 例：`feature/S2-DEV-012-wechat-share-page`
2. **提交 + 推分支**：`git push origin feature/<...>`（分支推送不受保护限制）
3. **建 PR**：`gh pr create`，body 必须含：
   - task id
   - 自测结果（关键：`pytest -m money_safety` + `pytest -m share_security` 全绿截图/输出）
   - 关联 ADR / PRD 条目
4. **Review**：魈（或指定 reviewer）在 GitHub PR 上 review + approve / request changes
5. **合并**：approve 后 `gh pr merge`；pre-push hook 本地兜底全量 pytest

## 三、与 taskboard 状态机对齐

| taskboard 状态 | Git/PR 对应 |
|---|---|
| `in-progress` | feature 分支开发中，尚未建 PR |
| `in-review` | PR open + 等 reviewer approve（必跟 `request_review`）|
| `done` | PR merged（必跟 `handoff`）|

- **`set_status in-review` ↔ PR open**：建 PR 后才置 in-review，body 带自测结果
- **`set_status done` ↔ PR merged**：PR 未 merge 不得置 done
- review comment 未 resolve → PR 不能合 → task 不能 done

## 四、push 前自检（pre-push 兜底 + 人工确认）

- push 分支前本地跑 `pytest -m "money_safety or share_security"` 全绿
- 涉及支付/share 安全路径的改动，PR body 必须显式声明已跑对应 gate
- 缓存目录（`.hypothesis/`、`.taskboard-tmp/`）已在 `.gitignore`，勿提交

## 五、例外

- 今日（2026-05-29）已直推 main 的 23 commit 不回溯（双 gate 干净，既成事实）
- 新规从下一个 task（D4-D10 阶段）生效
- 紧急 hotfix 仍走 PR，但可 fast-track review（reviewer 优先响应），不绕过 protection
