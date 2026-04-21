import SwiftUI

struct OrderDetailView: View {
    let orderId: String
    let isCompanion: Bool

    @StateObject private var viewModel = OrderViewModel()
    @State private var showCancelAlert = false
    @State private var showActionAlert = false
    @State private var pendingAction = ""
    @State private var paymentResult: PaymentStatus?
    @State private var paymentErrorMessage: String?
    @State private var showPaymentResult = false

    var body: some View {
        Group {
            if viewModel.isLoading && viewModel.currentOrder == nil {
                ProgressView()
            } else if let order = viewModel.currentOrder {
                ScrollView {
                    VStack(spacing: 16) {
                        // Status header
                        statusHeader(order)

                        // Order info card
                        orderInfoCard(order)

                        // Action buttons
                        actionButtons(order)
                    }
                    .padding()
                }
            } else {
                Text("订单不存在")
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("订单详情")
        .navigationBarTitleDisplayMode(.inline)
        .task { await viewModel.loadOrder(id: orderId) }
        .alert("确认取消", isPresented: $showCancelAlert) {
            Button("取消", role: .cancel) {}
            Button("确认取消", role: .destructive) {
                Task { await performAction("cancel") }
            }
        } message: {
            Text("确定要取消该订单吗？")
        }
        .alert("确认操作", isPresented: $showActionAlert) {
            Button("取消", role: .cancel) {}
            Button("确认") {
                Task { await performAction(pendingAction) }
            }
        } message: {
            Text(actionMessage)
        }
        .sheet(isPresented: $showPaymentResult) {
            if let result = paymentResult {
                NavigationStack {
                    PaymentResultView(
                        status: result,
                        orderId: orderId,
                        errorMessage: paymentErrorMessage
                    )
                }
            }
        }
        // 统一挂载后端 guard-code 提示。
        .phoneRequiredAlert($viewModel.phoneRequiredMessage)
        .paymentRequiredAlert($viewModel.paymentRequiredMessage)
        .verificationRequiredAlert($viewModel.verificationRequiredMessage)
    }

    private func statusHeader(_ order: Order) -> some View {
        HStack {
            VStack(alignment: .leading) {
                Text(order.status.displayName)
                    .font(.title2.bold())
                Text(order.orderNumber)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(12)
    }

    private func orderInfoCard(_ order: Order) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            infoRow("服务类型", order.serviceType.displayName)
            infoRow("医院", order.hospitalName ?? "未知")
            infoRow("预约日期", order.appointmentDate)
            if let time = order.appointmentTime {
                infoRow("预约时间", time)
            }
            infoRow("费用", "¥\(order.price as NSDecimalNumber)")
            if let desc = order.description, !desc.isEmpty {
                infoRow("备注", desc)
            }
            if let companionName = order.companionName {
                infoRow("陪诊师", companionName)
            }
            if let patientName = order.patientName {
                infoRow("患者", patientName)
            }
        }
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(12)
    }

    private func infoRow(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label)
                .foregroundStyle(.secondary)
                .frame(width: 80, alignment: .leading)
            Text(value)
            Spacer()
        }
        .font(.subheadline)
    }

    @ViewBuilder
    private func actionButtons(_ order: Order) -> some View {
        if isCompanion {
            companionActions(order)
        } else {
            patientActions(order)
        }
    }

    @ViewBuilder
    private func patientActions(_ order: Order) -> some View {
        VStack(spacing: 12) {
            if order.status == .created || order.status == .accepted {
                Button(role: .destructive) {
                    showCancelAlert = true
                } label: {
                    Text("取消订单")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
            }

            if order.status == .created {
                Button {
                    Task {
                        if let _ = await viewModel.payOrder(id: order.id) {
                            paymentResult = .success
                        } else {
                            paymentResult = .fail
                            paymentErrorMessage = viewModel.errorMessage
                        }
                        showPaymentResult = true
                    }
                } label: {
                    Text("立即支付")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
            }
        }
    }

    @ViewBuilder
    private func companionActions(_ order: Order) -> some View {
        VStack(spacing: 12) {
            if order.status == .created {
                Button {
                    pendingAction = "accept"
                    showActionAlert = true
                } label: {
                    Text("接受订单")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)

                Button(role: .destructive) {
                    pendingAction = "reject"
                    showActionAlert = true
                } label: {
                    Text("拒绝订单")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
            }

            if order.status == .accepted {
                Button {
                    pendingAction = "start"
                    showActionAlert = true
                } label: {
                    Text("直接开始服务")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)

                Button {
                    pendingAction = "request-start"
                    showActionAlert = true
                } label: {
                    Text("请求患者确认开始")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
            }

            if order.status == .inProgress {
                Button {
                    pendingAction = "complete"
                    showActionAlert = true
                } label: {
                    Text("完成服务")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
            }
        }
    }

    private func performAction(_ action: String) async {
        let success = await viewModel.performAction(action, orderId: orderId)
        if success {
            await viewModel.loadOrder(id: orderId)
        }
    }

    private var actionMessage: String {
        switch pendingAction {
        case "accept": return "确定要接受该订单吗？"
        case "reject": return "确定要拒绝该订单吗？拒绝后系统将自动退款给患者。"
        case "start": return "确认开始为患者提供陪诊服务？"
        case "request-start": return "向患者发送开始服务的确认请求？"
        case "complete": return "确认已完成本次陪诊服务？"
        default: return "确认操作？"
        }
    }
}
