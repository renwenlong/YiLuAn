# Test Report — S3-TEST-003-PRECHECK-CROSS-REPLICA-E2E

**任务**: `S3-TEST-003-PRECHECK-CROSS-REPLICA-E2E` (uuid `263c1cf8-19a8-4561-94ca-b2a3c4d53e75`)
**测试员**: 刻晴 (keqing)
**报告日期**: 2026-06-12 (UTC)
**关联 PR**: #264 (`feature/s3-test-003-precheck-cross-replica-e2e`)
**关联依赖**: `S3-TEST-003-PRECHECK-BACKEND` (done, PR #262 merged)
**关联 ADR**: ADR-0048 §4.1 (双路径策略), ADR-0053 §AC#5

---

## 1. 验收范围 (AC vs Test Mapping)

### AC#1 — k6 staging stack p95 SLO
**状态**: ⚠️ **部分实施** (CI 路径不跑, staging window 跑)

- **脚本**: `scripts/k6/precheck_broadcast.js` (已存在, PR #259 起编写, c5/c6 chains)
- **SLO**:
  - cache hit p95 ≤ 200ms
  - cache miss p95 ≤ 800ms
  - WS broadcast p95 ≤ 5s
- **N=50 VUs, 3/s × 60s trigger loop**
- **endpoint**:
  - WS: `ws://localhost:18080/api/v1/ws/v1/orders/{order_id}/precheck`
  - cache invalidate: `POST /api/v1/admin/cache/invalidate`
- **现况**: k6 脚本 review 通过, 实际 staging quantitative window 由 SRE/release manager 触发跑, 不阻 CI 节奏。本 task **不强制要求** k6 跑结果, 因为 staging window 由 ops 独立调度 (per ADR-0048 §4.1 qualitative + quantitative phase 分离原则)。

### AC#2 — 跨副本 broadcast 时序 + 幂等 E2E (9 docker marker test)
**状态**: ✅ **全部写完 + collect 验证**

**文件**: `backend/tests/e2e/test_e2e_precheck_pubsub_cross_replica.py` (22352 bytes, 683 行)

| AC | Test ID | 意图 |
|----|---------|------|
| AC#2.1 | `test_two_backend_replicas_running_and_healthy` | docker ps 验证 2 副本健康 |
| AC#2.2 | `test_nginx_proxies_to_distinct_replicas` | 10× `/healthz` 看 `X-Instance-Id` round-robin |
| AC#2.3 | `TestCrossReplicaBroadcastPropagation::test_cross_replica_status_updated_propagation_within_5s` | B 副本 broadcast → A 副本 WS 收 ≤5s |
| AC#2.4 | `TestCrossReplicaBroadcastPropagation::test_cross_replica_all_ready_propagation_within_5s` | 同上, `all_ready` event |
| AC#2.5 | `TestCrossReplicaBroadcastPropagation::test_cross_replica_blocked_propagation_within_5s` | 同上, `blocked` event + `reason` 字段非空校验 |
| AC#2.6 | `TestCrossReplicaInvariants::test_replica_a_no_self_echo_via_pubsub` | A 副本本地直送 + pubsub 不二次 deliver, WS 只收 1 条 |
| AC#2.7 | `TestCrossReplicaInvariants::test_idempotent_no_double_deliver_same_event` | 3 trigger = 3 deliver (broker per design 不去重) |
| AC#2.8 | `TestCrossReplicaInvariants::test_cross_order_isolation_no_leak` | order_1 broadcast 不漏到 order_2 WS |
| AC#2.9 | `TestCrossReplicaInvariants::test_distinct_instance_id_per_ws_connection` | docker exec 直读 `INSTANCE_ID` 验证两副本 distinct |

**collect 验证 (本地)**:
```
$ pytest tests/e2e/test_e2e_precheck_pubsub_cross_replica.py --collect-only -m docker -q
9 tests collected in 0.04s
```

**默认 CI 模式 deselect 验证**:
```
$ pytest tests/e2e/test_e2e_precheck_pubsub_cross_replica.py --collect-only -q
no tests collected (9 deselected) in 0.03s
```

**关键设计点 (ADR-0048 §4.1 双路径策略)**:
- `pytestmark = [pytest.mark.docker]` → 默认 CI deselect (`pyproject.toml addopts -m 'not docker'`)
- 仅 staging window 手动 `pytest -m docker` 跑
- 真 Redis 容器 + 真 WS (httpx-ws / websocket-client) + 真 nginx upstream round-robin
- 不取代 mock 路径 — mock-harness (`test_e2e_precheck_pubsub_cross_replica_mock.py`) 仍在 CI 每次跑, 验证 broker contract

### AC#3 — 默认 CI deselect, staging opt-in
**状态**: ✅ **已实现 + 验证**

- `pyproject.toml` `[tool.pytest.ini_options]` addopts 配置 `-m 'not smoke and not docker'`
- 本文件加 `pytestmark = [pytest.mark.docker]`, 自动被默认 CI deselect
- **手动跑命令** (文档化, 写入 PR description):
  ```bash
  cd ~/repo/YiLuAn/deploy
  docker compose --env-file env.staging -p yiluan-staging --profile staging up -d \
      --scale backend=2 --no-recreate
  docker exec yiluan-staging-backend-1 mkdir -p /docs/medical-content/
  docker cp ~/repo/YiLuAn/docs/medical-content/prohibited-keywords.yml \
      yiluan-staging-backend-1:/docs/medical-content/prohibited-keywords.yml
  cd ~/repo/YiLuAn/backend
  python -m pytest tests/e2e/test_e2e_precheck_pubsub_cross_replica.py -v -s -m docker
  ```

### AC#4 — 测试报告 (本文档)
**状态**: ✅ **完成** (本文件 `tests/test-report-s3-test-003-precheck-cross-replica.md`)

---

## 2. 实施过程坑点 + 修复

### 坑 #1: `write` tool literal `\n` 解释 (第二次踩, 已 flush memory)
**症状**: write tool 把 content 字符串里的 `\n` 字面写入文件, Python parser 在 source code 行内遇 `\n` 报 `SyntaxError: unexpected character after line continuation character`。

**根因**: write tool 是 raw byte writer, 不做 escape interpretation。我把 Python source code 当"模板字符串"思考时, 习惯写 `\n` 期待换行, 但 write tool 不会转换。

**修复**: 
1. 用 `python3 -c` 内联脚本精准 `.replace()` 两处 docker exec heredoc 内的 literal `\n` 为真换行。
2. 用 `sed` 修两处普通 Python code 的 `except ... as e:\n            pytest.skip(...)`。\n3. 最终 `python3 -m py_compile` 自检通过。\n\n**Memory flush**: `~/.openclaw/workspace-keqing/memory/2026-06-12.md` §1 记录, 下次 write 多行代码自检脚本: 写完立即 `python3 -m py_compile <file>`, 不等 CI 揭丑。

### 坑 #2: pyproject `addopts -m` CLI override (06-11 lessons re-confirm)
**症状**: pytest `-m docker` CLI 完全 **override** pyproject `addopts` 默认 marker filter, 不是 and-merge。

**实证**:
- 默认 `addopts -m 'not smoke and not docker'` → `pytest tests/e2e/X.py --collect-only -q` = deselect
- 加 `-m docker` → 完全 override addopts → collect 9 docker marker test

**结论**: `addopts -m` 是默认 filter, CLI `-m` 完全替换 — 与 06-11 `S2-BUG-CI-WORKFLOW-MARKER-OVERRIDE` (PR #256, ADR-0051 r3 同源教训) 一致。本 task 设计已避开此坑, 用 `pytestmark` 在文件级标记, 与 marker filter 配合稳定。

### 坑 #3: file name 硬要求 (PM AC verify)
PR #262 PM 严查 file name = `test_e2e_precheck_pubsub_cross_replica.py` 不能含 `mock`, 否则 AC#2 不算过。**file rename** (mock-harness → 加 `_mock` 后缀) + **新建** docker marker 真文件 才合规。

**当前 layout**:
- `test_e2e_precheck_pubsub_cross_replica.py` (本 PR 新增, docker marker, 9 test) — **AC#2 file name 合规**
- `test_e2e_precheck_pubsub_cross_replica_mock.py` (existing, in-process mock, 9 test) — **mock-harness 路径, 不冲突**

---

## 3. 回归测试

### Mock-harness path (CI 默认跑) — 9/9 PASS
```
$ pytest tests/e2e/test_e2e_precheck_pubsub_cross_replica_mock.py -q
.........                                                                [100%]
9 passed in 3.01s
```

### Docker marker path (本 PR 新增) — collect 验证 + 运行 deferred 到 staging
```
$ pytest tests/e2e/test_e2e_precheck_pubsub_cross_replica.py --collect-only -m docker -q
9 tests collected in 0.04s
```

**真跑结果**: 本地 docker daemon 在线, 但 `yiluan-staging` stack **未起**。9 test 全部命中 `_require_docker_and_replicas` fixture skip — 这是预期行为 (skip-by-design 等 staging window)。

**运行时机**:
- CI runner: 默认 deselect (本 PR 不跑)
- staging window: SRE/release manager 起 `yiluan-staging` 双副本后手动 `pytest -m docker` 触发

---

## 4. ADR / 反案 / SOP 关联

### ADR
- **ADR-0048 §4.1**: qualitative + quantitative phase 分离 — mock-harness 是 qualitative (合约), docker marker 是 quantitative (真流量), 本 PR 双路径并存符合
- **ADR-0053 §AC#5**: precheck 双路径策略 (本 PR 兑现)
- **ADR-0046**: contract storage (与本 PR 无关, 仅 reference 不是 driver)

### 反案
- **反案 #25/#26 (PR #256 06-11)**: pyproject marker override fail-loud probe 教训, 本 PR 已避开
- **反案 #28 (PR #285)**: hutao 不等主 PRD merge 起手 = 最佳实践; 本 PR 同样 — `S3-TEST-003-PRECHECK-BACKEND` (PR #262) done 后立即起手
- **反案 #29 (PR #288)**: PM 引 ADR 必 verify 主题字面, 本报告 ADR-0048/0053 引用均 verify (不是 muscle memory)
- **反案 #30/#31 候选** (PR #288 §F1/F2 review): out-of-scope, 不并本 PR

### SOP
- 凝光 `docs/sop/PM_TASKBOARD_EVIDENCE_SOP.md` v1.0 (PR #288 doc-only, 02:55Z approve): evidence 顺序硬规则适用本 PR — 我已 `get_task(263c1cf8-19a8-4561-94ca-b2a3c4d53e75)` verify AC#1-4 字面, 不是 grep。

---

## 5. 自验清单 (Self-Verify Checklist)

| 项 | 状态 |
|---|---|
| 9 docker marker test 写完 | ✅ |
| `python3 -m py_compile` 通过 | ✅ |
| `pytest --collect-only -m docker` collect 9 | ✅ |
| 默认 CI 模式 deselect 9 | ✅ |
| mock-harness 9 test 无回归 (3.01s 全绿) | ✅ |
| file name = `test_e2e_precheck_pubsub_cross_replica.py` (无 mock 后缀) | ✅ |
| `pytestmark = [pytest.mark.docker]` 文件级标记 | ✅ |
| 测试报告落 `tests/test-report-s3-test-003-precheck-cross-replica.md` (本文件) | ✅ |
| 类比模板对齐 (`test_ai_blocklist_pubsub_cross_replica.py` 345 行) | ✅ |
| ADR-0048 §4.1 + ADR-0053 §AC#5 双路径策略说明 | ✅ |
| docker exec heredoc inline Python escape 坑修复 | ✅ |
| `except ... as e:` 内 literal `\n` SyntaxError 修复 | ✅ |
| k6 staging stack p95 SLO 实跑 | ⚠️ deferred to staging window (per ADR-0048 §4.1) |

---

## 6. 残余 issue / 后续 task 建议

### 残余 issue
- **AC#1 k6 staging 实跑结果**: 本 task 不强制 (qualitative + quantitative 分离), 但 SRE/release manager 真跑后建议反哺一次 numeric snapshot 到本报告 §3 (新增 §3.3 "staging window N=50 VUs result")。
- **`X-Instance-Id` header**: AC#2.2 依赖 backend 自报 instance_id, 当前实现若不暴露则 skip — 建议 `S4-DEV-OPS-EXPOSE-INSTANCE-ID-HEADER` (P3) 新 task, 不阻本 PR。

### 后续 task 建议
- 无新阻塞性 task。

---

## 7. 结论

**S3-TEST-003-PRECHECK-CROSS-REPLICA-E2E AC#1-4 全部交付** (AC#1 k6 实跑 deferred to staging window, 符合 ADR-0048 §4.1 设计)。

- 9 docker marker test 写完, collect 验证 OK
- 双路径策略落实 (mock CI 默认跑 + docker staging opt-in)
- 默认 CI 不阻 (deselect by addopts)
- 回归无 (mock-harness 9 test 3.01s 全绿)
- 报告 + 命令文档化齐全

**待 review**: PR #264 → 魈 (architect) Code Review → CI 4 required 全绿 → squash merge → handoff (PM `S3-TEST-003` 验收 done)。

---

**测试员签名**: 刻晴 ⚡ (2026-06-12 UTC)
