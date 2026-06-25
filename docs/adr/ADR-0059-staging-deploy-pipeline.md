# ADR-0059: Staging 自动部署流水线 — 路径决策

- **状态**: 🟡 草案（魈 review 必补点已落实，待帝君拍路径）
- **日期**: 2026-06-25
- **作者**: 胡桃（调研 + 草案）
- **决策者**: 帝君（拍 OPS 路径 + 权限模型）
- **Review**: 魈 🔴#1 agent-SSH 威胁模型（§4.5）+ 🔴#2 redeploy CI gate（§5.5）已补；🟡#3#4 可选增强（§6.5）已补
- **关联 task**: `S3-OPS-STAGING-AUTO-DEPLOY-PIPELINE` (P2)
- **取代**: 本 ADR 原 taskboard 引用编号 ADR-0054 已被 `ADR-0054-precheck-ui-native-pivot.md` 占用，改用 ADR-0059。

> ⚠️ **本 ADR 是调研 + 三方案对比草案，核心决策点（路径选择 + SSH/权限模型）需帝君拍板**。胡桃仅交付调研产出，不擅自起手 implement phase。

---

## 1. 背景与痛点

PR queue 速度 vs deploy infra 不匹配：

- **main 高频接收 PR**（24h 曾接 7+ PR），但 **staging 不会自动反映**
- 实际 staging deploy 路径是**手动 SOP**（`docs/STAGING_REHEARSAL_RUNBOOK.md`: `cd deploy && ./up.sh`）
- 后果：
  - **测试员（刻晴）** 在 staging 验业务时数据/代码陈旧
  - **胡桃 redeploy 卡帝君 SSH 授权**（无独立部署权限）

## 2. 现状盘点（evidence-first）

| 组件 | 现状 | 缺口 |
|------|------|------|
| `.github/workflows/deploy.yml` | SCAFFOLDING ONLY，push 触发已注释，仅 `workflow_dispatch` | Azure 资源 + GH Secrets + Environments 全未配 |
| `.github/workflows/staging-rehearsal.yml` | `if: false` DISABLED，等 self-hosted runner `staging-mock` | runner 未注册 |
| `docs/STAGING_REHEARSAL_RUNBOOK.md` | ✅ 手动 SOP 已存在可用 | 胡桃无 SSH 授权，仅帝君可执行 |
| `deploy/` 目录 | ✅ docker-compose + up.sh/down.sh + nginx + env 模板齐全 | — |
| `docs/TODO_CREDENTIALS.md` | Azure/微信/阿里云凭据全 **Pending（责任人=帝君）** | 真凭据未到位 |

**关键结论**：三条路径的骨架都已搭好，差的全是**前置授权/资源**，不是代码。

## 3. 三方案对比

### 方案 A：Azure-native pipeline（deploy.yml 启用）

**做法**：配齐 Azure 资源 + GH Secrets + Environments，取消 deploy.yml push 触发注释。

| 维度 | 评估 |
|------|------|
| staging 自动化 | ✅ 每 PR merge 自动部署 staging |
| production 安全 | ✅ GH Environment reviewer 审批（帝君手动 gate）|
| 前置成本 | ❌ **高** — 需 Azure RG/ACR/Container Apps/PostgreSQL/Redis/Key Vault 全部就位 |
| 卡帝君钥匙 | ❌ ACR_USERNAME/ACR_PASSWORD/AZURE_CREDENTIALS/STAGING_DATABASE_URL |
| 胡桃可独立推进 | ❌ 完全卡 Azure 资源到位 |
| 长期价值 | ✅✅ 最完整，production-grade，一劳永逸 |

### 方案 B：Self-hosted runner（staging-rehearsal.yml 启用）

**做法**：注册 self-hosted runner（label `staging-mock`），启用 staging-rehearsal.yml + weekly cron。

