import SwiftUI
import Combine

@MainActor
class AuthViewModel: ObservableObject {
    @Published var isAuthenticated = false
    @Published var currentUser: User?
    @Published var isLoading = false
    @Published var errorMessage: String?

    init() {
        // Check for existing token
        if KeychainManager.accessToken != nil {
            isAuthenticated = true
            Task { await fetchCurrentUser() }
        }
    }

    func sendOTP(phone: String) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let request = SendOTPRequest(phone: phone)
            try await APIClient.shared.requestVoid(.sendOTP, body: request)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func verifyOTP(phone: String, code: String) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let request = VerifyOTPRequest(phone: phone, code: code)
            let response: TokenResponse = try await APIClient.shared.request(
                .verifyOTP, body: request
            )
            KeychainManager.accessToken = response.accessToken
            KeychainManager.refreshToken = response.refreshToken
            currentUser = response.user
            isAuthenticated = true
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func fetchCurrentUser() async {
        do {
            currentUser = try await APIClient.shared.request(.me)
        } catch {
            // Token invalid — sign out
            signOut()
        }
    }

    func setRole(_ role: UserRole) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            struct UpdateRoleRequest: Encodable {
                let role: String
            }
            let body = UpdateRoleRequest(role: role.rawValue)
            currentUser = try await APIClient.shared.request(.updateMe, body: body)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    /// Apple Sign-In flow (W18-A): trigger native sheet, exchange identity
    /// token with backend, store our access/refresh tokens.
    func loginWithApple(service: AppleSignInService = AppleSignInService()) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let credential = try await service.signIn()

            var userInfoPayload: AppleUserInfoPayload? = nil
            if credential.email != nil || credential.fullName != nil {
                userInfoPayload = AppleUserInfoPayload(
                    email: credential.email,
                    firstName: credential.fullName?.givenName,
                    lastName: credential.fullName?.familyName
                )
            }

            let body = AppleLoginRequest(
                identityToken: credential.identityToken,
                authorizationCode: credential.authorizationCode,
                userInfo: userInfoPayload
            )
            let response: TokenResponse = try await APIClient.shared.request(
                .appleLogin, body: body
            )
            KeychainManager.accessToken = response.accessToken
            KeychainManager.refreshToken = response.refreshToken
            currentUser = response.user
            isAuthenticated = true
        } catch AppleSignInError.userCancelled {
            // Cancelling is not an error worth surfacing.
            return
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func signOut() {
        KeychainManager.clearTokens()
        isAuthenticated = false
        currentUser = nil
    }

    func switchRole(to role: UserRole) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let body = SwitchRoleRequest(role: role.rawValue)
            currentUser = try await APIClient.shared.request(.switchRole, body: body)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
