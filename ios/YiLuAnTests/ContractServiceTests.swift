import XCTest
@testable import YiLuAn

/// S3-DEV-001-CONTRACT-UI iOS service tests.
///
/// 覆盖:
/// - APIEndpoint.contractAccept / contractDetail factory functions
/// - ContractStatus enum 6 状态 + userFacingMessage 映射
/// - ContractAcceptanceResponse Codable
/// - ContractDetailResponse Codable (含 nullable signedUrl)
final class ContractServiceTests: XCTestCase {

    // MARK: - Endpoint construction (S3 CONTRACT-API)

    func testContractAcceptEndpoint() {
        let endpoint = APIEndpoint.contractAccept(id: "contract-uuid-1")
        XCTAssertEqual(endpoint.path, "contracts/contract-uuid-1/accept")
        XCTAssertEqual(endpoint.method, .post)
        XCTAssertTrue(endpoint.requiresAuth)
    }

    func testContractDetailEndpoint() {
        let endpoint = APIEndpoint.contractDetail(id: "abc-def-123")
        XCTAssertEqual(endpoint.path, "contracts/abc-def-123")
        XCTAssertEqual(endpoint.method, .get)
        XCTAssertTrue(endpoint.requiresAuth)
    }

    func testContractEndpointURLConstruction() {
        let endpoint = APIEndpoint.contractAccept(id: "x1")
        let url = endpoint.url
        XCTAssertTrue(url.absoluteString.contains("api/v1/contracts/x1/accept"))
    }

    // MARK: - ContractStatus enum

    func testContractStatusRawValuesMatchBackend() {
        // ADR-0047 §3.1 ground truth — 6 状态 wire format
        XCTAssertEqual(ContractStatus.pendingGeneration.rawValue, "pending_generation")
        XCTAssertEqual(ContractStatus.generating.rawValue, "generating")
        XCTAssertEqual(ContractStatus.active.rawValue, "active")
        XCTAssertEqual(ContractStatus.generationFailed.rawValue, "generation_failed")
        XCTAssertEqual(ContractStatus.generationPermanentlyFailed.rawValue, "generation_permanently_failed")
        XCTAssertEqual(ContractStatus.manuallyInvalidated.rawValue, "manually_invalidated")
    }

    func testActiveStatusHasEmptyUserMessage() {
        // active → signed URL 打开 PDF, 不显示文案
        XCTAssertEqual(ContractStatus.active.userFacingMessage, "")
    }

    func testPendingGenerationShowsGeneratingMessage() {
        XCTAssertTrue(ContractStatus.pendingGeneration.userFacingMessage.contains("生成"))
        XCTAssertTrue(ContractStatus.generating.userFacingMessage.contains("生成"))
    }

    func testFailedStatusShowsCustomerServiceMessage() {
        XCTAssertTrue(ContractStatus.generationFailed.userFacingMessage.contains("失败"))
        XCTAssertTrue(ContractStatus.generationPermanentlyFailed.userFacingMessage.contains("失败"))
    }

    func testInvalidatedStatusShowsInvalidatedMessage() {
        XCTAssertTrue(ContractStatus.manuallyInvalidated.userFacingMessage.contains("作废"))
    }

    // MARK: - Codable: ContractAcceptanceResponse

    func testContractAcceptanceResponseDecodes() throws {
        let json = """
        {
            "contract_id": "c-uuid-1",
            "order_id": "o-uuid-1",
            "accepted_at": "2026-06-08T07:00:00Z",
            "audit_log_id": "log-uuid-1"
        }
        """.data(using: .utf8)!

        let resp = try JSONDecoder().decode(ContractAcceptanceResponse.self, from: json)
        XCTAssertEqual(resp.contractId, "c-uuid-1")
        XCTAssertEqual(resp.orderId, "o-uuid-1")
        XCTAssertEqual(resp.acceptedAt, "2026-06-08T07:00:00Z")
        XCTAssertEqual(resp.auditLogId, "log-uuid-1")
    }

    // MARK: - Codable: ContractDetailResponse (含 nullable signedUrl)

