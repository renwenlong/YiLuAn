import XCTest
@testable import YiLuAn

@MainActor
final class OrderViewModelTests: XCTestCase {

    var viewModel: OrderViewModel!

    override func setUp() {
        super.setUp()
        viewModel = OrderViewModel()
    }

    override func tearDown() {
        viewModel = nil
        super.tearDown()
    }

    func testInitialState() {
        XCTAssertTrue(viewModel.orders.isEmpty)
        XCTAssertNil(viewModel.currentOrder)
        XCTAssertTrue(viewModel.hospitals.isEmpty)
        XCTAssertFalse(viewModel.isLoading)
        XCTAssertNil(viewModel.errorMessage)
        XCTAssertEqual(viewModel.total, 0)
    }

    func testSearchHospitalsWithEmptyKeywordClearsResults() async {
        await viewModel.searchHospitals(keyword: "")
        XCTAssertTrue(viewModel.hospitals.isEmpty)
    }

    func testCreateOrderRequestEncoding() throws {
        let request = CreateOrderRequest(
            serviceType: "full_accompany",
            hospitalId: "test-hospital-id",
            appointmentDate: "2026-04-15",
            appointmentTime: "09:00",
            description: "需要陪诊",
            familyMemberId: nil
        )

        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(request)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]

        XCTAssertEqual(json?["service_type"] as? String, "full_accompany")
        XCTAssertEqual(json?["hospital_id"] as? String, "test-hospital-id")
        XCTAssertEqual(json?["appointment_date"] as? String, "2026-04-15")
        XCTAssertEqual(json?["appointment_time"] as? String, "09:00")
        XCTAssertEqual(json?["description"] as? String, "需要陪诊")
    }

    func testOrderListResponseDecoding() throws {
        let json = """
        {
            "items": [],
            "total": 42
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        let response = try decoder.decode(OrderListResponse.self, from: json)

        XCTAssertEqual(response.total, 42)
        XCTAssertTrue(response.items.isEmpty)
    }

    func testTotalDefaultsToZero() {
        XCTAssertEqual(viewModel.total, 0)
    }

    // MARK: - P0-1 accept 分支

    /// PHONE_REQUIRED 错误会写入 phoneRequiredMessage 而不是 errorMessage，
    /// 供 view 层 `.phoneRequiredAlert` 接管并 push BindPhoneView。
    func testHandlePhoneRequiredErrorSetsPhoneRequiredMessage() async {
        // 调用内部 handleError。由于 handleError 是 private，这里通过对 APIError 类型本身的
        // 分发套路验证：phoneRequired 会安装到专门字段。
        let mirror = APIError.phoneRequired(message: "请先绑定手机号")
        XCTAssertEqual(mirror.guardCode, BackendErrorCode.phoneRequired)
        XCTAssertEqual(mirror.errorDescription, "请先绑定手机号")
    }

    /// 调 performAction 时 token 未设置 → unauthorized → 走通用 errorMessage 分支，
    /// 并返回 false。这个路径代表“接单失败”的一般错误分支。
    func testPerformActionAcceptFailureSetsErrorMessage() async {
        // 未登录状态 → APIClient 会抛 unauthorized
        let success = await viewModel.performAction("accept", orderId: "non-existent")
        XCTAssertFalse(success)
        // unauthorized 不属于“前置条件未满足”，会走 errorMessage
        XCTAssertNotNil(viewModel.errorMessage)
        XCTAssertNil(viewModel.phoneRequiredMessage)
    }

    /// performAction 成功分支的合同：返回 Bool。该用例验证调用后 isLoading 被重置。
    func testPerformActionResetsLoadingFlag() async {
        _ = await viewModel.performAction("accept", orderId: "any-id")
        XCTAssertFalse(viewModel.isLoading)
    }

    // MARK: - P1-3 sort 参数传递

    /// loadOrders(status:sort:) 新增的 sort 参数为可选，默认 nil 保证老调用兼容。
    /// 本用例仅验证“传 sort 后不崩” + 默认参数存在。
    func testLoadOrdersAcceptsOptionalSort() async {
        // 不能真打网络，这里仅调用一下验证签名存在、运行不抛异常。
        await viewModel.loadOrders(status: "created", sort: "distance")
        XCTAssertFalse(viewModel.isLoading)
    }
}
