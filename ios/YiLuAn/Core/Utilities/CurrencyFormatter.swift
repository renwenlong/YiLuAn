import Foundation

/// CurrencyFormatter
///
/// 与微信小程序 / admin-h5 (PR #67) 保持一致的人民币货币展示格式：
/// - 千分位分隔符 `,`
/// - 始终保留两位小数
/// - 输出形如 `1,234.56`（不带单位，由调用方拼接 `元` 或 `¥`）
///
/// 提供 `cny(_:)` 重载，分别接受 `Decimal` 与 `Double`，
/// 以及 `cnyWithUnit(_:)` 直接返回带 `¥` 前缀的字符串。
///
/// 注意：使用 `Locale(identifier: "en_US_POSIX")` 以避免不同区域设置导致
/// 分隔符不稳定（例如部分中文区域可能采用 `１,２３４` 全角形式）。
enum CurrencyFormatter {

    /// 内部共享的 NumberFormatter（带千分位 + 两位小数）。
    private static let numberFormatter: NumberFormatter = {
        let f = NumberFormatter()
        f.numberStyle = .decimal
        f.locale = Locale(identifier: "en_US_POSIX")
        f.usesGroupingSeparator = true
        f.groupingSeparator = ","
        f.groupingSize = 3
        f.decimalSeparator = "."
        f.minimumFractionDigits = 2
        f.maximumFractionDigits = 2
        f.roundingMode = .halfUp
        return f
    }()

    // MARK: - Public API

    /// 将 `Decimal` 金额格式化为千分位 + 两位小数字符串，例如 `1,234.56`。
    static func cny(_ value: Decimal) -> String {
        let number = NSDecimalNumber(decimal: value)
        return numberFormatter.string(from: number) ?? fallback(number.doubleValue)
    }

    /// 将 `Double` 金额格式化为千分位 + 两位小数字符串，例如 `1,234.56`。
    static func cny(_ value: Double) -> String {
        return numberFormatter.string(from: NSNumber(value: value)) ?? fallback(value)
    }

    /// 带 `¥` 前缀的金额字符串，例如 `¥1,234.56`。
    /// 与微信小程序 `formatCNY` / admin-h5 `formatCurrency` 一致。
    static func cnyWithUnit(_ value: Decimal) -> String {
        return "¥" + cny(value)
    }

    /// 带 `¥` 前缀的金额字符串（Double 重载）。
    static func cnyWithUnit(_ value: Double) -> String {
        return "¥" + cny(value)
    }

    // MARK: - Private

    /// 格式化失败时的兜底（理论上 NumberFormatter 不会失败）。
    private static func fallback(_ value: Double) -> String {
        return String(format: "%.2f", value)
    }
}
