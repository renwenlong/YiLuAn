import Foundation

/// Precheck WebSocket 客户端 — 4 信任卡实时推送
///
/// **S3-DEV-003-TRUST-UI-IOS (方案 B canonical)**
///
/// 端点: `/ws/v1/orders/{order_id}/precheck` (注意 path 含 `/v1/`)
/// 后端: `backend/app/api/v1/ws.py:580`
///
/// 协议:
/// - First frame auth: `{type:"auth", token:"<jwt>"}` → 服务端回 `{type:"auth_ok"}`
/// - Ping/pong 心跳: `{type:"ping"}` → `{type:"pong"}` (30s 间隔, 抵抗 NAT 静默回收)
/// - 服务端推 3 类 event: `precheck.status.updated` / `precheck.all_ready` / `precheck.blocked`
/// - 任何非 ping 上行帧 → 服务端 close 4012 (read-only stream)
///
/// Close codes (后端 `_authenticate` + handler):
/// - 4001: 鉴权失败 / token 无效 / user 不存在
/// - 4002: idle_timeout (服务端 5min 无心跳)
/// - 4003: not_owner (ABAC Layer 2.5)
/// - 4004: order_not_found
/// - 4011: auth_timeout / invalid_auth_frame
/// - 4012: upstream_write_forbidden (我们违反 read-only)
///
/// 重连策略:
/// - 4001/4003/4004/4011: 永久失败, 不重连 (调用方应跳回登录或 OrderDetailView)
/// - 4002/4012/网络抖动: 调用方按需重连 (本类不内置 — 避免 revoke 死循环, 参考 ShareWebSocket)
/// - polling fallback: 调用方在 WS 断开时切到 30s HTTP polling (PRD-003 v0.4 §S3-REQ-003)
///
/// **设计借鉴**: 与 `Features/Share/Services/ShareWebSocket.swift` 同模式
/// (first-frame auth + ping timer + 不内置重连), 而非
/// `Core/Networking/WebSocketClient.swift` actor 模式 (那个走自动重连 5 次, 对 precheck 场景过于激进).
@MainActor
final class PrecheckWebSocket {

    // MARK: - Public callbacks

    /// 收到 3 个 precheck event 之一 (status.updated / all_ready / blocked).
    /// ViewModel 应当**重新 GET HTTP** 拿最新 summary (WS 仅是 invalidate 信号).
    var onEvent: ((PrecheckWSEvent) -> Void)?

    /// WS 关闭. 调用方根据 code 决定重连 / fallback polling.
    var onClose: ((Int, String) -> Void)?

    /// 鉴权成功 (收到 `{type:"auth_ok"}`).
    var onAuthOK: (() -> Void)?

    // MARK: - Inputs

    let orderId: String

    // MARK: - Internal

    private var task: URLSessionWebSocketTask?
    private let session: URLSession
    private var isConnected: Bool = false
    private let pingInterval: TimeInterval
    private var pingTimer: Timer?

    init(
        orderId: String,
        urlSession: URLSession = .shared,
        pingInterval: TimeInterval = 30
    ) {
        self.orderId = orderId
        self.session = urlSession
        self.pingInterval = pingInterval
    }

    // MARK: - Lifecycle

    /// 建立连接 + 发 first-frame auth.
    func connect() {
        guard task == nil else { return }  // 已连不重复
        guard let token = KeychainManager.accessToken else {
            onClose?(4001, "missing_access_token")
            return
        }

        // path: /ws/v1/orders/{order_id}/precheck
        // baseURL: ws://localhost:8000 (dev) 或 wss://api.yiluan.app (prod)
        let url = AppConfig.wsBaseURL
            .appendingPathComponent("ws")
            .appendingPathComponent("v1")
            .appendingPathComponent("orders")
            .appendingPathComponent(orderId)
            .appendingPathComponent("precheck")

        let task = session.webSocketTask(with: url)
        self.task = task
        task.resume()
        sendAuth(token: token)
        receiveLoop()
    }

    /// 主动关闭 (视图退出 / 用户关闭).
    func disconnect() {
        stopPingTimer()
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        isConnected = false
    }

    // MARK: - Heartbeat

    /// 在 auth_ok 后启动. NAT 中间设备 60s~5min 静默回收 idle 连接, 30s ping 安全裕度足.
    private func startPingTimer() {
        stopPingTimer()
        pingTimer = Timer.scheduledTimer(
            withTimeInterval: pingInterval,
            repeats: true
        ) { [weak self] _ in
            Task { @MainActor [weak self] in
                self?.sendPing()
            }
        }
    }

    private func stopPingTimer() {
        pingTimer?.invalidate()
        pingTimer = nil
    }

    /// 走应用层 ping (后端 expect `{type:"ping"}` JSON 帧, 不是 WS protocol-level ping).
    private func sendPing() {
        guard let task else { return }
        let payload: [String: String] = ["type": "ping"]
        guard let data = try? JSONSerialization.data(withJSONObject: payload),
              let str = String(data: data, encoding: .utf8) else { return }
        task.send(.string(str)) { [weak self] err in
            guard let self else { return }
            if let err {
                let nsErr = err as NSError
                // disconnect() 触发的 cancel 不上报
                if nsErr.domain == NSURLErrorDomain, nsErr.code == NSURLErrorCancelled {
                    return
                }
                Task { @MainActor [weak self] in
                    self?.stopPingTimer()
                    self?.onClose?(-1, "ping_failed: \(err.localizedDescription)")
                }
            }
        }
    }

    // MARK: - send (auth only)

    /// First-frame auth — 与后端 `_authenticate(channel="precheck")` 对齐.
    private func sendAuth(token: String) {
        let payload: [String: String] = ["type": "auth", "token": token]
        guard let data = try? JSONSerialization.data(withJSONObject: payload),
              let str = String(data: data, encoding: .utf8) else { return }
        task?.send(.string(str)) { [weak self] err in
            if let err {
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
                        return  // disconnect() 触发的 cancel, 不上报
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
            // 防协议漂移: 不静默丢帧.
            onClose?(-1, "unknown_message_kind")
        }
    }

    private func decodeAndDispatch(_ data: Data) {
        guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return
        }

        // auth_ok 是 sentinel, 启动 ping timer
        if (obj["type"] as? String) == "auth_ok" {
            isConnected = true
            startPingTimer()
            onAuthOK?()
            return
        }

        // pong 是心跳 ack, 静默吃掉
        if (obj["type"] as? String) == "pong" {
            return
        }

        // 3 个 precheck event 之一
        // 后端 `precheck_broadcast.py:111/125/141` 用 `event` 字段携带类型 (不是 `type` 字段)
        if let eventStr = obj["event"] as? String,
           let event = PrecheckEventType(rawValue: eventStr) {
            onEvent?(PrecheckWSEvent(event: event, rawPayload: obj))
        }
        // 未知 event type 静默丢弃 (forward-compat: 后端加新 event 不应 crash 旧 client)
    }
}
