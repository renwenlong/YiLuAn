import SwiftUI

struct CompanionDetailView: View {
    let companionId: String
    @StateObject private var viewModel = CompanionProfileViewModel()

    var body: some View {
        ScrollView {
            if viewModel.isLoading {
                ProgressView()
                    .frame(maxWidth: .infinity, minHeight: 300)
            } else if let companion = viewModel.selectedCompanion {
                VStack(spacing: 20) {
                    // Avatar and name
                    VStack(spacing: 12) {
                        avatarView(companion)

                        Text(companion.displayName ?? companion.realName)
                            .font(.title2.bold())

                        // Rating and orders
                        HStack(spacing: 16) {
                            ratingView(companion.avgRating)
                            Text("\(companion.totalOrders) 单")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        }
                    }
                    .padding(.top, 8)

                    Divider()

                    // Service area
                    if let area = companion.serviceArea, !area.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("服务区域")
                                .font(.headline)

                            HStack {
                                ForEach(area.components(separatedBy: ","), id: \.self) { tag in
                                    Text(tag.trimmingCharacters(in: .whitespaces))
                                        .font(.caption)
                                        .padding(.horizontal, 10)
                                        .padding(.vertical, 4)
                                        .background(Color.blue.opacity(0.1))
                                        .foregroundStyle(.blue)
                                        .cornerRadius(12)
                                }
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal)
                    }

                    // Bio
                    if let bio = companion.bio, !bio.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("个人简介")
                                .font(.headline)
                            Text(bio)
                                .font(.body)
                                .foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal)
                    }

                    // Verification badge
                    HStack {
                        Image(systemName: verificationIcon(companion.verificationStatus))
                        Text(verificationLabel(companion.verificationStatus))
                            .font(.footnote)
                    }
                    .foregroundStyle(verificationColor(companion.verificationStatus))
                    .padding(.horizontal)

                    Spacer(minLength: 20)

                    // Book button
                    NavigationLink {
                        CreateOrderView()
                    } label: {
                        Text("预约陪诊")
                            .font(.headline)
                            .foregroundStyle(.white)
                            .frame(maxWidth: .infinity)
                            .padding()
                            .background(Color.blue)
                            .cornerRadius(12)
                    }
                    .padding(.horizontal)
                }
            } else if let error = viewModel.errorMessage {
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.largeTitle)
                        .foregroundStyle(.secondary)
                    Text(error)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, minHeight: 300)
            }
        }
        .navigationTitle("陪诊师详情")
        .navigationBarTitleDisplayMode(.inline)
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
            .frame(width: 100, height: 100)
            .clipShape(Circle())
        } else {
            Image(systemName: "person.circle.fill")
                .font(.system(size: 80))
                .foregroundStyle(.gray)
                .frame(width: 100, height: 100)
        }
    }

    private func ratingView(_ rating: Double) -> some View {
        HStack(spacing: 2) {
            ForEach(1...5, id: \.self) { star in
                Image(systemName: star <= Int(rating.rounded()) ? "star.fill" : "star")
                    .font(.caption)
                    .foregroundStyle(.orange)
            }
            Text(String(format: "%.1f", rating))
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
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
        case "verified": return .green
        case "pending": return .orange
        case "rejected": return .red
        default: return .secondary
        }
    }
}

#Preview {
    NavigationStack {
        CompanionDetailView(companionId: "test-id")
    }
}
