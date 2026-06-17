# Makefile — YiLuAn 开发便捷命令
#
# 目前仅承载 worktree git identity 隔离相关 target
# (S3-OPS-WORKTREE-GIT-IDENTITY-ISOLATION)。后续可按需扩展。

.PHONY: help verify-worktree-identity setup-worktree-identity

help: ## 显示可用 target
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-28s\033[0m %s\n", $$1, $$2}'

verify-worktree-identity: ## 校验当前 worktree 的 git identity 是否按 agent 正确隔离
	@bash scripts/setup-agent-worktree.sh --verify

setup-worktree-identity: ## 配置当前 worktree 的 per-agent git identity（自动从目录名推断 agent）
	@bash scripts/setup-agent-worktree.sh
