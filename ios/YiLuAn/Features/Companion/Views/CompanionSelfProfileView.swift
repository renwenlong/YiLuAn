import SwiftUI

struct CompanionSelfProfileView: View {
    @StateObject private var viewModel = CompanionProfileViewModel()

    var body: some View {
        ScrollView {
            VStack(spacing: Spacing.lg) {
                // Header
                VStack(spacing: Spacing.md) {
                    Image(systemName: "person.circle.fill")
                        .font(.system(size: 80))
                        .foregroundStyle(Color.brand)

                    Text(viewModel.selectedCompanion?.realName ?? "加载中...")
                        .font(.title2.bold())

                    if let status = viewModel.selectedCompanion?.verificationStatus {
                        HStack(spacing: Spacing.xs) {
                            Image(systemName: verificationIcon(status))
                                .foregroundStyle(verificationColor(status))
                            Text(verificationLabel(status))
                                .font(.dsCaption)
                                .foregroundStyle(verificationColor(status))
                        }
                    }
                }
                .padding(.top, Spacing.xl)

                // Stats
                if let stats = viewModel.stats {
                    HStack(spacing: 0) {
                        statItem(value: String(format: "%.1f", stats.avgRating), label: "评分")
                        Divider().frame(height: 40)
                        statItem(value: "\(stats.totalOrders)", label: "总订单")
                        Divider().frame(height: 40)
                        statItem(value: String(format: "¥%.0f", stats.totalEarnings), label: "总收入")
                    }
                    .padding()
                    .background(Color(.systemGray6))
                    .cornerRadius(CornerRadius.lg)
                    .padding(.horizontal)
                }

                // Profile Info
                VStack(alignment: .leading, spacing: Spacing.lg) {
                    if let bio = viewModel.selectedCompanion?.bio, !bio.isEmpty {
                        infoSection(title: "个人简介", content: bio)
                    }

                    if let area = viewModel.selectedCompanion?.serviceArea, !area.isEmpty {
                        infoSection(title: "服务区域", content: area)
                    }
                }
                .padding(.horizontal)

                // Edit Button
                NavigationLink {
                    CompanionProfileEditView()
                } label: {
                    Text("编辑资料")
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(Color.brand)
                        .foregroundStyle(.white)
                        .cornerRadius(CornerRadius.lg)
                }
                .padding(.horizontal)
            }
        }
        .navigationTitle("我的主页")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await viewModel.loadOwnProfile()
            await viewModel.loadStats()
        }
        .refreshable {
            await viewModel.loadOwnProfile()
            await viewModel.loadStats()
        }
    }

    private func statItem(value: String, label: String) -> some View {
        VStack(spacing: Spacing.xs) {
            Text(value)
                .font(.dsHeadline)
                .bold()
            Text(label)
                .font(.dsCaption)
                .foregroundStyle(Color.textSecondary)
        }
        .frame(maxWidth: .infinity)
    }

    private func infoSection(title: String, content: String) -> some View {
        VStack(alignment: .leading, spacing: Spacing.sm) {
            Text(title)
                .font(.dsHeadline)
            Text(content)
                .font(.dsBody)
                .foregroundStyle(Color.textSecondary)
        }
    }

    private func verificationIcon(_ status: String) -> String {
        switch status {
        case "verified": return "checkmark.seal.fill"
        case "pending": return "clock.fill"
        case "rejected": return "xmark.seal.fill"
        default: return "questionmark.circle"
        }
    }

    private func verificationColor(_ status: String) -> Color {
        switch status {
        case "verified": return .success
        case "pending": return .warning
        case "rejected": return .danger
        default: return .textHint
        }
    }

    private func verificationLabel(_ status: String) -> String {
        switch status {
        case "verified": return "已认证"
        case "pending": return "审核中"
        case "rejected": return "未通过"
        default: return "未认证"
        }
    }
}

#Preview {
    NavigationStack {
        CompanionSelfProfileView()
    }
}