    func testContractDetailResponseActiveDecodes() throws {
        let json = """
        {
            "contract_id": "c1",
            "order_id": "o1",
            "template_version": "v1.0.0",
            "status": "active",
            "signed_url": "https://storage/c.pdf?sig=xxx",
            "signed_url_expires_at": "2026-06-08T07:15:00Z",
            "generated_at": "2026-06-08T06:55:00Z"
        }
        """.data(using: .utf8)!

        let resp = try JSONDecoder().decode(ContractDetailResponse.self, from: json)
        XCTAssertEqual(resp.contractId, "c1")
        XCTAssertEqual(resp.status, .active)
        XCTAssertEqual(resp.signedUrl, "https://storage/c.pdf?sig=xxx")
        XCTAssertNotNil(resp.signedUrlExpiresAt)
        XCTAssertNotNil(resp.generatedAt)
    }

    func testContractDetailResponsePendingDecodesWithNullUrl() throws {
        let json = """
        {
            "contract_id": "c2",
            "order_id": "o2",
            "template_version": "v1.0.0",
            "status": "pending_generation",
            "signed_url": null,
            "signed_url_expires_at": null,
            "generated_at": null
        }
        """.data(using: .utf8)!

        let resp = try JSONDecoder().decode(ContractDetailResponse.self, from: json)
        XCTAssertEqual(resp.status, .pendingGeneration)
        XCTAssertNil(resp.signedUrl)
        XCTAssertNil(resp.signedUrlExpiresAt)
        XCTAssertNil(resp.generatedAt)
    }

    func testContractDetailResponseInvalidatedDecodes() throws {
        let json = """
        {
            "contract_id": "c3",
            "order_id": "o3",
            "template_version": "v1.0.0",
            "status": "manually_invalidated",
            "signed_url": null,
            "signed_url_expires_at": null,
            "generated_at": "2026-06-07T10:00:00Z"
        }
        """.data(using: .utf8)!

        let resp = try JSONDecoder().decode(ContractDetailResponse.self, from: json)
        XCTAssertEqual(resp.status, .manuallyInvalidated)
        XCTAssertNil(resp.signedUrl)
        XCTAssertNotNil(resp.generatedAt)
    }
}

/// S3-DEV-001-CONTRACT-UI: Order model 暴露 contract_id + insurance_id
/// (PR #207 bridge backend OrderResponse 加字段, iOS Codable 同步).
final class OrderContractIdDecodingTests: XCTestCase {

    func testOrderDecodesContractIdAndInsuranceId() throws {
        let json = """
        {
            "id": "o1",
            "order_number": "YLA20260608",
            "patient_id": "p1",
            "companion_id": null,
            "hospital_id": "h1",
            "service_type": "full_accompany",
            "status": "created",
            "appointment_date": "2026-06-10",
            "appointment_time": "09:00",
            "description": null,
            "price": "299.00",
            "service_name_snapshot": "全程陪诊",
            "service_price_snapshot": "299.00",
            "created_at": "2026-06-08T06:00:00Z",
            "updated_at": "2026-06-08T06:00:00Z",
            "hospital_name": "测试医院",
            "companion_name": null,
            "patient_name": null,
            "family_member": null,
            "contract_id": "contract-uuid",
            "insurance_id": "insurance-uuid"
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        decoder.dateDecodingStrategy = .custom { d in
            let str = try d.singleValueContainer().decode(String.self)
            if let date = ISO8601DateFormatter().date(from: str) { return date }
            return formatter.date(from: str) ?? Date()
        }

        let order = try decoder.decode(Order.self, from: json)
        XCTAssertEqual(order.contractId, "contract-uuid")
        XCTAssertEqual(order.insuranceId, "insurance-uuid")
    }

    func testLegacyOrderDecodesWithNullContractAndInsurance() throws {
        // 历史订单 (S3 启动前) — backend OrderResponse 返 null, iOS 应 decode 成 nil
        let json = """
        {
            "id": "o-legacy",
            "order_number": "YLA20260101",
            "patient_id": "p1",
            "companion_id": null,
            "hospital_id": "h1",
            "service_type": "errand",
            "status": "completed",
            "appointment_date": "2026-01-01",
            "appointment_time": "09:00",
            "description": null,
            "price": "149.00",
            "service_name_snapshot": "代办",
            "service_price_snapshot": "149.00",
            "created_at": "2026-01-01T06:00:00Z",
            "updated_at": "2026-01-01T06:00:00Z",
            "hospital_name": "医院",
            "companion_name": null,
            "patient_name": null,
            "family_member": null,
            "contract_id": null,
            "insurance_id": null
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        let order = try decoder.decode(Order.self, from: json)
        XCTAssertNil(order.contractId)
        XCTAssertNil(order.insuranceId)
    }
}
