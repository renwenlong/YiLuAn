import Foundation
import SwiftUI

/// [F-03] 紧急联系人管理 ViewModel — 列表 / 新增 / 更新 / 删除。
/// 后端限制：每个用户最多 3 个联系人；超出/重复手机会 409。
@MainActor
final class EmergencyContactsViewModel: ObservableObject {
    @Published var contacts: [EmergencyContact] = []
    @Published var isLoading = false
    @Published var errorMessage: String?

    static let maxContacts = 3

    var canAddMore: Bool { contacts.count < Self.maxContacts }

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            contacts = try await EmergencyService.listContacts()
        } catch {
            errorMessage = (error as? LocalizedError)?.errorDescription ?? "加载失败"
        }
    }

    func create(name: String, phone: String, relationship: String) async -> Bool {
        let body = EmergencyContactRequest(
            name: name.trimmingCharacters(in: .whitespaces),
            phone: phone.trimmingCharacters(in: .whitespaces),
            relationship: relationship.trimmingCharacters(in: .whitespaces)
        )
        do {
            _ = try await EmergencyService.createContact(body)
            await load()
            return true
        } catch {
            errorMessage = (error as? LocalizedError)?.errorDescription ?? "添加失败"
            return false
        }
    }

    func update(id: String, name: String, phone: String, relationship: String) async -> Bool {
        let body = EmergencyContactRequest(
            name: name.trimmingCharacters(in: .whitespaces),
            phone: phone.trimmingCharacters(in: .whitespaces),
            relationship: relationship.trimmingCharacters(in: .whitespaces)
        )
        do {
            _ = try await EmergencyService.updateContact(id: id, body: body)
            await load()
            return true
        } catch {
            errorMessage = (error as? LocalizedError)?.errorDescription ?? "更新失败"
            return false
        }
    }

    func delete(_ contact: EmergencyContact) async {
        do {
            try await EmergencyService.deleteContact(id: contact.id)
            await load()
        } catch {
            errorMessage = (error as? LocalizedError)?.errorDescription ?? "删除失败"
        }
    }
}
