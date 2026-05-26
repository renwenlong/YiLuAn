import SwiftUI

/// 可接订单顶部筛选（P1-3）。
///
/// 该页面列表固定 status=created（待接单），筛选主要作用于排序。
/// 与后端 `GET /orders?sort=` 对齐：
/// - `time`：预约时间从近到远（默认）
/// - `distance`：就诊医院距离从近到远
/// - `price`：价格从高到低
enum AvailableOrdersSort: String, CaseIterable, Identifiable {
    case time
    case distance
    case price

    var id: String { rawValue }

    var label: String {
        switch self {
        case .time: return "时间"
        case .distance: return "距离"
        case .price: return "价格"
        }
    }
}

/// 陪诊师可接订单列表。
///
/// 与小程序 `wechat/pages/companion/available-orders/index.js` 行为对齐：
/// - 行内「接单」按钮，点击 → 确认弹窗 → `viewModel.performAction("accept", orderId:)`
/// - 未绑手机号时后端返回 `PHONE_REQUIRED`，由 `.phoneRequiredAlert` 统一弹「去绑定」并 push BindPhoneView
/// - 接单成功 → toast + 列表移除该订单；失败 → 走 `viewModel.errorMessage` 错误提示
struct AvailableOrdersView: View {
    @StateObject private var viewModel = OrderViewModel()

    /// 正在 accept 的 order id，UI 上禁用按钮、显示 ProgressView
    @State private var acceptingOrderId: String?
    /// 确认接单弹窗的目标 order id
    @State private var pendingAcceptOrderId: String?
    /// 接单成功 toast
    @State private var showSuccessToast = false
    /// P1-3：当前选中的排序维度
    @State private var sort: AvailableOrdersSort = .time

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // P1-3: 顶部排序筛选条
                Picker("排序", selection: $sort) {
                    ForEach(AvailableOrdersSort.allCases) { option in
                        Text(option.label).tag(option)
                    }
                }
                .pickerStyle(.segmented)
                .padding(.horizontal)
                .padding(.vertical, 8)
                .onChange(of: sort) { _, newValue in
                    Task { await reload(sort: newValue) }
                }

                Group {
                    if viewModel.isLoading && viewModel.orders.isEmpty {
                        ProgressView()
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                    } else if viewModel.orders.isEmpty {
                        ContentUnavailableView("暂无可接订单", systemImage: "tray")
                    } else {
                        List(viewModel.orders) { order in
                            AvailableOrderRow(
                                order: order,
                                isAccepting: acceptingOrderId == order.id,
                                anyAccepting: acceptingOrderId != nil,
                                onAccept: { pendingAcceptOrderId = order.id }
                            )
                        }
                        .listStyle(.plain)
                        .refreshable {
                            await reload(sort: sort)
                        }
                    }
                }
            }
            .navigationTitle("可接订单")
            .task {
                await reload(sort: sort)
            }
            .alert(
                "确认接单",
                isPresented: Binding(
                    get: { pendingAcceptOrderId != nil },
                    set: { if !$0 { pendingAcceptOrderId = nil } }
                ),
                presenting: pendingAcceptOrderId
            ) { orderId in
                Button("取消", role: .cancel) {
                    pendingAcceptOrderId = nil
                }
                Button("确认接单") {
                    Task { await acceptOrder(id: orderId) }
                }
            } message: { _ in
                Text("确定要接受该订单吗？")
            }
            .overlay(alignment: .top) {
                if showSuccessToast {
                    Text("接单成功")
                        .font(.subheadline.bold())
                        .foregroundStyle(.white)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 10)
                        .background(.green.opacity(0.92), in: Capsule())
                        .shadow(radius: 4)
                        .padding(.top, 12)
                        .transition(.move(edge: .top).combined(with: .opacity))
                }
            }
            // 走 OrderViewModel 已有的 PHONE_REQUIRED 路径：后端拒接单时 → 弹「去绑定」→ push BindPhoneView
            .phoneRequiredAlert($viewModel.phoneRequiredMessage)
            .verificationRequiredAlert($viewModel.verificationRequiredMessage)
            .alert(
                "操作失败",
                isPresented: Binding(
                    get: { viewModel.errorMessage != nil },
                    set: { if !$0 { viewModel.errorMessage = nil } }
                ),
                presenting: viewModel.errorMessage
            ) { _ in
                Button("知道了", role: .cancel) { viewModel.errorMessage = nil }
            } message: { msg in
                Text(msg)
            }
        }
    }

    // MARK: - Actions

    private func reload(sort: AvailableOrdersSort) async {
        await viewModel.loadOrders(status: "created", sort: sort.rawValue)
    }

    private func acceptOrder(id: String) async {
        pendingAcceptOrderId = nil
        acceptingOrderId = id
        defer { acceptingOrderId = nil }

        let success = await viewModel.performAction("accept", orderId: id)
        if success {
            // 列表本地移除该单，体验与小程序「接单后 1s 跳详情」一致：iOS 直接从列表移除
            viewModel.orders.removeAll { $0.id == id }
            withAnimation { showSuccessToast = true }
            try? await Task.sleep(nanoseconds: 1_500_000_000)
            withAnimation { showSuccessToast = false }
        }
        // 失败分两类:
        //   1) PHONE_REQUIRED / VERIFICATION_REQUIRED → 由 ViewModel 写入对应 *RequiredMessage，
        //      由 .phoneRequiredAlert / .verificationRequiredAlert 接管。
        //   2) 其他错误 → 写到 errorMessage，由本 view 的 "操作失败" alert 弹出。
    }
}

// MARK: - Row

/// 单条可接订单行：左边订单摘要 + 右边「接单」按钮。
///
/// 按钮使用 `BorderlessButtonStyle`，避免 List Row 整行点击与按钮点击冲突；
/// 行本身仍可点击进入详情。
private struct AvailableOrderRow: View {
    let order: Order
    let isAccepting: Bool
    let anyAccepting: Bool
    let onAccept: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            NavigationLink(
                destination: OrderDetailView(orderId: order.id, isCompanion: true)
            ) {
                OrderRowView(order: order)
            }

            Button(action: onAccept) {
                if isAccepting {
                    ProgressView()
                        .controlSize(.small)
                        .frame(minWidth: 64, minHeight: 36)
                } else {
                    Text("接单")
                        .font(.subheadline.bold())
                        .frame(minWidth: 64, minHeight: 36)
                }
            }
            .buttonStyle(.borderedProminent)
            .tint(.accent)
            .controlSize(.small)
            .disabled(anyAccepting)
        }
        .padding(.vertical, 4)
    }
}

#Preview {
    AvailableOrdersView()
}
