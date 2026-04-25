# GoLive Runbook Dry-Run Report — 2026-04-25

> **演练人:** SRE / 发布工程师 (renwenlong)
> **目标:** 验证 `docs/runbook-go-live.md` + `docs/RUNBOOK_ROLLBACK.md` 各步骤本地可执行,暴露缺漏并产出时间预估。
> **范围:** 全本地 dry-run,**不触碰任何真实生产环境**(也无生产环境可触碰)。
> **运行环境:** Windows 11 + Docker Desktop 29.4.0 + WSL bash + Python 3.12.10。
> **演练耗时(实测):** 约 75 分钟(读现状 25 min + 实操 35 min + 写文档 15 min)。

## 0. 文件名澄清

任务描述写的是 `docs/RUNBOOK_GOLIVE.md`,**仓库实际文件名为 `docs/runbook-go-live.md`**(由 cf0aa8a 引入)。本报告以实际文件为准,并把"修订"打在该文件上。配套的 `docs/RUNBOOK_ROLLBACK.md` 已存在(ADR-0028 配套),也一并验证。

---

## 1. 现状审阅

| 资产 | 路径 | 状态 |
|---|---|---|
| GoLive runbook | `docs/runbook-go-live.md` | ✅ 存在,229 行,覆盖 B-01..B-05 + §8 告警 |
| 回滚 runbook | `docs/RUNBOOK_ROLLBACK.md` | ✅ 存在(ADR-0028 配套),A/B/C 三场景 |
| ADR canary | `docs/decisions/ADR-0028-canary-release-and-rollback.md` | ✅ 存在 |
| 迁移可逆性报告 | `docs/MIGRATION_REVERSIBILITY_REPORT.md` | ✅ 存在 |
| 灰度演练脚本 | `ops/scripts/canary_drill.sh` | ✅ mock 版,本地可跑 |
| 指标基线脚本 | `ops/scripts/metrics_baseline.sh` | ✅ 存在 |
| nginx canary 模板 | `ops/canary/nginx.canary.conf.template` | ✅ 存在 |
| Alertmanager + wechat-work webhook | `docker-compose.alertmanager.yml` + `ops/alertmanager/` | ✅ 存在 |
| Prometheus alerts.yml | `deploy/prometheus/alerts.yml` | ✅ 5 条规则 |
| /readiness endpoint | `backend/app/api/v1/health.py` | ✅ PR #20,5 项依赖检查 |
| CI: alembic-smoke / ci-smoke / api-docs-check / deploy(scaffold) | `.github/workflows/*.yml` | ✅ 存在;`deploy.yml` 只是骨架 |
| 部署脚本 `ops/scripts/deploy.sh` | (无) | ❌ 未实现 — 本次新增 |
| Preflight 一键脚本 | (无) | ❌ 未实现 — 本次新增 |
| Grafana dashboard JSON | `ops/grafana/` | ❌ 未实现 — 本次新增骨架 |
| 应急 Playbook(DB/Redis/支付/SMS) | (无,只有 §6 简表 + RUNBOOK_ROLLBACK) | ❌ 未实现 — 本次新增 |

---

## 2. Dry-Run 演练逐项记录

每条:**[状态] 步骤 — 实测/估算 — 备注**。状态:✅ OK / ⚠️ 需修订 / 🛑 阻塞 / ❌ 未实现。

### 2.1 预发布检查阶段 (Preflight)

