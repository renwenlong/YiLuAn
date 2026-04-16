import SwiftUI

struct CompanionDetailView: View {
    let companionId: String
    @StateObject private var viewModel = CompanionProfileViewModel()

    var body: some View {
        ScrollView {
            if viewModel.isLoading {
                VStack(spacing: Spacing.lg) {
                    // Skeleton
                    RoundedRectangle(cornerRadius: 0)
                        .fill(Color.bgSkeleton.opacity(0.5))
                        .frame(height: 220)
                    ForEach(0..<3, id: \.self) { _ in
                        RoundedRectangle(cornerRadius: CornerRadius.lg)
                            .fill(Color.bgSkeleton.opacity(0.3))
                            .frame(height: 80)
                            .padding(.horizontal, Spacing.lg)
                    }
                }
            } else if let companion = viewModel.selectedCompanion {
                VStack(spacing: 0) {
                    // Hero header with gradient
                    ZStack {
                        AppGradient.primary
                            .frame(height: 220)

                        // Decorative circles
                        Circle()
                            .fill(.white.opacity(0.08))
                            .frame(width: 200)
                            .offset(x: 120, y: -60)

                        VStack(spacing: Spacing.md) {
                            avatarView(companion)
                                .overlay(
                                    Circle()
                                        .stroke(.white, lineWidth: 3)
                                        .frame(width: 96, height: 96)
                                )
                                .shadow(color: .black.opacity(0.2), radius: 12, x: 0, y: 6)

                            VStack(spacing: Spacing.xs) {
                                Text(companion.displayName ?? companion.realName)
                                    .font(.dsH1)
                                    .foregroundStyle(.white)

                                // Verification badge
                                HStack(spacing: 4) {
                                    Image(systemName: verificationIcon(companion.verificationStatus))
                                        .font(.system(size: 12))
                                    Text(verificationLabel(companion.verificationStatus))
                                        .font(.dsSmall)
                                        .fontWeight(.medium)
                                }
                                .foregroundStyle(.white.opacity(0.85))
                                .padding(.horizontal, 10)
                                .padding(.vertical, 3)
                                .background(.white.opacity(0.2))
                                .clipShape(Capsule())
                            }

                            // Rating
                            ratingView(companion.avgRating)
                        }
                    }

                    VStack(spacing: Spacing.md) {
                        // Stats row
                        HStack(spacing: 0) {
                            statItem(value: String(companion.totalOrders), label: "完成订单")
                            Divider().frame(height: 30)
                            statItem(
                                value: String(format: "%.1f", companion.avgRating),
                                label: "服务评分"
                            )
                        }
                        .padding(.vertical, Spacing.lg)
                        .background(Color.bgCard)
                        .cornerRadius(CornerRadius.lg)
                        .shadow(color: .black.opacity(0.05), radius: 4, x: 0, y: 2)
                        .padding(.horizontal, Spacing.lg)
                        .offset(y: -24)

                        // Service area
                        if let area = companion.serviceArea, !area.isEmpty {
                            VStack(alignment: .leading, spacing: Spacing.md) {
                                Text("服务区域")
                                    .font(.dsTitle)
                                    .foregroundStyle(Color.textPrimary)

                                FlowLayout(spacing: Spacing.sm) {
                                    ForEach(area.components(separatedBy: ","), id: \.self) { tag in
                                        Text(tag.trimmingCharacters(in: .whitespaces))
                                            .font(.dsSubheadline)
                                            .badgeStyle(color: .brand)
                                    }
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(Spacing.lg)
                            .background(Color.bgCard)
                            .cornerRadius(CornerRadius.lg)
                            .shadow(color: .black.opacity(0.05), radius: 4, x: 0, y: 2)
                            .padding(.horizontal, Spacing.lg)
                        }

                        // Bio
                        if let bio = companion.bio, !bio.isEmpty {
                            VStack(alignment: .leading, spacing: Spacing.md) {
                                Text("个人简介")
                                    .font(.dsTitle)
                                    .foregroundStyle(Color.textPrimary)
                                Text(bio)
                                    .font(.dsBody)
                                    .foregroundStyle(Color.textSecondary)
                                    .lineSpacing(6)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(Spacing.lg)
                            .background(Color.bgCard)
                            .cornerRadius(CornerRadius.lg)
                            .shadow(color: .black.opacity(0.05), radius: 4, x: 0, y: 2)
                            .padding(.horizontal, Spacing.lg)
                        }
                    }
                    .padding(.bottom, 100)
                }
                .overlay(alignment: .bottom) {
                    // Book button
                    NavigationLink {
                        CreateOrderView()
                    } label: {
                        Text("预约陪诊")
                            .font(.dsTitle)
                            .fontWeight(.semibold)
                    }
                    .buttonStyle(PrimaryButtonStyle())
                    .padding(.horizontal, Spacing.xl)
                    .padding(.bottom, Spacing.xl)
                    .background(
                        LinearGradient(
                            colors: [.bgPage.opacity(0), .bgPage],
                            startPoint: .top, endPoint: .center
                        )
                        .frame(height: 100)
                        .allowsHitTesting(false),
                        alignment: .top
                    )
                }
            } else if let error = viewModel.errorMessage {
                VStack(spacing: Spacing.md) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 40))
                        .foregroundStyle(Color.textHint)
                    Text(error)
                        .font(.dsBody)
                        .foregroundStyle(Color.textSecondary)
                }
                .frame(maxWidth: .infinity, minHeight: 300)
            }
        }
        .background(Color.bgPage)
        .navigationTitle("陪诊师详情")
        .navigationBarTitleDisplayMode(.inline)
        .ignoresSafeArea(edges: .top)
        .task {
            await viewModel.loadDetail(id: companionId)
        }
    }

