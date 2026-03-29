import Foundation

struct SendOTPRequest: Encodable {
    let phone: String
}

struct VerifyOTPRequest: Encodable {
    let phone: String
    let code: String
}

struct TokenResponse: Decodable {
    let accessToken: String
    let refreshToken: String
    let user: User
}

struct RefreshTokenRequest: Encodable {
    let refreshToken: String
}

struct RefreshTokenResponse: Decodable {
    let accessToken: String
    let refreshToken: String
}
