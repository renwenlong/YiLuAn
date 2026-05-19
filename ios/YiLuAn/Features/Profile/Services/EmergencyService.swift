import Foundation

/// [F-03] EmergencyService — 紧急联系人 CRUD + 触发紧急事件 + 历史。
/// 后端：`/api/v1/emergency/...`。
enum EmergencyService {

    // MARK: - Contacts

    static func listContacts() async throws -> [EmergencyContact] {
        try await APIClient.shared.request(.emergencyContacts)
    }

    static func createContact(_ body: EmergencyContactRequest) async throws -> EmergencyContact {
        try await APIClient.shared.request(.createEmergencyContact, body: body)
    }

    static func updateContact(id: String, body: EmergencyContactRequest) async throws -> EmergencyContact {
        try await APIClient.shared.request(.updateEmergencyContact(id: id), body: body)
    }

    static func deleteContact(id: String) async throws {
        try await APIClient.shared.requestVoid(.deleteEmergencyContact(id: id))
    }

    // MARK: - Hotline + Trigger

    static func hotline() async throws -> EmergencyHotlineResponse {
        try await APIClient.shared.request(.emergencyHotline)
    }

    static func trigger(_ body: EmergencyTriggerRequest) async throws -> EmergencyTriggerResponse {
        try await APIClient.shared.request(.triggerEmergencyEvent, body: body)
    }

    // MARK: - History

    static func events() async throws -> [EmergencyEvent] {
        try await APIClient.shared.request(.emergencyEvents)
    }
}
