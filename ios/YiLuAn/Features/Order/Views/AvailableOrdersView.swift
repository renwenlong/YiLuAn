import SwiftUI

struct AvailableOrdersView: View {
    @StateObject private var viewModel = OrderViewModel()

    var body: some View {
        NavigationStack {
            Group {
                if viewModel.isLoading && viewModel.orders.isEmpty {
                    ProgressView()
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if viewModel.orders.isEmpty {
                    ContentUnavailableView("暂无可接订单", systemImage: "tray")
                } else {
                    List(viewModel.orders) { order in
                        NavigationLink(
                            destination: OrderDetailView(orderId: order.id, isCompanion: true)
                        ) {
                            OrderRowView(order: order)
                        }
                    }
                    .listStyle(.plain)
                    .refreshable {
                        await viewModel.loadOrders(status: "created")
                    }
                }
            }
            .navigationTitle("可接订单")
            .task {
                await viewModel.loadOrders(status: "created")
            }
        }
    }
}

#Preview {
    AvailableOrdersView()
}
