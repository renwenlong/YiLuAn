import XCTest
@testable import YiLuAn

final class DesignSystemTests: XCTestCase {

    // MARK: - Color Tests

    func testBrandColorHexValue() {
        // Color(hex:) should produce correct sRGB components
        let color = Color(hex: 0x1890FF)
        let uiColor = UIColor(color)
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        uiColor.getRed(&r, green: &g, blue: &b, alpha: &a)

        XCTAssertEqual(r, 0x18 / 255.0, accuracy: 0.01)
        XCTAssertEqual(g, 0x90 / 255.0, accuracy: 0.01)
        XCTAssertEqual(b, 0xFF / 255.0, accuracy: 0.01)
        XCTAssertEqual(a, 1.0, accuracy: 0.01)
    }

    func testDangerColorHexValue() {
        let color = Color(hex: 0xFF4D4F)
        let uiColor = UIColor(color)
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        uiColor.getRed(&r, green: &g, blue: &b, alpha: &a)

        XCTAssertEqual(r, 0xFF / 255.0, accuracy: 0.01)
        XCTAssertEqual(g, 0x4D / 255.0, accuracy: 0.01)
        XCTAssertEqual(b, 0x4F / 255.0, accuracy: 0.01)
    }

    func testHexColorWithAlpha() {
        let color = Color(hex: 0x000000, alpha: 0.5)
        let uiColor = UIColor(color)
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        uiColor.getRed(&r, green: &g, blue: &b, alpha: &a)

        XCTAssertEqual(a, 0.5, accuracy: 0.01)
    }

    // MARK: - Spacing Tests

    func testSpacingValues() {
        XCTAssertEqual(Spacing.xs, 4)
        XCTAssertEqual(Spacing.sm, 8)
        XCTAssertEqual(Spacing.md, 12)
        XCTAssertEqual(Spacing.lg, 16)
        XCTAssertEqual(Spacing.xl, 24)
        XCTAssertEqual(Spacing.xxl, 32)
    }

    // MARK: - Corner Radius Tests

    func testCornerRadiusValues() {
        XCTAssertEqual(CornerRadius.sm, 4)
        XCTAssertEqual(CornerRadius.md, 8)
        XCTAssertEqual(CornerRadius.lg, 12)
        XCTAssertEqual(CornerRadius.full, 9999)
    }

    // MARK: - New Design System v2 Tests

    func testNewColorTokens() {
        // Verify new tokens exist and have correct hex values
        let brandDark = Color(hex: 0x096DD9)
        let uiColor = UIColor(brandDark)
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        uiColor.getRed(&r, green: &g, blue: &b, alpha: &a)
        XCTAssertEqual(r, 0x09 / 255.0, accuracy: 0.01)
        XCTAssertEqual(g, 0x6D / 255.0, accuracy: 0.01)
        XCTAssertEqual(b, 0xD9 / 255.0, accuracy: 0.01)
    }

    func testNewSpacingValues() {
        XCTAssertEqual(Spacing.xxs, 2)
        XCTAssertEqual(Spacing.xxxl, 48)
    }

    func testNewCornerRadiusValues() {
        XCTAssertEqual(CornerRadius.xs, 2)
        XCTAssertEqual(CornerRadius.xl, 16)
    }
}
