import SwiftUI
import Combine

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

    // [F-WS] 全局通知 WS（与 wechat services/notificationWs.js 对齐）。
    // Chat 以外的唯一 WS 消费者；服务端 push 新通知后马上同步到 UI。
    private let wsClient = WebSocketClient()
    private var cancellables = Set<AnyCancellable>()

    init() {
        wsClient.messages
            .receive(on: DispatchQueue.main)
            .sink { [weak self] msg in
                guard let self else { return }
                self.handleWSMessage(msg)
            }
            .store(in: &cancellables)
    }

    /// 在 取到 token 后（登录成功 / 启动时）可调用。可重复调用。
    func startWebSocket() {
        Task { await wsClient.connectNotifications() }
    }

    func stopWebSocket() {
        Task { await wsClient.disconnect() }
    }

    /// WS 帧 -> 动作：与 wechat handleNotificationMessage 一致。
    /// 后端会 push 两种 payload：
    ///   - 完整 AppNotification（含 id/type/title/body） -> insert
    ///   - 类型控制帧（如 unread_count_changed） -> 变更 unreadCount
    private func handleWSMessage(_ msg: WSMessage) {
        guard case .text(let text) = msg, let data = text.data(using: .utf8) else { return }

        // 探 type 用于控制帧
        if let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let type = obj["type"] as? String {
            switch type {
            case "auth_ok":
                return // handshake 确认
            case "unread_count_changed":
                if let n = obj["count"] as? Int { unreadCount = n }
                return
            default:
                break
            }
        }

        // 完整 AppNotification
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        if let n = try? decoder.decode(AppNotification.self, from: data) {
            // 去重插入到顶部
            if !notifications.contains(where: { $0.id == n.id }) {
                notifications.insert(n, at: 0)
                total += 1
                if !n.isRead { unreadCount += 1 }
            }
        }
    }

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
