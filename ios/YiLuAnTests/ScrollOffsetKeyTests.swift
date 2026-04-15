import XCTest
@testable import YiLuAn

final class ScrollOffsetKeyTests: XCTestCase {

    func testDefaultValue() {
        XCTAssertEqual(ScrollOffsetKey.defaultValue, 0)
    }

    func testReduce() {
        var value: CGFloat = 10
        ScrollOffsetKey.reduce(value: &value) { 42 }
        XCTAssertEqual(value, 42)
    }

    func testReduceOverwritesPrevious() {
        var value: CGFloat = 100
        ScrollOffsetKey.reduce(value: &value) { 0 }
        XCTAssertEqual(value, 0)
    }
}
