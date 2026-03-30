import SwiftUI

struct CompanionStatsResponse: Decodable {
    let todayOrders: Int
    let totalOrders: Int
    let avgRating: Double
    let totalEarnings: Double
}

@MainActor
class CompanionProfileViewModel: ObservableObject {
    @Published var companions: [CompanionProfile] = []
    @Published var selectedCompanion: CompanionProfile?
    @Published var bio: String = ""
    @Published var serviceArea: String = ""
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var isSaved = false
    @Published var stats: CompanionStatsResponse?

    // MARK: - List & Detail

    func loadCompanions(area: String? = nil, search: String? = nil) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            var queryItems: [URLQueryItem] = []
            if let area, !area.isEmpty {
                queryItems.append(URLQueryItem(name: "area", value: area))
            }
            if let search, !search.isEmpty {
                queryItems.append(URLQueryItem(name: "search", value: search))
            }
            companions = try await APIClient.shared.request(
                .companions,
                queryItems: queryItems.isEmpty ? nil : queryItems
            )
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func loadDetail(id: String) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            selectedCompanion = try await APIClient.shared.request(.companion(id: id))
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Apply as Companion

    func applyAsCompanion(
        realName: String,
        idNumber: String?,
        serviceArea: String?,
        bio: String?
    ) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let body = ApplyCompanionRequest(
                realName: realName,
                idNumber: idNumber,
                serviceArea: serviceArea,
                bio: bio
            )
            selectedCompanion = try await APIClient.shared.request(
                .applyCompanion,
                body: body
            )
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Update Own Profile

    func loadOwnProfile() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let profile: CompanionProfile = try await APIClient.shared.request(
                .companion(id: "me")
            )
            selectedCompanion = profile
            bio = profile.bio ?? ""
            serviceArea = profile.serviceArea ?? ""
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func updateProfile() async {
        isLoading = true
        errorMessage = nil
        isSaved = false
        defer { isLoading = false }

        do {
            let body = UpdateCompanionProfileRequest(
                bio: bio.isEmpty ? nil : bio,
                serviceArea: serviceArea.isEmpty ? nil : serviceArea
            )
            selectedCompanion = try await APIClient.shared.request(
                .updateCompanionProfile,
                body: body
            )
            isSaved = true
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func loadStats() async {
        do {
            stats = try await APIClient.shared.request(.companionStats)
        } catch {
            // Stats are non-critical; silently ignore
        }
    }
}
