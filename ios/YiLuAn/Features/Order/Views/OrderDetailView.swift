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
    /// AI-9: 与小程序 actionLoading 对齐——状态切换期间禁用所有按钮 + 占位
    @State private var actionInProgress = false

    /// AI-9: 命中区 ≥ 44pt（HIG 推荐最小可点尺寸），按钮 frame 用这个常量。
    private let minTapSide: CGFloat = 44

    var body: some View {
        Group {
            if viewModel.isLoading && viewModel.currentOrder == nil {
                // AI-9: 用 redacted(.placeholder) 做骨架，避免首次 ProgressView 白屏
                skeletonContent
                    .redacted(reason: .placeholder)
                    .accessibilityLabel("加载中")
            } else if let order = viewModel.currentOrder {
                ScrollView {
                    VStack(spacing: Spacing.lg) {
                        // Status header
                        statusHeader(order)

                        // Order info card
                        orderInfoCard(order)

                        // Action buttons
                        actionButtons(order)
                    }
                    .padding(Spacing.lg)
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

    // MARK: - AI-9 Skeleton

    /// 与正常布局结构对齐的占位骨架（3-4 行假数据），首次加载时渲染。
    private var skeletonContent: some View {
        ScrollView {
            VStack(spacing: Spacing.lg) {
                // 假状态条
                HStack {
                    VStack(alignment: .leading, spacing: Spacing.xs) {
                        Text("XXXXXXXX")
                            .font(.title2.bold())
                        Text("ORDER-XXXXXXXX-XXXX")
                            .font(.caption)
                    }
                    Spacer()
                }
                .padding(Spacing.lg)
                .frame(maxWidth: .infinity)
                .background(Color(.systemGray6))
                .cornerRadius(CornerRadius.md)

                // 假信息卡
                VStack(alignment: .leading, spacing: Spacing.md) {
                    skeletonRow("服务类型", "陪诊服务 — 全程")
                    skeletonRow("医院", "XX 市第 X 人民医院")
                    skeletonRow("预约日期", "2025-XX-XX")
                    skeletonRow("费用", "¥ XXX.00")
                }
                .padding(Spacing.lg)
                .frame(maxWidth: .infinity)
                .background(Color(.systemGray6))
                .cornerRadius(CornerRadius.md)
            }
            .padding(Spacing.lg)
        }
    }

    private func skeletonRow(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label)
                .foregroundStyle(.secondary)
                .frame(width: 80, alignment: .leading)
            Text(value)
            Spacer()
        }
        .font(.subheadline)
    }

    // MARK: - Sections

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
        .padding(Spacing.lg)
        .background(Color(.systemGray6))
        .cornerRadius(CornerRadius.md)
    }

    private func orderInfoCard(_ order: Order) -> some View {
        VStack(alignment: .leading, spacing: Spacing.md) {
            infoRow("服务类型", order.serviceType.displayName)
            infoRow("医院", order.hospitalName ?? "未知")
            infoRow("预约日期", order.appointmentDate)
            if let time = order.appointmentTime {
                infoRow("预约时间", time)
            }
            infoRow("费用", "¥\(order.price as NSDecimalNumber)", isPrice: true)
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
        .padding(Spacing.lg)
        .background(Color(.systemGray6))
        .cornerRadius(CornerRadius.md)
    }

    private func infoRow(_ label: String, _ value: String, isPrice: Bool = false) -> some View {
        HStack {
            Text(label)
                .foregroundStyle(.secondary)
                .frame(width: 80, alignment: .leading)
            if isPrice {
                // P-02: 金额统一 brand orange + bold + .title2，与微信小程序 .polish-amount 保持一致
                Text(value)
                    .font(.title2.bold())
                    .foregroundColor(.accent)
                    .monospacedDigit()
            } else {
                Text(value)
            }
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
        VStack(spacing: Spacing.md) {
            if order.status == .created || order.status == .accepted {
                Button(role: .destructive) {
                    showCancelAlert = true
                } label: {
                    actionLabel("取消订单")
                }
                .buttonStyle(.bordered)
                .disabled(actionInProgress)
            }

            if order.status == .created {
                Button {
                    Task {
                        actionInProgress = true
                        defer { actionInProgress = false }
                        if let _ = await viewModel.payOrder(id: order.id) {
                            paymentResult = .success
                        } else {
                            paymentResult = .fail
                            paymentErrorMessage = viewModel.errorMessage
                        }
                        showPaymentResult = true
                    }
                } label: {
                    actionLabel(actionInProgress ? "处理中..." : "立即支付", showProgress: actionInProgress)
                }
                .buttonStyle(.borderedProminent)
                .disabled(actionInProgress)
            }
        }
    }

    @ViewBuilder
    private func companionActions(_ order: Order) -> some View {
        VStack(spacing: Spacing.md) {
            if order.status == .created {
                Button {
                    pendingAction = "accept"
                    showActionAlert = true
                } label: {
                    actionLabel(actionInProgress && pendingAction == "accept" ? "处理中..." : "接受订单",
                                showProgress: actionInProgress && pendingAction == "accept")
                }
                .buttonStyle(.borderedProminent)
                .disabled(actionInProgress)

                Button(role: .destructive) {
                    pendingAction = "reject"
                    showActionAlert = true
                } label: {
                    actionLabel("拒绝订单")
                }
                .buttonStyle(.bordered)
                .disabled(actionInProgress)
            }

            if order.status == .accepted {
                Button {
                    pendingAction = "start"
                    showActionAlert = true
                } label: {
                    actionLabel(actionInProgress && pendingAction == "start" ? "处理中..." : "直接开始服务",
                                showProgress: actionInProgress && pendingAction == "start")
                }
                .buttonStyle(.borderedProminent)
                .disabled(actionInProgress)

                Button {
                    pendingAction = "request-start"
                    showActionAlert = true
                } label: {
                    actionLabel("请求患者确认开始")
                }
                .buttonStyle(.bordered)
                .disabled(actionInProgress)
            }

            if order.status == .inProgress {
                Button {
                    pendingAction = "complete"
                    showActionAlert = true
                } label: {
                    actionLabel(actionInProgress && pendingAction == "complete" ? "处理中..." : "完成服务",
                                showProgress: actionInProgress && pendingAction == "complete")
                }
                .buttonStyle(.borderedProminent)
                .disabled(actionInProgress)
            }
        }
    }

    /// AI-9: 统一按钮 label，撑满宽度 + ≥44pt 高 + Rectangle 命中区
    @ViewBuilder
    private func actionLabel(_ text: String, showProgress: Bool = false) -> some View {
        HStack(spacing: Spacing.xs) {
            if showProgress {
                ProgressView()
                    .scaleEffect(0.85)
            }
            Text(text)
        }
        .frame(maxWidth: .infinity, minHeight: minTapSide)
        .contentShape(Rectangle())
    }

    private func performAction(_ action: String) async {
        actionInProgress = true
        defer { actionInProgress = false }
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
