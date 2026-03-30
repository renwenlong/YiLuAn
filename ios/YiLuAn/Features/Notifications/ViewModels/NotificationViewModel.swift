import SwiftUI

struct NotificationListResponse: Decodable {
    let items: [AppNotification]
    let total: Int
}

struct UnreadCountResponse: Decodable {
    let count: Int
}

struct MarkNotificationResponse: Decodable {
    let success: Bool
}

struct MarkAllReadResponse: Decodable {
    let markedRead: Int
}

struct RegisterDeviceRequest: Encodable {
    let token: String
    let deviceType: String

    enum CodingKeys: String, CodingKey {
        case token
        case deviceType = "device_type"
    }
}

struct DeviceTokenResponse: Decodable {
    let id: String
    let token: String
    let deviceType: String
    let createdAt: String
}

struct UnregisterDeviceRequest: Encodable {
    let token: String
}

@MainActor
class NotificationViewModel: ObservableObject {
    @Published var notifications: [AppNotification] = []
    @Published var unreadCount = 0
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var total = 0

    func loadNotifications(page: Int = 1) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let response: NotificationListResponse = try await APIClient.shared.request(
                .notifications,
                queryItems: [URLQueryItem(name: "page", value: "\(page)")]
            )
            if page == 1 {
                notifications = response.items
            } else {
                notifications.append(contentsOf: response.items)
            }
            total = response.total
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func loadUnreadCount() async {
        do {
            let response: UnreadCountResponse = try await APIClient.shared.request(.unreadCount)
            unreadCount = response.count
        } catch {
            // Silently ignore count failures
        }
    }

    func markRead(notificationId: String) async {
        do {
            let _: MarkNotificationResponse = try await APIClient.shared.request(
                .markNotificationRead(id: notificationId)
            )
            if let index = notifications.firstIndex(where: { $0.id == notificationId }) {
                // Create updated copy with isRead = true
                let old = notifications[index]
                let updated = AppNotification(
                    id: old.id, userId: old.userId, type: old.type,
                    title: old.title, body: old.body,
                    referenceId: old.referenceId, isRead: true,
                    createdAt: old.createdAt
                )
                notifications[index] = updated
                unreadCount = max(0, unreadCount - 1)
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func markAllRead() async {
        do {
            let _: MarkAllReadResponse = try await APIClient.shared.request(
                .markAllNotificationsRead
            )
            notifications = notifications.map { n in
                AppNotification(
                    id: n.id, userId: n.userId, type: n.type,
                    title: n.title, body: n.body,
                    referenceId: n.referenceId, isRead: true,
                    createdAt: n.createdAt
                )
            }
            unreadCount = 0
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func registerDeviceToken(_ token: String, deviceType: String = "ios") async {
        do {
            let body = RegisterDeviceRequest(token: token, deviceType: deviceType)
            let _: DeviceTokenResponse = try await APIClient.shared.request(
                .registerDevice, body: body
            )
        } catch {
            // Silently ignore device registration failures
        }
    }

    func deleteDeviceToken(_ token: String) async {
        do {
            let body = UnregisterDeviceRequest(token: token)
            let _: [String: Bool] = try await APIClient.shared.request(
                .deleteDevice, body: body
            )
        } catch {
            // Silently ignore device deletion failures
        }
    }
}
