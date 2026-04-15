import XCTest
@testable import YiLuAn

final class NewEndpointsAndModelsTests: XCTestCase {

    // MARK: - New API Endpoints

    func testBindPhoneEndpoint() {
        let endpoint = APIEndpoint.bindPhone
        XCTAssertEqual(endpoint.path, "auth/bind-phone")
        XCTAssertEqual(endpoint.method, .post)
        XCTAssertTrue(endpoint.requiresAuth)
    }

    func testSwitchRoleEndpoint() {
        let endpoint = APIEndpoint.switchRole
        XCTAssertEqual(endpoint.path, "users/me/switch-role")
        XCTAssertEqual(endpoint.method, .post)
        XCTAssertTrue(endpoint.requiresAuth)
    }

    func testWalletEndpoint() {
        let endpoint = APIEndpoint.wallet
        XCTAssertEqual(endpoint.path, "wallet")
        XCTAssertEqual(endpoint.method, .get)
        XCTAssertTrue(endpoint.requiresAuth)
    }

    func testWalletTransactionsEndpoint() {
        let endpoint = APIEndpoint.walletTransactions
        XCTAssertEqual(endpoint.path, "wallet/transactions")
        XCTAssertEqual(endpoint.method, .get)
        XCTAssertTrue(endpoint.requiresAuth)
    }

    // MARK: - New Request Models

    func testBindPhoneRequestEncoding() throws {
        let request = BindPhoneRequest(phone: "13800138000", code: "123456")
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(request)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: String]

        XCTAssertEqual(json?["phone"], "13800138000")
        XCTAssertEqual(json?["code"], "123456")
    }

    func testSwitchRoleRequestEncoding() throws {
        let request = SwitchRoleRequest(role: "companion")
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(request)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: String]

        XCTAssertEqual(json?["role"], "companion")
    }

    func testDeleteAccountRequestEncoding() throws {
        let request = DeleteAccountRequest(code: "654321")
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(request)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: String]

        XCTAssertEqual(json?["code"], "654321")
    }

    // MARK: - Companion Stats Response

    func testCompanionStatsDecoding() throws {
        let json = """
        {
            "today_orders": 3,
            "total_orders": 150,
            "avg_rating": 4.8,
            "total_earnings": 25000.00
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let stats = try decoder.decode(CompanionStatsResponse.self, from: json)

        XCTAssertEqual(stats.todayOrders, 3)
        XCTAssertEqual(stats.totalOrders, 150)
        XCTAssertEqual(stats.avgRating, 4.8, accuracy: 0.01)
        XCTAssertEqual(stats.totalEarnings, 25000.00, accuracy: 0.01)
    }

    // MARK: - Apply Companion Request

    func testApplyCompanionRequestEncoding() throws {
        let request = ApplyCompanionRequest(
            realName: "张三",
            idNumber: "110101199001011234",
            serviceArea: "朝阳区",
            bio: "专业陪诊5年"
        )
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(request)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: String]

        XCTAssertEqual(json?["real_name"], "张三")
        XCTAssertEqual(json?["id_number"], "110101199001011234")
        XCTAssertEqual(json?["service_area"], "朝阳区")
        XCTAssertEqual(json?["bio"], "专业陪诊5年")
    }

    func testApplyCompanionRequestOptionalFields() throws {
        let request = ApplyCompanionRequest(
            realName: "李四",
            idNumber: nil,
            serviceArea: nil,
            bio: nil
        )
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(request)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]

        XCTAssertEqual(json?["real_name"] as? String, "李四")
    }

    // MARK: - Notification Model

    func testNotificationTypeDecoding() throws {
        let types = ["order_status_changed", "new_message", "new_order", "review_received", "system"]
        let expected: [NotificationType] = [.orderStatusChanged, .newMessage, .newOrder, .reviewReceived, .system]

        for (raw, expected) in zip(types, expected) {
            let json = """
            {"id":"1","user_id":"u1","type":"\(raw)","title":"Title","body":"Body","is_read":false,"reference_id":null,"created_at":"2026-04-15T10:00:00Z"}
            """.data(using: .utf8)!

            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            decoder.dateDecodingStrategy = .iso8601
            let notification = try decoder.decode(AppNotification.self, from: json)
            XCTAssertEqual(notification.type, expected)
        }
    }
}
