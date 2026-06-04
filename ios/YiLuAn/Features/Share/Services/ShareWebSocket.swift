import Foundation

/// 家属端 share WebSocket 客户端（S2-INT-006 #2）
///
/// 对应后端：`/ws/share/{token}` (ADR-0036 §2.4)
/// - 鉴权：第一帧 `{"type":"share_auth","session":"<share_session_jwt>"}`
/// - 服务端→客户端只读（任何上行非 ping 帧服务端 close 4012）
/// - close codes：4001 token_mismatch / 4012 upstream_write_forbidden /
///                4013 token_revoked_or_expired / 4014 per_token_cap_exceeded
///
/// 用法：
/// ```
/// let ws = ShareWebSocket(shareToken: token, shareSession: jwt)
/// ws.onEvent = { event in /* 更新 UI */ }
/// ws.onClose = { code, reason in /* 处理重连 / 跳回 OTP */ }
/// ws.connect()
/// // ... 视图退出时 ws.disconnect()
/// ```
///
/// 断线重连：本类**不内置**重连（避免在已 revoke 场景下死循环），由调用方按
/// close code 决策——4013/4001 跳回 OTPView；4014/4012/网络抖动可重连 1~2 次。
///
/// 心跳（S2-INT-006-FOLLOWUP）：连接成功后每 `pingInterval`（默认 30s）发一次
/// `URLSessionWebSocketTask.sendPing`，失败 → onClose(-1, "ping_failed")。
/// 移动网络 NAT 中间设备约 60s~5min 静默回收 idle 连接，30s ping 安全裕度足。
@MainActor
final class ShareWebSocket {

    // MARK: - Public callbacks

    /// 收到服务端事件（已 JSON-decode 为 `[String: Any]`）。本类整体 @MainActor 隔离，
    /// callback 在主线程执行。
    var onEvent: (([String: Any]) -> Void)?

    /// WS 关闭回调。调用方根据 code 决定重连 / 跳回 OTPView。
    var onClose: ((Int, String) -> Void)?

    /// 鉴权成功（收到 `{"type":"share_auth_ok"}`）。
    var onAuthOK: (() -> Void)?

    // MARK: - Inputs

    let shareToken: String
    let shareSession: String

    // MARK: - Internal

    private var task: URLSessionWebSocketTask?
    private let session: URLSession
    private var isConnected: Bool = false

    /// 心跳间隔（秒）。测试可注入更小值。
    let pingInterval: TimeInterval

    /// 心跳 timer。disconnect / 链路断时 invalidate。
    private var pingTimer: Timer?

    init(
        shareToken: String,
        shareSession: String,
        urlSession: URLSession = .shared,
        pingInterval: TimeInterval = 30
    ) {
        self.shareToken = shareToken
        self.shareSession = shareSession
        self.session = urlSession
        self.pingInterval = pingInterval
    }

    // MARK: - Lifecycle

    /// 建立连接 + 发 share_auth 首帧。
    /// 服务端验证后返回 `share_auth_ok` 或 close 4001/4013。
    func connect() {
        guard task == nil else { return } // 已连不重复
        let url = AppConfig.wsBaseURL
            .appendingPathComponent("api")
            .appendingPathComponent(AppConfig.apiVersion)
            .appendingPathComponent("ws/share")
            .appendingPathComponent(shareToken)
        let task = session.webSocketTask(with: url)
        self.task = task
        task.resume()
        sendShareAuth()
        receiveLoop()
    }

    /// 主动关闭（视图退出 / 用户关闭）。
    func disconnect() {
        stopPingTimer()
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        isConnected = false
    }

    // MARK: - Heartbeat (S2-INT-006-FOLLOWUP)

    /// 在 share_auth_ok 后启动；scheduleTimer 必须在 @MainActor 的 RunLoop 上跑。
    private func startPingTimer() {
        stopPingTimer()
        pingTimer = Timer.scheduledTimer(
            withTimeInterval: pingInterval,
            repeats: true
        ) { [weak self] _ in
            // Timer 回调跑在 main RunLoop；显式 hop 回 MainActor 满足并发隔离。
            Task { @MainActor [weak self] in
                self?.sendPing()
            }
        }
    }

    private func stopPingTimer() {
        pingTimer?.invalidate()
        pingTimer = nil
    }

    private func sendPing() {
        guard let task else { return }
        task.sendPing { [weak self] err in
            guard let self else { return }
            if let err {
                // 刻晴 fix #2: disconnect 会触发 sendPing callback 以 URLError.cancelled
                // 失败。这类主动取消不算锁列上报 onClose。
                let nsErr = err as NSError
                if nsErr.domain == NSURLErrorDomain, nsErr.code == NSURLErrorCancelled {
                    return
                }
                Task { @MainActor [weak self] in
                    // 刻晴 fix #1: 先 stopPingTimer 再 onClose。
                    // 避免 onClose 回调中调 disconnect 老 timer 仍在跳 ping。
                    self?.stopPingTimer()
                    self?.onClose?(-1, "ping_failed: \(err.localizedDescription)")
                }
            }
        }
    }

    // MARK: - send (auth only, 不发业务帧)

    private func sendShareAuth() {
        let payload: [String: Any] = [
            "type": "share_auth",
            "session": shareSession,
        ]
        guard let data = try? JSONSerialization.data(withJSONObject: payload),
              let str = String(data: data, encoding: .utf8) else { return }
        task?.send(.string(str)) { [weak self] err in
            if let err {
                // 刻晴 fix #2: disconnect 会触发 send callback 以 URLError.cancelled
                // 失败。这类主动取消不算鉴权失败上报 onClose。
                let nsErr = err as NSError
                if nsErr.domain == NSURLErrorDomain, nsErr.code == NSURLErrorCancelled {
                    return
                }
                Task { @MainActor [weak self] in
                    self?.onClose?(-1, "send_auth_failed: \(err.localizedDescription)")
                }
            }
        }
    }

    // MARK: - receive loop

    private func receiveLoop() {
        task?.receive { [weak self] result in
            Task { @MainActor [weak self] in
                guard let self else { return }
                switch result {
                case .failure(let err):
                    let nsErr = err as NSError
                    if nsErr.domain == NSURLErrorDomain, nsErr.code == NSURLErrorCancelled {
                        return
                    }
                    self.onClose?(nsErr.code, "recv_failed: \(err.localizedDescription)")
                    return
                case .success(let message):
                    self.handleMessage(message)
                    self.receiveLoop()
                }
            }
        }
    }

    private func handleMessage(_ message: URLSessionWebSocketTask.Message) {
        switch message {
        case .string(let s):
            guard let data = s.data(using: .utf8) else { return }
            decodeAndDispatch(data)
        case .data(let d):
            decodeAndDispatch(d)
        @unknown default:
            // 防协议漂移：Swift 引入新 WS message kind 不静默丢帧，上报供调用方决策。
            onClose?(-1, "unknown_message_kind")
        }
    }

    private func decodeAndDispatch(_ data: Data) {
        guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return
        }
        let type = (obj["type"] as? String) ?? ""
        switch type {
        case "share_auth_ok":
            isConnected = true
            startPingTimer()
            onAuthOK?()
        case "share_auth_err":
            // 服务端鉴权失败（无效 JWT / token mismatch / revoke 等），将被 server close
            onClose?(4001, (obj["reason"] as? String) ?? "share_auth_err")
        default:
            onEvent?(obj)
        }
    }
}
