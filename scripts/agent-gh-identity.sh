#!/usr/bin/env bash
# =============================================================================
# agent-gh-identity.sh — 各 agent worktree 启动时 source, 注入本 workspace 的
#   GitHub identity（GH_TOKEN + git commit author）。
#
# 依据: ADR-0061 §4.1 S1（各 Agent 独立 GitHub Identity, 根治 self-approve 物理禁）
# 任务: S3-OPS-SEPARATE-GH-IDENTITY-PER-AGENT (AC#3)
#
# 机制（方案 A: GH_TOKEN 注入, ADR-0061 §3）:
#   - 从 ~/.openclaw/workspace-<agent>/.openclaw/secrets/github_pat 读 PAT
#   - export GH_TOKEN  → gh CLI 见 GH_TOKEN 优先用它, 跳过全局 hosts.yml
#     (~/.config/gh/hosts.yml 是 5 agent 共享单例, 见 ADR-0061 §2)
#   - git config user.name/email → commit author 身份（与 gh identity 正交）
#
# 平滑过渡（ADR-0061 §5 迁移期兼容）:
#   - secret 文件不存在 → 回退共享 renwenlong 身份（反案#37 workaround）
#   - 账号逐个到位逐个切, 不是硬切换; 回退不报错、不中断启动
#
# 幂等: 可重复 source, 每次覆盖 export/config 到确定值, 无副作用累积。
#
# 用法:
#   source scripts/agent-gh-identity.sh <agent_key>
#   # 例: source scripts/agent-gh-identity.sh hutao
#
# secret 文件规范见 ADR-0061 §4.1 S2:
#   路径 ~/.openclaw/workspace-<agent>/.openclaw/secrets/github_pat
#   权限 chmod 600, gitignore .openclaw/secrets/, scope repo+workflow+read:org
# =============================================================================
set -euo pipefail

AGENT_KEY="${1:?usage: agent-gh-identity.sh <agent_key> (e.g. hutao/xiao/keqing/ningguang/ganyu)}"

# 本 workspace 的 secret 路径（HOME 展开 → 各 agent 各自 workspace 目录）
SECRET="${HOME}/.openclaw/workspace-${AGENT_KEY}/.openclaw/secrets/github_pat"

if [[ -f "$SECRET" ]]; then
  # PAT 注入: 去掉所有空白字符（防尾部换行污染 token）
  GH_TOKEN="$(tr -d '[:space:]' < "$SECRET")"
  export GH_TOKEN

  # git commit author 身份（与 gh identity 正交, ADR-0061 §3 决定理由 4）
  git config --global user.name  "yiluan-${AGENT_KEY}"
  git config --global user.email "yiluan-${AGENT_KEY}@users.noreply.github.com"

  echo "[gh-identity] ${AGENT_KEY} → GH_TOKEN 注入 + git author=yiluan-${AGENT_KEY}"
else
  # 回退共享 renwenlong（反案#37 workaround, 平滑过渡）
  echo "[gh-identity] WARN: ${SECRET} 不存在, 回退共享 renwenlong (反案#37 workaround, 账号未到位)"
fi
