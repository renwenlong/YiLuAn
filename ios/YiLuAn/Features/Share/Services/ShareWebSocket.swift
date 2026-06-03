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
final class ShareWebSocket {

    // MARK: - Public callbacks

    /// 收到服务端事件（已 JSON-decode 为 `[String: Any]`）。回调在 task queue 上，
    /// 调用方需切回 `@MainActor`/`DispatchQueue.main` 更新 UI。
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

    init(
        shareToken: String,
        shareSession: String,
        urlSession: URLSession = .shared
    ) {
        self.shareToken = shareToken
        self.shareSession = shareSession
        self.session = urlSession
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
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        isConnected = false
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
                // 鉴权帧发不出去 → 链路断
                self?.onClose?(-1, "send_auth_failed: \(err.localizedDescription)")
            }
        }
    }

    // MARK: - receive loop

    private func receiveLoop() {
        task?.receive { [weak self] result in
            guard let self else { return }
            switch result {
            case .failure(let err):
                let nsErr = err as NSError
                // URLError.cancelled = 主动 disconnect()，不视作异常
                if nsErr.domain == NSURLErrorDomain, nsErr.code == NSURLErrorCancelled {
                    return
                }
                self.onClose?(nsErr.code, "recv_failed: \(err.localizedDescription)")
                return
            case .success(let message):
                self.handleMessage(message)
                self.receiveLoop() // 继续监听下一帧
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
            return
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
            onAuthOK?()
        case "share_auth_err":
            // 服务端鉴权失败（无效 JWT / token mismatch / revoke 等），将被 server close
            onClose?(4001, (obj["reason"] as? String) ?? "share_auth_err")
        default:
            onEvent?(obj)
        }
    }
}
