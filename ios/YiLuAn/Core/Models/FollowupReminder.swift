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
        let loc = LocalizationManager.shared
        switch status {
        case "pending":   return loc.t("followupReminders.statusPending")
        case "sent":      return loc.t("followupReminders.statusSent")
        case "cancelled": return loc.t("followupReminders.statusCancelled")
        case "failed":    return loc.t("followupReminders.statusFailed")
        default:          return status
        }
    }

    var canCancel: Bool { status == "pending" }
}