    @ViewBuilder
    private func avatarView(_ companion: CompanionProfile) -> some View {
        if let urlString = companion.avatarUrl, let url = URL(string: urlString) {
            AsyncImage(url: url) { image in
                image
                    .resizable()
                    .scaledToFill()
            } placeholder: {
                ProgressView()
            }
            .frame(width: 90, height: 90)
            .clipShape(Circle())
        } else {
            ZStack {
                Circle()
                    .fill(.white.opacity(0.2))
                    .frame(width: 90, height: 90)
                Text(String(companion.displayName?.prefix(1) ?? companion.realName.prefix(1)))
                    .font(.system(size: 36, weight: .bold))
                    .foregroundStyle(.white)
            }
        }
    }

    private func ratingView(_ rating: Double) -> some View {
        HStack(spacing: 4) {
            ForEach(1...5, id: \.self) { star in
                Image(systemName: star <= Int(rating.rounded()) ? "star.fill" : "star")
                    .font(.system(size: 14))
                    .foregroundStyle(star <= Int(rating.rounded()) ? Color.warning : .white.opacity(0.4))
            }
            Text(String(format: "%.1f", rating))
                .font(.dsSubheadline)
                .fontWeight(.medium)
                .foregroundStyle(.white.opacity(0.8))
        }
    }

    private func statItem(value: String, label: String) -> some View {
        VStack(spacing: 4) {
            Text(value)
                .font(.dsTitle)
                .foregroundStyle(Color.brand)
            Text(label)
                .font(.dsSmall)
                .foregroundStyle(Color.textHint)
        }
        .frame(maxWidth: .infinity)
    }

    private func verificationIcon(_ status: String) -> String {
        switch status {
        case "verified": return "checkmark.seal.fill"
        case "pending": return "clock.fill"
        default: return "questionmark.circle"
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

    private func verificationColor(_ status: String) -> Color {
        switch status {
        case "verified": return .success
        case "pending": return .warning
        case "rejected": return .danger
        default: return .textSecondary
        }
    }
}

// Simple flow layout for tags
struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let result = layoutResult(proposal: proposal, subviews: subviews)
        return result.size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let result = layoutResult(proposal: ProposedViewSize(width: bounds.width, height: nil), subviews: subviews)
        for (index, position) in result.positions.enumerated() {
            subviews[index].place(at: CGPoint(x: bounds.minX + position.x, y: bounds.minY + position.y), proposal: .unspecified)
        }
    }

    private func layoutResult(proposal: ProposedViewSize, subviews: Subviews) -> (size: CGSize, positions: [CGPoint]) {
        let maxWidth = proposal.width ?? .infinity
        var positions: [CGPoint] = []
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0

        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > maxWidth && x > 0 {
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }
            positions.append(CGPoint(x: x, y: y))
            rowHeight = max(rowHeight, size.height)
            x += size.width + spacing
        }

        return (CGSize(width: maxWidth, height: y + rowHeight), positions)
    }
}

#Preview {
    NavigationStack {
        CompanionDetailView(companionId: "test-id")
    }
}
