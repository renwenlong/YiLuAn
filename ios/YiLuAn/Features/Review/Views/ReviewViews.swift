import SwiftUI

struct WriteReviewView: View {
    let orderId: String
    @StateObject private var viewModel = ReviewViewModel()
    @Environment(\.dismiss) private var dismiss
    @State private var rating = 5
    @State private var content = ""

    var body: some View {
        NavigationStack {
            Form {
                Section("评分") {
                    HStack {
                        ForEach(1...5, id: \.self) { star in
                            Image(systemName: star <= rating ? "star.fill" : "star")
                                .foregroundColor(.orange)
                                .onTapGesture { rating = star }
                        }
                    }
                    .font(.title2)
                }

                Section("评价内容") {
                    TextEditor(text: $content)
                        .frame(minHeight: 100)
                }

                if let error = viewModel.errorMessage {
                    Section {
                        Text(error).foregroundColor(.red)
                    }
                }
            }
            .navigationTitle("写评价")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("提交") {
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
    let companionId: String
    @StateObject private var viewModel = ReviewViewModel()

    var body: some View {
        List {
            ForEach(viewModel.reviews) { review in
                ReviewRowView(review: review)
                    .padding(.vertical, 4)
            }
        }
        .navigationTitle("评价列表")
        .task { await viewModel.loadCompanionReviews(companionId: companionId) }
        .overlay {
            if viewModel.reviews.isEmpty && !viewModel.isLoading {
                ContentUnavailableView("暂无评价", systemImage: "star.slash")
            }
        }
    }
}

/// 单条评价展示行，在评价列表与 CompanionDetail 嵌入区间复用。
struct ReviewRowView: View {
    let review: Review

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(review.patientName ?? "患者")
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
    let companionId: String
    /// 嵌入页面只展示前 N 条；点击“查看全部” push 完整 ReviewListView。
    let previewLimit: Int = 5

    @StateObject private var viewModel = ReviewViewModel()

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.md) {
            HStack(alignment: .firstTextBaseline) {
                Text("用户评价")
                    .font(.dsTitle)
                    .foregroundStyle(Color.textPrimary)
                Spacer()
                if viewModel.total > 0 {
                    Text("共 \(viewModel.total) 条")
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
                    Text("暂无评价")
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
                            Text("查看全部评价")
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
