import SwiftUI

struct TodayOrdersView: View {
    @StateObject private var viewModel = OrderViewModel()

    private var todayOrders: [Order] {
        let today = ISO8601DateFormatter().string(from: Date()).prefix(10)
        return viewModel.orders.filter { order in
            order.appointmentDate.hasPrefix(String(today))
        }
    }

    private var inProgressOrders: [Order] {
        todayOrders.filter { $0.status == .inProgress }
    }

    private var acceptedOrders: [Order] {
        todayOrders.filter { $0.status == .accepted }
    }

    var body: some View {
        List {
            if !inProgressOrders.isEmpty {
                Section("进行中") {
                    ForEach(inProgressOrders) { order in
                        NavigationLink(destination: OrderDetailView(orderId: order.id, isCompanion: true)) {
                            OrderRowView(order: order)
                        }
                    }
                }
            }

            if !acceptedOrders.isEmpty {
                Section("已接单") {
                    ForEach(acceptedOrders) { order in
                        NavigationLink(destination: OrderDetailView(orderId: order.id, isCompanion: true)) {
                            OrderRowView(order: order)
                        }
                    }
                }
            }
        }
        .overlay {
            if !viewModel.isLoading && todayOrders.isEmpty {
                ContentUnavailableView("今日暂无订单", systemImage: "calendar.badge.exclamationmark")
            }
        }
        .navigationTitle("今日订单")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await viewModel.loadOrders(status: "accepted")
            let inProgress = viewModel.orders
            await viewModel.loadOrders(status: "in_progress")
            viewModel.orders.append(contentsOf: inProgress)
        }
        .refreshable {
            await viewModel.loadOrders(status: "accepted")
            let accepted = viewModel.orders
            await viewModel.loadOrders(status: "in_progress")
            viewModel.orders.append(contentsOf: accepted)
        }
    }
}

#Preview {
    NavigationStack {
        TodayOrdersView()
    }
}
