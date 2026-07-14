import Foundation
import SwiftUI

/// F-05: 家人 / 实际就诊人管理 ViewModel.
@MainActor
final class FamilyMembersViewModel: ObservableObject {
    @Published var members: [FamilyMember] = []
    @Published var isLoading = false
    @Published var errorMessage: String?

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            members = try await FamilyMembersService.list()
        } catch {
            errorMessage = (error as? LocalizedError)?.errorDescription ?? LocalizationManager.shared.t("order.loadFailed")
        }
    }

    func create(name: String, relation: String, phone: String?, gender: String, age: Int?, notes: String?) async -> Bool {
        let trimmedPhone = phone?.trimmingCharacters(in: .whitespaces)
        let body = FamilyMemberRequest(
            name: name,
            relation: relation,
            phone: (trimmedPhone?.isEmpty ?? true) ? nil : trimmedPhone,
            gender: gender,
            age: age,
            medicalNotes: (notes?.isEmpty ?? true) ? nil : notes
        )
        do {
            _ = try await FamilyMembersService.create(body)
            await load()
            return true
        } catch {
            errorMessage = (error as? LocalizedError)?.errorDescription ?? LocalizationManager.shared.t("emergencyContacts.addFailed")
            return false
        }
    }

    func delete(_ member: FamilyMember) async {
        do {
            try await FamilyMembersService.delete(id: member.id)
            await load()
        } catch {
            errorMessage = (error as? LocalizedError)?.errorDescription ?? LocalizationManager.shared.t("emergencyContacts.deleteFailed")
        }
    }
}
