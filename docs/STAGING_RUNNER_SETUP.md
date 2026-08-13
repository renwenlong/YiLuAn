# Staging Self-Hosted Runner Setup（未选方案 B 的技术参考）

> **状态**：ADR-0059 已于 2026-08-10 选择方案 C。本文件不构成启用授权；
> weekly cron 必须保持注释，且当前不得注册 runner 或设置
> `STAGING_RUNNER_READY`。未来若改选 B，须另行决策和 Review。
>
> **目的**：记录未选方案 B 的技术路径：注册并启用一台 self-hosted GitHub Actions runner，让
> `.github/workflows/staging-rehearsal.yml` 的 weekly staging rehearsal
> 自动跑（方案 B，ADR-0059）。
>
> **何时需要**：帝君提供一台常驻机器（带 Docker）+ runner 注册 token 之后。
> 在此之前 workflow 处于 inert 状态（`STAGING_RUNNER_READY` 未设 → job 被
> `if` 跳过），每周演练仍按 `docs/STAGING_REHEARSAL_RUNBOOK.md` 手动跑
> （fallback 不受影响 — AC#3）。
>
> **历史来源**：ADR-0059 的备选方案 B 与 CI gate 设计。

---

## 0. 前置条件（帝君提供）

| 项 | 说明 |
|----|------|
| 一台常驻机器 | Linux / macOS / Windows 均可；需能跑 `docker compose` 且能绑 `127.0.0.1:18080`（hosted runner 不行，故必须 self-hosted） |
| Docker | 已安装并运行（staging 栈靠 docker compose 拉起） |
| Python 3.11+ | rehearsal replay 脚本依赖（stdlib + httpx） |
| `gh` CLI | CI gate（§5.5）调 GitHub API 用；runner 上需可用 |
| runner 注册 token | 从 GitHub repo Settings → Actions → Runners → New self-hosted runner 获取（短时 token，注册时现取） |

> **安全 note（ADR-0059 §4.5）**：方案 B 下 deploy 在帝君机器上由 runner 进程
> 自跑，**agent 不持有任何 SSH key / 部署凭据**，天然规避 §4.5 的 agent-SSH
> 威胁面（凝光的安全前置自动满足）。runner 注册 token 由帝君在机器上一次性
> 录入，不落 agent workspace。

---

## 1. 注册 self-hosted runner（label `staging-mock`）

在帝君提供的机器上执行（GitHub 注册向导会给出对应平台的精确命令）：

```bash
# 1) 下载 runner（版本号以 GitHub 向导给的为准）
mkdir actions-runner && cd actions-runner
curl -o actions-runner.tar.gz -L \
  https://github.com/actions/runner/releases/download/<version>/actions-runner-<os>-<arch>.tar.gz
tar xzf actions-runner.tar.gz

# 2) 配置 runner —— label 必须含 staging-mock（workflow 的 runs-on 依赖它）
./config.sh \
  --url https://github.com/renwenlong/YiLuAn \
  --token <RUNNER_REGISTRATION_TOKEN> \
  --labels staging-mock \
  --name yiluan-staging-runner \
  --unattended

# 3) 作为服务常驻（推荐，重启自动拉起）
sudo ./svc.sh install
sudo ./svc.sh start
# 或前台手动跑（调试用）：./run.sh
```

校验：GitHub repo Settings → Actions → Runners 应出现 `yiluan-staging-runner`
状态 **Idle**，labels 含 `self-hosted` + `staging-mock`。

---

## 2. 启用 workflow（设 repo variable，无需改文件）

workflow job 的 `if` 条件是
`${{ vars.STAGING_RUNNER_READY == 'true' }}`，**通过 repo variable 开关，不用
编辑 yml**：

```bash
# 用 gh CLI 设 repo variable（一次即可）
gh variable set STAGING_RUNNER_READY --body "true" --repo renwenlong/YiLuAn

# 确认
gh variable list --repo renwenlong/YiLuAn | grep STAGING_RUNNER_READY
```

或 GitHub UI：repo Settings → Secrets and variables → Actions → Variables →
New repository variable → name `STAGING_RUNNER_READY`，value `true`。

**停用**：把 value 改为非 `true`（如 `false`）或删除该 variable，job 立即恢复
inert，**无需 revert workflow**。

---

## 3. 启用 weekly cron（可选）

`workflow_dispatch` 手动触发在 runner 就绪 + variable 设好后即可用。要恢复
每周三 14:00 GMT+8 自动跑，取消 `staging-rehearsal.yml` 顶部 `schedule:` 的
注释：

```yaml
on:
  workflow_dispatch: {}
  schedule:
    - cron: '0 6 * * 3'   # 14:00 GMT+8
```

（这一步需改 workflow 文件 + 走 PR，故列为可选；先用 `workflow_dispatch`
手动验证 runner 通路 OK 再开 cron。）

---

## 4. CI gate（ADR-0059 §5.5）说明

workflow 在 `checkout` 之后、`./up.sh` 之前内嵌一个 **CI gate step**：

```yaml
- name: CI gate (required checks green)
  shell: bash
  env:
    GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  run: |
    deploy/staging/check-main-ci.sh --sha "$(git rev-parse HEAD)"
```

`deploy/staging/check-main-ci.sh` 校验**待部署 commit** 的 4 个
branch-protection required checks 全部 `success`，否则 `exit 1` abort 部署：

- `Backend Tests`
- `Docker Build Verification`
- `WeChat Mini Program Tests`
- `Build & Test (iOS Simulator)`

**严格性**：任一 required check 为 `failure` / `pending` / `skipped` /
**MISSING（根本没跑）** 都会 abort —— 防止未过 CI 的代码污染刻晴的验收环境。
脚本逻辑见 `deploy/staging/check-main-ci.sh`，单测见
`deploy/staging/test_check_main_ci.sh`（`./test_check_main_ci.sh` 本地可跑，
无需网络）。

> gate 脚本可独立手动跑（手动 redeploy 前自检）：
> `deploy/staging/check-main-ci.sh --sha <SHA>`，exit 0 = 安全部署。

---

## 5. 验证通路（runner 就绪后）

1. 手动触发：repo Actions → staging-rehearsal → Run workflow（选 main）。
2. 观察 job 在 `yiluan-staging-runner` 上 pick up。
3. CI gate step 通过（main HEAD 4 required 全绿时）。
4. staging 栈拉起 → replay GREEN → 报告 upload → teardown。
5. 失败排查见 `docs/STAGING_REHEARSAL_RUNBOOK.md` §4。

---

## 6. 与手动 SOP 的关系（AC#3）

本 self-hosted runner 路径是**自动化增强**，不取代手动路径。
`docs/STAGING_REHEARSAL_RUNBOOK.md` 始终保留为 fallback：runner 故障 /
未启用时，按 runbook 手动跑演练。两条路径并存。

---

**最后更新**：2026-08-10（标记为 ADR-0059 未选方案 B 的技术参考）
