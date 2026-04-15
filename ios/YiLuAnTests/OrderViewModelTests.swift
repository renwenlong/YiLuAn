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
            description: "需要陪诊"
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
}
