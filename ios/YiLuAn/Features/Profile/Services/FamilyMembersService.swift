import Foundation

/// [F-05] FamilyMembersService — CRUD for /api/v1/users/me/family-members.
enum FamilyMembersService {
    static func list() async throws -> [FamilyMember] {
        let res: FamilyMemberListResponse = try await APIClient.shared.request(.familyMembers)
        return res.items
    }

    static func create(_ body: FamilyMemberRequest) async throws -> FamilyMember {
        try await APIClient.shared.request(.createFamilyMember, body: body)
    }

    static func update(id: String, body: FamilyMemberRequest) async throws -> FamilyMember {
        try await APIClient.shared.request(.updateFamilyMember(id: id), body: body)
    }

    static func delete(id: String) async throws {
        try await APIClient.shared.requestVoid(.deleteFamilyMember(id: id))
    }
}
