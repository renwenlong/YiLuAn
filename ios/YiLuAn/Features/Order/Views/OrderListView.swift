import SwiftUI

struct OrderListView: View {
    @StateObject private var viewModel = OrderViewModel()
    @State private var selectedTab = 0
    let isCompanion: Bool

    private let tabs = ["全部", "待接单", "进行中", "已完成"]
    private let statusMap: [Int: String?] = [
        0: nil,
        1: "created",
        2: "in_progress",
        3: "completed"
    ]

    var body: some View {
        VStack(spacing: 0) {
            // Tab bar
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 16) {
                    ForEach(0..<tabs.count, id: \.self) { index in
                        Button(action: {
                            selectedTab = index
                            Task { await loadOrders() }
                        }) {
                            Text(tabs[index])
                                .font(.subheadline)
                                .fontWeight(selectedTab == index ? .semibold : .regular)
                                .foregroundStyle(selectedTab == index ? .blue : .secondary)
                                .padding(.vertical, 8)
                                .padding(.horizontal, 16)
                                .background(
                                    selectedTab == index
                                        ? Color.blue.opacity(0.1)
                                        : Color.clear
                                )
                                .cornerRadius(16)
                        }
                    }
                }
                .padding(.horizontal)
            }
            .padding(.vertical, 8)

            // Order list
            if viewModel.isLoading && viewModel.orders.isEmpty {
                Spacer()
                ProgressView()
                Spacer()
            } else if viewModel.orders.isEmpty {
                Spacer()
                Text("暂无订单")
                    .foregroundStyle(.secondary)
                Spacer()
            } else {
                List(viewModel.orders) { order in
                    NavigationLink(
                        destination: OrderDetailView(orderId: order.id, isCompanion: isCompanion)
                    ) {
                        OrderRowView(order: order)
                    }
                }
                .listStyle(.plain)
                .refreshable {
                    await loadOrders()
                }
            }
        }
        .navigationTitle(isCompanion ? "我的订单" : "我的订单")
        .task { await loadOrders() }
    }

    private func loadOrders() async {
        await viewModel.loadOrders(status: statusMap[selectedTab] ?? nil)
    }
}

struct OrderRowView: View {
    let order: Order

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(order.orderNumber)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                Text(order.status.displayName)
                    .font(.caption)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 2)
                    .background(statusColor.opacity(0.1))
                    .foregroundStyle(statusColor)
                    .cornerRadius(4)
            }

            Text(order.hospitalName ?? "未知医院")
                .font(.subheadline.bold())

            HStack {
                Text(order.serviceType.displayName)
                    .font(.caption)
                Spacer()
                Text(order.appointmentDate)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if let time = order.appointmentTime {
                    Text(time)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            Text("¥\(order.price as NSDecimalNumber)")
                .font(.subheadline.bold())
                .foregroundStyle(.orange)
        }
        .padding(.vertical, 4)
    }

    private var statusColor: Color {
        switch order.status {
        case .created: return .orange
        case .accepted, .inProgress: return .blue
        case .completed, .reviewed: return .green
        case .cancelledByPatient, .cancelledByCompanion: return .red
        }
    }
}
