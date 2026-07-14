import SwiftUI

struct ChatListView: View {
    @EnvironmentObject var authViewModel: AuthViewModel
    @EnvironmentObject var loc: LocalizationManager
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
                    ContentUnavailableView(loc.t("chat.noMessage"), systemImage: "message.fill")
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
            .navigationTitle(loc.t("tabBar.chat"))
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
                    Text(order.hospitalName ?? loc.t("chat.unknownHospital"))
                        .font(.headline)
                        .lineLimit(1)
                    Spacer()
                    Text(loc.t("orderStatus." + order.status.rawValue))
                        .font(.caption)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 2)
                        .background(statusColor(order.status).opacity(0.1))
                        .foregroundStyle(statusColor(order.status))
                        .cornerRadius(4)
                }

                let isPatient = authViewModel.currentUser?.role == .patient
                let contactName = isPatient
                    ? (order.companionName ?? loc.t("chat.pendingAssignment"))
                    : (order.patientName ?? loc.t("chat.unknownPatient"))
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
