import SwiftUI

/// 患者端 Share 发起管理页（发起端 Owner 路径）。
/// ANDROID-DEV-B7-IOS-SHARE-ENTRY — 对齐小程序 WX-SHARE 发起端 (#395) + 后端契约。
///
/// 交互：选 scope → 生成分享链接（自动复制）→ 展示 active 列表 → 复制/撤销。
struct ShareManageView: View {
    @EnvironmentObject var loc: LocalizationManager
    @StateObject private var viewModel: ShareManageViewModel
    @Environment(\.dismiss) private var dismiss

    @State private var copiedToast: Bool = false
    @State private var revokeTarget: OrderShareToken?

    init(orderId: String) {
        _viewModel = StateObject(wrappedValue: ShareManageViewModel(orderId: orderId))
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: Spacing.lg) {
                    Text(loc.t("shareEntry.intro"))
                        .font(.footnote)
                        .foregroundStyle(.secondary)

                    createSection

                    Divider()

                    listSection
                }
                .padding()
            }
            .navigationTitle(loc.t("shareEntry.navTitle"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(loc.t("common.close")) { dismiss() }
                }
            }
            .task { await viewModel.loadShares() }
            .overlay(alignment: .bottom) {
                if copiedToast {
                    Text(loc.t("shareEntry.copied"))
                        .font(.subheadline)
                        .padding(.horizontal, 16).padding(.vertical, 8)
                        .background(.ultraThinMaterial, in: Capsule())
                        .padding(.bottom, 32)
                        .transition(.opacity)
                }
            }
            .alert(loc.t("shareEntry.revokeConfirm"), isPresented: revokeAlertBinding) {
                Button(loc.t("common.cancel"), role: .cancel) { revokeTarget = nil }
                Button(loc.t("shareEntry.revoke"), role: .destructive) {
                    if let t = revokeTarget {
                        Task { await viewModel.revokeShare(tokenId: t.id) }
                    }
                    revokeTarget = nil
                }
            }
        }
    }

    // MARK: - 创建区

    private var createSection: some View {
        VStack(alignment: .leading, spacing: Spacing.md) {
            Picker(loc.t("shareEntry.scopeLabel"), selection: $viewModel.scope) {
                Text(loc.t("shareScope.full")).tag(ShareScope.full)
                Text(loc.t("shareScope.progressOnly")).tag(ShareScope.progressOnly)
            }
            .pickerStyle(.segmented)

            Text(loc.t("shareEntry.limitReached"))
                .font(.caption)
                .foregroundStyle(.tertiary)

            Button {
                Task {
                    if let url = await viewModel.createShare() {
                        UIPasteboard.general.string = url
                        showCopiedToast()
                    }
                }
            } label: {
                HStack {
                    if viewModel.isCreating { ProgressView().tint(.white) }
                    Text(viewModel.isCreating ? loc.t("shareEntry.creating") : loc.t("shareEntry.createButton"))
                }
                .frame(maxWidth: .infinity, minHeight: 44)
            }
            .buttonStyle(.borderedProminent)
            .disabled(viewModel.isCreating)
        }
    }

    // MARK: - 列表区

    private var listSection: some View {
        VStack(alignment: .leading, spacing: Spacing.md) {
            HStack {
                Text(loc.t("shareEntry.activeListTitle")).font(.headline)
                Spacer()
                Text(loc.t("shareEntry.activeCount").replacingOccurrences(of: "{n}", with: "\(viewModel.activeCount)"))
                    .font(.caption).foregroundStyle(.secondary)
            }

            if viewModel.isLoading {
                Text(loc.t("common.loading")).foregroundStyle(.secondary)
            } else if viewModel.shares.isEmpty {
                Text(loc.t("shareEntry.emptyList"))
                    .font(.subheadline).foregroundStyle(.tertiary)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.vertical, 24)
            } else {
                ForEach(viewModel.shares) { share in
                    shareRow(share)
                }
            }
        }
    }

    private func shareRow(_ share: OrderShareToken) -> some View {
        VStack(alignment: .leading, spacing: Spacing.sm) {
            Text(share.shareScope.displayName)
                .font(.caption2)
                .padding(.horizontal, 10).padding(.vertical, 3)
                .background(Color.accentColor.opacity(0.12), in: Capsule())

            Text(share.shareURL)
                .font(.caption)
                .textSelection(.enabled)
                .lineLimit(2)

            HStack {
                Button {
                    UIPasteboard.general.string = share.shareURL
                    showCopiedToast()
                } label: {
                    Label(loc.t("shareEntry.copyLink"), systemImage: "doc.on.doc")
                }
                .font(.caption)
                .buttonStyle(.bordered)

                Spacer()

                Button(role: .destructive) {
                    revokeTarget = share
                } label: {
                    if viewModel.revokingId == share.id {
                        ProgressView()
                    } else {
                        Text(loc.t("shareEntry.revoke"))
                    }
                }
                .font(.caption)
                .buttonStyle(.bordered)
                .disabled(viewModel.revokingId == share.id)
            }
        }
        .padding()
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Helpers

    private var revokeAlertBinding: Binding<Bool> {
        Binding(
            get: { revokeTarget != nil },
            set: { if !$0 { revokeTarget = nil } }
        )
    }

    private func showCopiedToast() {
        withAnimation { copiedToast = true }
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            withAnimation { copiedToast = false }
        }
    }
}
