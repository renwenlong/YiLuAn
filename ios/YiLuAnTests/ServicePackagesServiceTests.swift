import XCTest
@testable import YiLuAn

/// S2-REQ-003-P5c · ServicePackage Codable + ServicePackagesService fallback 单测
///
/// 注意：不连真后端，只验：
/// (a) ServicePackage Codable 解码兼容 price string/number 两种格式
/// (b) ServicePackagesService.fallbackPackages 三档与 ServiceType enum 一致
/// (c) Order Codable 解码兼容 service_name_snapshot/service_price_snapshot 可选字段
@MainActor
final class ServicePackagesServiceTests: XCTestCase {

    func testServicePackageDecodingWithStringPrice() throws {
        let json = """
        {
            "code": "full_accompany",
            "name": "全程陪诊",
            "price": "299.00",
            "sort_order": 10,
            "description": "全程陪诊服务"
        }
        """.data(using: .utf8)!
        let decoder = JSONDecoder()
        let pkg = try decoder.decode(ServicePackage.self, from: json)
        XCTAssertEqual(pkg.code, "full_accompany")
        XCTAssertEqual(pkg.name, "全程陪诊")
        XCTAssertEqual(pkg.price, Decimal(299))
        XCTAssertEqual(pkg.sortOrder, 10)
        XCTAssertEqual(pkg.description, "全程陪诊服务")
        XCTAssertFalse(pkg.isFallback, "API 解码 isFallback 默认 false")
    }

    func testServicePackageDecodingWithNumericPrice() throws {
        let json = """
        {
            "code": "errand",
            "name": "代办跑腿",
            "price": 149,
            "sort_order": 30
        }
        """.data(using: .utf8)!
        let pkg = try JSONDecoder().decode(ServicePackage.self, from: json)
        XCTAssertEqual(pkg.price, Decimal(149))
        XCTAssertNil(pkg.description)
    }

    func testFallbackPackagesMatchServiceTypeEnum() {
        let fallback = ServicePackagesService.fallbackPackages
        XCTAssertEqual(fallback.count, 3, "fallback 必须含 3 标准档")
        let codes = fallback.map { $0.code }
        XCTAssertEqual(codes, ["full_accompany", "half_accompany", "errand"])
        // 与 ServiceType.displayName 一致
        for pkg in fallback {
            guard let st = ServiceType(rawValue: pkg.code) else {
                return XCTFail("fallback code 应是 ServiceType: \(pkg.code)")
            }
            XCTAssertEqual(pkg.name, st.displayName, "name 一致: \(pkg.code)")
            XCTAssertEqual(pkg.price, st.price, "price 一致: \(pkg.code)")
            XCTAssertTrue(pkg.isFallback, "fallback 实例必须标记 isFallback=true")
        }
    }

    func testFallbackPackagesSortOrderAscending() {
        let fallback = ServicePackagesService.fallbackPackages
        let sortOrders = fallback.map { $0.sortOrder }
        XCTAssertEqual(sortOrders, sortOrders.sorted(), "fallback 必须按 sort_order 升序")
    }

    func testOrderDecodingWithSnapshotFields() throws {
        let json = """
        {
            "id": "ord1",
            "order_number": "YLA20260604120000",
            "patient_id": "p1",
            "companion_id": null,
            "hospital_id": "h1",
            "service_type": "full_accompany",
            "service_name_snapshot": "全程陪诊",
            "service_price_snapshot": "299.00",
            "status": "created",
            "appointment_date": "2026-06-10",
            "appointment_time": "09:00",
            "description": null,
            "price": "299.00",
            "hospital_name": "北京协和医院",
            "companion_name": null,
            "patient_name": "张三",
            "family_member": null,
            "created_at": "2026-06-04T12:00:00Z",
            "updated_at": "2026-06-04T12:00:00Z"
        }
        """.data(using: .utf8)!
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        let order = try decoder.decode(Order.self, from: json)
        XCTAssertEqual(order.serviceNameSnapshot, "全程陪诊")
        XCTAssertEqual(order.servicePriceSnapshot, Decimal(string: "299.00"))
    }

    func testOrderDecodingTolerateMissingSnapshotFields() throws {
        // 历史订单 snapshot 字段缺失 → Codable 容许 (optional)
        let json = """
        {
            "id": "ord-legacy",
            "order_number": "YLA20240101000000",
            "patient_id": "p1",
            "companion_id": null,
            "hospital_id": "h1",
            "service_type": "errand",
            "status": "completed",
            "appointment_date": "2024-01-01",
            "appointment_time": "10:00",
            "description": null,
            "price": "149.00",
            "hospital_name": null,
            "companion_name": null,
            "patient_name": null,
            "family_member": null,
            "created_at": "2024-01-01T10:00:00Z",
            "updated_at": "2024-01-01T10:00:00Z"
        }
        """.data(using: .utf8)!
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        let order = try decoder.decode(Order.self, from: json)
        XCTAssertNil(order.serviceNameSnapshot, "历史订单允许 null")
        XCTAssertNil(order.servicePriceSnapshot)
    }
}
