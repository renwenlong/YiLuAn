#!/usr/bin/env bash
# setup-agent-worktree.sh — S3-OPS-WORKTREE-GIT-IDENTITY-ISOLATION
#
# 为什么需要这个脚本（反案 #16 同源教训）：
#   `git worktree` 创建的子 worktree **共享** base repo 的 `.git/config`
#   （包括 user.name / user.email）。同一 base repo 被多个 agent 各开一个
#   worktree 时，任何一个 agent 在 base config 里设的 user.* 会污染其他
#   worktree —— 实测 2026-06-15 PR #310 commit `aeb5e09` 被写成 author=刻晴
#   而非 hutao 本人，root cause 正是 `~/repo/YiLuAn/.git/config` 残留
#   `user.name=刻晴`。详见 docs/agent-worktree-setup.md。
#
#   修法：每个 agent worktree 启用 `extensions.worktreeConfig` 并用
#   `git config --worktree` 写**仅本 worktree 生效**的 user.name/email，
#   覆盖被污染的 base config。本脚本把这套动作标准化 + 可验证。
#
# 用法：
#   bash scripts/setup-agent-worktree.sh            # 自动从 worktree 目录名推断 agent
#   bash scripts/setup-agent-worktree.sh hutao      # 显式指定 agent
#   bash scripts/setup-agent-worktree.sh --verify    # 仅校验当前 worktree identity 是否正确
#   bash scripts/setup-agent-worktree.sh hutao --verify
#
# 退出码：
#   0  成功（已配置 / 校验通过）
#   1  失败（未知 agent / 在 base repo 上跑 / --verify 校验不通过）
set -euo pipefail

# ── agent identity 映射表 ──────────────────────────────────────────────
# 唯一真实来源：workspace TOOLS.md「团队角色（璃月）」表。
# slug → 中文显示名。email 统一 <slug>@yiluan.local（本地 commit 层身份，
# 不是 push 到真实 GitHub 的 account 身份，那是 S3-OPS-SEPARATE-GH-IDENTITY
# -PER-AGENT 远程仓库层 task 的范围，两者互补）。
agent_display_name() {
  case "$1" in
    hutao)     echo "胡桃" ;;
    keqing)    echo "刻晴" ;;
    xiao)      echo "魈" ;;
    ningguang) echo "凝光" ;;
    ganyu)     echo "甘雨" ;;
    *)         return 1 ;;
  esac
}

agent_email() {
  # 已由 agent_display_name 校验过是已知 slug，这里直接拼。
  echo "$1@yiluan.local"
}

KNOWN_AGENTS="hutao keqing xiao ningguang ganyu"

usage() {
  sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
}

# ── 参数解析 ───────────────────────────────────────────────────────────
AGENT=""
VERIFY_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --verify) VERIFY_ONLY=1 ;;
    -h|--help) usage; exit 0 ;;
    --*) echo "[setup-worktree] 未知参数: $arg" >&2; usage >&2; exit 1 ;;
    *)
      if [ -n "$AGENT" ]; then
        echo "[setup-worktree] 只能指定一个 agent，已有 '$AGENT'，又收到 '$arg'" >&2
        exit 1
      fi
      AGENT="$arg"
      ;;
  esac
done

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# ── 自动推断 agent（worktree 目录名 YiLuAn-<agent>）────────────────────
if [ -z "$AGENT" ]; then
  base="$(basename "$REPO_ROOT")"
  case "$base" in
    *-*)
      # YiLuAn-hutao → hutao；取最后一个 '-' 之后的部分
      AGENT="${base##*-}"
      ;;
    *)
      echo "[setup-worktree] ❌ 无法从目录名 '$base' 推断 agent。" >&2
      echo "    这看起来是 base repo（非 agent worktree）。base repo 不应配 agent identity。" >&2
      echo "    请在各 agent 的 worktree（~/repo/YiLuAn-<agent>）里跑本脚本，或显式传 agent slug。" >&2
      echo "    已知 agent: $KNOWN_AGENTS" >&2
      exit 1
      ;;
  esac
fi

# ── 校验 agent slug 合法 ──────────────────────────────────────────────
if ! NAME="$(agent_display_name "$AGENT")"; then
  echo "[setup-worktree] ❌ 未知 agent slug: '$AGENT'" >&2
  echo "    已知 agent: $KNOWN_AGENTS" >&2
  exit 1
fi
EMAIL="$(agent_email "$AGENT")"

# ── --verify 模式：只校验，不改 ───────────────────────────────────────
if [ "$VERIFY_ONLY" -eq 1 ]; then
  cur_name="$(git config user.name || true)"
  cur_email="$(git config user.email || true)"
  ok=1
  if [ "$cur_name" != "$NAME" ]; then
    echo "[setup-worktree] ❌ user.name 不匹配：当前='$cur_name' 期望='$NAME'" >&2
    ok=0
  fi
  if [ "$cur_email" != "$EMAIL" ]; then
    echo "[setup-worktree] ❌ user.email 不匹配：当前='$cur_email' 期望='$EMAIL'" >&2
    ok=0
  fi
  # worktreeConfig 必须开启，否则 --worktree 覆盖不生效（会被 base config 反污染）
  if [ "$(git config extensions.worktreeConfig || echo false)" != "true" ]; then
    echo "[setup-worktree] ❌ extensions.worktreeConfig 未开启 —— --worktree 覆盖不生效，identity 会被 base config 污染" >&2
    ok=0
  fi
  if [ "$ok" -eq 1 ]; then
    echo "[setup-worktree] ✅ 校验通过：$AGENT → $NAME <$EMAIL>（worktree-scoped）"
    exit 0
  fi
  echo "[setup-worktree] 修复：bash scripts/setup-agent-worktree.sh $AGENT" >&2
  exit 1
fi

# ── 配置模式：写 worktree-scoped identity ─────────────────────────────
git config extensions.worktreeConfig true
git config --worktree user.name "$NAME"
git config --worktree user.email "$EMAIL"

echo "[setup-worktree] ✅ 已配置本 worktree git identity（仅本 worktree 生效）："
echo "    worktree : $REPO_ROOT"
echo "    agent    : $AGENT"
echo "    user.name: $NAME"
echo "    user.email: $EMAIL"
echo "[setup-worktree] 校验：git config user.name / git config user.email"
echo "[setup-worktree] 或：make verify-worktree-identity"
