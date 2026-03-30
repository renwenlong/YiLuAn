import SwiftUI

struct PatientHomeView: View {
    @StateObject private var companionViewModel = CompanionProfileViewModel()

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    // Service cards
                    VStack(alignment: .leading, spacing: 12) {
                        Text("选择服务")
                            .font(.headline)

                        LazyVGrid(columns: [
                            GridItem(.flexible()),
                            GridItem(.flexible()),
                            GridItem(.flexible())
                        ], spacing: 12) {
                            ForEach(ServiceType.allCases, id: \.rawValue) { service in
                                NavigationLink {
                                    CreateOrderView()
                                } label: {
                                    serviceCard(service)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                    .padding(.horizontal)

                    // Recommended companions
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Text("推荐陪诊师")
                                .font(.headline)
                            Spacer()
                            NavigationLink("更多") {
                                CompanionListView()
                                    .navigationTitle("陪诊师列表")
                            }
                            .font(.subheadline)
                        }
                        .padding(.horizontal)

                        if companionViewModel.isLoading && companionViewModel.companions.isEmpty {
                            ProgressView()
                                .frame(maxWidth: .infinity, minHeight: 100)
                        } else if companionViewModel.companions.isEmpty {
                            Text("暂无推荐")
                                .foregroundStyle(.secondary)
                                .frame(maxWidth: .infinity, minHeight: 100)
                        } else {
                            ScrollView(.horizontal, showsIndicators: false) {
                                HStack(spacing: 12) {
                                    ForEach(companionViewModel.companions.prefix(5)) { companion in
                                        NavigationLink(
                                            destination: CompanionDetailView(companionId: companion.id)
                                        ) {
                                            companionCard(companion)
                                        }
                                        .buttonStyle(.plain)
                                    }
                                }
                                .padding(.horizontal)
                            }
                        }
                    }
                }
                .padding(.top)
            }
            .navigationTitle("医路安")
            .task {
                await companionViewModel.loadCompanions()
            }
        }
    }

    private func serviceCard(_ service: ServiceType) -> some View {
        VStack(spacing: 8) {
            Image(systemName: serviceIcon(service))
                .font(.title2)
                .foregroundStyle(.blue)
            Text(service.displayName)
                .font(.caption)
                .foregroundStyle(.primary)
            Text("¥\(service.price as NSDecimalNumber)")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 16)
        .background(Color(.systemGray6))
        .cornerRadius(12)
    }

    private func serviceIcon(_ service: ServiceType) -> String {
        switch service {
        case .fullAccompany: return "person.2.fill"
        case .halfAccompany: return "person.fill"
        case .errand: return "doc.text.fill"
        }
    }

    private func companionCard(_ companion: CompanionProfile) -> some View {
        VStack(spacing: 8) {
            if let urlString = companion.avatarUrl, let url = URL(string: urlString) {
                AsyncImage(url: url) { image in
                    image
                        .resizable()
                        .scaledToFill()
                } placeholder: {
                    ProgressView()
                }
                .frame(width: 56, height: 56)
                .clipShape(Circle())
            } else {
                Image(systemName: "person.circle.fill")
                    .font(.system(size: 44))
                    .foregroundStyle(.gray)
                    .frame(width: 56, height: 56)
            }

            Text(companion.displayName ?? companion.realName)
                .font(.caption)
                .lineLimit(1)

            HStack(spacing: 2) {
                Image(systemName: "star.fill")
                    .font(.caption2)
                    .foregroundStyle(.orange)
                Text(String(format: "%.1f", companion.avgRating))
                    .font(.caption2)
            }
        }
        .frame(width: 90)
        .padding(.vertical, 12)
        .background(Color(.systemGray6))
        .cornerRadius(12)
    }
}

#Preview {
    PatientHomeView()
}
