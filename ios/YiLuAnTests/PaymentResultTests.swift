import XCTest
@testable import YiLuAn

final class PaymentResultTests: XCTestCase {

    // MARK: - PaymentStatus Tests

    func testSuccessStatusProperties() {
        let status = PaymentStatus.success
        XCTAssertEqual(status.title, "支付成功")
        XCTAssertEqual(status.icon, "checkmark.circle.fill")
        XCTAssertEqual(status.defaultDescription, "您的订单已支付，请等待陪诊师接单")
    }

    func testFailStatusProperties() {
        let status = PaymentStatus.fail
        XCTAssertEqual(status.title, "支付失败")
        XCTAssertEqual(status.icon, "xmark.circle.fill")
        XCTAssertEqual(status.defaultDescription, "支付遇到问题，请重试")
    }

    func testCancelStatusProperties() {
        let status = PaymentStatus.cancel
        XCTAssertEqual(status.title, "支付取消")
        XCTAssertEqual(status.icon, "exclamationmark.circle.fill")
        XCTAssertEqual(status.defaultDescription, "您已取消支付，订单尚未完成")
    }

    func testPaymentStatusRawValues() {
        XCTAssertEqual(PaymentStatus(rawValue: "success"), .success)
        XCTAssertEqual(PaymentStatus(rawValue: "fail"), .fail)
        XCTAssertEqual(PaymentStatus(rawValue: "cancel"), .cancel)
        XCTAssertNil(PaymentStatus(rawValue: "unknown"))
    }
}
