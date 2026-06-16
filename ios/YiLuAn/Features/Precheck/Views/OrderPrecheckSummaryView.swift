import SwiftUI

/// 4 信任卡聚合 view — 挂在 OrderDetailView "立即支付" 按钮上方
///
/// **S3-DEV-003-TRUST-UI-IOS (方案 B canonical — 纯 Swift Native)**
///
/// 设计来源:
/// - `docs/design/S3-trust-precheck-ui.md` §3.2 (4 张牌设计)
/// - PRD-003 v0.4 §S3-REQ-003 (信任前置)
/// - ADR-0046 §3.5 (positive-list 字段)
///
/// 用法:
/// ```
/// OrderPrecheckSummaryView(orderId: order.id) { isReady in
///     // 用 isReady 决定支付按钮是否 enable
/// }
/// ```
///
/// 设计原则:
/// - 4 卡片**纵向堆叠**, 每卡独立显示 ready/blocked
/// - 不暴露证件原图 URL (后端 ABAC Layer 1 已物理排除原图字段)
/// - 资质证明图用 NavigationLink + AsyncImage, signed URL TTL ≤15min (过期自动 refresh)
/// - WS 在线 + polling fallback 状态在顶部小角标提示
struct OrderPrecheckSummaryView: View {
    let orderId: String

    /// 父 View 拿到 paymentEnabled 状态, 用于 disable 支付按钮.
    var onPrecheckReadyChanged: ((Bool) -> Void)?

    @StateObject private var viewModel: PrecheckViewModel

    init(
        orderId: String,
        onPrecheckReadyChanged: ((Bool) -> Void)? = nil
    ) {
        self.orderId = orderId
        self.onPrecheckReadyChanged = onPrecheckReadyChanged
        _viewModel = StateObject(wrappedValue: PrecheckViewModel(orderId: orderId))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            header

            if viewModel.isLoading && viewModel.summary == nil {
                ProgressView("加载信任卡...")
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.vertical, 20)
            } else if let summary = viewModel.summary {
                cardsList(summary)
                if let reason = summary.blockedReason, !summary.allReady {
                    blockedBanner(reason)
                }
            } else if let err = viewModel.errorMessage {
                errorBanner(err)
            }
        }
        .padding(.vertical, 8)
        .task {
            await viewModel.loadInitial()
        }
        .onDisappear {
            viewModel.teardown()
        }
        .onChange(of: viewModel.summary?.paymentEnabled) { _, newValue in
            onPrecheckReadyChanged?(newValue ?? false)
        }
    }

    // MARK: - Header (WS 状态 + 标题)

    private var header: some View {
        HStack {
            Text("订单准备状态")
                .font(.headline)
            Spacer()
            wsStatusIndicator
        }
    }

    @ViewBuilder
    private var wsStatusIndicator: some View {
        if viewModel.wsConnected {
            Label("实时", systemImage: "dot.radiowaves.left.and.right")
                .font(.caption)
                .foregroundStyle(.green)
        } else if viewModel.isPollingFallback {
            Label("轮询中", systemImage: "arrow.triangle.2.circlepath")
                .font(.caption)
                .foregroundStyle(.orange)
        } else {
            EmptyView()
        }
    }

    // MARK: - 4 cards

    @ViewBuilder
    private func cardsList(_ summary: OrderPrecheckSummary) -> some View {
        VStack(spacing: 8) {
            PrecheckCardView(
                title: "服务合同",
                ready: summary.contractStatus.ready,
                summaryLine: contractSummaryLine(summary.contractStatus),
                detailLink: summary.contractStatus.contractPdfUrl.map { url in
                    PrecheckDetailLink(label: "查看合同 PDF", url: url)
                }
            )
            PrecheckCardView(
                title: "保险保单",
                ready: summary.insuranceStatus.ready,
                summaryLine: insuranceSummaryLine(summary.insuranceStatus),
                detailLink: summary.insuranceStatus.insurancePolicyPdfUrl.map { url in
                    PrecheckDetailLink(label: "查看保单 PDF", url: url)
                }
            )
            PrecheckCardView(
                title: "AI 准备包",
                ready: summary.preparationStatus.ready,
                summaryLine: preparationSummaryLine(summary.preparationStatus),
                detailLink: nil
            )
            PrecheckCardView(
                title: "陪诊师资质",
                ready: summary.companionCertStatus.ready,
                summaryLine: PrecheckAccessibilityText.companionCertSummaryLine(summary.companionCertStatus),
                detailLink: nil,  // 资质证明图通过 NavigationLink 单开页, 不在卡片直接展开
                accessibilityLabel: PrecheckAccessibilityText.companionCertAccessibilityLabel(summary.companionCertStatus),
                accessibilityHint: PrecheckAccessibilityText.companionCertAccessibilityHint(summary.companionCertStatus)
            )
        }
    }

    // MARK: - Banner

    private func blockedBanner(_ reason: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.orange)
            Text(reason)
                .font(.subheadline)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(Color.orange.opacity(0.12))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private func errorBanner(_ err: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: "xmark.octagon.fill")
                .foregroundStyle(.red)
            Text("加载失败: \(err)")
                .font(.subheadline)
            Spacer()
            Button("重试") {
                Task { await viewModel.refresh() }
            }
            .font(.caption)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(Color.red.opacity(0.12))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    // MARK: - Summary line helpers

    private func contractSummaryLine(_ card: ContractStatusCard) -> String {
        if card.ready {
            let version = card.contractTemplateVersion.map { " v\($0)" } ?? ""
            return "已生成\(version)"
        }
        return "未就绪"
    }

    private func insuranceSummaryLine(_ card: InsuranceStatusCard) -> String {
        if card.ready, let policy = card.insurancePolicyNoMasked {
            return "保单 \(policy)"
        }
        return card.ready ? "已生效" : "未就绪"
    }

    private func preparationSummaryLine(_ card: PreparationStatusCard) -> String {
        if card.ready {
            if let count = card.sectionsCount, count > 0 {
                return "已生成 \(count) 项"
            }
            return "已生成"
        }
        return "生成中"
    }

}

