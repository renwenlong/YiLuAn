import XCTest
@testable import YiLuAn

final class APIEndpointTests: XCTestCase {

    func testDeleteAccountEndpoint() {
        let endpoint = APIEndpoint.deleteAccount
        XCTAssertEqual(endpoint.path, "users/me")
        XCTAssertEqual(endpoint.method, .delete)
        XCTAssertTrue(endpoint.requiresAuth)
    }

    func testPayOrderEndpoint() {
        let endpoint = APIEndpoint.payOrder(id: "test-id")
        XCTAssertEqual(endpoint.path, "orders/test-id/pay")
        XCTAssertEqual(endpoint.method, .post)
        XCTAssertTrue(endpoint.requiresAuth)
    }

    func testRefundOrderEndpoint() {
        let endpoint = APIEndpoint.refundOrder(id: "abc-123")
        XCTAssertEqual(endpoint.path, "orders/abc-123/refund")
        XCTAssertEqual(endpoint.method, .post)
        XCTAssertTrue(endpoint.requiresAuth)
    }

    func testSendOTPDoesNotRequireAuth() {
        let endpoint = APIEndpoint.sendOTP
        XCTAssertEqual(endpoint.method, .post)
        XCTAssertFalse(endpoint.requiresAuth)
    }

    func testEndpointURLConstruction() {
        let endpoint = APIEndpoint.me
        let url = endpoint.url
        XCTAssertTrue(url.absoluteString.contains("api/v1/users/me"))
    }
}
