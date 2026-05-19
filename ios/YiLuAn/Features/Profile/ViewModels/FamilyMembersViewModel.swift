import Foundation
import SwiftUI

/// F-05: 家人 / 实际就诊人管理 ViewModel.
@MainActor
final class FamilyMembersViewModel: ObservableObject {
    @Published var members: [FamilyMember] = []
    @Published var isLoading = false
    @Published var errorMessage: String?

    private let service: FamilyMemberService

    init(service: FamilyMemberService = .shared) {
        self.service = service
    }

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            members = try await service.list()
        } catch {
            errorMessage = (error as? LocalizedError)?.errorDescription ?? "加载失败"
        }
    }

    func create(name: String, relation: String, phone: String?, gender: String, age: Int?, notes: String?) async -> Bool {
        let trimmedPhone = phone?.trimmingCharacters(in: .whitespaces)
        let body = CreateFamilyMemberRequest(
            name: name,
            relation: relation,
            phone: (trimmedPhone?.isEmpty ?? true) ? nil : trimmedPhone,
            gender: gender,
            age: age,
            medicalNotes: (notes?.isEmpty ?? true) ? nil : notes
        )
        do {
            _ = try await service.create(body)
            await load()
            return true
        } catch {
            errorMessage = (error as? LocalizedError)?.errorDescription ?? "添加失败"
            return false
        }
    }

    func delete(_ member: FamilyMember) async {
        do {
            try await service.delete(id: member.id)
            await load()
        } catch {
            errorMessage = (error as? LocalizedError)?.errorDescription ?? "删除失败"
        }
    }
}
