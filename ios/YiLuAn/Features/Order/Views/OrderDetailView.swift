import SwiftUI
import UIKit

struct OrderDetailView: View {
    let orderId: String
    let isCompanion: Bool

    @StateObject private var viewModel = OrderViewModel()
    @EnvironmentObject var loc: LocalizationManager
    /// P1-2: 完成订单查评价状态，用于决定“去评价” / “已评价”的孕讗。
    @StateObject private var reviewViewModel = ReviewViewModel()
    @State private var showCancelAlert = false
    @State private var showActionAlert = false
    @State private var pendingAction = ""
    @State private var paymentResult: PaymentStatus?
    @State private var paymentErrorMessage: String?
    @State private var showPaymentResult = false
    /// AI-9: 与小程序 actionLoading 对齐——状态切换期间禁用所有按钮 + 占位
    @State private var actionInProgress = false
    /// [F-03] 紧急呼叫面板
    @State private var showEmergencySheet = false
    /// [F-07] 复诊提醒创建面板
    @State private var showFollowupSheet = false
    // ANDROID-DEV-B7-IOS-SHARE-ENTRY: 家属分享发起管理 sheet
    @State private var showShareManage = false

    /// S3-DEV-001-CONTRACT-UI (ADR-0047 §6.3): 合同/保障 checkbox 默认 unchecked.
    /// PIPL/民法典电子合同合规要求,不允许 "记住选择" 跳过下次确认.
    @State private var contractAccepted = false
    /// S3-DEV-001-CONTRACT-UI: 合同非 active 状态时弹 alert (生成中 / 失败 / 作废).
    @State private var contractStatusAlertMessage: String?
    /// S3-DEV-001-CONTRACT-UI: 保障条款静态 alert (S3 vendor PLACEHOLDER 阶段).
    @State private var showInsuranceTermsAlert = false
    /// S3-DEV-001-CONTRACT-UI: 合同 service (复用 APIClient.shared).
    private let contractService = ContractService()

    /// S3-DEV-003-TRUST-UI-IOS: 4 信任卡 precheck 状态闸门.
    /// `precheckPaymentEnabled=true` 表示 4 张牌全 ready + 后端 `payment_enabled=true`,
    /// 此时支付按钮才 enable. 后端 ABAC + PM payment-pause overrides 决定.
    ///
    /// 历史订单 (`contractId == nil`) 跳过 precheck 闸门: 默认 `true`,
    /// 不是依赖 PrecheckViewModel 的 404 fallback (历史订单没 4 牌记录).
    @State private var precheckPaymentEnabled = false

    /// AI-9: 命中区 ≥ 44pt（HIG 推荐最小可点尺寸），按钮 frame 用这个常量。
    private let minTapSide: CGFloat = 44

