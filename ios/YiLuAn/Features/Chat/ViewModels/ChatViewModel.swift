import SwiftUI
import Combine

struct SendMessageRequest: Encodable {
    let content: String
    let type: String
}

struct ChatMessageListResponse: Decodable {
    let items: [ChatMessage]
    let total: Int
}

struct MarkReadResponse: Decodable {
    let markedRead: Int
}

@MainActor
class ChatViewModel: ObservableObject {
    @Published var messages: [ChatMessage] = []
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var total = 0

    private let wsClient = WebSocketClient()
    private var cancellables = Set<AnyCancellable>()

    init() {
        setupWebSocket()
    }

    func loadMessages(orderId: String) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let response: ChatMessageListResponse = try await APIClient.shared.request(
                .chatMessages(orderId: orderId)
            )
            messages = response.items
            total = response.total
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func sendMessage(orderId: String, content: String, type: String = "text") async {
        errorMessage = nil

        do {
            let body = SendMessageRequest(content: content, type: type)
            let message: ChatMessage = try await APIClient.shared.request(
                .sendChatMessage(orderId: orderId), body: body
            )
            messages.append(message)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func markRead(orderId: String) async {
        do {
            let _: MarkReadResponse = try await APIClient.shared.request(
                .markChatRead(orderId: orderId)
            )
        } catch {
            // Silently ignore mark-read failures
        }
    }

    func connectWebSocket(orderId: String) async {
        await wsClient.connect(orderId: orderId)
    }

    func disconnectWebSocket() async {
        await wsClient.disconnect()
    }

    private func setupWebSocket() {
        wsClient.messages
            .receive(on: DispatchQueue.main)
            .sink { [weak self] wsMessage in
                guard let self else { return }
                if case .text(let text) = wsMessage,
                   let data = text.data(using: .utf8) {
                    let decoder = JSONDecoder()
                    decoder.keyDecodingStrategy = .convertFromSnakeCase
                    decoder.dateDecodingStrategy = .iso8601
                    if let message = try? decoder.decode(ChatMessage.self, from: data) {
                        self.messages.append(message)
                    }
                }
            }
            .store(in: &cancellables)
    }
}
