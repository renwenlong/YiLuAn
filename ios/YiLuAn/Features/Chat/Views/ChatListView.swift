import SwiftUI

struct ChatListView: View {
    @EnvironmentObject var authViewModel: AuthViewModel
    @StateObject private var viewModel = OrderViewModel()

    private var chatOrders: [Order] {
        viewModel.orders.filter {
            $0.status == .accepted || $0.status == .inProgress || $0.status == .completed
        }
    }

    var body: some View {
        NavigationStack {
            Group {
                if viewModel.isLoading && viewModel.orders.isEmpty {
                    ProgressView()
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if chatOrders.isEmpty {
                    ContentUnavailableView("暂无消息", systemImage: "message.fill")
                } else {
                    List(chatOrders) { order in
                        NavigationLink {
                            ChatRoomView(
                                orderId: order.id,
                                currentUserId: authViewModel.currentUser?.id ?? ""
                            )
                        } label: {
                            chatRow(order)
                        }
                    }
                    .listStyle(.plain)
                    .refreshable {
                        await viewModel.loadOrders()
                    }
                }
            }
            .navigationTitle("消息")
            .task {
                await viewModel.loadOrders()
            }
        }
    }

    private func chatRow(_ order: Order) -> some View {
        HStack(spacing: 12) {
            Image(systemName: "message.circle.fill")
                .font(.system(size: 40))
                .foregroundStyle(.blue)

            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(order.hospitalName ?? "未知医院")
                        .font(.headline)
                        .lineLimit(1)
                    Spacer()
                    Text(order.status.displayName)
                        .font(.caption)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 2)
                        .background(statusColor(order.status).opacity(0.1))
                        .foregroundStyle(statusColor(order.status))
                        .cornerRadius(4)
                }

                let isPatient = authViewModel.currentUser?.role == .patient
                let contactName = isPatient
                    ? (order.companionName ?? "待分配")
                    : (order.patientName ?? "未知患者")
                Text(contactName)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
        }
        .padding(.vertical, 4)
    }

    private func statusColor(_ status: OrderStatus) -> Color {
        switch status {
        case .accepted: return .blue
        case .inProgress: return .orange
        case .completed: return .green
        default: return .secondary
        }
    }
}

#Preview {
    ChatListView()
        .environmentObject(AuthViewModel())
}
