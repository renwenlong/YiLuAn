import Foundation
import Combine

enum WSMessage {
    case text(String)
    case data(Data)
}

/// WebSocket 客户端，支持 chat 单订单流（query token，legacy）和全局通知流（first-frame auth handshake）。
/// - chat   : `/ws/chat/{orderId}?token=...`
/// - notif  : `/ws/notifications`，连上后立即发送 `{type:"auth", token:"..."}`，等待 `{type:"auth_ok"}`
actor WebSocketClient {
    private var webSocketTask: URLSessionWebSocketTask?
    private let session: URLSession
    private var retryCount = 0
    private let maxRetries = 5

    private var currentURL: URL?
    private var pendingAuthPayload: String?  // 非 nil 表示需要 first-frame auth

    private let messageSubject = PassthroughSubject<WSMessage, Never>()
    private let connectionSubject = CurrentValueSubject<Bool, Never>(false)

    nonisolated var messages: AnyPublisher<WSMessage, Never> {
        messageSubject.eraseToAnyPublisher()
    }

    nonisolated var isConnected: AnyPublisher<Bool, Never> {
        connectionSubject.eraseToAnyPublisher()
    }

    init() {
        self.session = URLSession(configuration: .default)
    }

    // MARK: - Chat (legacy query-token)

    func connect(orderId: String) {
        guard let token = KeychainManager.accessToken else { return }

        var components = URLComponents(
            url: AppConfig.wsBaseURL.appendingPathComponent("ws/chat/\(orderId)"),
            resolvingAgainstBaseURL: false
        )!
        components.queryItems = [URLQueryItem(name: "token", value: token)]

        guard let url = components.url else { return }

        currentURL = url
        pendingAuthPayload = nil
        openTask(url: url)
    }

    // MARK: - Notifications (first-frame auth handshake)

    /// 连接全局通知 WS。鉴权走 first-frame：`{"type":"auth","token":"<jwt>"}`，
    /// 服务端验证通过会回 `{"type":"auth_ok"}` —— 与 wechat services/notificationWs.js 对齐。
    func connectNotifications() {
        guard let token = KeychainManager.accessToken else { return }

        let url = AppConfig.wsBaseURL.appendingPathComponent("ws/notifications")
        currentURL = url
        // 序列化一次，连上后第一帧发出去
        let payload: [String: String] = ["type": "auth", "token": token]
        if let data = try? JSONSerialization.data(withJSONObject: payload),
           let str = String(data: data, encoding: .utf8) {
            pendingAuthPayload = str
        } else {
            pendingAuthPayload = nil
        }
        openTask(url: url)
    }

    func disconnect() {
        webSocketTask?.cancel(with: .normalClosure, reason: nil)
        webSocketTask = nil
        currentURL = nil
        pendingAuthPayload = nil
        connectionSubject.send(false)
        retryCount = 0
    }

    func send(text: String) async throws {
        guard let task = webSocketTask else { return }
        try await task.send(.string(text))
    }

    // MARK: - Private

    private func openTask(url: URL) {
        webSocketTask = session.webSocketTask(with: url)
        webSocketTask?.resume()
        connectionSubject.send(true)
        retryCount = 0
        // first-frame auth
        if let payload = pendingAuthPayload, let task = webSocketTask {
            Task {
                try? await task.send(.string(payload))
            }
        }
        receiveMessage()
    }

    private func receiveMessage() {
        webSocketTask?.receive { [weak self] result in
            guard let self else { return }
            switch result {
            case .success(let message):
                switch message {
                case .string(let text):
                    self.messageSubject.send(.text(text))
                case .data(let data):
                    self.messageSubject.send(.data(data))
                @unknown default:
                    break
                }
                Task { await self.receiveMessage() }
            case .failure:
                self.connectionSubject.send(false)
                Task { await self.reconnect() }
            }
        }
    }

    private func reconnect() async {
        guard retryCount < maxRetries, let url = currentURL else { return }
        retryCount += 1
        let delay = UInt64(pow(2.0, Double(retryCount))) * 1_000_000_000
        try? await Task.sleep(nanoseconds: delay)
        // 自动恢复：用上次 URL + auth payload 重连（对 notifications 关键，chat 调用方也可继续观察 isConnected）。
        openTask(url: url)
    }
}
