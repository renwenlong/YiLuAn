# 魈 — S2-DEV-006 调度锁 + token 滚动窗口 revoke Code Review

**结论**：✅ **通过 set done**。`@with_scheduler_lock` red line 闭环；五个点全 verified；上轮埋的两个 follow-up（record_access precise distinct / mid-session revoke 踢人）这轮兑现。

---

## ✅ 5 个 review 点 verified

### 1. 双防线只扣 1 次费

- **enqueue 幂等**：`AIDigest(order_id unique)` upsert PENDING → 同 order 多次 enqueue 只 1 行
- **worker scheduler lock**：`process_pending_digests_job` 整段 drain 包在 `async with acquire_scheduler_lock(...)` 内，`not lock.acquired` 直接 skip

两道防线叠加正确——即使两副本同一毫秒拿到同一 pending 行，advisory lock 串行化保证只一个 drain。**`@with_scheduler_lock` PRD §F4 / ADR-0035 §3 P1-A red line 至此满足**。

**架构师视角加分**：lock 包的是**整个 drain 批次**而不是单行——避免"副本 A 处理 row1 时副本 B 抢到 row2"的撕裂，整批由单实例 drain，metrics/cost 计账不会跨副本错乱。

### 2. 滚动窗口 ≠ 单计数器

- 新建 `OrderShareAccessLog` append-only 表（`f7a8b9c0d1e2` migration）
- scanner 走 `count_distinct_accessors_in_window(token, now-24h)` = `COUNT(DISTINCT accessor_openid) WHERE accessed_at > now-24h`
- token 行上的 `distinct_accessor_count` 保留作 display 近似值，注释明示「aggregate stays approximation; scanner computes precise」

**完美兑现** S2-DEV-001 review 我提的「record_access distinct 留 S2-DEV-006 升级 precise 24h-rolling-window」。单计数器无法做滚动窗口（删不掉 24h 前的计数），append-only log + 时间窗 COUNT DISTINCT 是唯一正解。

测试覆盖到位：同人复用 distinct=1 / 窗口外 24h 排除（3in 3out→3）/ 6>5 revoke / 5 边界不误 revoke。

### 3. mid-session revoke 踢人

share WS **ping 心跳分支**复查 `token.is_active`，scanner/手动 revoke 后下次 ping（前端定时心跳）→ close 4013。

**补上 S2-DEV-003 的真实缺口**：上轮 WS 只在**握手时**校验 is_active，已建立的 socket revoke 后不被踢——异常泄露 token 被 scanner 自动 revoke 了但家属屏幕还在实时刷位置，等于 revoke 形同虚设。这轮心跳分支补齐，**revoke 在一个 ping 间隔内真生效**。

这是我上轮没主动点出但确实存在的洞，胡桃自己识别并补上 —— 加分。

### 4. WS 访问也计 distinct

握手成功用 JWT `acc` openid 记一条 access log → 只连 WS 不打 REST 的家属也进 distinct 统计。

**正确**——否则泄露场景"链接被转发到群，群友只看 WS 实时位置不点 REST 详情"会绕过滥用检测。访问入口全覆盖。

### 5. 复用现有锁体系

直接用 `app/core/distributed_lock`（PG advisory / Redis NX / 假锁自适应），没新起一套。

**对**——`acquire_scheduler_lock` 已是项目既有调度锁抽象，复用保证 deploy 环境（有无 Redis）自适应一致。测试验了 `RedisNXLock 真并发抢锁互斥`（gather 两协程 1 win 1 lose）—— 不是 mock 而是真锁语义测试，可信。

---

## 💭 报备两点

### 1. migration id 撞车自修

`e1f2a3b4c5d6` 撞 `add_admin_notes` → 删除重命名 `f7a8b9c0d1e2`，`alembic heads` 现单一 head。

**处理正确**。这是第二次 migration id 撞车（上次 S2-DEV-001 `a1b2c3d4e5f6` 也撞过），建议团队约定：**新 migration id 用 `alembic revision` 自动生成的随机 hash，不要手写顺序 id**。我记进 follow-up，不挡 done。

### 2. OTP 频控（刻晴 N9a/b）不在本 task

**判断对**——OTP 频控依赖 Aliyun SMS 真验证器，本 task scope 是调度锁 + scanner，不硬塞。

但 **N9a/b 不能无限期挂**：它对应 ADR-0036 §2.2 OTP 降级路径 + PRD F2 OTP 速率限制（我 + 刻晴双轴 review 意见：单 token 24h≤5 / 单手机号 1h≤3）。建议建独立 task **S2-DEV-011 Aliyun SMS OTP 真验证器 + 频控**，灰度前必须 done（否则 F2 iOS/H5 降级路径不可用 + SMS 成本敞口）。

---

## 🟡 follow-up（不挡 done）

1. ⚠️ **建 S2-DEV-011**：Aliyun SMS OTP 真验证器 + 双轴频控（单 token 24h≤5 / 单手机号 1h≤3）+ `share_otp_invalid_total{reason}` metric + 顺收刻晴 N9a/b。**灰度前必 done**（F2 降级路径硬依赖）
2. 💭 团队约定：新 migration id 用 `alembic revision` 自动 hash，不手写顺序 id（已撞车两次）
3. 💭 S2-DEV-005 follow-up 启动 log effective 价格——本 task 没带，可放 S2-DEV-011 或灰度部署 checklist

---

## ❌ 不采纳/反对

无。

---

## Set done 路径

直接 set done。`@with_scheduler_lock` red line 闭环，灰度前置的后端骨架（S2-DEV-001/002/003/005/006）全齐，剩 S2-DEV-004 OpenAPI baseline 闸门（CI 配置类）+ S2-DEV-011 OTP（新建）。

**Review 完成时间**：2026-05-29 07:58 UTC
**Reviewer**：魈
