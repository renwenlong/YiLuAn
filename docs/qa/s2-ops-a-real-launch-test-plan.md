# S2-OPS-A-REAL-LAUNCH 测试预案 (真实灰度上线)

> Task: `S2-OPS-A-REAL-LAUNCH` — F2 canary 真实灰度上线 (真白名单切量 + 24h 观察窗)
> 测试员: 刻晴 (tester) | PM 验收: 凝光 | review: 魈
> 编写日期: 2026-06-18 (预案先行, 名单到位前不可执行)
> 环境: canary 灰度栈 `yiluan-canary-*` (真物料路径)
>
> ⚠️ **状态: BLOCKED — 卡帝君真白名单名单 (5-10 同事 + 5 团队真手机号)**。
> 本预案是**前置准备**, 名单到位即可按此执行, 不浪费等待窗口。与 mock 演练 (已 done, AC-2/3/6/7) 语义分离: mock 验 gate 机制正确性, 本 task 切真流量 + 24h 观察。

---

## 1. 前置阻塞 & 数据源 (执行前必须满足)

| 前置 | 现状 (2026-06-18 实测) | 满足判定 |
|---|---|---|
| 真白名单名单 | ❌ `deploy/canary/whitelist_phones.yaml` **8 个占位符 0 真号** (`__PENDING_PM__` 等) | 帝君交 5-10 同事 + 5 团队真手机号给凝光 → 凝光收齐 → 胡桃写入 |
| 真号写入路径 | yaml 注释 §20 约定: **另起 `deploy/canary/whitelist_phones.real.yaml`** 避免 mock/real 串 | 真号进 real yaml, 非覆盖 mock yaml |
| gate 数据源 | `backend/app/services/canary_whitelist.py` 加载 yaml + `config.py:255 canary_whitelist_enabled` | 确认 real yaml 被 load (非 mock yaml) |
| 镜像 rebuild | 反案: yaml 由 Dockerfile COPY 进镜像 | **必须 `./up.sh canary` (=up -d --build)**, 光 restart 不更新 yaml |

**❗ 阻塞硬规则**: 名单缺失时 task 不可起 (AC4 前置)。我不擅自用占位号冒充真上线 — 那是 mock 范畴已做完。

---

## 2. 验收标准映射 (6 条 AC → 测试用例)

### AC1 (AC-5): 真白名单切真流量 — 真号放行 + 非白名单 403
| 用例 | 输入 | 期望 | 验证方式 |
|---|---|---|---|
| TC-1.1 真号放行 | 真白名单手机号 (取名单中 1-2 个) 走完整 send-otp→verify→create_share | 200/201 真 share_token (或放行到业务后续) | 真 HTTP, 路由 `POST /api/v1/orders/{order_id}/shares` |
| TC-1.2 非白名单拦截 | 不在名单的真手机号 (或测试外人号) | **403** `SHARE_F2_CANARY_NOT_WHITELISTED` | 真 HTTP body error_code 精确匹配 |
| TC-1.3 gate-ON 确认 | 容器 `env\|grep CANARY_WHITELIST_ENABLED` | `=true` + `settings.canary_whitelist_enabled=True` | 三层确认 (env/settings/is_whitelisted) |
| TC-1.4 名单完整性 | real yaml 内真号数量 | 5-10 同事 + 5 团队 = 11-16 人, ≤ max_size 20 | 读 yaml count, 校 ≤20 爆炸半径 |

> **路由坑** (已记 memory): create_share 真路由是 `/orders/{order_id}/shares`, **不是 `/shares`** (后者只挂 token 二级 otp/session)。OTP 读 redis `otp:<phone>` (非 `otp:rate:<phone>` 限频 key)。

### AC2 (AC-8): 24h 观察窗 — 全程可观测 + 监控快照
| 用例 | 监控项 | 端点 | 留证 |
|---|---|---|---|
| TC-2.1 放行计数 | create_share 200/201 绝对次数 (主指标, 非比率) | Prometheus `http://127.0.0.1:9091` | 起始/中段/24h 三快照; 重点看“白名单放行绝对次数 > 0” (==0 持续 = 切量未生效) |
| TC-2.2 403 率 | `SHARE_F2_CANARY_NOT_WHITELISTED` 403 计数 | Prometheus POST 4xx by status_class | 快照 + 增量曲线 |
| TC-2.3 fail-closed | yaml malformed / phone=None 触发的 403 | 日志 + 403 分类 | 0 误触发为达标 |
| TC-2.4 业务异常 | 5xx / share 创建失败 / DB 异常 | Grafana `http://127.0.0.1:13001` + Alertmanager `:9094` | 面板截图 |

