import SwiftUI

/// 家属端订单脱敏视图（S2-INT-006 / INT-004 follow-up）
///
/// 拉 `ShareService.fetchShareOrder(shareSession:)` 返回 `ShareOrderResponse`，
/// 按 `share_scope` 渲染脱敏视图：
/// - 始终显示：订单号 / 状态 / 服务类型 / 预约日期时段 / 医院 / 脱敏患者姓名 / 陪诊师
/// - scope=full：can_view_images + can_view_ai_summary 都 true → 显示影像 / AI 摘要入口
/// - scope=progress_only：影像 / AI 摘要不可见，仅显示 timeline 进度
///
/// 注意：本视图不显示 PII（电话 / 身份证 / medical_notes），后端已脱敏（§2.5）
struct ShareOrderView: View {
    let shareSession: ShareSessionStore.SavedSession

    @State private var order: ShareOrderResponse?
    @State private var loadState: LoadState = .loading
    @Environment(\.dismiss) private var dismiss

    enum LoadState: Equatable {
        case loading
        case loaded
        case error(String)
        case sessionExpired
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    switch loadState {
                    case .loading:
                        loadingView
                    case .loaded:
                        if let order {
                            orderContent(order)
                        }
                    case .error(let msg):
                        errorView(msg)
                    case .sessionExpired:
                        sessionExpiredView
                    }
                }
                .padding()
            }
            .navigationTitle("订单进度")
            .navigationBarTitleDisplayMode(.inline)
            .task {
                await loadOrder()
            }
            .refreshable {
                await loadOrder()
            }
        }
    }

    // MARK: - Loading

    private var loadingView: some View {
        HStack(spacing: 12) {
            ProgressView()
            Text("加载中…").foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .center)
        .padding(.vertical, 64)
    }

    private func errorView(_ msg: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle")
                .font(.largeTitle)
                .foregroundStyle(.orange)
            Text(msg).font(.subheadline).multilineTextAlignment(.center)
            Button("重试") { Task { await loadOrder() } }
                .buttonStyle(.borderedProminent)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 48)
    }

    private var sessionExpiredView: some View {
        VStack(spacing: 12) {
            Image(systemName: "clock.badge.exclamationmark")
                .font(.largeTitle)
                .foregroundStyle(.orange)
            Text("查看链接已过期")
                .font(.headline)
            Text("share_session 30 分钟有效期已过，请重新通过短信验证码进入")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            Button("关闭") { dismiss() }
                .buttonStyle(.bordered)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 48)
    }

    // MARK: - Order content

    @ViewBuilder
    private func orderContent(_ order: ShareOrderResponse) -> some View {
        scopeBadge(order.shareScope)

        section(title: "订单") {
            row("订单号", order.orderNumber)
            row("状态", order.status)
            row("服务类型", order.serviceType)
        }

        section(title: "预约") {
            row("日期", order.appointmentDate)
            row("时段", order.appointmentTime)
            if let hospital = order.hospitalName {
                row("医院", hospital)
            }
        }

        section(title: "患者 & 陪诊师") {
            if let masked = order.patientNameMasked {
                row("患者", masked)
            }
            if let companion = order.companion {
                if let name = companion.name {
                    row("陪诊师", name)
                }
            } else {
                row("陪诊师", "未指派")
            }
        }

        // scope 闸门：scope=full 时显示影像 / AI 摘要入口
        // scope=progress_only 时仅显示 timeline
        if order.canViewImages || order.canViewAISummary {
            section(title: "增值内容") {
                if order.canViewImages {
                    Label("可查看就诊影像", systemImage: "photo")
                        .font(.subheadline)
                        .foregroundStyle(.blue)
                }
                if order.canViewAISummary {
                    Label("可查看 AI 就诊摘要", systemImage: "doc.text.magnifyingglass")
                        .font(.subheadline)
                        .foregroundStyle(.blue)
                }
            }
        }

        if let timeline = order.timeline, !timeline.isEmpty {
            section(title: "进度时间线") {
                timelineView(timeline)
            }
        }

        // PII 提示（§2.5 后端已脱敏）
        Text("出于隐私保护，患者电话 / 身份证 / 病情描述对家属侧不可见")
            .font(.caption)
            .foregroundStyle(.tertiary)
            .padding(.top, 8)
    }

    private func scopeBadge(_ scope: ShareScope) -> some View {
        HStack {
            Image(systemName: scope == .full ? "eye.fill" : "eye.slash")
                .foregroundStyle(scope == .full ? .blue : .gray)
            Text(scope.displayName)
                .font(.caption.weight(.semibold))
                .foregroundStyle(scope == .full ? .blue : .secondary)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(
            (scope == .full ? Color.blue : Color.gray)
                .opacity(0.1)
        )
        .cornerRadius(16)
    }

    @ViewBuilder
    private func section<Content: View>(
        title: String,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
                .textCase(.uppercase)
            VStack(alignment: .leading, spacing: 6) {
                content()
            }
            .padding()
            .background(Color(.systemGray6))
            .cornerRadius(12)
        }
    }

    private func row(_ label: String, _ value: String) -> some View {
        HStack(alignment: .top) {
            Text(label)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .frame(width: 80, alignment: .leading)
            Text(value)
                .font(.subheadline)
            Spacer()
        }
    }

    private func timelineView(_ items: [ShareTimelineItem]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                HStack(alignment: .top, spacing: 12) {
                    Circle().fill(.blue).frame(width: 8, height: 8).padding(.top, 6)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(item.event)
                            .font(.subheadline.weight(.medium))
                        if let detail = item.detail {
                            Text(detail).font(.caption).foregroundStyle(.secondary)
                        }
                        Text(formatTimestamp(item.at))
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                }
            }
        }
    }

    private func formatTimestamp(_ date: Date) -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd HH:mm"
        f.timeZone = TimeZone(identifier: "Asia/Shanghai")
        return f.string(from: date)
    }

    // MARK: - Networking

    private func loadOrder() async {
        // session 过期检查（ShareSessionStore.activeSession() 也做但这里防御性 double-check）
        if shareSession.expiresAt <= Date() {
            loadState = .sessionExpired
            return
        }
        loadState = .loading
        do {
            let resp = try await ShareService.fetchShareOrder(shareSession: shareSession.jwt)
            order = resp
            loadState = .loaded
        } catch APIError.unauthorized {
            ShareSessionStore.clear()
            loadState = .sessionExpired
        } catch let APIError.httpError(statusCode, _) where statusCode == 401 {
            // 401 = session 失效（被 owner revoke 或服务端过期）
            ShareSessionStore.clear()
            loadState = .sessionExpired
        } catch {
            loadState = .error(error.localizedDescription)
        }
    }
}
