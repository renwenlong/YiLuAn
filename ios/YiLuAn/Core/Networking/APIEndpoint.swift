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
}
