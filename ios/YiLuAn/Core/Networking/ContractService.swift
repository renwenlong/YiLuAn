import Foundation

/// S3-DEV-001-CONTRACT-UI (ADR-0047 §6.2 + §6.3) — iOS 端 contract API client.
///
/// 对应后端 PR #206 endpoint:
/// - POST /api/v1/contracts/{id}/accept  (用户勾选合同同意, 写 user_audit_logs)
/// - GET  /api/v1/contracts/{id}         (查看合同 + signed URL TTL=15min)
///
/// 不暴露 admin invalidate (admin H5 端走, iOS 用户端不调).

// MARK: - Response models

/// `ContractStatus` 6 状态机 (ADR-0047 §3.1 ground truth).
enum ContractStatus: String, Codable {
    case pendingGeneration = "pending_generation"
    case generating
    case active
    case generationFailed = "generation_failed"
    case generationPermanentlyFailed = "generation_permanently_failed"
    case manuallyInvalidated = "manually_invalidated"

    /// 给用户看的状态文案 (status != .active 时使用).
    var userFacingMessage: String {
        switch self {
        case .pendingGeneration, .generating:
            return "合同生成中,请稍后查看"
        case .active:
            return ""  // signed URL 直接打开 PDF, 不显示文案
        case .generationFailed, .generationPermanentlyFailed:
            return "合同生成失败,客服已介入处理"
        case .manuallyInvalidated:
            return "合同已作废,请联系客服"
        }
    }
}

/// POST /accept 返回。
struct ContractAcceptanceResponse: Codable {
    let contractId: String
    let orderId: String
    let acceptedAt: String  // ISO-8601 from server
    let auditLogId: String

    enum CodingKeys: String, CodingKey {
        case contractId = "contract_id"
        case orderId = "order_id"
        case acceptedAt = "accepted_at"
        case auditLogId = "audit_log_id"
    }
}

/// GET /contracts/{id} 返回。
struct ContractDetailResponse: Codable {
    let contractId: String
    let orderId: String
    let templateVersion: String
    let status: ContractStatus
    let signedUrl: String?
    let signedUrlExpiresAt: String?
    let generatedAt: String?

    enum CodingKeys: String, CodingKey {
        case contractId = "contract_id"
        case orderId = "order_id"
        case templateVersion = "template_version"
        case status
        case signedUrl = "signed_url"
        case signedUrlExpiresAt = "signed_url_expires_at"
        case generatedAt = "generated_at"
    }
}

// MARK: - Service

/// Contract API service.
///
/// 调 `APIClient.shared.request` (同 OrderViewModel pattern).
/// 失败 ViewModel 层 catch 并展示 toast/alert.
final class ContractService {
    private let apiClient: APIClient

    init(apiClient: APIClient = .shared) {
        self.apiClient = apiClient
    }

    /// 用户勾选 "我已阅读" → 写 audit log (POST /accept).
    ///
    /// 失败 ViewModel 层 toast 但不回滚 UI 勾选状态 (服务端有 cron 兜底重试 audit
    /// log 写入; 不要因 audit 网络抖动阻死支付链路, PRD-003 §5 业务诉求).
    func acceptContract(contractId: String) async throws -> ContractAcceptanceResponse {
        return try await apiClient.request(
            .contractAccept(id: contractId),
            body: EmptyBody()
        )
    }

    /// 查看合同详情 + 取 signed URL (15min TTL, ViewerRole.USER).
    ///
    /// 服务端会同时写 user_audit_logs.contract_viewed (PIPL 取证).
    /// `status != .active` 时 `signedUrl == nil`, caller 用
    /// `status.userFacingMessage` 显示文案。
    func getContract(contractId: String) async throws -> ContractDetailResponse {
        return try await apiClient.request(.contractDetail(id: contractId))
    }
}
