import Foundation

enum HTTPMethod: String {
    case get = "GET"
    case post = "POST"
    case put = "PUT"
    case delete = "DELETE"
    case patch = "PATCH"
}

struct APIEndpoint {
    let path: String
    let method: HTTPMethod
    let requiresAuth: Bool

    var url: URL {
        AppConfig.apiBaseURL.appendingPathComponent(path)
    }

    // MARK: - Auth
    static let sendOTP = APIEndpoint(path: "auth/send-otp", method: .post, requiresAuth: false)
    static let verifyOTP = APIEndpoint(path: "auth/verify-otp", method: .post, requiresAuth: false)
    static let refreshToken = APIEndpoint(path: "auth/refresh", method: .post, requiresAuth: false)
    static let bindPhone = APIEndpoint(path: "auth/bind-phone", method: .post, requiresAuth: true)
    static let appleLogin = APIEndpoint(path: "auth/apple/login", method: .post, requiresAuth: false)

    // MARK: - Users
    static let me = APIEndpoint(path: "users/me", method: .get, requiresAuth: true)
    static let updateMe = APIEndpoint(path: "users/me", method: .put, requiresAuth: true)
    static let deleteAccount = APIEndpoint(path: "users/me", method: .delete, requiresAuth: true)
    static let switchRole = APIEndpoint(path: "users/me/switch-role", method: .post, requiresAuth: true)
    static let uploadAvatar = APIEndpoint(path: "users/me/avatar", method: .post, requiresAuth: true)

    // MARK: - Patient Profile
    static let patientProfile = APIEndpoint(path: "users/me/patient-profile", method: .get, requiresAuth: true)
    static let updatePatientProfile = APIEndpoint(path: "users/me/patient-profile", method: .put, requiresAuth: true)

    // MARK: - Companions
    static let companions = APIEndpoint(path: "companions", method: .get, requiresAuth: true)
    static func companion(id: String) -> APIEndpoint {
        APIEndpoint(path: "companions/\(id)", method: .get, requiresAuth: true)
    }
    static let applyCompanion = APIEndpoint(path: "companions/apply", method: .post, requiresAuth: true)
    static let updateCompanionProfile = APIEndpoint(path: "companions/me", method: .put, requiresAuth: true)
    static let companionStats = APIEndpoint(path: "companions/me/stats", method: .get, requiresAuth: true)

    // MARK: - Orders
    static let orders = APIEndpoint(path: "orders", method: .get, requiresAuth: true)
    static let createOrder = APIEndpoint(path: "orders", method: .post, requiresAuth: true)

    // MARK: - Public (S2-REQ-003-P5c)
    static let publicServicePackages = APIEndpoint(
        path: "public/service-packages",
        method: .get,
        requiresAuth: false
    )
    static func order(id: String) -> APIEndpoint {
        APIEndpoint(path: "orders/\(id)", method: .get, requiresAuth: true)
    }
    static func orderAction(id: String, action: String) -> APIEndpoint {
        APIEndpoint(path: "orders/\(id)/\(action)", method: .post, requiresAuth: true)
    }
    static func payOrder(id: String) -> APIEndpoint {
        APIEndpoint(path: "orders/\(id)/pay", method: .post, requiresAuth: true)
    }
    static func refundOrder(id: String) -> APIEndpoint {
        APIEndpoint(path: "orders/\(id)/refund", method: .post, requiresAuth: true)
    }

    // MARK: - Contracts (S3-DEV-001-CONTRACT-API, PR #206 + #207 bridge)
    static func contractAccept(id: String) -> APIEndpoint {
        APIEndpoint(path: "contracts/\(id)/accept", method: .post, requiresAuth: true)
    }
    static func contractDetail(id: String) -> APIEndpoint {
        APIEndpoint(path: "contracts/\(id)", method: .get, requiresAuth: true)
    }

    // MARK: - Chat
    static func chatMessages(orderId: String) -> APIEndpoint {
        APIEndpoint(path: "chats/\(orderId)/messages", method: .get, requiresAuth: true)
    }
    static func sendChatMessage(orderId: String) -> APIEndpoint {
        APIEndpoint(path: "chats/\(orderId)/messages", method: .post, requiresAuth: true)
    }
    static func markChatRead(orderId: String) -> APIEndpoint {
        APIEndpoint(path: "chats/\(orderId)/read", method: .post, requiresAuth: true)
    }

    // MARK: - Reviews
    static func createReview(orderId: String) -> APIEndpoint {
        APIEndpoint(path: "orders/\(orderId)/review", method: .post, requiresAuth: true)
    }
    static func orderReview(orderId: String) -> APIEndpoint {
        APIEndpoint(path: "orders/\(orderId)/review", method: .get, requiresAuth: true)
    }
    static func companionReviews(companionId: String) -> APIEndpoint {
        APIEndpoint(path: "companions/\(companionId)/reviews", method: .get, requiresAuth: true)
    }

    // MARK: - Notifications
    static let notifications = APIEndpoint(path: "notifications", method: .get, requiresAuth: true)
    static let unreadCount = APIEndpoint(path: "notifications/unread-count", method: .get, requiresAuth: true)
    static func markNotificationRead(id: String) -> APIEndpoint {
        APIEndpoint(path: "notifications/\(id)/read", method: .post, requiresAuth: true)
    }
    static let markAllNotificationsRead = APIEndpoint(path: "notifications/read-all", method: .post, requiresAuth: true)
    static let registerDevice = APIEndpoint(path: "notifications/device-token", method: .post, requiresAuth: true)
    static let deleteDevice = APIEndpoint(path: "notifications/device-token", method: .delete, requiresAuth: true)

