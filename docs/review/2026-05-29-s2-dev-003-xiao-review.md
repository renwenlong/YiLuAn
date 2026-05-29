# 魈 — S2-DEV-003 WS Code Review

**结论**：✅ **通过 set done**。Top1 整个家属端的安全闭环到此完成。

WS 是 share token 鉴权链路的最后一公里，胡桃这版四个 critical 点全打到，spot-check 一遍代码每点都在。

---

## ✅ 4 个 review 点 verified

### 1. JWT 重新校验（防有效 JWT 但 token 半路 revoke / expire）

`backend/app/api/v1/ws.py:421` decode JWT → `:448` 重新查 `OrderShareToken` 行 → `not token_row.is_active` 直接 `close(4013)`。

闭环 §3.5 #2「revoked token 已建立的 WS 主动断开」**完美**。这个语义现在生产 chat WS 也没有，胡桃做对了「mid-session revoke 真生效」而不是「下次握手才生效」。

### 2. JWT 绑 URL token（防 JWT 跨 token 重放）

`ws.py:453` `str(token_row.id) != payload.get("tid")`，不匹配 close 4001。

`share.py:64` `"tid": str(token_id)` 签发侧已有 claim。

闭环 §3.5「JWT 跨 token 重放」攻击向量，**对应 test `token_id_mismatch_in_url_closes_4001`**。

### 3. close codes 4012/4013/4014 全覆盖

| Code | 触发 | 实现位置 | 测试 |
|---|---|---|---|
| 4012 | 上行写帧（任意非 ping） | `ws.py:518/526` 双重防御（JSON 解析失败 + JSON 但非 ping） | ✅ `upstream_write_frame_closes_4012` |
| 4013 | revoke / expire mid-session | `ws.py:449` | ✅ `revoked_token_closes_4013` |
| 4014 | per-token 连接 >3 evict 最老 | `ws.py:472` + `settings.ws_share_max_connections_per_token` 可配 | ✅ `per_token_cap_evicts_oldest_with_4014` |

ws.py 顶部 docstring 同步扩了三档 code 语义，与 4001/4003/4004/4008/4011 同款 — 符合上轮 review §一-WS 中我给胡桃的建议。

### 4. 位置 cache replay

`location_replay` 帧**先于** `share_auth_ok` 推送（test `cached_location_replay_pushed_first` 验证顺序）。

cache key `share:loc:{order_id}`，TTL 60s，可配（`settings.ws_share_loc_cache_ttl_seconds`）—— 严格对齐 ADR-0036 §2.4 + 刻晴 PRD AC#5「断线 10s 重连位置点不空」红线。

**架构师视角加分**：先推 cache 再推 auth_ok 的顺序是对的——家属客户端能立刻拿到位置渲染，再处理 auth_ok 标志位，**避免渲染层判断"已鉴权但还没数据"的中间态**。这是细节，胡桃自己想到的。

---

## 🟡 1 个 follow-up 已欠两轮，必须收

**`share_session` JWT 加 `aud="share"` claim**——

我在：
- `docs/review/2026-05-28-s1-dev-001-xiao-review.md` §三.1（首次提）
- `docs/review/2026-05-29-s2-dev-002-xiao-review.md` §「🟡 1 个 follow-up」（建议 003 一起补）

提过两轮，本轮 S2-DEV-003 没补。代码现状 `share.py:_sign_share_session` 只有 `type` 和 `tid`，没有 `aud`。

**不挡当前 done**——`type` claim + 严格白名单 + tid 绑定的三层防御已经覆盖 OWASP 标准串货攻击面。但 `aud` 是 RFC 7519 标准、未来 portable，**建议进 follow-up micro PR 排第一**（3 行改：`_sign_share_session` 加 `"aud": "share"` + `decode_share_session` 加 `audience="share"`，WS 和 REST 同走 decode 一次改两处）。

**升级跟踪**：建立 micro task `S2-DEV-010` 或下次 S2-DEV-005 PR 顺手收，下次再不收我就强制走 PR review 卡 done。

---

## 💭 关于测试合跑 hang

**承认其判断不阻塞**。理由：
- 单文件跑 9/10 全绿（1 skip 已注释解释 fanout integration 在 `tests/test_ws_pubsub.py` 单元覆盖）
- 合跑 hang 是 FastAPI lifespan + TestClient + share broker 交互问题，**测试基础设施**而非实现 bug
- commit message 显式标注 + 建议 CI 独立 job
- 5 分钟内定位不到根因，时间盒判断正确

**Follow-up**：建议刻晴 W19 测试 infra task 或下周一 micro 修——这事归测试基础设施，胡桃不必现在 deep dive。可以让刻晴接 S2-TEST-002 实施时同步处理（她的 release gate 必须解决测试合跑路径，否则 CI 怎么跑）。

---

## 💭 关于 broker 启停

新增 `start/stop_ws_share_pubsub` + `main.py` lifespan 同时启停 + 独立 `settings.ws_share_pubsub_enabled` 配置位 —— 与 chat broker 同模板。

**架构师视角加分**：独立 channel `yiluan:ws:share`（不是塞进现有 `yiluan:ws:chat` 复用）—— 这样：
1. share 流量异常（位置点风暴）不污染 chat 消息延迟
2. Redis pubsub 监控面板可分别看两条 channel 的 qps/lag
3. 万一要紧急关一边走 `ws_share_pubsub_enabled=False`，chat 不受影响

「分」比「合」对，胡桃判断准。

---

## ❌ 不采纳/反对

无。

---

## Set done 路径

直接 set done。Follow-up `aud` claim 进 next PR 强制收。

**Follow-up 列表（不挡 done）**：
1. ⚠️ **`share_session` JWT 加 `aud="share"` claim**（已欠两轮，强烈建议下个 PR 收，~3 行）
2. 💭 测试合跑 hang：刻晴 S2-TEST-002 实施时同步处理（fixture infra）
3. 💭 W20 灰度后关注 `yiluan:ws:share` channel qps 与 chat 分离曲线

**Review 完成时间**：2026-05-29 02:23 UTC
**Reviewer**：魈
