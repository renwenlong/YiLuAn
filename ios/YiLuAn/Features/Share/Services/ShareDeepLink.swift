import Foundation

/// 家属端 share deep link 解析（S2-INT-006 #2）
///
/// 截获两类入口，统一抽出 `shareToken`：
/// - **UniversalLink**：`https://m.yiluan.cn/s/{token}`（生产 / 灰度）
/// - **URL scheme**：`yiluan://share/{token}`（debug / 内部测试 fallback）
///
/// 调用方：`YiLuAnApp` `.onOpenURL { url in if let t = ShareDeepLink.parse(url) ... }`。
/// 解析失败返回 nil，调用方负责忽略或提示。
enum ShareDeepLink {

    /// 短链 token 长度严格 40 字符（与后端 `generate_share_token` 配置一致）
    static let tokenLength = 40

    /// 允许的 UniversalLink host（避免被钓鱼链接误识别）
    static let allowedHosts: Set<String> = ["m.yiluan.cn"]

    /// 允许的 URL scheme（debug fallback）
    static let allowedScheme = "yiluan"

    /// 解析入参 url，成功返回 shareToken，失败返回 nil。
    static func parse(_ url: URL) -> String? {
        // 1. UniversalLink: https://m.yiluan.cn/s/{token}
        if let scheme = url.scheme?.lowercased(),
           scheme == "https",
           let host = url.host?.lowercased(),
           allowedHosts.contains(host) {
            return parseUniversalLinkPath(url.path)
        }

        // 2. URL scheme: yiluan://share/{token}
        if url.scheme?.lowercased() == allowedScheme {
            // host = "share", path = "/{token}"
            // 或 host = "{token}" 兼容旧式（不再支持，要求 share/token 二段式）
            if url.host?.lowercased() == "share" {
                let token = url.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
                return validateToken(token)
            }
        }

        return nil
    }

    /// 解析 UniversalLink path 段：`/s/{token}` → token
    private static func parseUniversalLinkPath(_ path: String) -> String? {
        // path 形如 "/s/AbCdEf...0123"
        let components = path.split(separator: "/", omittingEmptySubsequences: true)
        guard components.count == 2, components[0] == "s" else {
            return nil
        }
        return validateToken(String(components[1]))
    }

    /// token 形态校验：长度 + URL-safe 字符集
    /// URL-safe = [A-Za-z0-9_-]
    private static func validateToken(_ raw: String) -> String? {
        guard raw.count == tokenLength else { return nil }
        let urlSafe = CharacterSet(charactersIn:
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
        )
        guard raw.unicodeScalars.allSatisfy({ urlSafe.contains($0) }) else {
            return nil
        }
        return raw
    }
}
