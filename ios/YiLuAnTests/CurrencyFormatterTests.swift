import XCTest
@testable import YiLuAn

/// W18 Day 4 Action #6
///
/// 验证 CurrencyFormatter 与微信小程序 / admin-h5 (PR #67) 一致：
/// 千分位 + 两位小数。
final class CurrencyFormatterTests: XCTestCase {

    // MARK: - Decimal overload

    func testZero() {
        XCTAssertEqual(CurrencyFormatter.cny(Decimal(0)), "0.00")
    }

    func testHalf() {
        XCTAssertEqual(CurrencyFormatter.cny(Decimal(string: "0.5")!), "0.50")
    }

    func testOne() {
        XCTAssertEqual(CurrencyFormatter.cny(Decimal(1)), "1.00")
    }

    func testNoThousandsBoundary() {
        // 999.99 不应出现千分位
        XCTAssertEqual(CurrencyFormatter.cny(Decimal(string: "999.99")!), "999.99")
    }

    func testThousandsBoundary() {
        // 1234.56 -> "1,234.56"
        XCTAssertEqual(CurrencyFormatter.cny(Decimal(string: "1234.56")!), "1,234.56")
    }

    func testLargeNumberRoundsToTwoDecimals() {
        // 1234567.891 -> "1,234,567.89" （HALF_UP）
        XCTAssertEqual(CurrencyFormatter.cny(Decimal(string: "1234567.891")!), "1,234,567.89")
    }

    func testNegativeAmount() {
        XCTAssertEqual(CurrencyFormatter.cny(Decimal(string: "-1234.5")!), "-1,234.50")
    }

    func testDecimalPrecisionEdge() {
        // Decimal 精度足够保留长尾，formatter 截断到两位
        let value = Decimal(string: "0.005")!
        // 0.005 在 HALF_UP 下应进位到 0.01
        XCTAssertEqual(CurrencyFormatter.cny(value), "0.01")
    }

    // MARK: - Double overload

    func testDoubleOverload() {
        XCTAssertEqual(CurrencyFormatter.cny(1234.5), "1,234.50")
        XCTAssertEqual(CurrencyFormatter.cny(0.0), "0.00")
    }

    // MARK: - cnyWithUnit

    func testCnyWithUnit() {
        XCTAssertEqual(CurrencyFormatter.cnyWithUnit(Decimal(string: "1234.56")!), "¥1,234.56")
        XCTAssertEqual(CurrencyFormatter.cnyWithUnit(Decimal(0)), "¥0.00")
    }

    func testCnyWithUnitDouble() {
        XCTAssertEqual(CurrencyFormatter.cnyWithUnit(99.9), "¥99.90")
    }
}
