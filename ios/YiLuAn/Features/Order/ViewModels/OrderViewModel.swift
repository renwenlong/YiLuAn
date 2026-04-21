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

struct HospitalListResponse: Decodable {
    let items: [Hospital]
    let total: Int
}

@MainActor
class OrderViewModel: ObservableObject {
    @Published var orders: [Order] = []
    @Published var currentOrder: Order?
    @Published var hospitals: [Hospital] = []
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var total = 0
    /// 当后端返回 PHONE_REQUIRED 时设置，view 进行弹窗 + 引导用户去绑定手机号。
    @Published var phoneRequiredMessage: String?
    /// 当后端返回 PAYMENT_REQUIRED 时设置，view 弹窗并提示用户/陪诊师先完成支付。
    @Published var paymentRequiredMessage: String?
    /// 当后端返回 VERIFICATION_REQUIRED 时设置，view 弹窗并提示陪诊师资质未审核通过。
    @Published var verificationRequiredMessage: String?

    /// 统一的错误处理：遇到机器可读码写入对应的 *RequiredMessage，
    /// 其余错误写到 errorMessage。
    private func handleError(_ error: Error) {
        if let apiError = error as? APIError {
            switch apiError {
            case .phoneRequired(let msg):
                phoneRequiredMessage = msg
                return
            case .paymentRequired(let msg):
                paymentRequiredMessage = msg
                return
            case .verificationRequired(let msg):
                verificationRequiredMessage = msg
                return
            default:
                break
            }
        }
        errorMessage = error.localizedDescription
    }

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
            handleError(error)
        }
    }

    func loadOrder(id: String) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            currentOrder = try await APIClient.shared.request(.order(id: id))
        } catch {
            handleError(error)
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
            handleError(error)
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
            handleError(error)
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
            handleError(error)
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
            handleError(error)
            return nil
        }
    }

    func searchHospitals(keyword: String) async {
        guard !keyword.isEmpty else {
            hospitals = []
            return
        }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let queryItems = [URLQueryItem(name: "keyword", value: keyword)]
            let response: [Hospital] = try await APIClient.shared.request(
                .hospitals, queryItems: queryItems
            )
            hospitals = response
        } catch {
            handleError(error)
        }
    }
}
