# Staging Rehearsal Runbook (D-044)

> **Trigger**: 每周三 14:00 GMT+8（UTC 周三 06:00）
> **Owner**: 当周 on-call DevOps（默认 wenlong）
> **Why**: 5 个 P0 Blocker（B-01~B-05）等待外部资源期间，用 mock provider
> 跑完整患者旅程，避免 provider 抽象层 drift、回归手感丢失。
> 决议来源: D-044。

## 1. 准备

需要的本地依赖：

- Docker Desktop 已启动
- Python 3.11+（脚本只依赖 stdlib + httpx）
- `gh` CLI（如需上报失败到 GitHub Issue）

## 2. 一键拉起 staging 栈

PowerShell（推荐）:

```powershell
cd C:\Users\wenlongren\Desktop\PZAPP\YiLuAn-staging\deploy\staging
./up.ps1
```

bash（macOS/Linux）:

```bash
cd deploy/staging
./up.sh
```

成功标志：

- `docker compose -p yiluan-staging ps` 全部 `healthy`
- `curl http://127.0.0.1:18080/api/v1/ping` → `{"message":"pong","version":"v1"}`
- `curl http://127.0.0.1:18080/__staging/mock-pay/health` → `{"status":"ok",...}`
- `curl http://127.0.0.1:18080/__staging/mock-sms/health` → `{"status":"ok",...}`

## 3. 跑周演练

```powershell
cd C:\Users\wenlongren\Desktop\PZAPP\YiLuAn-staging
python -X utf8 deploy/staging/replay/run-weekly-rehearsal.py
```

退出码 `0` = 全绿；非零 = 失败，查看末行 `[rehearsal] report:` 指示的报告路径。

报告路径示例：`deploy/staging/reports/rehearsal-2026-04-27.md`

报告自动包含：
- 每步耗时 + 结果
- 失败步骤的完整 traceback
- 可重放的 artefact JSON（订单号、payment_id 等）

> **首次运行**：脚本会自动调 `seed_staging.py` 准备 5 个 patient + 3 个 companion +
> 1 个 admin + 111 家医院。后续如果数据库已 seed，可加 `--skip-seed`。

## 4. 失败时的处理

| 失败位置                 | 第一反应                                               |
|--------------------------|--------------------------------------------------------|
| `ping backend`           | `docker logs yiluan-staging-backend-staging-1 --tail=200` |
| `pick hospital`          | 检查 seed 是否成功；重新 `python deploy/staging/seed_staging.py` |
| `pay order`              | 看 `payment_service` 日志；mock provider 是否启用      |
| `trigger wechat callback`| 看 `mock-pay-stub` 日志：`docker logs yiluan-staging-mock-pay-stub-1` |
| `companion accepts`      | 检查 companion 是否被 admin approve 为 `verified`      |
| `admin refund`           | 检查 `13900000000` 用户在 DB 中是否含 `admin` 角色      |

升级路径：

1. **本地修：** 在 worktree 起 `branch fix/staging-...`，本地修复后跑过 replay
   再 PR。
2. **provider 抽象层 drift（最严重）：** 立即在群里 @架构组，开 P1 Issue，
   贴报告链接 + 失败步骤截图。
3. **基础设施抖动**：`./down.ps1 && ./up.ps1` 重起，再跑一遍；连续两次失败
   才算真失败。

## 5. 报告归档

- 报告自动写到 `deploy/staging/reports/rehearsal-YYYY-MM-DD.md`
- 每月底（每月最后一周三的下一个工作日）打包提交一次：
  ```bash
  git add deploy/staging/reports/
  git commit -m "ops(D-044): archive staging rehearsal reports YYYY-MM"
  git push
  ```
- 大于 6 个月的报告可以归档到 `deploy/staging/reports/archive/YYYY/`。

## 6. 清理 staging 栈

```powershell
cd C:\Users\wenlongren\Desktop\PZAPP\YiLuAn-staging\deploy\staging
./down.ps1            # 保留 volume
./down.ps1 -RemoveVolumes   # 同时删 pgdata，下次首次启动会重建
```

## 7. CI 触发（GitHub Actions，可选）

`.github/workflows/staging-rehearsal.yml` 配置了 `cron: '0 6 * * 3'`
（即每周三 14:00 GMT+8），但需要 self-hosted runner（hosted runner 不能跑
docker compose + 本地 18080 端口的栈）。

当前状态：**未启用 self-hosted runner**，每周演练靠本 runbook 手动执行。

启用方法：

1. 在公司内网机器上注册 self-hosted runner，标签 `staging-mock`。
2. 把 workflow `runs-on: ubuntu-latest` 改为 `runs-on: [self-hosted, staging-mock]`。
3. 取消 workflow 文件顶部的 `# DISABLED:` 注释。

## 8. 验收 checklist（每周跑完贴到群里）

- [ ] `up.ps1` / `up.sh` 一键起栈成功
- [ ] `replay` 脚本 GREEN
- [ ] 报告已 commit
- [ ] 后端 pytest 1161 例 0 failed（每月或 backend 改动后跑一次即可）
- [ ] 任何失败已建 Issue / 已上报

---

**最后更新**：2026-04-27（首版，随 D-044 落地）
