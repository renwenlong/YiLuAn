import XCTest
@testable import YiLuAn

/// S2-INT-006 #2 · ShareDeepLink 解析单测
/// 覆盖：UniversalLink 合法 / URL scheme 合法 / 各类非法 url
final class ShareDeepLinkTests: XCTestCase {

    private let validToken = "AbCdEf0123456789AbCdEf0123456789AbCdEf01" // 40 字符

    // MARK: - UniversalLink

    func testValidUniversalLinkExtractsToken() {
        let url = URL(string: "https://m.yiluan.cn/s/\(validToken)")!
        XCTAssertEqual(ShareDeepLink.parse(url), validToken)
    }

    func testUniversalLinkRejectsWrongHost() {
        let url = URL(string: "https://attacker.cn/s/\(validToken)")!
        XCTAssertNil(ShareDeepLink.parse(url))
    }

    func testUniversalLinkRejectsHTTPScheme() {
        // 必须 https
        let url = URL(string: "http://m.yiluan.cn/s/\(validToken)")!
        XCTAssertNil(ShareDeepLink.parse(url))
    }

    func testUniversalLinkRejectsExtraPathSegments() {
        // /s/<token>/extra 不被识别（防路径污染）
        let url = URL(string: "https://m.yiluan.cn/s/\(validToken)/extra")!
        XCTAssertNil(ShareDeepLink.parse(url))
    }

    func testUniversalLinkRejectsWrongPathPrefix() {
        let url = URL(string: "https://m.yiluan.cn/share/\(validToken)")!
        XCTAssertNil(ShareDeepLink.parse(url))
    }

    // MARK: - URL scheme

    func testValidURLSchemeExtractsToken() {
        let url = URL(string: "yiluan://share/\(validToken)")!
        XCTAssertEqual(ShareDeepLink.parse(url), validToken)
    }

    func testURLSchemeRejectsUnknownHost() {
        let url = URL(string: "yiluan://unknown/\(validToken)")!
        XCTAssertNil(ShareDeepLink.parse(url))
    }

    func testURLSchemeRejectsWrongScheme() {
        let url = URL(string: "other://share/\(validToken)")!
        XCTAssertNil(ShareDeepLink.parse(url))
    }

    // MARK: - Token 形态校验

    func testRejectsTokenShorterThan40() {
        let short = String(repeating: "a", count: 39)
        let url = URL(string: "https://m.yiluan.cn/s/\(short)")!
        XCTAssertNil(ShareDeepLink.parse(url))
    }

    func testRejectsTokenLongerThan40() {
        let long = String(repeating: "a", count: 41)
        let url = URL(string: "https://m.yiluan.cn/s/\(long)")!
        XCTAssertNil(ShareDeepLink.parse(url))
    }

    func testRejectsTokenWithNonURLSafeChars() {
        // URL-safe = [A-Za-z0-9_-]，含 +/= 等 base64 字符被拒
        let badChars = "AbCdEf+/=123456789AbCdEf0123456789AbCdEf01" // 40 字符但含 +/=
        let url = URL(string: "yiluan://share/\(badChars)")!
        XCTAssertNil(ShareDeepLink.parse(url))
    }

    func testAcceptsTokenWithDashUnderscore() {
        let valid = "AbCdEf_-0123456789AbCdEf0123456789AbCdEf" // 40 字符含 _-
        let url = URL(string: "https://m.yiluan.cn/s/\(valid)")!
        XCTAssertEqual(ShareDeepLink.parse(url), valid)
    }
}
