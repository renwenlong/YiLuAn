import SwiftUI

struct WriteReviewView: View {
    @EnvironmentObject var loc: LocalizationManager
    let orderId: String
    @StateObject private var viewModel = ReviewViewModel()
    @Environment(\.dismiss) private var dismiss
    @State private var rating = 5
    @State private var content = ""

    var body: some View {
        NavigationStack {
            Form {
                Section(loc.t("review.ratingSection")) {
                    HStack {
                        ForEach(1...5, id: \.self) { star in
                            Image(systemName: star <= rating ? "star.fill" : "star")
                                .foregroundColor(.orange)
                                .onTapGesture { rating = star }
                        }
                    }
                    .font(.title2)
                }

                Section(loc.t("review.contentSection")) {
                    TextEditor(text: $content)
                        .frame(minHeight: 100)
                }

                if let error = viewModel.errorMessage {
                    Section {
                        Text(error).foregroundColor(.red)
                    }
                }
            }
            .navigationTitle(loc.t("review.writeTitle"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(loc.t("common.cancel")) { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(loc.t("common.submit")) {
                        Task {
                            await viewModel.submitReview(
                                orderId: orderId, rating: rating, content: content
                            )
                            if viewModel.submitSuccess { dismiss() }
                        }
                    }
                    .disabled(content.count < 5 || viewModel.isLoading)
                }
            }
        }
    }
}

struct ReviewListView: View {
    @EnvironmentObject var loc: LocalizationManager
    let companionId: String
    @StateObject private var viewModel = ReviewViewModel()

    var body: some View {
        List {
            ForEach(viewModel.reviews) { review in
                ReviewRowView(review: review)
                    .padding(.vertical, 4)
            }
        }
        .navigationTitle(loc.t("review.listTitle"))
        .task { await viewModel.loadCompanionReviews(companionId: companionId) }
        .overlay {
            if viewModel.reviews.isEmpty && !viewModel.isLoading {
                ContentUnavailableView(loc.t("review.empty"), systemImage: "star.slash")
            }
        }
    }
}

/// 单条评价展示行，在评价列表与 CompanionDetail 嵌入区间复用。
struct ReviewRowView: View {
    @EnvironmentObject var loc: LocalizationManager
    let review: Review

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(review.patientName ?? loc.t("review.patient"))
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                Spacer()
                HStack(spacing: 2) {
                    ForEach(1...5, id: \.self) { star in
                        Image(systemName: star <= review.rating ? "star.fill" : "star")
                            .font(.caption)
                            .foregroundColor(.orange)
                    }
                }
            }
            if let comment = review.comment {
                Text(comment)
                    .font(.body)
            }
        }
    }
}

/// 供 CompanionDetailView 嵌入使用的评价区。
///
/// 不使用 `List`（避免与外部 ScrollView 产生嵌套滚动 / 高度不确定的问题），
/// 与小程序 `wechat/pages/companion-detail/index.wxml` 底部的评价区行为对齐。
struct CompanionReviewSection: View {
    @EnvironmentObject var loc: LocalizationManager
    let companionId: String
    /// 嵌入页面只展示前 N 条；点击“查看全部” push 完整 ReviewListView。
    let previewLimit: Int = 5

    @StateObject private var viewModel = ReviewViewModel()

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.md) {
            HStack(alignment: .firstTextBaseline) {
                Text(loc.t("review.userReviews"))
                    .font(.dsTitle)
                    .foregroundStyle(Color.textPrimary)
                Spacer()
                if viewModel.total > 0 {
                    Text(loc.t("review.totalCount", "\(viewModel.total)"))
                        .font(.dsSmall)
                        .foregroundStyle(Color.textHint)
                }
            }

            if viewModel.isLoading && viewModel.reviews.isEmpty {
                ProgressView()
                    .frame(maxWidth: .infinity, minHeight: 80)
            } else if viewModel.reviews.isEmpty {
                VStack(spacing: Spacing.sm) {
                    Image(systemName: "star.slash")
                        .font(.system(size: 28))
                        .foregroundStyle(Color.textHint)
                    Text(loc.t("review.empty"))
                        .font(.dsBody)
                        .foregroundStyle(Color.textSecondary)
                }
                .frame(maxWidth: .infinity, minHeight: 80)
            } else {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(viewModel.reviews.prefix(previewLimit))) { review in
                        ReviewRowView(review: review)
                            .padding(.vertical, Spacing.sm)
                        Divider()
                    }
                }

                if viewModel.total > previewLimit {
                    NavigationLink {
                        ReviewListView(companionId: companionId)
                    } label: {
                        HStack {
                            Text(loc.t("review.viewAll"))
                            Image(systemName: "chevron.right")
                        }
                        .font(.dsSubheadline)
                        .foregroundStyle(Color.brand)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, Spacing.sm)
                    }
                }
            }
        }
        .task {
            await viewModel.loadCompanionReviews(companionId: companionId)
        }
    }
}
