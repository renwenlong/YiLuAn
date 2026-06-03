import Foundation

/// 家属端 share_session JWT 本地存储（S2-INT-004 / F2 OTP 路径）
///
/// share_session 是 30min TTL 的短期 JWT，仅在家属侧浏览订单脱敏视图时使用。
/// 与 access_token 完全隔离：不进 `KeychainManager.accessToken/refreshToken` 命名空间。
///
/// 存储项：
/// - `share_session_jwt`：JWT 字符串
/// - `share_session_expires_at`：ISO8601 过期时间
/// - `share_session_scope`：share_scope 字符串（full / progress_only）
/// - `share_session_order_id`：关联订单 ID
/// - `share_session_token`：换 session 时用的 share_token（短链 ID，刷新 session 时复用）
///
/// 过期判定由本类负责：`activeSession()` 检查 expires_at <= now 则返回 nil + 自动 clear。
enum ShareSessionStore {

    // MARK: - Keychain key namespace

    private enum Keys {
        static let jwt = "share_session_jwt"
        static let expiresAt = "share_session_expires_at"
        static let scope = "share_session_scope"
        static let orderId = "share_session_order_id"
        static let token = "share_session_token"
    }

    /// 已保存的 share session 快照
    struct SavedSession: Equatable {
        let jwt: String
        let expiresAt: Date
        let scope: ShareScope
        let orderId: UUID
        let shareToken: String
    }

    // MARK: - Save / Load / Clear

    /// 保存 share_session（覆盖现有）。
    /// 调用方：ExchangeSession 成功后立即 save。
    static func save(response: ExchangeSessionResponse, shareToken: String) {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        try? KeychainManager.save(key: Keys.jwt, value: response.shareSession)
        try? KeychainManager.save(
            key: Keys.expiresAt,
            value: formatter.string(from: response.shareSessionExpiresAt)
        )
        try? KeychainManager.save(key: Keys.scope, value: response.shareScope.rawValue)
        try? KeychainManager.save(key: Keys.orderId, value: response.orderId.uuidString)
        try? KeychainManager.save(key: Keys.token, value: shareToken)
    }

    /// 返回当前有效的 share session（未过期）。过期或缺字段时返回 nil + 自动 clear。
    static func activeSession() -> SavedSession? {
        guard let jwt = KeychainManager.get(key: Keys.jwt),
              let expiresStr = KeychainManager.get(key: Keys.expiresAt),
              let scopeStr = KeychainManager.get(key: Keys.scope),
              let orderIdStr = KeychainManager.get(key: Keys.orderId),
              let tokenStr = KeychainManager.get(key: Keys.token),
              let expiresAt = parseISO8601(expiresStr),
              let scope = ShareScope(rawValue: scopeStr),
              let orderId = UUID(uuidString: orderIdStr)
        else {
            return nil
        }
        // 过期 → 清掉，返回 nil
        if expiresAt <= Date() {
            clear()
            return nil
        }
        return SavedSession(
            jwt: jwt,
            expiresAt: expiresAt,
            scope: scope,
            orderId: orderId,
            shareToken: tokenStr
        )
    }

    /// 清空全部 share session keychain 项。
    /// 调用方：401 / token 被 owner revoke / 用户主动登出。
    static func clear() {
        KeychainManager.delete(key: Keys.jwt)
        KeychainManager.delete(key: Keys.expiresAt)
        KeychainManager.delete(key: Keys.scope)
        KeychainManager.delete(key: Keys.orderId)
        KeychainManager.delete(key: Keys.token)
    }

    // MARK: - Helpers

    private static func parseISO8601(_ s: String) -> Date? {
        let withFrac = ISO8601DateFormatter()
        withFrac.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = withFrac.date(from: s) { return d }
        let noFrac = ISO8601DateFormatter()
        noFrac.formatOptions = [.withInternetDateTime]
        return noFrac.date(from: s)
    }
}
