# 版本管理的 Git Hooks（S2-OPS-003）

本目录的 hook 纳入版本管理，全队一致。

## 启用（每个 clone 跑一次）

```bash
bash scripts/setup-hooks.sh
# 等价于：git config core.hooksPath .githooks
```

## pre-push 做什么

**快速本地门（秒级，不再霸占 SSH 连接 6 分钟）：**

1. **ruff lint** —— 仅 lint 本次推送新/改的 backend Python 文件（不被历史 lint 欠债拖累）。
2. **marker gate** —— `pytest -m "money_safety or share_security"`（~12s），守资金/分享安全两条最高危线，本地即时拦。

**全量测试**（1349 pytest + e2e + 全部 release gate + 369 wechat jest）由 **GitHub Actions CI**
（`.github/workflows/test.yml`）跑，且是 main branch protection 的 **required status checks**
（`Backend Tests` / `Docker Build Verification` / `WeChat Mini Program Tests`，strict=true）——
PR 必须三个 CI 全绿 + 基于最新 main 才能合。

## 为什么从「本地全量」改成「本地快速 + CI 全量」

旧 pre-push 在 push 的 SSH 连接生命周期内跑 ~6 分钟全量测试，GitHub SSH idle-timeout
会在测试跑完前掐断连接 → gate 全绿后传输阶段报 `Connection closed by remote host`（exit 141），
push 失败，逼人用 `--no-verify` 绕过（反而丢 gate）。诊断 + 修复见 S2-OPS-003。

质量门没放水：全量 gate 平移到 CI 的 required check（已用负向验证确认红 PR 真的合不了），
本地保留 marker gate 守最高危线，零空窗。

## 紧急跳过

`git push --no-verify`（极少用；marker gate 失败别绕，先修——那是资金/分享最高危线）。
