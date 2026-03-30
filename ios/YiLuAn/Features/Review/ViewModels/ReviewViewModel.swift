import SwiftUI

struct CreateReviewRequest: Encodable {
    let rating: Int
    let content: String
}

struct ReviewListResponse: Decodable {
    let items: [Review]
    let total: Int
}

@MainActor
class ReviewViewModel: ObservableObject {
    @Published var review: Review?
    @Published var reviews: [Review] = []
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var total = 0
    @Published var submitSuccess = false

    func submitReview(orderId: String, rating: Int, content: String) async {
        isLoading = true
        errorMessage = nil
        submitSuccess = false
        defer { isLoading = false }

        do {
            let body = CreateReviewRequest(rating: rating, content: content)
            let result: Review = try await APIClient.shared.request(
                .createReview(orderId: orderId), body: body
            )
            review = result
            submitSuccess = true
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func loadReview(orderId: String) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            review = try await APIClient.shared.request(.orderReview(orderId: orderId))
        } catch let error as APIError {
            if case .httpError(let code, _) = error, code == 404 {
                review = nil
            } else {
                errorMessage = error.localizedDescription
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func loadCompanionReviews(companionId: String, page: Int = 1) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let response: ReviewListResponse = try await APIClient.shared.request(
                .companionReviews(companionId: companionId),
                queryItems: [URLQueryItem(name: "page", value: "\(page)")]
            )
            if page == 1 {
                reviews = response.items
            } else {
                reviews.append(contentsOf: response.items)
            }
            total = response.total
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
