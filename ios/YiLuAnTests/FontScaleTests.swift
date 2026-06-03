import XCTest
@testable import YiLuAn

/// S2-INT-004 · 巨字号缩放表单测（双端 token 完整一致，逐项钉死）
/// 真源：docs/design/wireframes/U1-folding-stepper/README.md §「巨字号缩放表」
/// **与微信 `wechat/__tests__/utils/fontScale.test.js` 逐 case 对齐**。
final class FontScaleTests: XCTestCase {

    func testRegularModeTokens() {
        let t = FontScale.tokens(huge: false)
        XCTAssertEqual(t.bodyFont, 14)
        XCTAssertEqual(t.metaFont, 12)
        XCTAssertEqual(t.primaryBtnH, 42)
        XCTAssertEqual(t.labelMarginTop, 12)
        XCTAssertEqual(t.labelMarginBottom, 6)
        XCTAssertEqual(t.stepNum, 22)
        XCTAssertEqual(t.summaryClamp, 1)
    }

    func testHugeModeTokens() {
        let t = FontScale.tokens(huge: true)
        XCTAssertEqual(t.bodyFont, 18)
        XCTAssertEqual(t.metaFont, 15)
        XCTAssertEqual(t.primaryBtnH, 50)
        XCTAssertEqual(t.labelMarginTop, 15)
        XCTAssertEqual(t.labelMarginBottom, 8)
        XCTAssertEqual(t.stepNum, 26)
        XCTAssertEqual(t.summaryClamp, 2)
    }

    func testSummaryClampRegularOneLineHugeTwoLines() {
        XCTAssertEqual(FontScale.summaryClamp(huge: false), 1)
        XCTAssertEqual(FontScale.summaryClamp(huge: true), 2)
    }

    /// 缩放非等比断言（正文 14→18 与按钮 42→50 比例不同 → 证明非等比）
    func testScalingIsNonUniform() {
        let n = FontScale.tokens(huge: false)
        let h = FontScale.tokens(huge: true)
        XCTAssertNotEqual(
            h.bodyFont / n.bodyFont,
            h.primaryBtnH / n.primaryBtnH,
            "缩放必须非等比（钉死要求逐项取值）"
        )
    }
}
