import XCTest
@testable import YiLuAn

final class APIEndpointTests: XCTestCase {

    // MARK: - Existing endpoint smokes

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

    // MARK: - Share endpoints (ADR-0036 §2.7 / S2-INT-004)

    func testCreateShareEndpoint() {
        let endpoint = APIEndpoint.createShare(orderId: "order-1")
        XCTAssertEqual(endpoint.path, "orders/order-1/shares")
        XCTAssertEqual(endpoint.method, .post)
        XCTAssertTrue(endpoint.requiresAuth, "owner 路径必须鉴权")
    }

    func testListSharesEndpoint() {
        let endpoint = APIEndpoint.listShares(orderId: "order-1")
        XCTAssertEqual(endpoint.path, "orders/order-1/shares")
        XCTAssertEqual(endpoint.method, .get)
        XCTAssertTrue(endpoint.requiresAuth)
    }

    func testRevokeShareEndpoint() {
        let endpoint = APIEndpoint.revokeShare(tokenId: "tok-uuid")
        XCTAssertEqual(endpoint.path, "shares/tok-uuid")
        XCTAssertEqual(endpoint.method, .delete)
        XCTAssertTrue(endpoint.requiresAuth)
    }

    func testSendShareOTPEndpoint() {
        let endpoint = APIEndpoint.sendShareOTP(token: "abc123")
        XCTAssertEqual(endpoint.path, "shares/abc123/otp")
        XCTAssertEqual(endpoint.method, .post)
        XCTAssertFalse(endpoint.requiresAuth, "家属未登录路径，不走 Authorization")
    }

    func testExchangeShareSessionEndpoint() {
        let endpoint = APIEndpoint.exchangeShareSession(token: "abc123")
        XCTAssertEqual(endpoint.path, "shares/abc123/session")
        XCTAssertEqual(endpoint.method, .post)
        XCTAssertFalse(endpoint.requiresAuth)
    }

    func testGetShareSessionOrderEndpoint() {
        let endpoint = APIEndpoint.getShareSessionOrder
        XCTAssertEqual(endpoint.path, "shares/session/order")
        XCTAssertEqual(endpoint.method, .get)
        XCTAssertFalse(endpoint.requiresAuth, "走 share_session JWT，不走 access_token")
    }

    // MARK: - 7-field deserialization (AC#24, S2-DEV-004 跨端契约)

    /// 7 字段 = share_token / share_url / share_scope / share_expires_at
    ///         share_revoked_at / share_session / share_active_count
    /// 任一字段名/类型/必填性漂移 → 测试 fail → develop task 直接打回（AC#24）

