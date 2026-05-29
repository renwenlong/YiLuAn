// S2-TEST-002 / PRD-001 §6.C AC#24 — iOS APIEndpoint contract test stub
//
// ADR-0036 §2.7 七字段 + 6 个 REST 端点：
//   POST   /orders/{order_id}/shares
//   GET    /orders/{order_id}/shares
//   DELETE /orders/{order_id}/shares/{token_id}
//   POST   /shares/{token}/session
//   GET    /shares/session/order
//   (WS)   /ws/share/{token}
//
// 阶段 A（当前）：S2-DEV-002 端点未落地，全部 XCTSkip。
// 阶段 B（S2-DEV-002 done）：移除 XCTSkip，启用反序列化断言；CI 接入 ios-tests workflow。

import XCTest
@testable import YiLuAn

final class ShareEndpointContractTests: XCTestCase {

    // MARK: - POST /orders/{order_id}/shares

    func test_createShareResponse_decodes_seven_fields() throws {
        try XCTSkipIf(true, "await S2-DEV-002 — CreateShareResponse model 未定义")
        // 期望（阶段 B）：
        // let json = """{"share_token":"xxx","share_scope":"full",
        //   "share_expires_at":"2026-06-01T00:00:00Z","share_revoked_at":null,
        //   "share_url":"https://...","token_id":"uuid"}"""
        // let resp = try JSONDecoder.yiluan.decode(CreateShareResponse.self, from: json.data(using:.utf8)!)
        // XCTAssertEqual(resp.shareScope, .full)
        // XCTAssertNotNil(resp.shareToken)
    }

    // MARK: - GET /orders/{order_id}/shares (列表)

    func test_listShareResponse_decodes_active_tokens_with_cap3() throws {
        try XCTSkipIf(true, "await S2-DEV-002 — ListShareResponse model 未定义")
    }

    // MARK: - DELETE /orders/{order_id}/shares/{token_id}

    func test_revokeShare_204_no_content() throws {
        try XCTSkipIf(true, "await S2-DEV-002 — DELETE endpoint 未落地")
    }

    // MARK: - POST /shares/{token}/session  → share_session JWT

    func test_createShareSessionResponse_decodes_share_session_field() throws {
        try XCTSkipIf(true, "await S2-DEV-002 — ShareSession JWT 通道未落地")
        // 期望（阶段 B）：
        // 必须包含 share_session (string, JWT) + patient_name_masked
        // share_session 必须能在 SessionStorage 中复用 30min
    }

    // MARK: - GET /shares/session/order  → 脱敏订单视图

    func test_shareOrderView_decodes_with_patient_name_masked() throws {
        try XCTSkipIf(true, "await S2-DEV-002 — GET endpoint + 脱敏 schema 未落地")
        // 期望：patient_name_masked 必须存在；原 patient_name 不应该出现
    }

    func test_shareOrderView_scope_progress_only_omits_digest_url() throws {
        try XCTSkipIf(true, "await S2-DEV-002 — scope gate 未落地")
        // 期望：scope=progress_only 时 digest_url 必须为 null 或字段缺失
    }

    // MARK: - 字段类型 / 必填性硬断（与 ADR-0036 §2.7 对齐）

    func test_share_scope_enum_values_match_adr() throws {
        try XCTSkipIf(true, "await S2-DEV-002 — ShareScope enum import 未对齐")
        // 期望：ShareScope.allCases == [.full, .progressOnly]
    }
}
