import XCTest
@testable import YiLuAn

@MainActor
final class ReviewViewModelTests: XCTestCase {

    var viewModel: ReviewViewModel!

    override func setUp() {
        super.setUp()
        viewModel = ReviewViewModel()
    }

    override func tearDown() {
        viewModel = nil
        super.tearDown()
    }

    func testInitialState() {
        XCTAssertNil(viewModel.review)
        XCTAssertTrue(viewModel.reviews.isEmpty)
        XCTAssertFalse(viewModel.isLoading)
        XCTAssertNil(viewModel.errorMessage)
        XCTAssertEqual(viewModel.total, 0)
        XCTAssertFalse(viewModel.submitSuccess)
    }

    // MARK: - Request 体编码（snake_case 对齐后端）

    func testCreateReviewRequestEncoding() throws {
        let request = CreateReviewRequest(rating: 5, content: "服务非常好")
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(request)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]

        XCTAssertEqual(json?["rating"] as? Int, 5)
        XCTAssertEqual(json?["content"] as? String, "服务非常好")
    }

    // MARK: - 分页响应 decode

    func testReviewListResponseDecoding() throws {
        let json = """
        {
            "items": [
                {
                    "id": "rev-1",
                    "order_id": "ord-1",
                    "companion_id": "cmp-1",
                    "patient_id": "pat-1",
                    "rating": 5,
                    "comment": "很好",
                    "patient_name": "张三",
                    "created_at": "2026-01-15T10:00:00Z"
                }
            ],
            "total": 1
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        let response = try decoder.decode(ReviewListResponse.self, from: json)

        XCTAssertEqual(response.total, 1)
        XCTAssertEqual(response.items.count, 1)
        XCTAssertEqual(response.items.first?.rating, 5)
    }

    func testReviewListResponseEmptyDecoding() throws {
        let json = """
        { "items": [], "total": 0 }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let response = try decoder.decode(ReviewListResponse.self, from: json)

        XCTAssertTrue(response.items.isEmpty)
        XCTAssertEqual(response.total, 0)
    }

    // MARK: - 空态：分页第一页空 + view 层"暂无评价"占位的契约

    /// loadCompanionReviews 在 page=1 时会覆盖 reviews。这里只验证 ViewModel 的内部状态契约：
    /// 默认状态下 reviews.isEmpty == true，且非 loading —— 这是 CompanionReviewSection
    /// 与 ReviewListView 展示"暂无评价"占位的前提。
    func testEmptyStateBeforeAnyLoad() {
        XCTAssertTrue(viewModel.reviews.isEmpty)
        XCTAssertFalse(viewModel.isLoading)
    }
}