    // MARK: - Hospitals
    static let hospitals = APIEndpoint(path: "hospitals", method: .get, requiresAuth: true)
    static func hospital(id: String) -> APIEndpoint {
        APIEndpoint(path: "hospitals/\(id)", method: .get, requiresAuth: false)
    }

    // MARK: - Wallet
    static let wallet = APIEndpoint(path: "wallet", method: .get, requiresAuth: true)
    static let walletTransactions = APIEndpoint(path: "wallet/transactions", method: .get, requiresAuth: true)

    // MARK: - Family Members (F-05)
    static let familyMembers = APIEndpoint(path: "users/me/family-members", method: .get, requiresAuth: true)
    static let createFamilyMember = APIEndpoint(path: "users/me/family-members", method: .post, requiresAuth: true)
    static func updateFamilyMember(id: String) -> APIEndpoint {
        APIEndpoint(path: "users/me/family-members/\(id)", method: .patch, requiresAuth: true)
    }
    static func deleteFamilyMember(id: String) -> APIEndpoint {
        APIEndpoint(path: "users/me/family-members/\(id)", method: .delete, requiresAuth: true)
    }

    // MARK: - Emergency (F-03)
    static let emergencyContacts = APIEndpoint(path: "emergency/contacts", method: .get, requiresAuth: true)
    static let createEmergencyContact = APIEndpoint(path: "emergency/contacts", method: .post, requiresAuth: true)
    static func updateEmergencyContact(id: String) -> APIEndpoint {
        APIEndpoint(path: "emergency/contacts/\(id)", method: .put, requiresAuth: true)
    }
    static func deleteEmergencyContact(id: String) -> APIEndpoint {
        APIEndpoint(path: "emergency/contacts/\(id)", method: .delete, requiresAuth: true)
    }
    static let emergencyHotline = APIEndpoint(path: "emergency/hotline", method: .get, requiresAuth: true)
    static let triggerEmergencyEvent = APIEndpoint(path: "emergency/events", method: .post, requiresAuth: true)
    static let emergencyEvents = APIEndpoint(path: "emergency/events", method: .get, requiresAuth: true)

    // MARK: - Hospitals (extra)
    static let hospitalFilters = APIEndpoint(path: "hospitals/filters", method: .get, requiresAuth: false)
    static let nearestHospitalRegion = APIEndpoint(path: "hospitals/nearest-region", method: .get, requiresAuth: false)

    // MARK: - Followup Reminders (F-07)
    static func createFollowupReminder(orderId: String) -> APIEndpoint {
        APIEndpoint(path: "orders/\(orderId)/followup-reminders", method: .post, requiresAuth: true)
    }
    static let myFollowupReminders = APIEndpoint(path: "orders/me/followup-reminders", method: .get, requiresAuth: true)
    static func cancelFollowupReminder(id: String) -> APIEndpoint {
        APIEndpoint(path: "orders/me/followup-reminders/\(id)", method: .delete, requiresAuth: true)
    }

    // MARK: - Family Share (ADR-0036 §2.7 / PRD-001 v1.2 §4)
    // F2 家属端分享链路。权限类型按后端镶嵌：
    //   - 订单 owner 侧（3 个端点）：requiresAuth=true
    //   - 家属侧走 share_session（3 个端点）：requiresAuth=false，
    //     调用方手动在 Authorization header 贴 share_session JWT

    /// POST /api/v1/orders/{order_id}/shares  — owner 创建分享链接
    static func createShare(orderId: String) -> APIEndpoint {
        APIEndpoint(path: "orders/\(orderId)/shares", method: .post, requiresAuth: true)
    }

    /// GET /api/v1/orders/{order_id}/shares  — owner 查询当前 active token 列表
    static func listShares(orderId: String) -> APIEndpoint {
        APIEndpoint(path: "orders/\(orderId)/shares", method: .get, requiresAuth: true)
    }

    /// DELETE /api/v1/shares/{token_id}  — owner 吊销单个 token（触发 WS close 4013）
    static func revokeShare(tokenId: String) -> APIEndpoint {
        APIEndpoint(path: "shares/\(tokenId)", method: .delete, requiresAuth: true)
    }

    /// POST /api/v1/shares/{token}/otp  — 家属侧请求下发验证码（40 字符 token）
    /// requiresAuth=false—家属未登录，仅开放 share 下转
    static func sendShareOTP(token: String) -> APIEndpoint {
        APIEndpoint(path: "shares/\(token)/otp", method: .post, requiresAuth: false)
    }

    /// POST /api/v1/shares/{token}/session  — 换 share_session JWT（40 字符 token）
    /// requiresAuth=false—未登录家属可访
    static func exchangeShareSession(token: String) -> APIEndpoint {
        APIEndpoint(path: "shares/\(token)/session", method: .post, requiresAuth: false)
    }

    /// GET /api/v1/shares/session/order  — 家属侧拉脱敏订单视图
    /// requiresAuth=false；Authorization header 贴 share_session JWT 由调用方负责
    static let getShareSessionOrder = APIEndpoint(
        path: "shares/session/order", method: .get, requiresAuth: false
    )
}
