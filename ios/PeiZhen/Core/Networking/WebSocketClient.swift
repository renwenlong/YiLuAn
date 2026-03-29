import Foundation
import Combine

enum WSMessage {
    case text(String)
    case data(Data)
}

actor WebSocketClient {
    private var webSocketTask: URLSessionWebSocketTask?
    private let session: URLSession
    private var retryCount = 0
    private let maxRetries = 5

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

    func connect(orderId: String) {
        guard let token = KeychainManager.accessToken else { return }

        var components = URLComponents(
            url: AppConfig.wsBaseURL.appendingPathComponent("ws/chat/\(orderId)"),
            resolvingAgainstBaseURL: false
        )!
        components.queryItems = [URLQueryItem(name: "token", value: token)]

        guard let url = components.url else { return }

        webSocketTask = session.webSocketTask(with: url)
        webSocketTask?.resume()
        connectionSubject.send(true)
        retryCount = 0
        receiveMessage()
    }

    func disconnect() {
        webSocketTask?.cancel(with: .normalClosure, reason: nil)
        webSocketTask = nil
        connectionSubject.send(false)
        retryCount = 0
    }

    func send(text: String) async throws {
        guard let task = webSocketTask else { return }
        try await task.send(.string(text))
    }

    // MARK: - Private

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
        guard retryCount < maxRetries else { return }
        retryCount += 1
        let delay = UInt64(pow(2.0, Double(retryCount))) * 1_000_000_000
        try? await Task.sleep(nanoseconds: delay)
        // Reconnection requires the orderId — caller should observe isConnected and call connect() again
    }
}
