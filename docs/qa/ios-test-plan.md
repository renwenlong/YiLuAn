# iOS Test Plan

> 与 `docs/qa/release-gates.md` 配套，覆盖 iOS 端 release gate 测试约束。

---

## 1. 现状

- 框架：XCTest（XCUITest 暂未引入；已在 S1-TEST-001 列为 P1 盲点 GAP-06）
- 既有覆盖：APIEndpointTests / AuthViewModelTests / OrderViewModelTests / 等 ≈ 57 case
- CI：`.github/workflows/ios-tests.yml`

---

## 2. 401 Refresh 测试（S2-TEST-003 / ADR-0035 §3 P0-B）

### 背景

`APIClient.refreshTokenIfNeeded()` 当前：

```swift
guard !isRefreshing else { return }
```

`guard` **仅防重入**——并发 5 个 401 请求时第 2~5 个直接 return，原 request retry 时仍带旧 access token，触发死循环或假性成功。

### 用例矩阵（`ios/YiLuAnTests/Concurrency/APIClient401RefreshTests.swift`）

| ID | 场景 | 期望 |
|----|------|------|
| C1 | 并发 5 个 401 | `/auth/refresh` 只被调用 1 次 |
| C2 | refresh 成功 | 5 个挂起请求自动用新 token 重放并 200 |
| C3 | refresh 失败 | 统一抛 `APIError.authExpired` + Keychain 清空 |
| C4 | refresh 期间新请求 | 加入挂起队列，refresh 完成后顺序重放 |
| C5 | refresh 超时 > 10s | 降级登出，请求不悬空 |
| C6 | refresh token 本身 401 | 立即强登出，不再 retry |

### 当前状态

阶段 A：全部 `XCTSkipIf(true)`，P0-B 实施后去 skip。

### 实施期建议

P0-B 修复 PR 必须：

1. 引入 `actor TokenRefreshCoordinator`（或 NSLock + CheckedContinuation 队列）
2. 删除 `guard !isRefreshing else { return }` 反模式
3. `APIError.authExpired` 新增 case，触发 `AppState` 登出广播
4. 配套 `MockURLProtocol` 测试基础设施
5. C1-C6 全绿 + Hypothesis-style 并发 fuzz（可选）

---

## 3. 跨端 Share 契约（S2-TEST-002 / `ShareEndpointContractTests`）

阶段 A：全部 `XCTSkipIf`，等 S2-DEV-002 6 个端点落地后启用。详见 `docs/qa/release-gates.md` §4。

---

## 4. CI Gate

- `ios-tests.yml` 已运行单测
- W20 联调期前：本文档表格中所有 C1-C6 必须从 `XCTSkip` 转为绿
- W20 灰度期前：`ShareEndpointContractTests` 必须从 `XCTSkip` 转为绿
- 任一回退到 skip 必须 PR 描述显式说明 + Owner 双签