    var body: some View {
        Group {
            if viewModel.isLoading && viewModel.currentOrder == nil {
                // AI-9: 用 redacted(.placeholder) 做骨架，避免首次 ProgressView 白屏
                skeletonContent
                    .redacted(reason: .placeholder)
                    .accessibilityLabel(loc.t("order.loading"))
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
                Text(loc.t("error.ORDER_NOT_FOUND"))
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle(loc.t("order.orderDetail"))
        .navigationBarTitleDisplayMode(.inline)
        .task { await viewModel.loadOrder(id: orderId) }
        // P1-2: 订单进入完成/已评价状态后，拉取评价以决定展示“写评价”还是“已评价摘要”
        .task(id: viewModel.currentOrder?.status) {
            guard !isCompanion, let order = viewModel.currentOrder else { return }
            if order.status == .completed || order.status == .reviewed {
                await reviewViewModel.loadReview(orderId: orderId)
            }
        }
        .alert(loc.t("companionOrderDetail.cancelAcceptedTitle"), isPresented: $showCancelAlert) {
            Button(loc.t("common.cancel"), role: .cancel) {}
            Button(loc.t("companionOrderDetail.cancelAcceptedTitle"), role: .destructive) {
                Task { await performAction("cancel") }
            }
        } message: {
            Text(loc.t("companionOrderDetail.cancelAcceptedContent"))
        }
        .alert(loc.t("order.confirmAction"), isPresented: $showActionAlert) {
            Button(loc.t("common.cancel"), role: .cancel) {}
            Button(loc.t("common.confirm")) {
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
        .sheet(isPresented: $showEmergencySheet) {
            EmergencyCallSheet(orderId: orderId)
        }
        .sheet(isPresented: $showFollowupSheet) {
            FollowupReminderCreateSheet(orderId: orderId) {}
        }
        // ANDROID-DEV-B7-IOS-SHARE-ENTRY: 家属分享发起管理页。
        .sheet(isPresented: $showShareManage) {
            ShareManageView(orderId: orderId)
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
                    skeletonRow(loc.t("createOrder.stepService"), loc.t("order.companionServiceFull"))
                    skeletonRow(loc.t("order.hospital"), loc.t("order.hospitalPlaceholder"))
                    skeletonRow(loc.t("order.appointmentDate"), "2025-XX-XX")
                    skeletonRow(loc.t("orderDetail.feeLabel"), "¥ XXX.00")
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
                Text(loc.t("orderStatus." + order.status.rawValue))
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
            // S2-REQ-003-P5c: 优先显示 snapshot 名称 (admin 改名后历史订单仍显示下单时名称)
            infoRow(loc.t("createOrder.stepService"), order.serviceNameSnapshot ?? loc.t("serviceType." + order.serviceType.rawValue))
            infoRow(loc.t("order.hospital"), order.hospitalName ?? loc.t("order.statusUnknown"))
            infoRow(loc.t("order.appointmentDate"), order.appointmentDate)
            if let time = order.appointmentTime {
                infoRow(loc.t("orderDetail.appointmentTime"), time)
            }
            infoRow(loc.t("orderDetail.feeLabel"), CurrencyFormatter.cnyWithUnit(order.price), isPrice: true)
            if let desc = order.description, !desc.isEmpty {
                infoRow(loc.t("orderDetail.notesLabel"), desc)
            }
            if let companionName = order.companionName {
                infoRow(loc.t("role.companion"), companionName)
            }
            if let patientName = order.patientName {
                infoRow(loc.t("role.patient"), patientName)
            }
            // F-05: 代他人下单 — 重点提示陪诊师“实际就诊人”与账户不同
            if let fm = order.familyMember {
                let relLabel: String = {
                    switch fm.relation ?? "other" {
                    case "self": return loc.t("createOrder.self")
                    case "parent": return loc.t("relation.parent")
                    case "spouse": return loc.t("relation.spouse")
                    case "child": return loc.t("relation.child")
                    case "sibling": return loc.t("relation.sibling")
                    case "grandparent": return loc.t("relation.grandparent")
                    case "relative": return loc.t("relation.relative")
                    case "friend": return loc.t("relation.friend")
                    default: return loc.t("relation.other")
                    }
                }()
                let phoneSuffix = (fm.phone?.isEmpty == false) ? " · \(fm.phone!)" : ""
                infoRow(loc.t("order.rowActualPatient"), "\(fm.name)（\(relLabel)）\(phoneSuffix)")
            }
            // [F-05] 代他人下单：后端 OrderResponse.family_member 非空时呈现
            if let fm = order.familyMember {
                infoRow(loc.t("order.rowActualPatient"), "\(fm.name)（\(FamilyRelation.label(for: fm.relation))）")
                if let phone = fm.phone, !phone.isEmpty {
                    infoRow(loc.t("orderDetail.phoneLabel"), phone)
                }
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
                    actionLabel(loc.t("orderDetail.cancelOrder"))
                }
                .buttonStyle(.bordered)
                .disabled(actionInProgress)
            }

            if order.status == .created {
                // S3-DEV-003-TRUST-UI-IOS: 4 信任卡 precheck summary, 挂在支付按钮上方.
                // 设计来源 docs/design/S3-trust-precheck-ui.md §3.1.
                // 任一卡片 ready=false → precheckPaymentEnabled=false → 支付按钮灰显.
                // 历史订单 (contractId == nil) 跳过闸门, 不加载 precheck UI.
                if order.contractId != nil {
                    OrderPrecheckSummaryView(orderId: order.id) { enabled in
                        precheckPaymentEnabled = enabled
                    }
                } else {
                    // 历史订单: 默认 precheck 闸门开
                    Color.clear.frame(height: 0).onAppear {
                        precheckPaymentEnabled = true
                    }
                }

                // S3-DEV-001-CONTRACT-UI (ADR-0047 §6.3): 合同 checkbox 默认 unchecked +
                // 支付按钮 disabled until 勾选. order.contractId == nil (历史订单) 时
                // 不显示 checkbox, 支付按钮直接可用.
                if let contractId = order.contractId {
                    contractAcceptanceRow(contractId: contractId, hasInsurance: order.insuranceId != nil)
                }

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
                    actionLabel(actionInProgress ? loc.t("orderDetail.processing") : loc.t("orderDetail.payNow"), showProgress: actionInProgress)
                }
                .buttonStyle(.borderedProminent)
                // disabled =
                //   actionInProgress
                //   OR (合同存在 && 未勾选)
                //   OR (合同存在 && !precheckPaymentEnabled) — S3-DEV-003-TRUST-UI-IOS 4 信任卡未全 ready
                // 历史订单 (contractId == nil) 跳过 precheck 闸门 (上方 onAppear set true).
                .disabled(
                    actionInProgress
                    || (order.contractId != nil && !contractAccepted)
                    || (order.contractId != nil && !precheckPaymentEnabled)
                )
            }

            // [F-03] 紧急呼叫：服务进行中/已接单状态可用，与 wechat 一致
            if order.status == .accepted || order.status == .inProgress {
                Button(role: .destructive) {
                    showEmergencySheet = true
                } label: {
                    HStack {
                        Image(systemName: "exclamationmark.triangle.fill")
                        Text(loc.t("orderDetail.emergencyCall"))
                    }
                    .frame(maxWidth: .infinity, minHeight: minTapSide)
                }
                .buttonStyle(.bordered)
                .tint(.red)
                .disabled(actionInProgress)
            }

            // [F-07] 复诊提醒：仅已完成/已评价订单可创建。后端对 status 会再校验。
            if order.status == .completed || order.status == .reviewed {
                Button {
                    showFollowupSheet = true
                } label: {
                    HStack {
                        Image(systemName: "bell.badge")
                        Text(loc.t("orderDetail.createFollowup"))
                    }
                    .frame(maxWidth: .infinity, minHeight: minTapSide)
                }
                .buttonStyle(.bordered)
                .tint(.accent)
                .disabled(actionInProgress)
            }

            // P1-2: 完成状态下的评价入口 / 已评价摘要
            if order.status == .completed || order.status == .reviewed {
                reviewSection(order)
            }

            // ANDROID-DEV-B7-IOS-SHARE-ENTRY: 家属分享发起入口。
            // 对齐小程序 WX-SHARE 发起端: 付款后有进度可分享时显示
            // (accepted/in_progress/completed/reviewed 态)。
            if order.status == .accepted || order.status == .inProgress
                || order.status == .completed || order.status == .reviewed {
                Button {
                    showShareManage = true
                } label: {
                    HStack {
                        Image(systemName: "person.2.badge.gearshape")
                        Text(loc.t("shareEntry.entryButton"))
                    }
                    .frame(maxWidth: .infinity, minHeight: minTapSide)
                }
                .buttonStyle(.bordered)
                .tint(.accent)
                .disabled(actionInProgress)
            }
        }
    }

    /// P1-2: 根据 `reviewViewModel.review` 是否存在，返回“写评价”入口或评分摘要。
    @ViewBuilder
    private func reviewSection(_ order: Order) -> some View {
        if let review = reviewViewModel.review {
            // 已评价：展示评分摘要
            VStack(alignment: .leading, spacing: Spacing.sm) {
                HStack {
                    Text(loc.t("order.myReview"))
                        .font(.subheadline.bold())
                    Spacer()
                    HStack(spacing: 2) {
                        ForEach(1...5, id: \.self) { star in
                            Image(systemName: star <= review.rating ? "star.fill" : "star")
                                .font(.caption)
                                .foregroundColor(.orange)
                        }
                    }
                }
                if let comment = review.comment, !comment.isEmpty {
                    Text(comment)
                        .font(.body)
                        .foregroundStyle(.secondary)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(Spacing.lg)
            .background(Color(.systemGray6))
            .cornerRadius(CornerRadius.md)
        } else if !reviewViewModel.isLoading {
            // 未评价：提供写评价入口
            NavigationLink {
                WriteReviewView(orderId: order.id)
            } label: {
                HStack {
                    Image(systemName: "square.and.pencil")
                    Text(loc.t("orderDetail.writeReview"))
                }
                .frame(maxWidth: .infinity, minHeight: minTapSide)
            }
            .buttonStyle(.borderedProminent)
            .tint(.orange)
            .disabled(actionInProgress)
        }
    }

    // MARK: - Contract acceptance (S3-DEV-001-CONTRACT-UI)

    /// 合同/保障 checkbox 行 — order.status == .created && order.contractId != nil 时展示.
    @ViewBuilder
    private func contractAcceptanceRow(contractId: String, hasInsurance: Bool) -> some View {
        VStack(alignment: .leading, spacing: Spacing.xs) {
            HStack(alignment: .top, spacing: Spacing.sm) {
                Button {
                    Task { await toggleContractAccept(contractId: contractId) }
                } label: {
                    Image(systemName: contractAccepted ? "checkmark.square.fill" : "square")
                        .font(.title3)
                        .foregroundColor(contractAccepted ? .green : .secondary)
                        .accessibilityLabel(contractAccepted ? loc.t("order.contractAgreed") : loc.t("order.contractNotAgreed"))
                }
                .buttonStyle(.plain)

                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 4) {
                        Text(loc.t("login.agreementPre"))
                            .font(.subheadline)
                        Button(loc.t("orderDetail.contractLink")) {
                            Task { await viewContract(contractId: contractId) }
                        }
                        .font(.subheadline)
                        .foregroundColor(.green)
                    }
                    if hasInsurance {
                        Button(loc.t("orderDetail.insuranceLink")) {
                            showInsuranceTermsAlert = true
                        }
                        .font(.subheadline)
                        .foregroundColor(.green)
                    }
                }
                Spacer()
            }
            if !contractAccepted {
                Text(loc.t("orderDetail.contractHint"))
                    .font(.caption)
                    .foregroundColor(.orange)
                    .padding(.leading, 32)
            }
        }
        .padding(Spacing.md)
        .background(Color(.systemGray6))
        .cornerRadius(8)
        .alert(loc.t("order.contractStatus"), isPresented: .init(
            get: { contractStatusAlertMessage != nil },
            set: { if !$0 { contractStatusAlertMessage = nil } }
        )) {
            Button(loc.t("common.gotIt"), role: .cancel) { }
        } message: {
            Text(contractStatusAlertMessage ?? "")
        }
        .alert(loc.t("orderDetail.insuranceTitle"), isPresented: $showInsuranceTermsAlert) {
            Button(loc.t("orderDetail.gotIt"), role: .cancel) { }
        } message: {
            Text(loc.t("orderDetail.insuranceContent"))
        }
    }

    /// 切换勾选状态. 勾选时立即调 POST /accept 写 audit log
    /// (ADR-0047 §3.5 PIPL 取证). 失败不回滚 UI — 服务端 cron 兜底.
    private func toggleContractAccept(contractId: String) async {
        let newChecked = !contractAccepted
        contractAccepted = newChecked
        guard newChecked else { return }  // 取消勾选不发 audit
        do {
            _ = try await contractService.acceptContract(contractId: contractId)
        } catch {
            // 失败 toast 但不回滚 contractAccepted — 服务端 cron 兜底
            contractStatusAlertMessage = loc.t("orderDetail.contractNetErr")
        }
    }

    /// 查看合同 PDF — 取 signed URL (15min TTL) → Safari 打开.
    /// 服务端会同时写 user_audit_logs.contract_viewed.
    private func viewContract(contractId: String) async {
        do {
            let detail = try await contractService.getContract(contractId: contractId)
            if let signedUrl = detail.signedUrl, let url = URL(string: signedUrl) {
                await UIApplication.shared.open(url)
            } else {
                contractStatusAlertMessage = detail.status.userFacingMessage
            }
        } catch {
            contractStatusAlertMessage = loc.t("order.contractLoadFailed")
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
                    actionLabel(actionInProgress && pendingAction == "accept" ? loc.t("orderDetail.processing") : loc.t("chat.acceptOrder"),
                                showProgress: actionInProgress && pendingAction == "accept")
                }
                .buttonStyle(.borderedProminent)
                .disabled(actionInProgress)

                Button(role: .destructive) {
                    pendingAction = "reject"
                    showActionAlert = true
                } label: {
                    actionLabel(loc.t("order.rejectOrder"))
                }
                .buttonStyle(.bordered)
                .disabled(actionInProgress)
            }

            if order.status == .accepted {
                Button {
                    pendingAction = "start"
                    showActionAlert = true
                } label: {
                    actionLabel(actionInProgress && pendingAction == "start" ? loc.t("orderDetail.processing") : loc.t("order.startServiceDirectly"),
                                showProgress: actionInProgress && pendingAction == "start")
                }
                .buttonStyle(.borderedProminent)
                .disabled(actionInProgress)

                Button {
                    pendingAction = "request-start"
                    showActionAlert = true
                } label: {
                    actionLabel(loc.t("order.requestPatientConfirmStart"))
                }
                .buttonStyle(.bordered)
                .disabled(actionInProgress)
            }

            if order.status == .inProgress {
                Button {
                    pendingAction = "complete"
                    showActionAlert = true
                } label: {
                    actionLabel(actionInProgress && pendingAction == "complete" ? loc.t("orderDetail.processing") : loc.t("companionOrderDetail.complete"),
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
        case "accept": return loc.t("companionOrderDetail.acceptConfirmDefault")
        case "reject": return loc.t("order.confirmRejectRefund")
        case "start": return loc.t("order.confirmStartService")
        case "request-start": return loc.t("order.sendStartConfirmToPatient")
        case "complete": return loc.t("companionOrderDetail.completeContent")
        default: return loc.t("order.confirmActionQuestion")
        }
    }
}
