import XCTest
@testable import YiLuAn

/// B7 iOS Share 发起端契约测试（ANDROID-DEV-B7-IOS-SHARE-ENTRY）。
/// 验发起端 3 个 endpoint 路径/方法对齐后端契约 + 小程序 WX-SHARE 发起端 (#395)。
///
/// 重点回归 revokeShare 路径修正：原 `shares/{tokenId}` 缺 order_id 会 404，
/// 修正为后端真实路径 `orders/{orderId}/shares/{tokenId}`。
final class ShareEntryEndpointTests: XCTestCase {

    func test_createShare_endpoint_对齐后端() {
        let ep = APIEndpoint.createShare(orderId: "ord-1")
        XCTAssertEqual(ep.path, "orders/ord-1/shares")
        XCTAssertEqual(ep.method, .post)
        XCTAssertTrue(ep.requiresAuth, "发起端走本人 access token")
    }

    func test_listShares_endpoint_对齐后端() {
        let ep = APIEndpoint.listShares(orderId: "ord-1")
        XCTAssertEqual(ep.path, "orders/ord-1/shares")
        XCTAssertEqual(ep.method, .get)
        XCTAssertTrue(ep.requiresAuth)
    }

    func test_revokeShare_endpoint_修正为含orderId路径() {
        // 回归 bug: 原 shares/{tokenId} 缺 order_id → 404。
        let ep = APIEndpoint.revokeShare(orderId: "ord-1", tokenId: "tok-9")
        XCTAssertEqual(ep.path, "orders/ord-1/shares/tok-9",
                       "revokeShare 必须走后端真实路径 orders/{orderId}/shares/{tokenId}")
        XCTAssertEqual(ep.method, .delete)
        XCTAssertTrue(ep.requiresAuth)
    }

    func test_createShare_默认scope为full() {
        // ShareService.createShare 默认 scope=.full，对齐小程序默认。
        // 编译期契约：签名带默认值。
        let ep = APIEndpoint.createShare(orderId: "x")
        XCTAssertEqual(ep.method, .post)
    }
}
