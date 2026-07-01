# GitHub PAT Secret 规范 (ADR-0061 §4.1 S2)

任务: S3-OPS-SEPARATE-GH-IDENTITY-PER-AGENT — 各 agent 独立 GitHub identity, 根治 self-approve 物理禁。

## 真实 secret 路径 (workspace 外, 不在本 repo)

    ~/.openclaw/workspace-<agent>/.openclaw/secrets/github_pat

5 个 agent 各自 workspace: hutao / xiao / keqing / ningguang / ganyu。
本 repo 内 .openclaw/secrets/ 已整目录 gitignore (纵深防御, 无例外口子)，真 PAT 绝不入 repo。

## 文件规范

| 项 | 要求 |
|---|---|
| 内容 | 单行 PAT，无其他内容 |
| 权限 | chmod 600 (仅 owner 读写) |
| scope | repo + workflow + read:org |

## 使用

agent worktree 启动时 source 注入脚本 (ADR-0061 §4.1 S1):

    source scripts/agent-gh-identity.sh <agent_key>

脚本读上述路径, export GH_TOKEN + 设 git commit author (yiluan-<agent>)。
secret 不存在 → 回退共享 renwenlong (反案#37 workaround, 平滑过渡, 不中断启动)。

## 物料到位流程 (卡帝君, ADR-0061 §4.2)

1. 帝君注册 5 个 GH 账号 yiluan-{hutao,keqing,xiao,ningguang,ganyu} (AC#1)
2. 各账号生成 PAT，写入各 workspace secret 路径 (AC#2)
3. chmod 600 各 secret 文件
4. 验证各 identity push/PR/comment (AC#4)

AC#1 账号注册 + AC#2 真 PAT 生成卡帝君人工前置; 机制/脚本已就位, 物料到位即接。
