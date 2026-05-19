import Foundation

/// [F-07] 复诊提醒 Service — backend `/orders/...` 路由。
enum FollowupReminderService {

    /// 为已完成订单创建一条提醒。后端要求 order.status ∈ {completed, reviewed}。
    static func create(orderId: String, remindAt: Date, note: String?) async throws -> FollowupReminder {
        let body = CreateFollowupReminderRequest(orderId: orderId, remindAt: remindAt, note: note)
        return try await APIClient.shared.request(.createFollowupReminder(orderId: orderId), body: body)
    }

    /// 当前用户的全部提醒（按 remind_at 升序）。
    static func list() async throws -> [FollowupReminder] {
        let resp: FollowupReminderListResponse = try await APIClient.shared.request(.myFollowupReminders)
        return resp.items
    }

    /// 取消一条 pending 提醒。
    static func cancel(id: String) async throws {
        try await APIClient.shared.requestVoid(.cancelFollowupReminder(id: id))
    }
}
