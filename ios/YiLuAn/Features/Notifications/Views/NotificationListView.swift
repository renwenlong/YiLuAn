import SwiftUI

struct NotificationListView: View {
    @StateObject private var viewModel = NotificationViewModel()

    var body: some View {
        List {
            ForEach(viewModel.notifications) { notification in
                NotificationRowView(notification: notification)
                    .onTapGesture {
                        if !notification.isRead {
                            Task { await viewModel.markRead(notificationId: notification.id) }
                        }
                    }
            }
        }
        .navigationTitle("通知")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                if viewModel.unreadCount > 0 {
                    Button("全部已读") {
                        Task { await viewModel.markAllRead() }
                    }
                }
            }
        }
        .task {
            await viewModel.loadNotifications()
            await viewModel.loadUnreadCount()
        }
        .refreshable {
            await viewModel.loadNotifications()
            await viewModel.loadUnreadCount()
        }
        .overlay {
            if viewModel.notifications.isEmpty && !viewModel.isLoading {
                ContentUnavailableView("暂无通知", systemImage: "bell.slash")
            }
        }
    }
}

struct NotificationRowView: View {
    let notification: AppNotification

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: iconName)
                .foregroundColor(iconColor)
                .frame(width: 32, height: 32)

            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(notification.title)
                        .font(.subheadline)
                        .fontWeight(notification.isRead ? .regular : .semibold)
                    Spacer()
                    if !notification.isRead {
                        Circle()
                            .fill(.red)
                            .frame(width: 8, height: 8)
                    }
                }
                Text(notification.body)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .lineLimit(2)
            }
        }
        .padding(.vertical, 4)
        .opacity(notification.isRead ? 0.7 : 1.0)
    }

    private var iconName: String {
        switch notification.type {
        case .orderStatusChanged: return "arrow.triangle.2.circlepath"
        case .newMessage: return "message"
        case .newOrder: return "doc.badge.plus"
        case .reviewReceived: return "star"
        case .system: return "bell"
        }
    }

    private var iconColor: Color {
        switch notification.type {
        case .orderStatusChanged: return .blue
        case .newMessage: return .green
        case .newOrder: return .orange
        case .reviewReceived: return .yellow
        case .system: return .gray
        }
    }
}