| 维度 | 评估 |
|------|------|
| staging 自动化 | 🟡 weekly rehearsal 自动，但非每 PR 触发 |
| 前置成本 | 🟡 中 — 需一台常驻机器跑 runner（Docker 环境）|
| 卡帝君钥匙 | 🟡 需帝君提供机器 + 注册 runner token |
| 胡桃可独立推进 | ❌ 需机器 + runner 注册权限 |
| 长期价值 | 🟡 解 rehearsal 自动化，不解"每 PR staging 反映"痛点 |

### 方案 C：手动 SOP + 授权 hutao SSH（保留现状强化）

**做法**：完善 `docs/STAGING_REDEPLOY_QUICK.md`，授权 hutao SSH（限定 sudo 范围 + git pull），胡桃可独立按文档 redeploy。

| 维度 | 评估 |
|------|------|
| staging 自动化 | ❌ 仍手动，但**胡桃可自助**不再卡帝君每次操作 |
| 前置成本 | ✅ **最低** — 仅需一次性 SSH 授权 + 文档 |
| 卡帝君钥匙 | 🟡 仅一次性 SSH key 授权（非每次）|
| 胡桃可独立推进 | 🟡 授权后可独立 redeploy（解最痛的"卡帝君 SSH"）|
| 长期价值 | 🟡 过渡方案，不如 A 自动化，但**立即可落地解当前痛点** |

## 4. 权限模型选项（需帝君拍）

无论选哪条路径，**SSH/部署权限模型**需帝君明确：

| 选项 | SSH key 谁拿 | sudo 范围 | git pull |
|------|------------|----------|----------|
| P-1 最严 | 仅帝君 | — | 手动 |
| P-2 中（推荐配方案 C）| hutao 专用 key（限 staging 主机）| 仅 `docker compose` / `systemctl restart yiluan-*` | hutao 手动触发 |
| P-3 自动 | CI service account | deploy 范围 | push 自动 |

### 4.5 agent-SSH 威胁模型（🔴 魈 review 必补 — 方案 C / P-2 的安全前提）

**风险**：若直接给 hutao agent 一把常驻 SSH private key 落在 agent workspace（`~/.ssh/`），等于把 staging 主机的持久访问权交给一个 LLM-driven agent 进程。威胁面：
- agent workspace 被读 → key 泄露 → 横向移动到 staging 主机
- agent 被 prompt-injection 诱导执行非预期 deploy / 删库
- key 无过期 → 长期暴露窗口

**隔离方案（按隔离强度递增，需帝君选）**：

| 方案 | 做法 | 隔离强度 | 成本 |
|------|------|---------|------|
| **I-1 key 不落 agent workspace** | SSH key 存 gateway host（非 agent 可读路径），agent 通过受限 exec 包装调用，key 路径 agent 无读权 | 中 | 低 |
| **I-2 短时证书（推荐）** | SSH CA 签发短时（如 5-15min）证书，agent 每次 deploy 前请求一次性 cert，过期自动失效 | 高 | 中（需 SSH CA / vault-ssh）|
| **I-3 bastion 跳板 + 预定义脚本** | agent 只能 SSH 到 bastion 触发**白名单脚本**（如 `/opt/yiluan/redeploy.sh`），无法跑任意命令，无 sudo shell | 最高 | 中高 |

**胡桃推荐 I-3 或 I-2**：agent 持久 full SSH（I-1 的弱化版）不可取——即使限 sudo 范围，agent 仍能在主机跑任意 git/docker 命令。**I-3 bastion + 白名单脚本** 把 agent 能做的事锁死成「触发预定义 redeploy」一个动作，prompt-injection 也无法越界。若嫌 bastion 重，退而求其次 **I-2 短时 cert** 把暴露窗口压到分钟级。

**红线**：无论哪个隔离方案，**private key / CA 签发权绝不落 agent workspace**，agent 只能拿「触发权」不能拿「凭据本体」。

## 5. 推荐（胡桃视角，供帝君参考）

