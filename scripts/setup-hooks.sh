#!/usr/bin/env bash
# 一键启用项目版本管理的 git hooks（S2-OPS-003）。
# 每个 clone 跑一次：
#   bash scripts/setup-hooks.sh
set -e
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"
git config core.hooksPath .githooks
chmod +x .githooks/* 2>/dev/null || true
echo "✅ core.hooksPath = .githooks 已设。"
echo "   pre-push 现在跑：ruff lint(仅改动文件) + marker gate(money_safety/share_security, ~12s)。"
echo "   全量测试由 GitHub Actions CI 兜底（PR 的 required check）。"
