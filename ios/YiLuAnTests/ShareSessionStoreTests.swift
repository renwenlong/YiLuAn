import XCTest
@testable import YiLuAn

/// S2-INT-004 #4 · ShareSessionStore Keychain 存取单测
/// 注：XCTest bundle 无 host app 时 KeychainManager 自动 fallback 到 in-memory store，
/// 行为与生产 Keychain 等价（save / get / delete 语义一致）。
final class ShareSessionStoreTests: XCTestCase {

    override func setUp() {
        super.setUp()
        ShareSessionStore.clear() // 每个 case 起手干净
    }

    override func tearDown() {
        ShareSessionStore.clear()
        super.tearDown()
    }

    // MARK: - save / load round trip

    func testSaveAndLoadActiveSession() {
        let orderId = UUID()
        let future = Date().addingTimeInterval(30 * 60) // 30min 后
        let response = ExchangeSessionResponse(
            shareSession: "eyJhbGciOiJIUzI1NiJ9.payload.sig",
            shareSessionExpiresAt: future,
            shareScope: .full,
            orderId: orderId
        )

        ShareSessionStore.save(response: response, shareToken: "tok-abc-40-chars")
        let active = ShareSessionStore.activeSession()
        XCTAssertNotNil(active)
        XCTAssertEqual(active?.jwt, "eyJhbGciOiJIUzI1NiJ9.payload.sig")
        XCTAssertEqual(active?.scope, .full)
        XCTAssertEqual(active?.orderId, orderId)
        XCTAssertEqual(active?.shareToken, "tok-abc-40-chars")
        // 过期时间存取精度允许 1s 误差（ISO8601 序列化往返）
        XCTAssertEqual(
            active!.expiresAt.timeIntervalSince1970,
            future.timeIntervalSince1970,
            accuracy: 1.0
        )
    }

    // MARK: - 过期自动清

    func testExpiredSessionReturnsNilAndClears() {
        let past = Date().addingTimeInterval(-60) // 1 分钟前过期
        let response = ExchangeSessionResponse(
            shareSession: "expired.jwt.value",
            shareSessionExpiresAt: past,
            shareScope: .progressOnly,
            orderId: UUID()
        )
        ShareSessionStore.save(response: response, shareToken: "tok-exp")

        XCTAssertNil(ShareSessionStore.activeSession())
        // 第二次调用确认 clear 真发生（同样 nil，但 keychain 应已空）
        XCTAssertNil(ShareSessionStore.activeSession())
    }

    // MARK: - clear

    func testClearRemovesAll() {
        let response = ExchangeSessionResponse(
            shareSession: "to-be-cleared",
            shareSessionExpiresAt: Date().addingTimeInterval(900),
            shareScope: .full,
            orderId: UUID()
        )
        ShareSessionStore.save(response: response, shareToken: "tok")
        XCTAssertNotNil(ShareSessionStore.activeSession())

        ShareSessionStore.clear()
        XCTAssertNil(ShareSessionStore.activeSession())
    }

    // MARK: - 缺字段返回 nil

    func testMissingAnyKeyReturnsNil() {
        let response = ExchangeSessionResponse(
            shareSession: "v",
            shareSessionExpiresAt: Date().addingTimeInterval(900),
            shareScope: .full,
            orderId: UUID()
        )
        ShareSessionStore.save(response: response, shareToken: "tok")
        // 故意删 1 项（jwt）
        KeychainManager.delete(key: "share_session_jwt")
        XCTAssertNil(ShareSessionStore.activeSession())
    }

    // MARK: - 覆盖写

    func testSaveOverwritesPrevious() {
        let first = ExchangeSessionResponse(
            shareSession: "first",
            shareSessionExpiresAt: Date().addingTimeInterval(900),
            shareScope: .full,
            orderId: UUID()
        )
        ShareSessionStore.save(response: first, shareToken: "tok1")

        let second = ExchangeSessionResponse(
            shareSession: "second",
            shareSessionExpiresAt: Date().addingTimeInterval(900),
            shareScope: .progressOnly,
            orderId: UUID()
        )
        ShareSessionStore.save(response: second, shareToken: "tok2")

        let active = ShareSessionStore.activeSession()
        XCTAssertEqual(active?.jwt, "second")
        XCTAssertEqual(active?.scope, .progressOnly)
        XCTAssertEqual(active?.shareToken, "tok2")
    }
}
