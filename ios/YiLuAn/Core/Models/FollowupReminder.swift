import Foundation

/// [F-07] 复诊提醒。
/// backend：`/orders/{id}/followup-reminders`、`/orders/me/followup-reminders`
struct FollowupReminder: Codable, Identifiable, Hashable {
    let id: String
    let userId: String?
    let orderId: String
    let remindAt: Date
    let status: String  // pending | sent | cancelled | failed
    let attempts: Int
    let note: String?
    let sentAt: Date?
    let createdAt: Date?
}

struct FollowupReminderListResponse: Decodable {
    let items: [FollowupReminder]
    let total: Int
}

struct CreateFollowupReminderRequest: Encodable {
    let orderId: String
    let remindAt: Date
    let note: String?
}

extension FollowupReminder {
    var statusLabel: String {
        switch status {
        case "pending":   return "待提醒"
        case "sent":      return "已发送"
        case "cancelled": return "已取消"
        case "failed":    return "发送失败"
        default:          return status
        }
    }

    var canCancel: Bool { status == "pending" }
}