// MARK: - Accessibility text helpers

/// Precheck card accessibility copy — kept as pure helpers so unit tests can
/// lock VoiceOver / screen-reader semantics without snapshotting SwiftUI.
enum PrecheckAccessibilityText {
    static func cardStatusText(_ ready: Bool) -> String {
        ready ? "已就绪" : "未就绪"
    }

    static func companionCertSummaryLine(_ card: CompanionCertStatusCard) -> String {
        let status = "状态: \(cardStatusText(card.ready))"
        let name = nonEmpty(card.companionCertPseudonymName).map { "姓名: \($0)" } ?? "姓名未提供"
        let workId = nonEmpty(card.companionCertWorkId).map { "工号: \($0)" } ?? "工号未提供"
        let qualifications = nonEmpty(card.companionCertQualifications?.joined(separator: "、"))
            .map { "资质: \($0)" } ?? "资质未提供"
        let verifiedAt = formatDate(card.companionCertVerifiedAt)
            .map { "认证时间: \($0)" }
            ?? (card.ready ? "认证时间未提供" : "认证时间待核验")

        return [status, name, workId, qualifications, verifiedAt].joined(separator: "; ")
    }

    static func companionCertAccessibilityLabel(_ card: CompanionCertStatusCard) -> String {
        "陪诊师资质: \(companionCertSummaryLine(card))"
    }

    static func companionCertAccessibilityHint(_ card: CompanionCertStatusCard) -> String {
        if card.ready {
            return "资质已通过核验, 可继续付款; 证件原图不会在用户端展示。"
        }
        return "资质尚未就绪, 请等待核验完成或重新选择陪诊师; 当前状态不只依赖颜色提示。"
    }

    private static func nonEmpty(_ text: String?) -> String? {
        guard let text = text?.trimmingCharacters(in: .whitespacesAndNewlines), !text.isEmpty else {
            return nil
        }
        return text
    }

    private static func formatDate(_ date: Date?) -> String? {
        guard let date else { return nil }
        let calendar = Calendar(identifier: .gregorian)
        let components = calendar.dateComponents(in: TimeZone(secondsFromGMT: 0)!, from: date)
        guard let year = components.year, let month = components.month, let day = components.day else {
            return nil
        }
        return String(format: "%04d-%02d-%02d", year, month, day)
    }
}

// MARK: - Single card

/// 单张信任卡 — ready / blocked 两态
struct PrecheckCardView: View {
    let title: String
    let ready: Bool
    let summaryLine: String
    let detailLink: PrecheckDetailLink?
    let accessibilityLabel: String?
    let accessibilityHint: String?

    init(
        title: String,
        ready: Bool,
        summaryLine: String,
        detailLink: PrecheckDetailLink?,
        accessibilityLabel: String? = nil,
        accessibilityHint: String? = nil
    ) {
        self.title = title
        self.ready = ready
        self.summaryLine = summaryLine
        self.detailLink = detailLink
        self.accessibilityLabel = accessibilityLabel
        self.accessibilityHint = accessibilityHint
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            statusIcon

            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.subheadline.weight(.medium))
                Text(summaryLine)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                if let link = detailLink {
                    detailLinkButton(link)
                }
            }

            Spacer()
        }
        .padding(12)
        .background(Color.gray.opacity(0.06))
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilityLabel ?? "\(title): \(PrecheckAccessibilityText.cardStatusText(ready)), \(summaryLine)")
        .accessibilityHint(accessibilityHint ?? "状态卡片, 不需要额外操作。")
    }

    @ViewBuilder
    private var statusIcon: some View {
        if ready {
            VStack(spacing: 2) {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(.green)
                    .font(.title3)
                Text("已就绪")
                    .font(.caption2)
                    .foregroundStyle(.green)
            }
            .accessibilityHidden(true)
        } else {
            VStack(spacing: 2) {
                Image(systemName: "clock.fill")
                    .foregroundStyle(.orange)
                    .font(.title3)
                Text("未就绪")
                    .font(.caption2)
                    .foregroundStyle(.orange)
            }
            .accessibilityHidden(true)
        }
    }

    @ViewBuilder
    private func detailLinkButton(_ link: PrecheckDetailLink) -> some View {
        if let url = URL(string: link.url) {
            Link(link.label, destination: url)
                .font(.caption)
        }
    }
}

/// 单卡片可选 detail 链接 (signed URL, 用户点开看 PDF / 图).
struct PrecheckDetailLink {
    let label: String
    let url: String
}
