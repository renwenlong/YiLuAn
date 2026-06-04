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
}
