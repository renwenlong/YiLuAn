import XCTest
import AuthenticationServices
@testable import YiLuAn

/// Tests for ``AppleSignInService`` credential parsing and error mapping.
///
/// Real `ASAuthorizationController` flows can't run in a unit test bundle
/// (they need a key window + the Apple ID UI), so we exercise the pure
/// helper ``AppleSignInService.makeCredential(from:)`` via a stub
/// `AppleIDCredentialRepresentable`. This is the same code the live
/// delegate path executes — we just bypass the system UI.
///
/// [W18-A]
@MainActor
final class AppleSignInServiceTests: XCTestCase {

    // MARK: - Stub credential

    private struct StubAppleCredential: AppleIDCredentialRepresentable {
        var user: String
        var identityToken: Data?
        var authorizationCode: Data?
        var email: String?
        var fullName: PersonNameComponents?
    }

    private func nameComponents(given: String, family: String) -> PersonNameComponents {
        var c = PersonNameComponents()
        c.givenName = given
        c.familyName = family
        return c
    }

    // MARK: - Parsing

    func testMakeCredentialParsesAllFields() throws {
        let stub = StubAppleCredential(
            user: "001234.deadbeef.0001",
            identityToken: Data("eyJhbGciOiJSUzI1NiJ9.payload.sig".utf8),
            authorizationCode: Data("auth-code-xyz".utf8),
            email: "person@privaterelay.appleid.com",
            fullName: nameComponents(given: "Test", family: "User")
        )

        let credential = try AppleSignInService.makeCredential(from: stub)

        XCTAssertEqual(credential.user, "001234.deadbeef.0001")
        XCTAssertEqual(credential.identityToken, "eyJhbGciOiJSUzI1NiJ9.payload.sig")
        XCTAssertEqual(credential.authorizationCode, "auth-code-xyz")
        XCTAssertEqual(credential.email, "person@privaterelay.appleid.com")
        XCTAssertEqual(credential.fullName?.givenName, "Test")
        XCTAssertEqual(credential.fullName?.familyName, "User")
    }

    func testMakeCredentialAllowsNilOptionalFields() throws {
        // Subsequent (non-first) sign-ins from Apple omit email + fullName.
        let stub = StubAppleCredential(
            user: "001234.deadbeef.0001",
            identityToken: Data("token".utf8),
            authorizationCode: Data("code".utf8),
            email: nil,
            fullName: nil
        )

        let credential = try AppleSignInService.makeCredential(from: stub)

        XCTAssertNil(credential.email)
        XCTAssertNil(credential.fullName)
        XCTAssertEqual(credential.identityToken, "token")
    }

    // MARK: - Error propagation

    func testMakeCredentialThrowsWhenIdentityTokenMissing() {
        let stub = StubAppleCredential(
            user: "001",
            identityToken: nil,
            authorizationCode: Data("code".utf8),
            email: nil,
            fullName: nil
        )

        XCTAssertThrowsError(try AppleSignInService.makeCredential(from: stub)) { error in
            XCTAssertEqual(error as? AppleSignInError, .missingTokenData)
        }
    }

    func testMakeCredentialThrowsWhenAuthorizationCodeMissing() {
        let stub = StubAppleCredential(
            user: "001",
            identityToken: Data("token".utf8),
            authorizationCode: nil,
            email: nil,
            fullName: nil
        )

        XCTAssertThrowsError(try AppleSignInService.makeCredential(from: stub)) { error in
            XCTAssertEqual(error as? AppleSignInError, .missingTokenData)
        }
    }
}
