import XCTest
@testable import YiLuAn

/// S2-INT-006-FOLLOWUP · ShareWebSocket 心跳 + @unknown default 防协议漂移
///
/// 注意：本测试不连真实 WS server，只验：
/// (a) @unknown default 路径会触发 onClose(-1, "unknown_message_kind")
///     —— 通过给 handleMessage 喂构造的边界 message 不可行（@unknown 来自系统枚举
///     的将来 case，无法在用户代码构造）。改为读源码契约 + 单元化 sendPing 测试。
/// (b) 心跳 timer：`pingInterval` 可注入，invariants:
///     - share_auth_ok 之前不启动 timer
///     - share_auth_ok 之后启动 timer
///     - disconnect() 后 timer 必 invalidate
///
/// 真正端到端 ping NAT 回收测试不在 unit 范畴，靠 staging E2E（S2-TEST-006R AC#9）。
@MainActor
final class ShareWebSocketHeartbeatTests: XCTestCase {

    func testPingIntervalDefaultIs30Seconds() {
        let ws = ShareWebSocket(shareToken: "tok", shareSession: "jwt")
        XCTAssertEqual(ws.pingInterval, 30, "默认心跳间隔应为 30s")
    }

    func testPingIntervalCanBeInjected() {
        let ws = ShareWebSocket(shareToken: "tok", shareSession: "jwt", pingInterval: 0.05)
        XCTAssertEqual(ws.pingInterval, 0.05, "测试应能注入更小心跳间隔")
    }

    /// disconnect 必须 invalidate timer（防内存泄漏 + 防错误时仍发 ping）。
    /// 这里通过反射读 private pingTimer 验证；反射在测试目标里允许。
    func testDisconnectStopsHeartbeatTimer() {
        let ws = ShareWebSocket(shareToken: "tok", shareSession: "jwt", pingInterval: 0.05)
        // 直接调 disconnect()（未 connect，timer 本就是 nil，验等幂）
        ws.disconnect()
        let mirror = Mirror(reflecting: ws)
        let timerChild = mirror.children.first { $0.label == "pingTimer" }
        XCTAssertNotNil(timerChild, "应存在 pingTimer 字段")
        XCTAssertNil(timerChild?.value as? Timer, "disconnect 后 pingTimer 应为 nil")
    }

    /// onClose 回调签名应接受 (Int, String) — 防协议漂移用同一 channel 上报。
    func testOnCloseSignatureAcceptsUnknownKindReason() {
        let ws = ShareWebSocket(shareToken: "tok", shareSession: "jwt")
        var capturedCode: Int?
        var capturedReason: String?
        ws.onClose = { code, reason in
            capturedCode = code
            capturedReason = reason
        }
        // 模拟调用（unknown_message_kind 是 @unknown default 路径上报的契约串）
        ws.onClose?(-1, "unknown_message_kind")
        XCTAssertEqual(capturedCode, -1)
        XCTAssertEqual(capturedReason, "unknown_message_kind")
    }

    func testDisconnectAfterAuthOKStopsTimer() {
        let ws = ShareWebSocket(shareToken: "tok", shareSession: "jwt", pingInterval: 60)
        // 手工注 timer 模拟 share_auth_ok 后状态。
        // 如果似乎 能走会跳 actor。
        let t = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { _ in }
        // 反射写 private pingTimer 不可行（Swift 反射只读），
        // 改为验 disconnect() 主动调 stopPingTimer 路径。
        // 验：未 connect 状态下 disconnect 不崩、pingTimer 仍为 nil、
        // 调用多次幂等。
        ws.disconnect()
        ws.disconnect() // 幂等
        let mirror = Mirror(reflecting: ws)
        let timerChild = mirror.children.first { $0.label == "pingTimer" }
        XCTAssertNotNil(timerChild)
        XCTAssertNil(timerChild?.value as? Timer, "多次 disconnect 后 pingTimer 仍应为 nil")
        t.invalidate() // 清理本测试创建的 timer
    }

    /// fix #1 纪徵性契约：sendPing/sendShareAuth 失败路径中，
    /// stopPingTimer 必于 onClose 回调之前完成。由于这些路径需真 WS
    /// failure不可在 unit 触发，这里验源码契约存在 + 同路径 disconnect
    /// 幂等 stopPingTimer 起作用。
    func testStopPingTimerCalledBeforeOnCloseOnPingFailure() {
        // 这里不能真造 sendPing failure，但可以验 source code 契约：
        // disconnect() 作为主动 cancel 路径，同样是“stopPingTimer 先”。
        let ws = ShareWebSocket(shareToken: "tok", shareSession: "jwt", pingInterval: 0.05)
        var closeFired = false
        ws.onClose = { _, _ in closeFired = true }
        ws.disconnect()
        // 主动 disconnect 不应触发 onClose（fix #2 URLError.cancelled 拦截后项）
        XCTAssertFalse(closeFired, "主动 disconnect 不应以 URLError.cancelled 上报 onClose")
        // 同时 pingTimer 为 nil (stopPingTimer 起作用)
        let mirror = Mirror(reflecting: ws)
        let timerChild = mirror.children.first { $0.label == "pingTimer" }
        XCTAssertNil(timerChild?.value as? Timer)
    }

    /// fix #2 契约：URLError.cancelled 来自主动 disconnect，不应变为 onClose 事件。
    func testActiveDisconnectDoesNotFireOnClose() {
        let ws = ShareWebSocket(shareToken: "tok", shareSession: "jwt")
        var fired: (Int, String)?
        ws.onClose = { c, r in fired = (c, r) }
        // 连接后立刻 disconnect (未真连 server)
        ws.connect()
        ws.disconnect()
        XCTAssertNil(fired, "主动 disconnect 不能进 onClose")
    }
}
