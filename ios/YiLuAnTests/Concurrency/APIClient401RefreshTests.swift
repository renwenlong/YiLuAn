// S2-TEST-003 / ADR-0035 §3 P0-B (iOS APIClient 401 并发 refresh) — 测试用例预写
//
// 当前 APIClient.refreshTokenIfNeeded() 的 guard 仅防重入，未挂起其他并发请求：
//   guard !isRefreshing else { return }   // ← 直接返回，旧 access token 仍被重放
//
// W20 D4-D10 P0-B 修复必须满足下面 6 条用例。当前全部 XCTSkip，
// 修复落地后去 skip 直接接入 ios-tests workflow（作为 P0-B 的 release gate）。
//
// 用例覆盖：
//   C1  并发 5 个 401 请求只触发 1 次 /auth/refresh
//   C2  refresh 成功后 5 个挂起请求自动用新 token 重放
//   C3  refresh 失败统一抛 AuthExpired + 触发强登出（KeychainManager.clearTokens）
//   C4  refresh 期间新进请求加入挂起队列，refresh 完成后顺序重放
//   C5  refresh 超时（> 10s）降级登出，不让请求悬空
//   C6  refresh token 本身 401 → 立即强登出，不再 retry
//
// 实现提示（给胡桃/iOS 实施者）：
//   - 引入 actor TokenRefreshCoordinator 或 NSLock + CheckedContinuation 队列
//   - 改 refreshTokenIfNeeded() 为 await 已 inflight 的 Task；唯一 source-of-truth
//   - APIError.authExpired 新增 case，触发 NotificationCenter post → AppState 登出
//   - URLProtocol mock 工具：见 ios/YiLuAnTests/Mocks/MockURLProtocol.swift（待 P0-B 时一并落）

import XCTest
@testable import YiLuAn

final class APIClient401RefreshTests: XCTestCase {

    override func setUp() {
        super.setUp()
        // 阶段 A：用例全 skip；保留 setUp 结构供 P0-B 落地时复用
    }

    func test_c1_concurrent_5_401_triggers_single_refresh() async throws {
        try XCTSkipIf(true, "await P0-B implementation (S2-DEV-008 or W20 联调)")
        // 期望：5 个并发请求同时收到 401 → /auth/refresh 调用计数器 == 1
    }

    func test_c2_refresh_success_replays_all_pending_with_new_token() async throws {
        try XCTSkipIf(true, "await P0-B implementation")
        // 期望：refresh 完成后 5 个挂起请求自动用新 access token 重放并 200
    }

    func test_c3_refresh_failure_throws_auth_expired_and_clears_keychain() async throws {
        try XCTSkipIf(true, "await P0-B implementation")
        // 期望：refresh 返回 401 → 所有挂起请求统一抛 APIError.authExpired
        //       + KeychainManager.accessToken == nil + refreshToken == nil
    }

    func test_c4_new_requests_during_refresh_join_pending_queue() async throws {
        try XCTSkipIf(true, "await P0-B implementation")
        // 期望：refresh 进行中（500ms）期间新进 3 个请求，refresh 完成后这 3 个也用新 token 重放
    }

    func test_c5_refresh_timeout_10s_degrades_to_logout() async throws {
        try XCTSkipIf(true, "await P0-B implementation")
        // 期望：refresh 调用挂起 > 10s → 触发超时降级 → 所有挂起请求统一抛 authExpired
    }

    func test_c6_refresh_token_itself_401_strong_logout_no_retry() async throws {
        try XCTSkipIf(true, "await P0-B implementation")
        // 期望：/auth/refresh 返回 401 → 不再 retry 原请求 → 立即清 token + 抛 authExpired
    }

    // ---- 辅助断言（P0-B 落地时启用） ----

    func test_design_token_isRefreshing_must_not_short_circuit() async throws {
        try XCTSkipIf(true, "await P0-B implementation")
        // 断当前实现的反模式：guard !isRefreshing else { return } 必须删除或重构为 await Task.
    }
}
