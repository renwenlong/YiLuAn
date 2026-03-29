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

    func signOut() {
        KeychainManager.clearTokens()
        isAuthenticated = false
        currentUser = nil
    }
}
