import Foundation

/// 家庭陪诊分享 Service (ADR-0036 / PRD-001 v1.2 §F2 / S2-INT-004)
///
/// 端点划分：
/// - Owner 路径（订单 owner 鉴权）：createShare / listShares / revokeShare
/// - Family 路径（未登录访客，share_session JWT 流）：
///     sendShareOTP → exchangeShareSession(otp: ...) → fetchShareOrder(session: ...)
///
/// iOS App 走 F2 OTP 兜底（与微信端 wx_openid 静默授权对立）：
///   1. UniversalLink / 自定义 scheme 截获 https://m.yiluan.cn/s/{token}
///   2. UI 引导输入手机号 → sendShareOTP
///   3. UI 输入 6 位验证码 → exchangeShareSession(phone+otp) → 拿到 share_session
///   4. fetchShareOrder(session:) 拉脱敏视图
///   5. share_session 存 Keychain（受 ShareSessionStore 管理，过期重走 OTP）
enum ShareService {

    // MARK: - Owner endpoints

    /// 患者端为订单创建分享链接。返回新建 token + 当前 active count。
    /// 后端约束：同订单 active token 上限 3，第 4 个自动 revoke 最老。
    static func createShare(orderId: String, scope: ShareScope = .full) async throws -> CreateShareResponse {
        struct Body: Encodable {
            let shareScope: ShareScope
            enum CodingKeys: String, CodingKey { case shareScope = "share_scope" }
        }
        return try await APIClient.shared.request(
            .createShare(orderId: orderId),
            body: Body(shareScope: scope)
        )
    }

    /// 患者端查询订单当前 active 分享列表。
    static func listShares(orderId: String) async throws -> ListSharesResponse {
        try await APIClient.shared.request(.listShares(orderId: orderId))
    }

    /// 患者端吊销单个 token（按 token 行 UUID）。
    /// 触发服务端 WS close 4013 / 已发 viewer session 失效。
    /// ANDROID-DEV-B7: 后端路径需 orderId + tokenId。
    static func revokeShare(orderId: String, tokenId: String) async throws {
        try await APIClient.shared.requestVoid(.revokeShare(orderId: orderId, tokenId: tokenId))
    }

    // MARK: - Family endpoints (OTP fallback path, F2)

    /// 家属侧请求向 phone 下发短信验证码。token = 短链中的 share_token。
    /// 后端双轴频控：单 token 24h ≤ 5 次发码、单手机号 1h ≤ 3 个不同 token 绑定。
    static func sendShareOTP(token: String, phone: String) async throws -> SendShareOTPResponse {
        try await APIClient.shared.request(
            .sendShareOTP(token: token),
            body: SendShareOTPRequest(phone: phone)
        )
    }

    /// 家属侧用 phone+otp 换 share_session JWT（30min TTL）。
    /// 返回的 share_session 调用方负责存 Keychain（ShareSessionStore.save）。
    static func exchangeShareSession(
        token: String,
        phone: String,
        otp: String
    ) async throws -> ExchangeSessionResponse {
        try await APIClient.shared.request(
            .exchangeShareSession(token: token),
            body: ExchangeSessionRequest.otp(phone: phone, otp: otp)
        )
    }

    /// 家属侧拉脱敏订单视图。需传入有效 share_session JWT。
    /// 401 → session 过期/被 revoke，调用方应跳回 OTP 输入页。
    static func fetchShareOrder(shareSession: String) async throws -> ShareOrderResponse {
        try await APIClient.shared.request(
            .getShareSessionOrder,
            shareSession: shareSession
        )
    }
}
