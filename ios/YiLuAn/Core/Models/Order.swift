import Foundation

enum ServiceType: String, Codable, CaseIterable {
    case fullAccompany = "full_accompany"
    case halfAccompany = "half_accompany"
    case errand

    var displayName: String {
        switch self {
        case .fullAccompany: return "全程陪诊"
        case .halfAccompany: return "半程陪诊"
        case .errand: return "代办"
        }
    }

    var price: Decimal {
        switch self {
        case .fullAccompany: return AppConfig.ServicePrice.fullAccompany
        case .halfAccompany: return AppConfig.ServicePrice.halfAccompany
        case .errand: return AppConfig.ServicePrice.errand
        }
    }
}

enum OrderStatus: String, Codable {
    case created
    case accepted
    case inProgress = "in_progress"
    case completed
    case reviewed
    case cancelledByPatient = "cancelled_by_patient"
    case cancelledByCompanion = "cancelled_by_companion"

    var displayName: String {
        switch self {
        case .created: return "待接单"
        case .accepted: return "已接单"
        case .inProgress: return "进行中"
        case .completed: return "已完成"
        case .reviewed: return "已评价"
        case .cancelledByPatient: return "患者取消"
        case .cancelledByCompanion: return "陪诊师取消"
        }
    }
}

struct Order: Codable, Identifiable {
    let id: String
    let orderNumber: String
    let patientId: String
    let companionId: String?
    let hospitalId: String
    let serviceType: ServiceType
    let status: OrderStatus
    let appointmentDate: Date
    let description: String?
    let price: Decimal
    let createdAt: Date
    let updatedAt: Date

    // Populated from joins
    let hospitalName: String?
    let companionName: String?
    let patientName: String?
}
