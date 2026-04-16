import SwiftUI

// MARK: - Brand Colors (synced with wechat/styles/variables.wxss v2.0)

extension Color {
    // Brand
    static let brand = Color(hex: 0x1890FF)
    static let brandDark = Color(hex: 0x096DD9)
    static let brandLight = Color(hex: 0xE6F7FF)
    static let brandLighter = Color(hex: 0xBAE7FF)
    static let secondary = Color(hex: 0x722ED1)
    static let accent = Color(hex: 0xFF7A45)

    // Semantic
    static let success = Color(hex: 0x52C41A)
    static let successLight = Color(hex: 0xF6FFED)
    static let warning = Color(hex: 0xFAAD14)
    static let warningLight = Color(hex: 0xFFFBE6)
    static let danger = Color(hex: 0xFF4D4F)
    static let dangerLight = Color(hex: 0xFFF2F0)

    // Text
    static let textPrimary = Color(hex: 0x1F2937)
    static let textSecondary = Color(hex: 0x6B7280)
    static let textHint = Color(hex: 0x9CA3AF)
    static let textDisabled = Color(hex: 0xD1D5DB)

    // Backgrounds
    static let bgPage = Color(hex: 0xF7F8FA)
    static let bgCard = Color.white
    static let bgInput = Color(hex: 0xF9FAFB)
    static let bgHover = Color(hex: 0xF3F4F6)
    static let bgSkeleton = Color(hex: 0xE5E7EB)

    // Borders
    static let border = Color(hex: 0xE5E7EB)
    static let borderLight = Color(hex: 0xF3F4F6)
    static let borderInput = Color(hex: 0xD1D5DB)

    // Mask
    static let bgMask = Color.black.opacity(0.45)

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

// MARK: - Gradients (synced with wechat design)

enum AppGradient {
    static let primary = LinearGradient(
        colors: [Color(hex: 0x1890FF), Color(hex: 0x36CFC9)],
        startPoint: .topLeading, endPoint: .bottomTrailing
    )
    static let warm = LinearGradient(
        colors: [Color(hex: 0xFF7A45), Color(hex: 0xFFAB76)],
        startPoint: .topLeading, endPoint: .bottomTrailing
    )
    static let success = LinearGradient(
        colors: [Color(hex: 0x52C41A), Color(hex: 0x73D13D)],
        startPoint: .topLeading, endPoint: .bottomTrailing
    )
    static let hero = LinearGradient(
        colors: [Color(hex: 0x1890FF), Color(hex: 0xE6F7FF)],
        startPoint: .top, endPoint: .bottom
    )
}

// MARK: - Typography

extension Font {
    static let dsHero = Font.system(size: 24, weight: .bold)         // 48rpx
    static let dsH1 = Font.system(size: 18, weight: .bold)           // 36rpx
    static let dsTitle = Font.system(size: 16, weight: .bold)        // 32rpx
    static let dsHeadline = Font.system(size: 15, weight: .semibold)
    static let dsBody = Font.system(size: 14)                        // 28rpx
    static let dsSubheadline = Font.system(size: 12)                 // 24rpx
    static let dsCaption = Font.system(size: 12)
    static let dsSmall = Font.system(size: 10)                       // 20rpx
}

// MARK: - Spacing

enum Spacing {
    static let xxs: CGFloat = 2
    static let xs: CGFloat = 4
    static let sm: CGFloat = 8
    static let md: CGFloat = 12
    static let lg: CGFloat = 16
    static let xl: CGFloat = 24
    static let xxl: CGFloat = 32
    static let xxxl: CGFloat = 48
}

// MARK: - Corner Radius

enum CornerRadius {
    static let xs: CGFloat = 2
    static let sm: CGFloat = 4
    static let md: CGFloat = 8
    static let lg: CGFloat = 12
    static let xl: CGFloat = 16
    static let full: CGFloat = 9999
}

// MARK: - Shadows

enum AppShadow {
    static func sm() -> some View {
        Color.black.opacity(0.05)
    }

    static let smRadius: CGFloat = 4
    static let mdRadius: CGFloat = 8
    static let lgRadius: CGFloat = 16
}

// MARK: - View Modifiers

struct CardStyle: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(Color.bgCard)
            .cornerRadius(CornerRadius.lg)
            .shadow(color: .black.opacity(0.05), radius: 4, x: 0, y: 2)
    }
}

struct ElevatedCardStyle: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(Color.bgCard)
            .cornerRadius(CornerRadius.xl)
            .shadow(color: .black.opacity(0.08), radius: 8, x: 0, y: 4)
    }
}

struct PrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.dsTitle)
            .foregroundColor(.white)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
            .background(AppGradient.primary)
            .cornerRadius(CornerRadius.md)
            .shadow(color: Color.brand.opacity(0.3), radius: 8, x: 0, y: 4)
            .scaleEffect(configuration.isPressed ? 0.98 : 1.0)
            .animation(.easeInOut(duration: 0.15), value: configuration.isPressed)
    }
}

struct SecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.dsTitle)
            .foregroundColor(.textSecondary)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
            .background(Color.bgPage)
            .cornerRadius(CornerRadius.md)
            .scaleEffect(configuration.isPressed ? 0.98 : 1.0)
            .animation(.easeInOut(duration: 0.15), value: configuration.isPressed)
    }
}

struct GhostButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.dsTitle)
            .foregroundColor(.brand)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 13)
            .overlay(RoundedRectangle(cornerRadius: CornerRadius.md).stroke(Color.brand, lineWidth: 1))
            .scaleEffect(configuration.isPressed ? 0.98 : 1.0)
            .animation(.easeInOut(duration: 0.15), value: configuration.isPressed)
    }
}

struct DangerButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.dsTitle)
            .foregroundColor(.white)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
            .background(Color.danger)
            .cornerRadius(CornerRadius.md)
            .shadow(color: Color.danger.opacity(0.3), radius: 8, x: 0, y: 4)
            .scaleEffect(configuration.isPressed ? 0.98 : 1.0)
            .animation(.easeInOut(duration: 0.15), value: configuration.isPressed)
    }
}

extension View {
    func cardStyle() -> some View {
        modifier(CardStyle())
    }

    func elevatedCardStyle() -> some View {
        modifier(ElevatedCardStyle())
    }
}

// MARK: - Badge Style

struct BadgeStyle: ViewModifier {
    let color: Color

    func body(content: Content) -> some View {
        content
            .font(.dsSmall)
            .fontWeight(.medium)
            .foregroundColor(color)
            .padding(.horizontal, 8)
            .padding(.vertical, 2)
            .background(color.opacity(0.1))
            .clipShape(Capsule())
    }
}

extension View {
    func badgeStyle(color: Color) -> some View {
        modifier(BadgeStyle(color: color))
    }
}