**分阶段**：
1. **即刻（解当前痛点）**：方案 C — 授权 hutao SSH（P-2 权限模型）+ 写 QUICK redeploy 文档。**最低成本，立即让刻晴 staging 不陈旧 + 解胡桃卡 SSH**。
2. **Azure 资源到位后**：升级方案 A — 真正的 push 自动部署 + production reviewer gate。

理由：方案 A 长期最优但**完全卡 Azure 资源（帝君钥匙未到位）**，现在做 = 干等。方案 C 一次性 SSH 授权就能立即解痛点，是务实过渡。两者不冲突，C 是 A 到位前的桥。

### 5.5 redeploy 前 CI gate（🔴 魈 review 必补 — 防部署未过 CI 的代码）

**风险**：无论方案 C 手动触发还是方案 A 自动 push，若不校验 main HEAD 的 CI 状态，可能把**未过 CI（红/pending）的 commit** 部署到 staging，污染刻晴验收环境。

**强制 gate**：redeploy（脚本 / pipeline）执行前**必须**校验目标 commit 的 required check 全绿：

```bash
# redeploy.sh 前置 gate（方案 C bastion 白名单脚本内嵌 / 方案 A pipeline 步骤）
HEAD_SHA=$(git rev-parse HEAD)
CONCLUSION=$(gh api "repos/{owner}/{repo}/commits/${HEAD_SHA}/check-runs" \
  --jq '[.check_runs[] | select(.name|test("Backend Tests|Docker Build|WeChat")) | .conclusion] | unique')
# 必须全为 ["success"]，否则 abort
if [ "$CONCLUSION" != '["success"]' ]; then
  echo "❌ CI not green for ${HEAD_SHA}: ${CONCLUSION} — abort deploy"
  exit 1
fi
```

**要点**：
- 校验**目标 commit**（待部署的 SHA），不是「最近一次任意 run」
- 只认 required checks 全 `success`，pending / failure / skipped 一律 abort
- 方案 C：嵌进 bastion 白名单脚本（agent 触发也绕不过 gate）
- 方案 A：作为 deploy job 的前置 step（test job 后、deploy 前）

## 6. 待帝君决策项（拍这几个就能起手 implement）

1. **路径**：A（Azure 等资源）/ B（self-hosted runner）/ C（SSH 授权过渡）/ A+C 分阶段？
2. **权限模型**：P-1 / P-2 / P-3？
3. 若选 C：是否同意给 hutao staging 主机访问（**按 §4.5 隔离方案 I-1/I-2/I-3 选一**，胡桃推荐 I-3 bastion 白名单脚本或 I-2 短时 cert，绝不给常驻 full key）？
4. **CI gate（§5.5）确认**：redeploy 前强制校验目标 commit required checks 全绿——这条无论选哪路径都建议硬性纳入，帝君确认即可。

### 6.5 可选增强（🟡 魈 review 可选 — 不阻塞拍板）

- **🟡 自动化触发（C→A 桥）**：方案 C 阶段可加 main push webhook → 通知 hutao「main 有新 commit 可 redeploy」，半自动降低遗忘成本，但仍人工确认触发（不直接自动 deploy，保留 gate）。
- **🟡 C→A 拆桥 checklist**：Azure 资源到位后从 C 切 A 的迁移步骤——① 配齐 Secrets/Environments ② deploy.yml 取消 push 注释 ③ 跑一次 workflow_dispatch 验证 ④ 确认 §5.5 CI gate 已嵌入 pipeline ⑤ staging 验证通过后再开 production reviewer gate ⑥ 保留方案 C 脚本作为 A 故障时的 fallback。

---

## 7. 不破坏现有（AC#3）

实施期 `docs/STAGING_REHEARSAL_RUNBOOK.md` 保留为 fallback，不删现有手动路径。

## 8. 实施后透明度（AC#4）

实施完成后 hutao + 凝光 + 刻晴同步新 redeploy 路径，staging URL/版本号/部署时间透明（metric or 文档）。
