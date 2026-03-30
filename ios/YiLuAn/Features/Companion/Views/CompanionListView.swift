import SwiftUI

struct CompanionListView: View {
    @StateObject private var viewModel = CompanionProfileViewModel()
    @State private var searchText = ""
    @State private var selectedArea = ""

    private let areaOptions = ["全部", "北京", "上海", "广州", "深圳", "杭州", "成都"]

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
                            Text(area)
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
                    Text("暂无陪诊师")
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
        .searchable(text: $searchText, prompt: "搜索陪诊师")
        .onSubmit(of: .search) {
            Task { await loadData() }
        }
        .task {
            await loadData()
        }
        .alert("错误", isPresented: .init(
            get: { viewModel.errorMessage != nil },
            set: { if !$0 { viewModel.errorMessage = nil } }
        )) {
            Button("确定", role: .cancel) {}
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
                    Text("(\(companion.totalOrders)单)")
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
