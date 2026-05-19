import Foundation

/// F-05: thin wrapper around APIClient for family-member CRUD.
@MainActor
final class FamilyMemberService {
    static let shared = FamilyMemberService()
    private let api: APIClient

    init(api: APIClient = .shared) {
        self.api = api
    }

    func list() async throws -> [FamilyMember] {
        let response: FamilyMemberListResponse = try await api.request(.familyMembers)
        return response.items
    }

    func create(_ body: CreateFamilyMemberRequest) async throws -> FamilyMember {
        try await api.request(.createFamilyMember, body: body)
    }

    func update(id: String, body: UpdateFamilyMemberRequest) async throws -> FamilyMember {
        try await api.request(.updateFamilyMember(id: id), body: body)
    }

    func delete(id: String) async throws {
        try await api.requestVoid(.deleteFamilyMember(id: id))
    }
}
