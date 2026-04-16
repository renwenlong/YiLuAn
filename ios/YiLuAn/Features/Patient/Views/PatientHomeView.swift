import SwiftUI

struct PatientHomeView: View {
    @StateObject private var companionViewModel = CompanionProfileViewModel()

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: Spacing.xl) {
                    // Hero header
                    ZStack(alignment: .bottomLeading) {
                        AppGradient.hero
                            .frame(height: 140)
                            .ignoresSafeArea(edges: .top)

                        Text("找到您身边的\n专业陪诊师")
                            .font(.dsH1)
                            .foregroundStyle(.white)
                            .padding(.horizontal, Spacing.xl)
                            .padding(.bottom, Spacing.lg)
                    }

                    // Service cards
                    VStack(alignment: .leading, spacing: Spacing.md) {
                        Text("选择服务")
                            .font(.dsTitle)
                            .foregroundStyle(Color.textPrimary)
                            .padding(.horizontal, Spacing.lg)

                        LazyVGrid(columns: [
                            GridItem(.flexible()),
                            GridItem(.flexible()),
                            GridItem(.flexible())
                        ], spacing: Spacing.md) {
                            ForEach(ServiceType.allCases, id: \.rawValue) { service in
                                NavigationLink {
                                    CreateOrderView()
                                } label: {
                                    serviceCard(service)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                        .padding(.horizontal, Spacing.lg)
                    }

                    // Recommended companions
                    VStack(alignment: .leading, spacing: Spacing.md) {
                        HStack {
                            Text("推荐陪诊师")
                                .font(.dsTitle)
                                .foregroundStyle(Color.textPrimary)
                            Spacer()
                            NavigationLink {
                                CompanionListView()
                                    .navigationTitle("陪诊师列表")
                            } label: {
                                HStack(spacing: 4) {
                                    Text("更多")
                                        .font(.dsSubheadline)
                                    Image(systemName: "chevron.right")
                                        .font(.system(size: 10, weight: .semibold))
                                }
                                .foregroundStyle(Color.brand)
                            }
                        }
                        .padding(.horizontal, Spacing.lg)

                        if companionViewModel.isLoading && companionViewModel.companions.isEmpty {
                            HStack(spacing: Spacing.md) {
                                ForEach(0..<3, id: \.self) { _ in
                                    RoundedRectangle(cornerRadius: CornerRadius.lg)
                                        .fill(Color.bgSkeleton.opacity(0.5))
                                        .frame(width: 110, height: 140)
                                }
                            }
                            .padding(.horizontal, Spacing.lg)
                        } else if companionViewModel.companions.isEmpty {
                            VStack(spacing: Spacing.sm) {
                                Image(systemName: "person.2.slash")
                                    .font(.system(size: 32))
                                    .foregroundStyle(Color.textHint)
                                Text("暂无推荐，稍后再来看看")
                                    .font(.dsSubheadline)
                                    .foregroundStyle(Color.textHint)
                            }
                            .frame(maxWidth: .infinity, minHeight: 100)
                        } else {
                            ScrollView(.horizontal, showsIndicators: false) {
                                HStack(spacing: Spacing.md) {
                                    ForEach(companionViewModel.companions.prefix(5)) { companion in
                                        NavigationLink(
                                            destination: CompanionDetailView(companionId: companion.id)
                                        ) {
                                            companionCard(companion)
                                        }
                                        .buttonStyle(.plain)
                                    }
                                }
                                .padding(.horizontal, Spacing.lg)
                            }
                        }
                    }
                }
                .padding(.bottom, 120)
            }
            .background(Color.bgPage)
            .navigationTitle("医路安")
            .task {
                await companionViewModel.loadCompanions()
            }
        }
    }

    private func serviceCard(_ service: ServiceType) -> some View {
        VStack(spacing: Spacing.sm) {
            ZStack {
                Circle()
                    .fill(Color.brand.opacity(0.1))
                    .frame(width: 44, height: 44)

                Image(systemName: serviceIcon(service))
                    .font(.system(size: 20))
                    .foregroundStyle(Color.brand)
            }

            Text(service.displayName)
                .font(.dsSubheadline)
                .fontWeight(.medium)
                .foregroundStyle(Color.textPrimary)

            Text("¥\(service.price as NSDecimalNumber)")
                .font(.dsSmall)
                .foregroundStyle(Color.accent)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, Spacing.lg)
        .background(Color.bgCard)
        .cornerRadius(CornerRadius.lg)
        .shadow(color: .black.opacity(0.05), radius: 4, x: 0, y: 2)
    }

    private func serviceIcon(_ service: ServiceType) -> String {
        switch service {
        case .fullAccompany: return "person.2.fill"
        case .halfAccompany: return "person.fill"
        case .errand: return "doc.text.fill"
        }
    }

    private func companionCard(_ companion: CompanionProfile) -> some View {
        VStack(spacing: Spacing.sm) {
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
                .overlay(Circle().stroke(.white, lineWidth: 2))
                .shadow(color: .black.opacity(0.1), radius: 4, x: 0, y: 2)
            } else {
                ZStack {
                    Circle()
                        .fill(AppGradient.primary)
                        .frame(width: 56, height: 56)

                    Text(String(companion.displayName?.prefix(1) ?? companion.realName.prefix(1)))
                        .font(.dsTitle)
                        .foregroundStyle(.white)
                }
                .shadow(color: .brand.opacity(0.2), radius: 4, x: 0, y: 2)
            }

            Text(companion.displayName ?? companion.realName)
                .font(.dsSubheadline)
                .fontWeight(.medium)
                .foregroundStyle(Color.textPrimary)
                .lineLimit(1)

            HStack(spacing: 2) {
                Image(systemName: "star.fill")
                    .font(.system(size: 10))
                    .foregroundStyle(Color.warning)
                Text(String(format: "%.1f", companion.avgRating))
                    .font(.dsSmall)
                    .foregroundStyle(Color.textSecondary)
            }
        }
        .frame(width: 110)
        .padding(.vertical, Spacing.md)
        .background(Color.bgCard)
        .cornerRadius(CornerRadius.lg)
        .shadow(color: .black.opacity(0.05), radius: 4, x: 0, y: 2)
    }
}

#Preview {
    PatientHomeView()
}
