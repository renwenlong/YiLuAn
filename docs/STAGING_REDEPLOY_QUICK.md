# Staging 手动 Redeploy 快速手册（ADR-0059 方案 C）

> **用途**：把 `origin/main` 上已通过 required CI 的明确 commit 部署到 staging。
> **当前边界**：受限 SSH / deploy wrapper 尚未由帝君配置前，本手册由帝君在
> staging 主机执行；胡桃只提供 SHA 与 CI 证据。不得把 private key 放进 agent
> workspace，也不得给 agent 任意远程 shell。

## 1. 部署前确认

记录目标 commit，且只允许部署 `origin/main` 上的 SHA：

```bash
cd <staging-checkout>
git fetch origin main
TARGET_SHA="$(git rev-parse origin/main)"
git merge-base --is-ancestor "$TARGET_SHA" origin/main
printf 'target=%s\n' "$TARGET_SHA"
```

如果需要部署的 SHA 不是当前 `origin/main`，停止并先确认原因；不得用本地 feature
branch、未 push commit 或任意 tag 替代。

## 2. Required CI gate（不可跳过）

```bash
cd <staging-checkout>
deploy/staging/check-main-ci.sh --sha "$TARGET_SHA"
```

只有脚本输出 `CI gate PASSED` 且退出码为 0 才能继续。以下任一情况立即停止：

- required check 缺失；
- check pending / failure / cancelled / skipped / neutral；
- `gh`、`python3` 或 GitHub API 不可用；
- 目标 SHA 与 `origin/main` 不一致。

## 3. 更新 checkout 并部署

```bash
cd <staging-checkout>
git checkout --detach "$TARGET_SHA"
cd deploy
./up.sh staging
```

`up.sh` 会构建并拉起 compose 栈、执行 migration、等待 backend health 并 seed
staging fixtures。不要使用 `git reset --hard` 清理未知改动；checkout 不干净时停止，
先确认文件归属。

## 4. 验活

```bash
curl -fsS http://127.0.0.1:18080/api/v1/ping
curl -fsS http://127.0.0.1:18080/health
curl -fsS http://127.0.0.1:18080/readiness
curl -fsS http://127.0.0.1:18080/__staging/mock-pay/health
curl -fsS http://127.0.0.1:18080/__staging/mock-sms/health
```

需要完整业务演练时：

```bash
cd <staging-checkout>
python3 deploy/staging/replay/run-weekly-rehearsal.py --skip-seed
```

故障定位与 teardown 见 `docs/STAGING_REHEARSAL_RUNBOOK.md`。

## 5. 回报与审计

每次 redeploy 在群里记录：

```text
staging redeploy
- SHA: <TARGET_SHA>
- URL: <staging URL>
- deployed_at: <UTC ISO-8601>
- operator: <operator / restricted wrapper identity>
- CI gate: 5/5 success
- health: ping/health/readiness/mock-pay/mock-sms PASS
- rehearsal: PASS / NOT_RUN / FAIL(<report>)
```

没有完整记录时，不得对外声称 staging 已更新。

## 6. 受限 wrapper 的主机侧契约

帝君配置的受限入口应只接受一个参数：`<origin-main-sha>`，并按固定顺序执行：

1. fetch `origin/main` 并验证参数 SHA 属于 `origin/main`；
2. 运行 `check-main-ci.sh --sha <sha>`；
3. checkout 该 SHA；
4. 运行 `deploy/up.sh staging`；
5. 执行 §4 验活；
6. 写入 §5 审计记录。

wrapper 必须拒绝额外 shell 参数、环境覆盖和任意命令拼接。推荐 bastion 白名单脚本
或短时证书调用；禁止常驻 full SSH key。