| # | 项 | 状态 | 实测耗时 | 备注 |
|---|---|---|---|---|
| 1 | 拉起本地 PG 容器(端口 55437) | ✅ | <2s | `docker run -d --name yiluan-dryrun-pg -p 55437:5432 postgres:15-alpine` |
| 2 | 拉起本地 Redis 容器(端口 56379) | ✅ | <2s | 同上 |
| 3 | 创建 venv + `pip install -r requirements.txt` | ✅ | ~80s | `.venv-dryrun` |
| 4 | `alembic current`(空库) | ✅ | <1s | 输出空,符合预期 |
| 5 | **第一轮** `alembic upgrade head` | ✅ | **2.46s** 实测 | 30 个 revision 全部应用,head=`e8f9a0b1c2d3` |
| 6 | **第一轮** `alembic downgrade base` | ✅ | **2.19s** 实测 | 全部回滚成功,无异常 |
| 7 | **第二轮** upgrade head | ✅ | **2.21s** 实测 | 幂等 |
| 8 | **第二轮** downgrade base | ✅ | **1.98s** 实测 | 幂等 |
| 9 | **第三轮** upgrade head | ✅ | **2.18s** 实测 | head=`e8f9a0b1c2d3` |
| 10 | `alembic_version` 终态校验 | ✅ | <1s | `e8f9a0b1c2d3 (head)`,与 `MIGRATION_REVERSIBILITY_REPORT.md` 一致 |
| 11 | 启动 uvicorn 应用 | ✅ | ~3s | port 8765 |
| 12 | `GET /health` | ✅ | <50ms | `{"status":"healthy","version":"0.1.0"}` |
| 13 | `GET /readiness` 5 项检查 | ✅ | ~310ms 总(db 90ms + redis 11ms + alembic 210ms + payment skip + sms skip) | HTTP 200,字段 `ready=true` |
| 14 | 配置完整性:`.env.example` vs `app/config.py` | ⚠️ | — | **不一致**:.env.example 用 `WECHAT_PAY_MCH_ID` 等命名,**runbook B-01 列的是 `WECHATPAY_MCH_ID`(无下划线)且 `WECHATPAY_APIV3_KEY`,代码侧实际叫 `wechat_pay_api_key_v3`**。详见问题 P-01。 |
| 15 | SMS 命名一致性 | ⚠️ | — | runbook B-02 用 `ALIYUN_SMS_AK_ID` / `ALIYUN_SMS_AK_SECRET` / `ALIYUN_SMS_SIGNATURE` / `ALIYUN_SMS_TEMPLATE_OTP`;**代码用 `ALIYUN_SMS_ACCESS_KEY_ID` / `ALIYUN_SMS_ACCESS_KEY_SECRET` / `ALIYUN_SMS_SIGN_NAME` / `ALIYUN_SMS_TEMPLATE_CODE`**(单模板,不是 4 个)。详见问题 P-02。 |
| 16 | `pytest -q tests/test_health.py tests/test_readiness.py` | ✅ | 1.68s,16 passed | 0 failed |
| 17 | `pytest -q tests/smoke/` | (跳过) | — | 已被 alembic-smoke CI 覆盖,且需要专用 PG fixture;preflight 会调用 |

### 2.2 发布阶段 (Canary / Blue-Green)

| # | 项 | 状态 | 实测/估算 | 备注 |
|---|---|---|---|---|
| 18 | `bash ops/scripts/canary_drill.sh --happy-path` | ✅ | 7.5s(mock 模式,真实 1800s/stage) | 输出完整 5%→25%→50%→100% 流程 |
| 19 | `bash ops/scripts/canary_drill.sh`(default = 5xx 触发回滚) | ⚠️ | — | **脚本文件包含 CRLF 行尾**,直接 `bash` 报 `$'\r': command not found`;必须先 `dos2unix` 或 git 配置 `core.autocrlf=input`。详见问题 P-03。 |
| 20 | nginx canary 模板渲染 | ⚠️ | — | 模板存在;但**没有渲染脚本**,需手工 `sed`/`envsubst`,人为出错风险高。问题 P-04。 |
| 21 | docker-compose 模拟 blue/green 双 backend | ❌ | — | **不存在**:`backend/docker-compose.yaml` 只有单 api 服务;无 prod 级 compose。本次新增 `ops/scripts/deploy.sh` 给出 mock 模拟。问题 P-05。 |
| 22 | DB 迁移在 5min 内能否完成 | ✅(估算) | 当前空库 ~2.5s 全量 30 个 revision;**生产中等数据(seed 67KB ≈ 1k 行级别)估 5-30s**,带索引重建估 < 60s,远低于 5min 上限 | 已写入修订 runbook 的"时间预算"一节 |
| 23 | Alertmanager + webhook stack 启动 | ⚠️ | — | `docker-compose.alertmanager.yml` 中 volume 路径 `../../prometheus/alertmanager.yml` 是从子目录视角写的,但 compose 文件本身在**仓库根**,实际相对仓库根应为 `./prometheus/alertmanager.yml`。会启动失败。问题 P-06。 |
| 24 | webhook dry-run 模式自检 | ✅(代码静态阅读) | — | `wechat-work-webhook.py` 在没有 `WECHAT_WORK_WEBHOOK_URL` 时进入 dry-run,不会向真生产发消息。已在新增 preflight 中加入 `/healthz` 检查。 |

