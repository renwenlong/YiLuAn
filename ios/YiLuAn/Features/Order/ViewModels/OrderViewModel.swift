import SwiftUI

struct CreateOrderRequest: Encodable {
    let serviceType: String
    let hospitalId: String
    let appointmentDate: String
    let appointmentTime: String
    let description: String?
}

struct OrderListResponse: Decodable {
    let items: [Order]
    let total: Int
}

@MainActor
class OrderViewModel: ObservableObject {
    @Published var orders: [Order] = []
    @Published var currentOrder: Order?
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var total = 0

    func loadOrders(status: String? = nil, page: Int = 1) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            var queryItems = [URLQueryItem(name: "page", value: "\(page)")]
            if let status {
                queryItems.append(URLQueryItem(name: "status", value: status))
            }
            let response: OrderListResponse = try await APIClient.shared.request(
                .orders, queryItems: queryItems
            )
            if page == 1 {
                orders = response.items
            } else {
                orders.append(contentsOf: response.items)
            }
            total = response.total
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func loadOrder(id: String) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            currentOrder = try await APIClient.shared.request(.order(id: id))
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func createOrder(
        serviceType: ServiceType,
        hospitalId: String,
        date: String,
        time: String,
        description: String?
    ) async -> Order? {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let body = CreateOrderRequest(
                serviceType: serviceType.rawValue,
                hospitalId: hospitalId,
                appointmentDate: date,
                appointmentTime: time,
                description: description
            )
            let order: Order = try await APIClient.shared.request(.createOrder, body: body)
            return order
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }

    func performAction(_ action: String, orderId: String) async -> Bool {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            currentOrder = try await APIClient.shared.request(
                .orderAction(id: orderId, action: action)
            )
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func payOrder(id: String) async -> Payment? {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let payment: Payment = try await APIClient.shared.request(.payOrder(id: id))
            return payment
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }

    func refundOrder(id: String) async -> Payment? {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let payment: Payment = try await APIClient.shared.request(.refundOrder(id: id))
            return payment
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }
}
