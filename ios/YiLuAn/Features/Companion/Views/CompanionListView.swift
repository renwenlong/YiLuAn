import SwiftUI

struct CompanionListView: View {
    @StateObject private var viewModel = CompanionProfileViewModel()
    @EnvironmentObject var loc: LocalizationManager
    @State private var searchText = ""
    @State private var selectedArea = ""

    // 注意: areaOptions 的城市名是传给后端的筛选 value(保持中文), 显示时经 areaDisplayKey 走字典
    private let areaOptions = ["全部", "北京", "上海", "广州", "深圳", "杭州", "成都"]

    private func areaDisplayKey(_ area: String) -> String {
        switch area {
        case "全部": return "order.tabAll"
        case "北京": return "profileEdit.defaultCity"
        case "上海": return "companion.cityShanghai"
        case "广州": return "companion.cityGuangzhou"
        case "深圳": return "companion.cityShenzhen"
        case "杭州": return "companion.cityHangzhou"
        case "成都": return "companion.cityChengdu"
        default: return area
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            // Area filter
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(areaOptions, id: \.self) { area in
                        Button {
                            selectedArea = area == "全部" ? "" : area
                            Task { await loadData() }
                        } label: {
                            Text(loc.t(areaDisplayKey(area)))
                                .font(.subheadline)
                                .padding(.horizontal, 14)
                                .padding(.vertical, 6)
                                .background(
                                    isAreaSelected(area) ? Color.blue : Color(.systemGray6)
                                )
                                .foregroundStyle(isAreaSelected(area) ? .white : .primary)
                                .cornerRadius(16)
                        }
                    }
                }
                .padding(.horizontal)
                .padding(.vertical, 8)
            }

            // Companion list
            if viewModel.isLoading && viewModel.companions.isEmpty {
                Spacer()
                ProgressView()
                Spacer()
            } else if viewModel.companions.isEmpty {
                Spacer()
                VStack(spacing: 12) {
                    Image(systemName: "person.2.slash")
                        .font(.largeTitle)
                        .foregroundStyle(.secondary)
                    Text(loc.t("companion.noCompanions"))
                        .foregroundStyle(.secondary)
                }
                Spacer()
            } else {
                ScrollView {
                    LazyVStack(spacing: 12) {
                        ForEach(viewModel.companions) { companion in
                            NavigationLink(destination: CompanionDetailView(companionId: companion.id)) {
                                companionCard(companion)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal)
                    .padding(.top, 4)
                }
            }
        }
        .searchable(text: $searchText, prompt: loc.t("companion.searchCompanion"))
        .onSubmit(of: .search) {
            Task { await loadData() }
        }
        .task {
            await loadData()
        }
        .alert(loc.t("companion.error"), isPresented: .init(
            get: { viewModel.errorMessage != nil },
            set: { if !$0 { viewModel.errorMessage = nil } }
        )) {
            Button(loc.t("companion.ok"), role: .cancel) {}
        } message: {
            Text(viewModel.errorMessage ?? "")
        }
    }

    private func isAreaSelected(_ area: String) -> Bool {
        if area == "全部" {
            return selectedArea.isEmpty
        }
        return selectedArea == area
    }

    private func loadData() async {
        await viewModel.loadCompanions(
            area: selectedArea.isEmpty ? nil : selectedArea,
            search: searchText.isEmpty ? nil : searchText
        )
    }

    private func companionCard(_ companion: CompanionProfile) -> some View {
        HStack(spacing: 12) {
            // Avatar
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

            // Info
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(companion.displayName ?? companion.realName)
                        .font(.headline)

                    if companion.verificationStatus == "verified" {
                        Image(systemName: "checkmark.seal.fill")
                            .font(.caption)
                            .foregroundStyle(.green)
                    }
                }

                HStack(spacing: 4) {
                    Image(systemName: "star.fill")
                        .font(.caption2)
                        .foregroundStyle(.orange)
                    Text(String(format: "%.1f", companion.avgRating))
                        .font(.caption)
                    Text(loc.t("companion.orderCount", companion.totalOrders))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                if let area = companion.serviceArea, !area.isEmpty {
                    Text(area)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }

            Spacer()

            Image(systemName: "chevron.right")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(12)
        .shadow(color: Color.black.opacity(0.05), radius: 4, y: 2)
    }
}

#Preview {
    NavigationStack {
        CompanionListView()
            .navigationTitle("陪诊师列表")
    }
}