### 2.3 回滚演练

| # | 项 | 状态 | 实测/估算 | 备注 |
|---|---|---|---|---|
| 25 | RUNBOOK_ROLLBACK 场景 A(流量层)语义 walk-through | ✅ | 估算 ≤ 30s 切流 | 步骤完整,nginx reload 平滑;只缺一个"切流后立即重置 stage 计数器"的提示 |
| 26 | 场景 A 验证 V1(`X-Canary-Pool` 采样 100 次) | ⚠️ | — | 命令使用 `%{header_x-canary-pool}`;**curl 7.85+ 才支持 header 形式**,需在前置中明示 `curl --version >= 7.85`。问题 P-07。 |
| 27 | 场景 B(代码层) | ✅ | 估算 5min(3 主机 × ~100s) | 命令完整 |
| 28 | 场景 B Redis 缓存清理 | ⚠️ | — | `redis-cli --scan --pattern "v2:*"` 在 prod-grade Redis(数百万 key)下可能阻塞,需追加 `--count 100` 提示;另外没有标明"缓存 schema 版本前缀约定在哪定义"。问题 P-08。 |
| 29 | 场景 C(DB downgrade)幂等性测试 | ✅ | upgrade↔downgrade 三轮全部通过(见行 5-9) | 实测可逆 |
| 30 | 场景 C 备份恢复演练 | ❌ | — | runbook 写了 `pg_dump --format=custom`,但**没演练 `pg_restore` 恢复路径**,也未指明 PITR(WAL 归档)恢复 RTO/RPO 估算。问题 P-09。 |
| 31 | 决定回滚→流量切回旧版本耗时(实测) | ✅(mock) | nginx reload 模拟 0.3s;**端到端口头宣布→实际 100% 切流估 1-3 分钟**(找人 + 编辑 + nginx -t + reload + 验证) | 与 ROLLBACK runbook SLA "≤30 秒"略有偏差,实际是"reload 命令本身 ≤30s",含决策时间需 1-3 分钟。runbook 应澄清。问题 P-10。 |

### 2.4 应急场景(本次重点补充)

| # | 项 | 状态 | 备注 |
|---|---|---|---|
| 32 | DB 主库挂 → 切从库 SOP | ❌ | runbook 完全没有,本次新增 `INCIDENT_PLAYBOOK.md` §1 |
| 33 | Redis 挂 → 降级路径 | ❌ | 同上,§2 |
| 34 | 第三方支付 / SMS 不通 → 限流+排队+用户提示 | ❌ | 同上,§3 / §4 |
| 35 | runbook 中 `payment_provider=mock` / `sms_provider=mock` 降级开关 | ✅(代码层) | 代码存在;但运行时切换需要重启,且没有 feature flag,需要 ops 重新部署。已在 INCIDENT_PLAYBOOK 中注明 |

### 2.5 通用前置 / 文档一致性

| # | 项 | 状态 | 备注 |
|---|---|---|---|
| 36 | runbook §0 引用 "§18 smoke 10 项" | ⚠️ | **§18 在文件中不存在**,是悬垂引用。问题 P-11。 |
| 37 | runbook §3 通道 = "钉钉 + 电话",但 D-040 实际选定**企业微信** | ⚠️ | 文档前后不一致。问题 P-12。 |
| 38 | runbook B-04 "wechatpay / 阿里云 SMS / 小程序域名白名单都换成正式域名" | ⚠️ | 步骤散在不同 Blocker,无 checklist 视图。新版本 runbook 增加了"全局白名单"汇总段。问题 P-13。 |
| 39 | runbook B-01 验证项 `wechatpay.ok=true` | 🛑 | **/readiness 实际响应字段是 `checks.payment.status`**,不是 `wechatpay.ok`。如果 ops 按 runbook 字面 grep 会永远不通过。问题 P-14(高风险)。 |
| 40 | runbook 没有"上线 T-24h / T-1h / T-0 时间线" | ⚠️ | 本次新增了简短时间线和总耗时预算 |
| 41 | runbook §6 "5xx > 1% 5min 熔断"vs RUNBOOK_ROLLBACK "5xx > 1% 2min 触发" | ⚠️ | 阈值不一致(5min vs 2min)。问题 P-15。 |
| 42 | runbook 没有列"每个步骤 owner",只在 Blocker 标题写"主导" | ⚠️ | 加表格化 owner |

