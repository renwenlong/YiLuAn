import Foundation

enum AppConfig {
    // MARK: - API
    #if DEBUG
    static let baseURL = URL(string: "http://localhost:8000")!
    #else
    static let baseURL = URL(string: "https://api.yiluan.app")!
    #endif

    static let apiVersion = "v1"
    static var apiBaseURL: URL {
        baseURL.appendingPathComponent("api/\(apiVersion)")
    }
    static var wsBaseURL: URL {
        var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false)!
        components.scheme = baseURL.scheme == "https" ? "wss" : "ws"
        return components.url!
    }

    // MARK: - Auth
    static let accessTokenKey = "com.yiluan.accessToken"
    static let refreshTokenKey = "com.yiluan.refreshToken"
    static let otpLength = 6
    static let devOTP = "000000"

    // MARK: - Pagination
    static let defaultPageSize = 20

    // MARK: - Pricing (CNY)
    enum ServicePrice {
        static let fullAccompany: Decimal = 299
        static let halfAccompany: Decimal = 199
        static let errand: Decimal = 149
    }
}
