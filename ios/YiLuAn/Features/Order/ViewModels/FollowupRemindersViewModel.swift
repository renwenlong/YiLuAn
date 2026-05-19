import Foundation
import SwiftUI

/// [F-07] 复诊提醒 ViewModel — 列表 / 创建 / 取消。
@MainActor
final class FollowupRemindersViewModel: ObservableObject {
    @Published var reminders: [FollowupReminder] = []
    @Published var isLoading = false
    @Published var errorMessage: String?

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            reminders = try await FollowupReminderService.list()
        } catch {
            errorMessage = (error as? LocalizedError)?.errorDescription ?? "加载失败"
        }
    }

    func cancel(_ r: FollowupReminder) async {
        do {
            try await FollowupReminderService.cancel(id: r.id)
            await load()
        } catch {
            errorMessage = (error as? LocalizedError)?.errorDescription ?? "取消失败"
        }
    }

    func create(orderId: String, remindAt: Date, note: String?) async -> Bool {
        do {
            _ = try await FollowupReminderService.create(orderId: orderId, remindAt: remindAt, note: note)
            await load()
            return true
        } catch {
            errorMessage = (error as? LocalizedError)?.errorDescription ?? "创建失败"
            return false
        }
    }
}
