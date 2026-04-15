import XCTest
@testable import YiLuAn

final class ModelTests: XCTestCase {

    // MARK: - ServiceType Tests

    func testServiceTypeDisplayNames() {
        XCTAssertEqual(ServiceType.fullAccompany.displayName, "全程陪诊")
        XCTAssertEqual(ServiceType.halfAccompany.displayName, "半程陪诊")
        XCTAssertEqual(ServiceType.errand.displayName, "代办")
    }

    func testServiceTypePrices() {
        XCTAssertEqual(ServiceType.fullAccompany.price, 299)
        XCTAssertEqual(ServiceType.halfAccompany.price, 199)
        XCTAssertEqual(ServiceType.errand.price, 149)
    }

    func testServiceTypeRawValues() {
        XCTAssertEqual(ServiceType.fullAccompany.rawValue, "full_accompany")
        XCTAssertEqual(ServiceType.halfAccompany.rawValue, "half_accompany")
        XCTAssertEqual(ServiceType.errand.rawValue, "errand")
    }

    // MARK: - OrderStatus Tests

    func testOrderStatusDisplayNames() {
        XCTAssertEqual(OrderStatus.created.displayName, "待接单")
        XCTAssertEqual(OrderStatus.accepted.displayName, "已接单")
        XCTAssertEqual(OrderStatus.inProgress.displayName, "进行中")
        XCTAssertEqual(OrderStatus.completed.displayName, "已完成")
        XCTAssertEqual(OrderStatus.reviewed.displayName, "已评价")
        XCTAssertEqual(OrderStatus.cancelledByPatient.displayName, "患者取消")
        XCTAssertEqual(OrderStatus.cancelledByCompanion.displayName, "陪诊师取消")
    }

    func testOrderStatusRawValues() {
        XCTAssertEqual(OrderStatus.inProgress.rawValue, "in_progress")
        XCTAssertEqual(OrderStatus.cancelledByPatient.rawValue, "cancelled_by_patient")
        XCTAssertEqual(OrderStatus.cancelledByCompanion.rawValue, "cancelled_by_companion")
    }

    // MARK: - UserRole Tests

    func testUserRoleRawValues() {
        XCTAssertEqual(UserRole.patient.rawValue, "patient")
        XCTAssertEqual(UserRole.companion.rawValue, "companion")
    }
}
