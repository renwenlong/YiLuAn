import Foundation

enum MessageType: String, Codable {
    case text
    case image
    case system
}

struct ChatMessage: Codable, Identifiable {
    let id: String
    let orderId: String
    let senderId: String
    let type: MessageType
    let content: String
    let isRead: Bool
    let createdAt: Date
}
