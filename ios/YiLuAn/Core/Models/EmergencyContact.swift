import Foundation

/// [F-03] 紧急联系人 + 紧急事件。后端：`/api/v1/emergency/...`。
/// 一个用户最多 3 个紧急联系人；触发事件后端返回前端要拨的号码。
struct EmergencyContact: Codable, Identifiable, Hashable {
    let id: String
    let userId: String?
    let name: String
    let phone: String
    let relationship: String
    let createdAt: Date?
    let updatedAt: Date?
}

/// POST/PUT body. PUT 时全部 optional（部分更新）。
struct EmergencyContactRequest: Encodable {
    var name: String?
    var phone: String?
    var relationship: String?
}

/// 触发紧急事件 body。`contactId` 与 `hotline` 二选一。
struct EmergencyTriggerRequest: Encodable {
    var orderId: String?
    var contactId: String?
    var hotline: Bool = false
    var location: String?
}

struct EmergencyEvent: Codable, Identifiable, Hashable {
    let id: String
    let patientId: String?
    let orderId: String?
    let contactCalled: String
    let contactType: String  // "contact" | "hotline"
    let location: String?
    let triggeredAt: Date?
}

/// 触发响应：`event` + 前端应拨打的号码。
struct EmergencyTriggerResponse: Decodable {
    let event: EmergencyEvent
    let phoneToCall: String
}

struct EmergencyHotlineResponse: Decodable {
    let hotline: String
}

/// 常用关系（与 wechat 一致；后端 free-form string，前端只是推荐选项）。
enum EmergencyRelationship {
    static let presets: [String] = [
        "配偶", "父母", "子女", "兄弟姐妹", "亲戚", "朋友", "其他",
    ]
}