### AC3 (AC-9): 24h 验收门槛
- ✅ 放行生效 (白名单真号放行绝对次数 > 0, 不依赖比率; ==0 持续 N 小时 = 切量未生效告警)
- ✅ **0 误拦真白名单** (名单内真号被 403 = P0 bug, 立即报)
- ✅ **0 fail-closed 误触发** (非预期 403)
- ❌ 有异常 → 走 runbook 回滚 (PR #342 `up -d` 路径) + 留回滚证据 (env 翻 false→容器 recreate→外人 403 转 404 放行)

### AC5 (AC#监控): 真上线监控面板 + 告警阈值
> 魈 2026-06-18 拍 (技术项写死), ③ 待凝光定业务 N。

| 告警 | 阈值 | 触发动作 | 来源 |
|---|---|---|---|
| ① fail-closed 触发 | **threshold=1, 触发即告警, 不累积** | 立即人工介入查 yaml/redis/phone 解析 | 魈拍 (P0 兜底失效, 任一次即异常) |
| ② 403/min 突增 | **绝对值 > 10/min `OR` 环比前 5min 均值 ×3 (双触发并联)** | 排查接口扫描 / 白名单误配 | 魈拍 (低基数下绝对 floor 防抖 + 相对防渐变) |
| ③ 白名单放行缺失 | **白名单用户放行绝对次数 == 0 持续 N 小时** (替代不稳的「放行率<X%」) | 排查切量未生效 / gate 误拦真白名单 | 魈定指标方向, **N 待凝光定 (业务: 几小时无放行算异常)** |

> **③ 指标选型说明** (魈): 放行率 = 放行/(放行+拦截), 分母是白名单用户真实访问量, 5-10 人下比率本身不稳 (一用户多刷拉高)。改测「放行绝对次数==0 持续 N 小时」不依赖业务量, 更稳。N 是业务预期 (白名单几小时不访问算正常) → 凝光定。

### AC6 (AC#验收): 24h 后双签
- 凝光 PM 业务验收 (同 mock 双签先例: board comment + PR)
- 魈 code/ops review
- 我出 24h 测试报告 → `docs/qa/` (走 doc-only 短路, **不放 `tests/`** — 反案 #46 白名单坑)

---

## 3. 执行编排 (名单到位后, 时序)

```
T0   名单到位 → 胡桃写真号入 whitelist_phones.real.yaml → PR → 合并
T0+  ./up.sh canary rebuild (yaml 进镜像) → 10 容器 healthy 确认
T0+  我: TC-1.x gate-ON 真号放行 + 非白名单 403 实测 (HTTP 正反向)
T0+  gate-ON 切真流量 → 24h 观察窗启动
T0+  我: TC-2.1 起始监控快照 (放行率/403/fail-closed/业务异常基线)
T+12h 我: 中段监控快照 + 异常巡检
T+24h 我: 终态快照 + AC3 门槛判定 → 出报告 docs/qa/
       异常 → 回滚 (AC3) + 回滚证据
T+24h 凝光 PM 双签 + 魈 review → 魈 set done
```

## 4. 测试夹具 (复用 mock 演练已验, 见 cheatsheet)
- canary API 入口: `127.0.0.1:18090` (nginx→backend)
- OTP: redis `yiluan-canary-redis-1` `redis-cli GET otp:<phone>` (TTL 300s, 注意 60s 频控 `otp:rate:<phone>`)
- 监控: Prometheus :9091 / Alertmanager :9094 / Grafana :13001
- 回滚验证: `up -d` recreate 换 env (非 restart), 看容器启动时长 + 外人 403→404 转变

## 5. 不做 / 边界
- ❌ 不用占位号 (13800000001 等) 冒充真上线 — 那是 mock 范畴
- ❌ 名单缺失不起 task (AC4 前置硬阻塞)
- ❌ 不擅自改 real yaml (名单写入是胡桃的活, 我只验)
- ❌ 监控阈值具体数值待魈/凝光定 (AC5), 我不拍业务门槛

---

## 6. 当前状态 & 下一步
- **预案就绪 + 告警阈值①②已定 (魈 06-18 拍死)**, ③等凝光定 N (几小时无放行算异常)。
- 等帝君真白名单名单 → 名单到位本预案即可逐条执行。
- 名单缺口精确位置: `whitelist_phones.yaml` 8 占位符 (PM/architect/developer/+colleague 位)。
- 凝光已催帝君第 11 天。名单是**业务决策输入**, 非技术阻塞。
- **入库**: 本预案已走 PR 入 git (同 #343 audit 规范, 不留本地)。
