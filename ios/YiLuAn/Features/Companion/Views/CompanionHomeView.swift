import SwiftUI

struct CompanionHomeView: View {
    @StateObject private var profileViewModel = CompanionProfileViewModel()
    @StateObject private var orderViewModel = OrderViewModel()

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    // Stats summary
                    HStack(spacing: 20) {
                        NavigationLink(destination: TodayOrdersView()) {
                            statCard(
                                title: "今日订单",
                                value: "\(profileViewModel.stats?.todayOrders ?? 0)"
                            )
                        }
                        .buttonStyle(.plain)
                        statCard(
                            title: "评分",
                            value: profileViewModel.stats.map {
                                String(format: "%.1f", $0.avgRating)
                            } ?? "--"
                        )
                        statCard(
                            title: "总订单",
                            value: "\(profileViewModel.stats?.totalOrders ?? 0)"
                        )
                    }
                    .padding(.horizontal)

                    // Recent orders
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Text("我的订单")
                                .font(.headline)
                            Spacer()
                            NavigationLink("查看全部") {
                                OrderListView(isCompanion: true)
                            }
                            .font(.subheadline)
                        }
                        .padding(.horizontal)

                        if orderViewModel.isLoading && orderViewModel.orders.isEmpty {
                            ProgressView()
                                .frame(maxWidth: .infinity, minHeight: 100)
                        } else if orderViewModel.orders.isEmpty {
                            Text("暂无订单")
                                .foregroundStyle(.secondary)
                                .frame(maxWidth: .infinity, minHeight: 100)
                        } else {
                            ForEach(orderViewModel.orders.prefix(5)) { order in
                                NavigationLink(
                                    destination: OrderDetailView(orderId: order.id, isCompanion: true)
                                ) {
                                    OrderRowView(order: order)
                                }
                                .buttonStyle(.plain)
                                .padding(.horizontal)
                            }
                        }
                    }

                    Spacer()
                }
                .padding(.top)
            }
            .navigationTitle("陪诊师工作台")
            .task {
                await profileViewModel.loadStats()
                await orderViewModel.loadOrders()
            }
            .refreshable {
                await profileViewModel.loadStats()
                await orderViewModel.loadOrders()
            }
        }
    }

    private func statCard(title: String, value: String) -> some View {
        VStack(spacing: 4) {
            Text(value)
                .font(.title2.bold())
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(12)
    }
}

#Preview {
    CompanionHomeView()
}