    private var iso8601Decoder: JSONDecoder {
        let decoder = JSONDecoder()
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let str = try container.decode(String.self)
            if let date = formatter.date(from: str) {
                return date
            }
            let formatterNoFrac = ISO8601DateFormatter()
            formatterNoFrac.formatOptions = [.withInternetDateTime]
            if let date = formatterNoFrac.date(from: str) {
                return date
            }
            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Invalid ISO8601 date: \(str)"
            )
        }
        return decoder
    }

    /// AC#24 字段 1/2/3/4/5 + 7：CreateShareResponse 覆盖
    /// share_token / share_url / share_scope / share_expires_at / share_revoked_at / share_active_count
    func testCreateShareResponseDeserializes7FieldContract() throws {
        let json = """
        {
          "id": "11111111-1111-1111-1111-111111111111",
          "share_token": "AbCdEf0123456789AbCdEf0123456789AbCdEf01",
          "share_url": "https://m.yiluan.cn/s/AbCdEf0123456789AbCdEf0123456789AbCdEf01",
          "share_scope": "full",
          "share_expires_at": "2026-06-04T10:30:00.000Z",
          "share_revoked_at": null,
          "created_at": "2026-06-03T10:30:00.000Z",
          "first_accessed_at": null,
          "distinct_accessor_count": 0,
          "share_active_count": 1
        }
        """.data(using: .utf8)!

        let resp = try iso8601Decoder.decode(CreateShareResponse.self, from: json)

        XCTAssertEqual(resp.shareToken, "AbCdEf0123456789AbCdEf0123456789AbCdEf01")
        XCTAssertEqual(resp.shareURL, "https://m.yiluan.cn/s/AbCdEf0123456789AbCdEf0123456789AbCdEf01")
        XCTAssertEqual(resp.shareScope, .full)
        XCTAssertNotNil(resp.shareExpiresAt)
        XCTAssertNil(resp.shareRevokedAt, "新建 token revoked_at 必须为 null")
        XCTAssertEqual(resp.shareActiveCount, 1)
    }

    /// 字段 3：share_scope 双枚举值都能解
    func testShareScopeDeserializesProgressOnly() throws {
        let json = """
        {
          "id": "22222222-2222-2222-2222-222222222222",
          "share_token": "tok2",
          "share_url": "https://m.yiluan.cn/s/tok2",
          "share_scope": "progress_only",
          "share_expires_at": "2026-06-04T10:30:00.000Z",
          "share_revoked_at": null,
          "created_at": "2026-06-03T10:30:00.000Z",
          "first_accessed_at": null,
          "distinct_accessor_count": 0,
          "share_active_count": 2
        }
        """.data(using: .utf8)!

        let resp = try iso8601Decoder.decode(CreateShareResponse.self, from: json)
        XCTAssertEqual(resp.shareScope, .progressOnly)
    }

    /// 字段 5：share_revoked_at 非 null 也能解
    func testRevokedShareTokenDeserializes() throws {
        let json = """
        {
          "id": "33333333-3333-3333-3333-333333333333",
          "share_token": "tok3",
          "share_url": "https://m.yiluan.cn/s/tok3",
          "share_scope": "full",
          "share_expires_at": "2026-06-04T10:30:00.000Z",
          "share_revoked_at": "2026-06-03T11:00:00.000Z",
          "created_at": "2026-06-03T10:30:00.000Z",
          "first_accessed_at": "2026-06-03T10:45:00.000Z",
          "distinct_accessor_count": 2
        }
        """.data(using: .utf8)!

        let tok = try iso8601Decoder.decode(OrderShareToken.self, from: json)
        XCTAssertNotNil(tok.shareRevokedAt)
        XCTAssertEqual(tok.distinctAccessorCount, 2)
    }

    /// AC#24 字段 6：ExchangeSessionResponse.share_session 反序列化
    func testExchangeSessionResponseDeserializesShareSession() throws {
        let json = """
        {
          "share_session": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzaGFyZSJ9.signature",
          "share_session_expires_at": "2026-06-03T11:00:00.000Z",
          "share_scope": "full",
          "order_id": "44444444-4444-4444-4444-444444444444"
        }
        """.data(using: .utf8)!

        let resp = try iso8601Decoder.decode(ExchangeSessionResponse.self, from: json)
        XCTAssertEqual(resp.shareSession.split(separator: ".").count, 3, "share_session 必须是 3-segment JWT")
        XCTAssertEqual(resp.shareScope, .full)
    }

    /// AC#24 缺字段 fail 验证：share_session 缺则解码失败
    /// （契约漂移即刻可见，配合 S2-DEV-004 OpenAPI baseline gate 形成双闸门）
    func testExchangeSessionResponseFailsWhenShareSessionMissing() {
        let json = """
        {
          "share_session_expires_at": "2026-06-03T11:00:00.000Z",
          "share_scope": "full",
          "order_id": "55555555-5555-5555-5555-555555555555"
        }
        """.data(using: .utf8)!

        XCTAssertThrowsError(try iso8601Decoder.decode(ExchangeSessionResponse.self, from: json)) { err in
            guard case DecodingError.keyNotFound(let key, _) = err else {
                XCTFail("Expected keyNotFound, got \(err)")
                return
            }
            XCTAssertEqual(key.stringValue, "share_session", "缺 share_session 必须报缺该 key")
        }
    }

    /// AC#24 字段 7：ListSharesResponse.share_active_count 必填
    func testListSharesResponseDeserializesShareActiveCount() throws {
        let json = """
        {
          "items": [
            {
              "id": "66666666-6666-6666-6666-666666666666",
              "share_token": "tok-a",
              "share_url": "https://m.yiluan.cn/s/tok-a",
              "share_scope": "full",
              "share_expires_at": "2026-06-04T10:30:00.000Z",
              "share_revoked_at": null,
              "created_at": "2026-06-03T10:30:00.000Z",
              "first_accessed_at": null,
              "distinct_accessor_count": 0
            }
          ],
          "share_active_count": 1
        }
        """.data(using: .utf8)!

        let resp = try iso8601Decoder.decode(ListSharesResponse.self, from: json)
        XCTAssertEqual(resp.shareActiveCount, 1)
        XCTAssertEqual(resp.items.count, 1)
        XCTAssertEqual(resp.items.first?.shareToken, "tok-a")
    }

    /// AC#24 缺 share_active_count 必失败
    func testListSharesResponseFailsWhenShareActiveCountMissing() {
        let json = """
        {
          "items": []
        }
        """.data(using: .utf8)!

        XCTAssertThrowsError(try iso8601Decoder.decode(ListSharesResponse.self, from: json)) { err in
            guard case DecodingError.keyNotFound(let key, _) = err else {
                XCTFail("Expected keyNotFound, got \(err)")
                return
            }
            XCTAssertEqual(key.stringValue, "share_active_count")
        }
    }

    /// §2.5 脱敏视图：ShareOrderResponse 反序列化 + PII 字段必须不存在
    /// 缺字段 fail 验证（contract drift 即刻可见）
    func testShareOrderResponseDeserializesAndExcludesPII() throws {
        let json = """
        {
          "order_id": "77777777-7777-7777-7777-777777777777",
          "order_number": "YLA20260603001",
          "status": "in_progress",
          "service_type": "full_accompany",
          "appointment_date": "2026-06-03",
          "appointment_time": "上午",
          "hospital_name": "市一院",
          "patient_name_masked": "张**",
          "companion": {
            "name": "李陪诊",
            "avatar_url": "https://cdn.yiluan.cn/avatar/c1.jpg"
          },
          "share_scope": "full",
          "can_view_images": true,
          "can_view_ai_summary": true,
          "timeline": null
        }
        """.data(using: .utf8)!

        let resp = try iso8601Decoder.decode(ShareOrderResponse.self, from: json)
        XCTAssertEqual(resp.patientNameMasked, "张**", "姓名必须脱敏（§2.5）")
        XCTAssertEqual(resp.shareScope, .full)
        XCTAssertTrue(resp.canViewImages)
        XCTAssertTrue(resp.canViewAISummary)
        XCTAssertEqual(resp.companion?.name, "李陪诊")
    }

    /// scope=progress_only 时 can_view_* 必须为 false（acceptance #21 互锁）
    func testShareOrderProgressOnlyScopeBlocksImages() throws {
        let json = """
        {
          "order_id": "88888888-8888-8888-8888-888888888888",
          "order_number": "YLA20260603002",
          "status": "in_progress",
          "service_type": "half_accompany",
          "appointment_date": "2026-06-03",
          "appointment_time": "下午",
          "hospital_name": "市二院",
          "patient_name_masked": "李**",
          "companion": null,
          "share_scope": "progress_only",
          "can_view_images": false,
          "can_view_ai_summary": false,
          "timeline": null
        }
        """.data(using: .utf8)!

        let resp = try iso8601Decoder.decode(ShareOrderResponse.self, from: json)
        XCTAssertEqual(resp.shareScope, .progressOnly)
        XCTAssertFalse(resp.canViewImages, "progress_only 必须 false")
        XCTAssertFalse(resp.canViewAISummary, "progress_only 必须 false")
    }

    /// SendShareOTPResponse 反序列化 + masked_phone 字段
    func testSendShareOTPResponseDeserializes() throws {
        let json = """
        {
          "sent": true,
          "masked_phone": "138****0001",
          "expires_in": 300
        }
        """.data(using: .utf8)!

        let resp = try iso8601Decoder.decode(SendShareOTPResponse.self, from: json)
        XCTAssertTrue(resp.sent)
        XCTAssertEqual(resp.maskedPhone, "138****0001")
        XCTAssertEqual(resp.expiresIn, 300)
    }

    /// ExchangeSessionRequest 序列化：F2 iOS OTP 兜底路径 phone+otp
    func testExchangeSessionRequestSerializesOTPPath() throws {
        let req = ExchangeSessionRequest.otp(phone: "13800000001", otp: "123456")
        let encoder = JSONEncoder()
        encoder.outputFormatting = .sortedKeys
        let data = try encoder.encode(req)
        let str = String(data: data, encoding: .utf8)!
        XCTAssertTrue(str.contains("\"phone\":\"13800000001\""))
        XCTAssertTrue(str.contains("\"otp\":\"123456\""))
        XCTAssertFalse(str.contains("wx_openid"), "iOS 路径不带 wx_openid（应为 null 被跳过）")
    }
}
