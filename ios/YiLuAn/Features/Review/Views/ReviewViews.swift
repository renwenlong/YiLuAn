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
