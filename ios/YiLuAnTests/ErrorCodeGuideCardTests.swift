import XCTest
@testable import YiLuAn

/// 验证 D-035 错误码 → ``ErrorCodeGuideCardType`` 的映射稳定，
/// 任何后端变更或前端常量漂移都会被捕获。
final class ErrorCodeGuideCardTests: XCTestCase {

    // MARK: - code → type 映射

    func testFromPhoneRequiredCode() {
        XCTAssertEqual(
            ErrorCodeGuideCardType.from(errorCode: APIErrorCode.phoneRequired),
            .phoneRequired
        )
    }

    func testFromVerificationRequiredCode() {
        XCTAssertEqual(
            ErrorCodeGuideCardType.from(errorCode: APIErrorCode.verificationRequired),
            .verificationRequired
        )
    }

    func testFromPaymentRequiredCode() {
        XCTAssertEqual(
            ErrorCodeGuideCardType.from(errorCode: APIErrorCode.paymentRequired),
            .paymentRequired
        )
    }

    func testFromUnknownCodeReturnsNil() {
        XCTAssertNil(ErrorCodeGuideCardType.from(errorCode: "SOME_UNKNOWN_CODE"))
    }

    func testFromNilReturnsNil() {
        XCTAssertNil(ErrorCodeGuideCardType.from(errorCode: nil))
    }

    // MARK: - 文案与可访问性

    func testEachTypeHasNonEmptyTitleAndCTA() {
        let allTypes: [ErrorCodeGuideCardType] = [
            .phoneRequired, .verificationRequired, .paymentRequired,
        ]
        for type in allTypes {
            XCTAssertFalse(
                type.title.isEmpty, "title for \(type) must be non-empty"
            )
            XCTAssertFalse(
                type.ctaTitle.isEmpty, "ctaTitle for \(type) must be non-empty"
            )
            XCTAssertFalse(
                type.iconName.isEmpty, "iconName for \(type) must be non-empty"
            )
        }
    }

    /// 三种语义必须使用三种不同的 accent 颜色，避免 UX 退化为"同款 toast"。
    func testEachTypeHasDistinctAccentColor() {
        let phone = ErrorCodeGuideCardType.phoneRequired.accentColor
        let verify = ErrorCodeGuideCardType.verificationRequired.accentColor
        let payment = ErrorCodeGuideCardType.paymentRequired.accentColor
        XCTAssertNotEqual(phone, verify)
        XCTAssertNotEqual(verify, payment)
        XCTAssertNotEqual(phone, payment)
    }

    /// 后端 API constant 与前端常量必须双向一致——这是 D-035 契约的核心。
    func testAPIErrorCodeStringsAreStable() {
        XCTAssertEqual(APIErrorCode.phoneRequired, "PHONE_REQUIRED")
        XCTAssertEqual(APIErrorCode.verificationRequired, "VERIFICATION_REQUIRED")
        XCTAssertEqual(APIErrorCode.paymentRequired, "PAYMENT_REQUIRED")
    }
}
