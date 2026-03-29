import Foundation

enum NotificationType: String, Codable {
    case orderStatusChanged = "order_status_changed"
    case newMessage = "new_message"
    case newOrder = "new_order"
    case reviewReceived = "review_received"
    case system
}

struct AppNotification: Codable, Identifiable {
    let id: String
    let userId: String
    let type: NotificationType
    let title: String
    let body: String
    let referenceId: String?
    let isRead: Bool
    let createdAt: Date
}
