import Foundation
import SwiftUI

/// I18N-DEV-003 (ADR-0063 §5)：应用内语言管理。
///
/// 为什么不直接用 `String(localized:)`：
///   系统 `String(localized:)` / `Text(verbatim:)` 走 **系统语言** bundle，
///   切换语言需重启 App。本方案要求**即时切换无需重启**（AC-2/AC-4），
///   故由 `LocalizationManager` 持有当前 locale，从对应 `.lproj` 子 bundle
///   手动查表；`@Published currentLanguage` 变更驱动 SwiftUI 依赖重渲染。
///
/// 用法：
///   - App 根视图 `.environmentObject(LocalizationManager.shared)`
///   - View 内：`@EnvironmentObject var loc: LocalizationManager`
///     `Text(loc.t("settings.title"))`
///   - 带参数：`loc.t("otp.sentTo", "+86 138****")`（对应 catalog "%@" 占位）
final class LocalizationManager: ObservableObject {
    static let shared = LocalizationManager()

    /// 支持的语言。rawValue 同时是 `.lproj` 目录名 / String Catalog locale code。
    enum Language: String, CaseIterable, Identifiable {
        case zhHans = "zh-Hans"
        case en = "en"

        var id: String { rawValue }

        /// 语言选择列表里展示的名字（用各自语言的自称，不随当前 UI 语言变）。
        var displayName: String {
            switch self {
            case .zhHans: return "简体中文"
            case .en: return "English"
            }
        }
    }

    /// AppStorage key（AC-5 持久化）。
    static let storageKey = "app_language"

    @Published private(set) var currentLanguage: Language

    /// 当前语言对应的 `.lproj` bundle；找不到时 fallback 主 bundle。
    private var bundle: Bundle

    private init() {
        let resolved = Self.resolveInitialLanguage()
        self.currentLanguage = resolved
        self.bundle = Self.loadBundle(for: resolved)
    }

    /// 冷启动语言解析（AC-5）：
    ///   1. 已持久化 `app_language` → 用它
    ///   2. 无值 → 读系统首选语言（zh* → 中文，否则英文）（FR-2）
    static func resolveInitialLanguage() -> Language {
        if let saved = UserDefaults.standard.string(forKey: storageKey),
           let lang = Language(rawValue: saved) {
            return lang
        }
        let preferred = Locale.preferredLanguages.first ?? "en"
        return preferred.hasPrefix("zh") ? .zhHans : .en
    }

    private static func loadBundle(for language: Language) -> Bundle {
        guard let path = Bundle.main.path(forResource: language.rawValue, ofType: "lproj"),
              let langBundle = Bundle(path: path) else {
            return Bundle.main
        }
        return langBundle
    }

    /// 切换语言：持久化 + 重载 bundle + 触发 SwiftUI 重渲染（即时，无需重启）。
    func setLanguage(_ language: Language) {
        guard language != currentLanguage else { return }
        UserDefaults.standard.set(language.rawValue, forKey: Self.storageKey)
        bundle = Self.loadBundle(for: language)
        currentLanguage = language
    }

    /// 查表。key 命中 String Catalog 时返回目标语言文案；未命中返回 key 本身
    /// （便于开发期定位漏 key）。
    func t(_ key: String) -> String {
        bundle.localizedString(forKey: key, value: key, table: nil)
    }

    /// 带参数版本（AC-6 动态拼接）。catalog 里用 `%@` / `%d` 占位，
    /// 由调用方保证占位顺序符合目标语言语序。
    func t(_ key: String, _ args: CVarArg...) -> String {
        let format = bundle.localizedString(forKey: key, value: key, table: nil)
        return String(format: format, arguments: args)
    }
}
