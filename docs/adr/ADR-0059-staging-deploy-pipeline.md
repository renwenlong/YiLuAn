# ADR-0059: Staging 部署路径

- **状态**: ✅ 已接受
- **提案日期**: 2026-06-25
- **决定日期**: 2026-08-10
- **作者**: 胡桃（调研 + 实施）
- **决策者**: 帝君
- **决定**: 采用方案 C（手动 SOP + 受限部署触发）
- **Review**: 魈 r1 要求 ADR 与实际选择一致，并保留权限威胁模型和 redeploy CI gate
- **关联 task**: `S3-OPS-STAGING-AUTO-DEPLOY-PIPELINE` (P2)
- **取代**: 原 taskboard 引用的 ADR-0054 编号已被占用，故使用 ADR-0059

> 2026-08-10 帝君明确选择 **C**。方案 A（Azure-native）和方案 B
>（self-hosted runner）当前均不启用；后续若外部资源与运营需求变化，须另开
>决策记录，不得把本 ADR 解释成已授权自动部署。

## 1. 背景

main 高频接收 PR，但 staging 不会自动反映。现有部署依赖手动 SOP，胡桃没有
受限部署入口时，每次 redeploy 都要等待帝君操作，影响刻晴在 staging 的验收。

## 2. 决策时能力盘点

2026-08-10 通过 GitHub API/CLI 对 `renwenlong/YiLuAn` 实测：

| 能力 | 实测结果 | 结论 |
|---|---|---|
| Actions repository secrets | 0 项 | 方案 A 不可启用 |
| GitHub Environments | 0 个 | A 的 staging/production reviewer gate 不存在 |
| self-hosted runners | 0 台 | 方案 B 无执行载体 |
| repository variables | 0 项 | `STAGING_RUNNER_READY` 未激活 |
| main required checks | `strict=true`，共 5 项 | 手动 redeploy 前必须逐项 fail-closed 校验 |
| 手动 staging SOP | 已存在 | 可作为方案 C 的基础 |
| 受限 SSH / deploy wrapper | 未提供 | C 的运行期外部前置，未满足前仍由帝君手动执行 |

`.github/workflows/staging-rehearsal.yml` 保留 `workflow_dispatch` 和
`STAGING_RUNNER_READY` gate 作为历史方案 B 的惰性骨架，但 weekly cron 保持注释，
不得以本 ADR 为由启用。

## 3. 备选方案

### A. Azure-native pipeline

配齐 Azure 资源、GitHub Secrets 与 Environments 后，通过 `deploy.yml` 自动部署。
长期能力最完整，但当前资源与权限均不存在，不能落地。

### B. Self-hosted runner

注册带 `staging-mock` label 的常驻 runner，运行 rehearsal workflow。仓库已有惰性
骨架和 CI gate，但当前没有 runner；而且 weekly rehearsal 不等于 main 每次合并后
自动刷新 staging。

### C. 手动 SOP + 受限部署触发（已选择）

保留人工确认，通过受限入口执行固定 redeploy 流程：校验目标 SHA 的 required
checks、更新 staging checkout、拉起服务、验活并回报版本。详细步骤见
`docs/STAGING_REDEPLOY_QUICK.md`。

| 维度 | 结论 |
|---|---|
| 自动化 | 不自动；保留人工确认 |
| 前置成本 | 最低，但仍需帝君一次性提供受限入口 |
| 安全边界 | agent 不持有常驻私钥，不获得任意 shell / 任意 sudo |
| 当前可执行性 | 仓库侧 SOP 与 CI gate 可完成；外部授权前仍由帝君执行 |
| 定位 | Azure-native 路径成熟前的可控过渡方案 |

## 4. 权限与威胁模型

### 4.1 强制安全边界

方案 C 的批准**不是**对通用 SSH、sudo 或凭据读取的授权。实现必须满足：

1. private key、SSH CA 签发权和主机凭据不落 agent workspace；
2. agent 只能触发固定 redeploy 流程，不能获得任意远程 shell；
3. sudo 范围仅覆盖预定义部署动作，不允许通配任意命令；
4. 目标必须是 `origin/main` 上的明确 commit SHA；
5. redeploy 前的 CI gate 不可绕过；
6. 每次执行必须留下操作者、SHA、时间、结果和 staging URL 的审计记录。

推荐基础设施实现为 bastion / host 上的白名单脚本（原方案 I-3）；也可用 5–15
分钟短时 SSH 证书（I-2），但仍只能调用白名单脚本。禁止给 agent 常驻 full SSH key。

### 4.2 未激活边界

截至决定时，受限 SSH / wrapper 尚未配置。因此“采用 C”表示**路径已定**，不表示
胡桃已经获得主机访问权。外部入口就绪前，帝君仍是实际部署操作者；胡桃只提供
目标 SHA、CI gate 证据与命令清单。

## 5. 手动 redeploy 的强制 CI gate

redeploy 必须校验**待部署 SHA**的 branch-protection required checks，且以下 5 项
全部存在并为 `success`：

- `Backend Tests`
- `Docker Build Verification`
- `WeChat Mini Program Tests`
- `Build & Test (iOS Simulator)`
- `Smoke tests (real Postgres + alembic)`

仓库实现为：

```bash
deploy/staging/check-main-ci.sh --sha <origin-main-sha>
```

任一 check 为 missing、pending、failure、cancelled、skipped 或 neutral 都必须中止。
脚本的 fixture 测试见 `deploy/staging/test_check_main_ci.sh`。

## 6. 实施与运行流程

### 6.1 仓库侧（本 ADR 对应 PR）

1. 保持 weekly cron 注释，不激活方案 B；
2. 同步 CI gate 到 main 的 5 个 required checks；
3. 提供 `docs/STAGING_REDEPLOY_QUICK.md`；
4. 保留 `docs/STAGING_REHEARSAL_RUNBOOK.md` 作为完整演练与故障排查手册；
5. 在文档中明确 SSH 授权未到位时的人工交接边界。

### 6.2 外部前置（帝君 / 基础设施）

1. 在 staging 主机或 bastion 安装白名单 redeploy wrapper；
2. 选择 I-3 白名单脚本或 I-2 短时证书，不下发常驻 agent 私钥；
3. 限制 wrapper 只接受 `origin/main` SHA，并内嵌 §5 CI gate；
4. 首次执行后核对审计记录和 staging 版本回报。

## 7. 后果

### 正向

- 不等待 Azure 或常驻 runner，即可沿现有部署栈落地；
- 每次部署保留人工确认，权限面小于通用 SSH；
- 5 项 required checks fail-closed，避免红灯或未跑 CI 的 commit 污染 staging；
- 将“路径已决定”和“外部权限已配置”分开，避免假完成。

### 代价与限制

- staging 不会随 main 自动刷新，仍可能因人工遗漏而陈旧；
- 帝君必须先配置受限入口，否则胡桃仍不能独立 redeploy；
- 白名单脚本 / 短时证书属于主机侧配置，不由仓库 PR 自动完成；
- 方案 B 的 workflow 骨架继续保持 inert，方案 A 仍等待 Azure 资源。

## 8. 后续升级条件

当 Azure 资源、Secrets、Environments 和 production reviewer gate 全部就绪时，可另开
ADR 评估从 C 升级到 A。升级不得静默修改本 ADR，也不得在未重新评审权限模型时
启用 push 自动部署。
