import Foundation

// MARK: - ShareScope

/// 分享数据切片（ADR-0036 §2.7 + PRD-001 v1.2 §4）
/// 与后端 ShareScope enum 严格对齐，与微信端 share_scope 字段一致。
enum ShareScope: String, Codable, CaseIterable {
    case full
    case progressOnly = "progress_only"

    var displayName: String {
        switch self {
        case .full: return "完整分享（位置+进度+影像+摘要）"
        case .progressOnly: return "仅进度"
        }
    }
}

// MARK: - OrderShareToken

/// 患者端订单分享 token 行（后端 ShareTokenResponse）
/// 7 字段反序列化必测（S2-DEV-004 / S2-INT-002 AC#24）：
///   share_token / share_url / share_scope / share_expires_at
///   share_revoked_at / share_session（在 ExchangeSessionResponse 中）
///   share_active_count（在 CreateShareResponse / ListSharesResponse 中）
struct OrderShareToken: Codable, Identifiable, Equatable {
    let id: UUID
    let shareToken: String
    let shareURL: String
    let shareScope: ShareScope
    let shareExpiresAt: Date
    let shareRevokedAt: Date?
    let createdAt: Date
    let firstAccessedAt: Date?
    let distinctAccessorCount: Int

    enum CodingKeys: String, CodingKey {
        case id
        case shareToken = "share_token"
        case shareURL = "share_url"
        case shareScope = "share_scope"
        case shareExpiresAt = "share_expires_at"
        case shareRevokedAt = "share_revoked_at"
        case createdAt = "created_at"
        case firstAccessedAt = "first_accessed_at"
        case distinctAccessorCount = "distinct_accessor_count"
    }
}

// MARK: - CreateShareResponse

/// POST /api/v1/orders/{order_id}/shares 响应
/// 含 share_active_count（同订单当前 active 数，上限 3）
struct CreateShareResponse: Codable, Equatable {
    let id: UUID
    let shareToken: String
    let shareURL: String
    let shareScope: ShareScope
    let shareExpiresAt: Date
    let shareRevokedAt: Date?
    let createdAt: Date
    let firstAccessedAt: Date?
    let distinctAccessorCount: Int
    let shareActiveCount: Int

    enum CodingKeys: String, CodingKey {
        case id
        case shareToken = "share_token"
        case shareURL = "share_url"
        case shareScope = "share_scope"
        case shareExpiresAt = "share_expires_at"
        case shareRevokedAt = "share_revoked_at"
        case createdAt = "created_at"
        case firstAccessedAt = "first_accessed_at"
        case distinctAccessorCount = "distinct_accessor_count"
        case shareActiveCount = "share_active_count"
    }
}

// MARK: - ListSharesResponse

/// GET /api/v1/orders/{order_id}/shares 响应
struct ListSharesResponse: Codable, Equatable {
    let items: [OrderShareToken]
    let shareActiveCount: Int

    enum CodingKeys: String, CodingKey {
        case items
        case shareActiveCount = "share_active_count"
    }
}

// MARK: - Exchange share_session

/// POST /api/v1/shares/{token}/session 请求体
/// F2 iOS/H5 OTP 兜底路径：phone + otp（与微信 wx_openid 二选一）
struct ExchangeSessionRequest: Codable, Equatable {
    let wxOpenid: String?
    let phone: String?
    let otp: String?

    enum CodingKeys: String, CodingKey {
        case wxOpenid = "wx_openid"
        case phone
        case otp
    }

    /// iOS App / 外部浏览器路径：phone + otp
    static func otp(phone: String, otp: String) -> ExchangeSessionRequest {
        ExchangeSessionRequest(wxOpenid: nil, phone: phone, otp: otp)
    }
}

/// POST /api/v1/shares/{token}/session 响应
/// share_session 是 30min JWT，存 Keychain 由 ShareSessionStore 管理
struct ExchangeSessionResponse: Codable, Equatable {
    let shareSession: String
    let shareSessionExpiresAt: Date
    let shareScope: ShareScope
    let orderId: UUID

    enum CodingKeys: String, CodingKey {
        case shareSession = "share_session"
        case shareSessionExpiresAt = "share_session_expires_at"
        case shareScope = "share_scope"
        case orderId = "order_id"
    }
}

// MARK: - Send OTP

/// POST /api/v1/shares/{token}/otp 请求体
struct SendShareOTPRequest: Codable, Equatable {
    let phone: String
}

/// POST /api/v1/shares/{token}/otp 响应
struct SendShareOTPResponse: Codable, Equatable {
    let sent: Bool
    let maskedPhone: String
    let expiresIn: Int

    enum CodingKeys: String, CodingKey {
        case sent
        case maskedPhone = "masked_phone"
        case expiresIn = "expires_in"
    }
}

// MARK: - Family-facing read-only order view (§2.5 PII rules)

/// 家属端只读陪诊师信息
struct ShareCompanionView: Codable, Equatable {
    let name: String?
    let avatarURL: String?

    enum CodingKeys: String, CodingKey {
        case name
        case avatarURL = "avatar_url"
    }
}

/// GET /api/v1/shares/session/order 响应
/// 严格脱敏视图（§2.5）：患者电话/身份证/medical_notes 不出现
struct ShareOrderResponse: Codable, Equatable {
    let orderId: UUID
    let orderNumber: String
    let status: String
    let serviceType: String
    let appointmentDate: String
    let appointmentTime: String
    let hospitalName: String?
    let patientNameMasked: String?
    let companion: ShareCompanionView?
    let shareScope: ShareScope
    let canViewImages: Bool
    let canViewAISummary: Bool
    let timeline: [ShareTimelineItem]?

    enum CodingKeys: String, CodingKey {
        case orderId = "order_id"
        case orderNumber = "order_number"
        case status
        case serviceType = "service_type"
        case appointmentDate = "appointment_date"
        case appointmentTime = "appointment_time"
        case hospitalName = "hospital_name"
        case patientNameMasked = "patient_name_masked"
        case companion
        case shareScope = "share_scope"
        case canViewImages = "can_view_images"
        case canViewAISummary = "can_view_ai_summary"
        case timeline
    }
}

/// timeline 单条（后端 list[dict]，iOS 端用 generic 结构承载）
struct ShareTimelineItem: Codable, Equatable {
    let at: Date
    let event: String
    let detail: String?
}