---

## 3. 关键发现汇总

### 3.1 Runbook 缺陷 (15)

| ID | 严重度 | 问题 | 对应修订 |
|---|---|---|---|
| P-01 | 🔴 高 | 微信支付 env 变量名与代码/`.env.example` 不一致(`WECHATPAY_MCH_ID` vs `WECHAT_PAY_MCH_ID`,且 `WECHATPAY_APIV3_KEY` vs `WECHAT_PAY_API_KEY_V3`,且没有 `WECHATPAY_PRIVATE_KEY_PEM` 这种 ENV,代码用的是 `WECHAT_PAY_PRIVATE_KEY_PATH` 文件路径) | runbook B-01 §步骤 1 改写 |
| P-02 | 🔴 高 | 阿里云 SMS env 变量名错误 + 模板数量错误(代码当前**只支持 1 个模板** `ALIYUN_SMS_TEMPLATE_CODE`,不是 4 个 OTP/订单/支付/评价) | runbook B-02 改写,把"4 模板"标为待办,并对齐变量名 |
| P-03 | 🟡 中 | `canary_drill.sh` CRLF 行尾,Linux 直接执行报错 | preflight 添加自动转换;repo 加 `.gitattributes` 限定 sh 为 LF(本次未改 .gitattributes,在 runbook 加提示) |
| P-04 | 🟡 中 | nginx canary 模板没有渲染脚本,纯手工 sed | runbook 新增"渲染步骤"小节 |
| P-05 | 🟡 中 | 缺 prod 级 docker-compose / 真实部署脚本 | 本次新增 `ops/scripts/deploy.sh`(骨架,真生产 TODO) |
| P-06 | 🔴 高 | `docker-compose.alertmanager.yml` 卷路径错误,从根启动会失败 | 修复 yml + runbook §8 步骤 2 加"从仓库根执行"说明 |
| P-07 | 🟢 低 | RUNBOOK_ROLLBACK 场景 A V1 命令依赖 curl 7.85+ | RUNBOOK_ROLLBACK 加版本提示 |
| P-08 | 🟡 中 | `redis-cli --scan` 在大库阻塞,且缓存 schema 前缀约定缺失 | RUNBOOK_ROLLBACK 加 `--count 100` + 引用 cache key 命名规范 |
| P-09 | 🟡 中 | 没有 `pg_restore` 恢复演练 / PITR RTO/RPO | 新增 INCIDENT_PLAYBOOK §1 + runbook 引用 |
| P-10 | 🟢 低 | 30 秒 SLA 含义模糊(reload vs 端到端) | RUNBOOK_ROLLBACK 改成"reload 后 ≤30s 切完;含决策时间端到端 ≤5min" |
| P-11 | 🟡 中 | runbook §0 引用 §18 smoke 不存在 | 修订:补一节 §18 给出 10 项 smoke list |
| P-12 | 🟡 中 | 通道前后不一致(钉钉 vs 企业微信) | 全篇统一"企业微信(主) + 电话(P0)" |
| P-13 | 🟢 低 | "全局白名单"无汇总 | 新增 §B-04 后置子表 |
| P-14 | 🔴 高 | `/readiness` 字段不匹配,验收命令会永远失败 | 改成 `jq '.checks.payment.status'` |
| P-15 | 🟡 中 | 5xx 阈值时间窗口前后矛盾(5min vs 2min) | 全篇统一"自动触发 1% × 2min;熔断动作监控窗口 5min" |

### 3.2 工具缺失 (5)

