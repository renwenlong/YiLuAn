import SwiftUI

// MARK: - Brand Colors (synced with wechat/styles/variables.wxss)

extension Color {
    // Brand
    static let brand = Color(hex: 0x1890FF)
    static let brandLight = Color(hex: 0xE6F7FF)
    static let secondary = Color(hex: 0x722ED1)

    // Semantic
    static let success = Color(hex: 0x52C41A)
    static let warning = Color(hex: 0xFAAD14)
    static let danger = Color(hex: 0xFF4D4F)

    // Text
    static let textPrimary = Color(hex: 0x333333)
    static let textSecondary = Color(hex: 0x666666)
    static let textHint = Color(hex: 0x999999)

    // Backgrounds
    static let bgPage = Color(hex: 0xF5F5F5)
    static let bgCard = Color.white

    // Borders
    static let border = Color(hex: 0xE8E8E8)
    static let borderLight = Color(hex: 0xF0F0F0)

    // Hex initializer
    init(hex: UInt, alpha: Double = 1.0) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255.0,
            green: Double((hex >> 8) & 0xFF) / 255.0,
            blue: Double(hex & 0xFF) / 255.0,
            opacity: alpha
        )
    }
}

// MARK: - Typography

extension Font {
    static let dsTitle = Font.system(size: 18, weight: .bold)
    static let dsHeadline = Font.system(size: 16, weight: .semibold)
    static let dsBody = Font.system(size: 15)
    static let dsSubheadline = Font.system(size: 14)
    static let dsCaption = Font.system(size: 12)
    static let dsSmall = Font.system(size: 10)
}

// MARK: - Spacing

enum Spacing {
    static let xs: CGFloat = 4
    static let sm: CGFloat = 8
    static let md: CGFloat = 12
    static let lg: CGFloat = 16
    static let xl: CGFloat = 24
    static let xxl: CGFloat = 32
}

// MARK: - Corner Radius

enum CornerRadius {
    static let sm: CGFloat = 4
    static let md: CGFloat = 8
    static let lg: CGFloat = 12
    static let full: CGFloat = 9999
}
