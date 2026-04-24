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

struct BindPhoneRequest: Encodable {
    let phone: String
    let code: String
}

struct SwitchRoleRequest: Encodable {
    let role: String
}

// MARK: - Apple Sign-In (W18-A)

struct AppleUserInfoPayload: Encodable {
    let email: String?
    let firstName: String?
    let lastName: String?

    enum CodingKeys: String, CodingKey {
        case email
        case firstName = "first_name"
        case lastName = "last_name"
    }
}

struct AppleLoginRequest: Encodable {
    let identityToken: String
    let authorizationCode: String
    let userInfo: AppleUserInfoPayload?

    enum CodingKeys: String, CodingKey {
        case identityToken = "identity_token"
        case authorizationCode = "authorization_code"
        case userInfo = "user_info"
    }
}