| ID | 工具 | 状态 |
|---|---|---|
| T-01 | `ops/scripts/golive_preflight.sh` | ✅ 本次新增,本地 dry-run 通过 |
| T-02 | `ops/scripts/deploy.sh` (--canary / --rollback) | ✅ 本次新增(docker-compose 模拟 + 真生产 TODO) |
| T-03 | `docs/ops/INCIDENT_PLAYBOOK.md` | ✅ 本次新增 |
| T-04 | `ops/grafana/dashboards.md` + 1 个示例 JSON 骨架 | ✅ 本次新增(关键面板列表;真实 JSON 待 Grafana 实例确定) |
| T-05 | `.gitattributes` 强制 sh=LF | ⚠️ 未在本 PR 内做,放 follow-up |

---

## 4. 高风险点 Top 3

1. **P-14(/readiness 字段名错误):** 真上线时 ops 跟着 runbook 跑 `curl … | grep 'wechatpay.ok=true'`,永远不会匹配,会被误判为"支付未就绪"导致回滚或延期。**已修订**。
2. **P-01 / P-02(支付/SMS 环境变量名错误 + 模板数量超出代码支持):** 直接照 runbook 把 secret 推到 KMS 后服务读不到,启动 503。**已修订**;同时在 `golive_preflight.sh` 中加入"配置 key 一致性"自动检查。
3. **P-06(Alertmanager compose 路径错误):** 上线前 30 分钟才发现 alert 通道挂了,会被迫选择"裸奔上线"或"延期"。**已修订** compose 路径,并在 preflight 中加入 `docker compose -f docker-compose.alertmanager.yml config` 干跑。

---

## 5. 时间预算(估算,基于本次 dry-run + 现有数据)

| 阶段 | 估算 | 依据 |
|---|---|---|
| Preflight 一键脚本(`golive_preflight.sh`) | 5-8 min | 包含 alembic 三轮 ~7s × 3 + readiness + 测试 + 配置 check |
| B-01..B-05 各 Blocker 操作 | 各 15-30 min | 多数是凭证写 KMS + redeploy |
| 灰度 5%→100%(4 个 stage × 30 分钟观察) | 2-2.5 小时 | ADR-0028 标准窗口 |
| 紧急回滚场景 A 端到端 | 1-3 min | reload 0.3s + 决策 + 验证 |
| 紧急回滚场景 B 端到端 | 5 min | 与 RUNBOOK_ROLLBACK 一致 |
| 紧急回滚场景 C 端到端 | 15-30 min | 备份 + downgrade + 验证 |

---

## 6. 修订/新增文件清单

| 类型 | 路径 |
|---|---|
| 修订 | `docs/runbook-go-live.md` |
| 修订 | `docs/RUNBOOK_ROLLBACK.md` |
| 修订 | `docker-compose.alertmanager.yml`(卷路径修正) |
| 新增 | `docs/ops/GOLIVE_DRYRUN_REPORT_2026-04-25.md`(本文件) |
| 新增 | `docs/ops/INCIDENT_PLAYBOOK.md` |
| 新增 | `ops/scripts/golive_preflight.sh` |
| 新增 | `ops/scripts/deploy.sh` |
| 新增 | `ops/grafana/README.md` + `ops/grafana/yiluan-overview.json`(骨架) |

---

## 7. 后续建议(不在本 PR)

- 增加 `.gitattributes`:`*.sh text eol=lf` 强制 LF,避免 Windows 提交后 Linux 跑不动。
- `golive_preflight.sh` 接入 CI(已有 `alembic-smoke.yml`,可加一步 readiness 端到端调用)。
- ADR-0028 的 watcher(自动 5xx > 1% × 2min 触发回滚)目前是 mock,建议下一 sprint 接 Prometheus webhook 真实落地。
- 阿里云 SMS 多模板支持(目前代码只支持单 template_code,runbook 提了 4 个用途模板,需 backend 扩展)。
- `pg_restore` 演练(沙箱):用最近一次备份恢复到独立容器,用 pytest 跑全量 smoke,作为"备份真的能恢复"的证据。

---

**Sign-off:** SRE / 发布工程师 — 2026-04-25
