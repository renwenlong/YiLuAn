import Foundation

/// Precheck HTTP service — GET 4 信任卡 summary
///
/// **S3-DEV-003-TRUST-UI-IOS**
///
/// 端点: `GET /api/v1/users/orders/{order_id}/precheck-status`
/// 后端: `backend/app/api/v1/users_precheck.py:91`
/// 响应: `OrderPrecheckSummaryView` (`backend/app/schemas/order_precheck.py:174`)
///
/// 鉴权: 已登录 access_token (走 APIClient 默认 Bearer header).
/// ABAC: Layer 2 endpoint 检查 order owner (mismatch → 404 mask 防枚举).
///
/// 用法:
/// ```
/// let summary = try await PrecheckService.shared.fetchPrecheckStatus(orderId: order.id)
/// ```
enum PrecheckService {
    static func fetchPrecheckStatus(orderId: String) async throws -> OrderPrecheckSummary {
        let endpoint = APIEndpoint(
            path: "users/orders/\(orderId)/precheck-status",
            method: .get,
            requiresAuth: true
        )
        return try await APIClient.shared.request(endpoint)
    }
}
