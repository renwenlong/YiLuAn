import SwiftUI

@MainActor
class ProfileViewModel: ObservableObject {
    @Published var patientProfile: PatientProfile?
    @Published var companionProfile: CompanionProfile?
    @Published var displayName: String = ""
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var isUploadingAvatar = false

    func loadProfile(role: UserRole?) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            switch role {
            case .patient:
                patientProfile = try await APIClient.shared.request(.patientProfile)
            case .companion:
                companionProfile = try await APIClient.shared.request(
                    .companion(id: "me")
                )
            case .none:
                break
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func updateDisplayName() async -> User? {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let body = UpdateDisplayNameRequest(displayName: displayName)
            let user: User = try await APIClient.shared.request(.updateMe, body: body)
            return user
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }

    func uploadAvatar(imageData: Data) async -> String? {
        isUploadingAvatar = true
        errorMessage = nil
        defer { isUploadingAvatar = false }

        do {
            let response = try await APIClient.shared.uploadImage(
                .uploadAvatar,
                imageData: imageData
            )
            return response.avatarUrl
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }
}
