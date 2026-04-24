import Foundation
import AuthenticationServices
#if canImport(UIKit)
import UIKit
#endif

/// Result of a successful Apple Sign-In flow.
///
/// Apple gives `email` / `fullName` only on the very first authorization for
/// a given Apple ID; subsequent sign-ins return only the stable `user`
/// identifier and the JWT (`identityToken`).
struct AppleCredential: Equatable {
    let identityToken: String
    let authorizationCode: String
    let user: String
    let email: String?
    let fullName: PersonNameComponents?
}

/// Errors emitted by ``AppleSignInService``.
enum AppleSignInError: Error, Equatable {
    /// The system returned a non-AppleID credential (e.g. a password credential).
    case unsupportedCredential
    /// `identityToken` or `authorizationCode` was missing/undecodable.
    case missingTokenData
    /// The user cancelled the sheet (typically `ASAuthorizationError.canceled`).
    case userCancelled
    /// Anything else surfaced by `ASAuthorizationController`.
    case authorizationFailed(message: String)
}

// MARK: - Provider abstraction (for tests)

/// Thin protocol around `ASAuthorizationAppleIDProvider` so unit tests can
/// substitute a stub that emits canned credentials without touching UIKit.
protocol AppleAuthorizationRequestProviding {
    func makeRequest() -> ASAuthorizationAppleIDRequest
}

struct DefaultAppleAuthorizationRequestProvider: AppleAuthorizationRequestProviding {
    func makeRequest() -> ASAuthorizationAppleIDRequest {
        let provider = ASAuthorizationAppleIDProvider()
        let request = provider.createRequest()
        request.requestedScopes = [.fullName, .email]
        return request
    }
}

// MARK: - Service

@MainActor
final class AppleSignInService: NSObject {
    private let requestProvider: AppleAuthorizationRequestProviding
    private var continuation: CheckedContinuation<AppleCredential, Error>?

    init(requestProvider: AppleAuthorizationRequestProviding = DefaultAppleAuthorizationRequestProvider()) {
        self.requestProvider = requestProvider
    }

    /// Present the system Sign-In with Apple sheet and return the resulting
    /// credential. Throws ``AppleSignInError`` on failure / cancel.
    func signIn() async throws -> AppleCredential {
        let request = requestProvider.makeRequest()
        let controller = ASAuthorizationController(authorizationRequests: [request])
        controller.delegate = self
        controller.presentationContextProvider = self

        return try await withCheckedThrowingContinuation { cont in
            self.continuation = cont
            controller.performRequests()
        }
    }

    /// Pure helper exposed for unit tests: turn an `ASAuthorizationAppleIDCredential`
    /// (or stub thereof) into our value-typed `AppleCredential`.
    static func makeCredential(
        from raw: AppleIDCredentialRepresentable
    ) throws -> AppleCredential {
        guard
            let idTokenData = raw.identityToken,
            let identityToken = String(data: idTokenData, encoding: .utf8),
            let codeData = raw.authorizationCode,
            let authorizationCode = String(data: codeData, encoding: .utf8)
        else {
            throw AppleSignInError.missingTokenData
        }
        return AppleCredential(
            identityToken: identityToken,
            authorizationCode: authorizationCode,
            user: raw.user,
            email: raw.email,
            fullName: raw.fullName
        )
    }
}

// MARK: - Test seam

/// Minimal subset of `ASAuthorizationAppleIDCredential` we actually read.
/// The real Apple type already conforms (its properties match by name).
protocol AppleIDCredentialRepresentable {
    var user: String { get }
    var identityToken: Data? { get }
    var authorizationCode: Data? { get }
    var email: String? { get }
    var fullName: PersonNameComponents? { get }
}

extension ASAuthorizationAppleIDCredential: AppleIDCredentialRepresentable {}

// MARK: - ASAuthorizationControllerDelegate

extension AppleSignInService: ASAuthorizationControllerDelegate {
    func authorizationController(
        controller: ASAuthorizationController,
        didCompleteWithAuthorization authorization: ASAuthorization
    ) {
        defer { self.continuation = nil }
        guard let cont = self.continuation else { return }

        guard let appleCredential = authorization.credential as? ASAuthorizationAppleIDCredential else {
            cont.resume(throwing: AppleSignInError.unsupportedCredential)
            return
        }
        do {
            let credential = try Self.makeCredential(from: appleCredential)
            cont.resume(returning: credential)
        } catch {
            cont.resume(throwing: error)
        }
    }

    func authorizationController(
        controller: ASAuthorizationController,
        didCompleteWithError error: Error
    ) {
        defer { self.continuation = nil }
        guard let cont = self.continuation else { return }

        if let asError = error as? ASAuthorizationError, asError.code == .canceled {
            cont.resume(throwing: AppleSignInError.userCancelled)
        } else {
            cont.resume(throwing: AppleSignInError.authorizationFailed(message: error.localizedDescription))
        }
    }
}

// MARK: - ASAuthorizationControllerPresentationContextProviding

extension AppleSignInService: ASAuthorizationControllerPresentationContextProviding {
    func presentationAnchor(for controller: ASAuthorizationController) -> ASPresentationAnchor {
        // Best-effort key window lookup. Falls back to a fresh anchor in
        // unusual states (e.g. during early-launch flows).
        #if canImport(UIKit)
        if let scene = UIApplication.shared.connectedScenes
            .compactMap({ $0 as? UIWindowScene })
            .first(where: { $0.activationState == .foregroundActive }),
           let window = scene.windows.first(where: { $0.isKeyWindow }) ?? scene.windows.first
        {
            return window
        }
        return ASPresentationAnchor()
        #else
        return ASPresentationAnchor()
        #endif
    }
}
