import Foundation

struct Payment: Codable, Identifiable {
    let id: String
    let orderId: String
    let userId: String
    let amount: Decimal
    let paymentType: String
    let status: String
    let createdAt: String
}
