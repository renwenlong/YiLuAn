#!/usr/bin/env bash
# =============================================================================
# enable-required-approvals.sh — 启用 main required_approving_review_count=1
#
# 依据: ADR-0061 §4.1 S3 / 任务 S3-OPS-SEPARATE-GH-IDENTITY-PER-AGENT (AC#5)
#
# 治理变更 — 不可自动 apply, 必须帝君本人背书后手动跑。
#
# 本脚本逆转帝君 2026-06-02 10:02Z 亲拍的方案A:
#   方案A = required_approving_review_count=0 (CI 绿即合, 取消人工 approve 闸)
#   本脚本 = 改回 =1 (强制 1 个 APPROVED review 才能合)
#
# 按反案#48 (改 branch protection 治理硬规必帝君本人背书):
#   merge ADR-0061 入 main != 解锁本脚本 apply — 二者完全独立。
#   ADR 入 main 仅冻结设计契约; count=0->1 的实际变更必须:
#     1 5 个 yiluan-* 账号 + PAT 就位 (architect yiluan-xiao != author 可真
#       --approve, 否则加了 required=1 -> 所有 PR 因无法 self-approve 卡死)
#     2 帝君单独点头批准逆转方案A (不是 merge 本 ADR 就算批准)
#     3 全 in-flight PR batch 协调 + 低峰期 apply (breaking change, 提前通知)
#
# 三前提缺一不可 apply。本脚本存在 = 物料/背书到位后一键可执行, 不是现在执行。
# =============================================================================
set -euo pipefail

if [[ "${1:-}" != "--i-have-emperor-approval" ]]; then
  cat >&2 <<'GUARD'
拒绝执行: 本脚本逆转帝君方案A (count=0->1), 是治理硬规变更 (反案#48)。
   merge ADR-0061 != 解锁 apply。apply 三前提:
     1 5 个 yiluan-* 账号 + PAT 就位
     2 帝君本人单独背书逆转方案A
     3 全 in-flight PR batch 协调 + 低峰期
   确认三前提全满足后, 显式加旗标重跑:
     bash scripts/qa/enable-required-approvals.sh --i-have-emperor-approval
GUARD
  exit 2
fi

echo "[branch-protection] apply required_approving_review_count=1 (帝君已背书旗标确认)..."
gh api -X PUT repos/renwenlong/YiLuAn/branches/main/protection/required_pull_request_reviews \
  -f required_approving_review_count=1 \
  -F dismiss_stale_reviews=true
echo "[branch-protection] required_approving_review_count=1 已启用 (方案A count=0 已逆转)"
