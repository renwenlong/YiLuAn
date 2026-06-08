# S2-OPS-020 CI 失败自动通报

帝君 2026-06-08 07:39 UTC 拍 A3f 立项,胡桃 implement,魈 review.

## 背景

PR #204 CI fail 黑盒 34h, PR #199 CI fail 黑盒 5h, 趋势恶化, 团队靠
dashboard 巡检不可持续, 流程死链。引入自动通报闭环。

## 实现

`.github/workflows/ci-failure-notify.yml` — 用 GitHub `workflow_run` event
监听其他 workflow 完成, conclusion ∈ {failure, cancelled, timed_out} 时:

1. **解析 PR 上下文** — 优先 `workflow_run.pull_requests[0]`, 兜底从
   `head_sha` 反查 PR (fork PR / push 事件需要)
2. **采集失败 job** — `gh api .../runs/{run_id}/jobs` 过滤
   conclusion!=success, 生成 markdown 摘要
3. **去重 (AC2)** — 在 PR comment 顶部写隐藏 marker
   `<!-- ci-failure-notify-marker:run_id={id} -->`, 同 run_id 已 comment 则
   跳过 (避免重试或多次 dispatch 时灌水)
4. **写 PR comment (AC1)** — 含 workflow / conclusion / run_id+url /
   author / 失败 job 列表 + log link
5. **发群 webhook (AC3)** — POST 飞书机器人 webhook URL, msg_type=text,
   1-2 行可读

## 监听范围

显式枚举 (workflow_run 不支持 wildcard):

- `Tests` — 含 3 个 required check (backend / docker-build / wechat)
- `Alembic Smoke (PG-only)` — 非 required 但 sprint 多次 fail
- `admin-v2 CI`

新增 workflow 需要监听时, 修 `on.workflow_run.workflows` 数组追加。

## Secret 依赖

| Secret 名 | 用途 | 缺失行为 |
|----------|------|---------|
| `GITHUB_TOKEN` | PR comment + jobs API | GitHub 默认注入, 不需配 |
| `LIYUE_GROUP_WEBHOOK_URL` | 璃月群飞书机器人 webhook | **dry-run** (仅 step log, 不发群) |

配置 `LIYUE_GROUP_WEBHOOK_URL`:

```bash
gh secret set LIYUE_GROUP_WEBHOOK_URL \
  --repo renwenlong/YiLuAn \
  --body 'https://open.feishu.cn/open-apis/bot/v2/hook/<hook-id>'
```

未配前 PR comment 仍正常 (AC1 + AC2 不依赖群 webhook)。

## 端到端验证 (AC4)

### 场景 1: 故意 CI fail 触发 (主路径)

1. 起一个 throwaway 测试 PR (在 backend 加一行 `assert False`)
2. 等 `Tests` workflow 跑完, conclusion=failure
3. ≤2min 内 (`workflow_run` 排队 + notify job 跑 ~30s):
   - **AC1 检查**: PR 自动收到 comment, 内容含
     `Backend Tests (failure)` + log link
   - **AC3 检查**: 璃月群收到飞书消息 (若 secret 已配); 未配则 notify job
     log 含 `LIYUE_GROUP_WEBHOOK_URL secret not configured; dry-run`

### 场景 2: 同 run 重复触发 (AC2 去重)

1. 在场景 1 的 throwaway PR 上 manually re-run failed jobs (workflow_run
   id 不变, 因为 re-run failed 共享 parent run)
2. 等再次 conclusion=failure
3. **AC2 检查**: 不写新 PR comment (因为 marker 命中); notify job log 含
   `Dedupe hit (run_id=... already commented), skipping`
4. 若用 "re-run all jobs" (生成新 run_id), 则会写新 comment (新 run_id 不
   命中 dedupe), 符合预期 — 用户故意要新 attempt 的反馈

### 场景 3: workflow conclusion=success (negative)

1. 正常通过的 PR, `Tests` workflow conclusion=success
2. **检查**: notify job 不跑 (job 级 if 过滤), Actions tab 看不到 notify
   workflow 入口 — workflow 仍触发但所有 job skip

### 场景 4: PR 关闭后失败 (edge case)

`workflow_run` 仍触发, `pr.has_pr` resolve 失败 (无 open PR), notify job
log 含 `No PR associated with workflow_run; skipping PR comment`, 群
webhook 仍正常 (无 pr_line 前缀)。

## 已知限制 (不在本 task 范围)

- pre-commit hook 强制 alembic check + pytest -q (我 02:42 UTC 提的 A 选项
  第 1 件) **不包含** — 帝君拍全 A 但 OPS-020 task scope 仅覆盖第 2 件,
  hook 留观测期, 视本 task 上线后效果再立项
- 主分支 push 失败暂不通知 PR (无对应 PR), 只发群 webhook (push 事件
  workflow_run 的 pull_requests 字段为空, has_pr=false 跳过 PR comment)
- 非 GitHub Actions 触发的失败 (如 Jenkins / 本地 hook) 不在本机制覆盖

## 关联

- 父 task: S2-OPS-020-CI-FAIL-AUTO-NOTIFY (status=in-progress, assignee=developer)
- 触发场景: PR #204 (34h)、PR #199 (5h)
- AC: AC1 (≤2min PR comment) / AC2 (run_id 去重) / AC3 (群 webhook) / AC4
  (端到端实测)
- ADR: 无 — 本 task 是单文件 workflow 改动, 实现层细节, 不上 ADR
