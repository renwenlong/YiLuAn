import Foundation

enum APIError: Error, LocalizedError {
    case invalidURL
    case invalidResponse
    case httpError(statusCode: Int, message: String?)
    case decodingError(Error)
    case networkError(Error)
    case unauthorized
    case phoneRequired(message: String)
    case paymentRequired(message: String)
    case verificationRequired(message: String)

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Invalid URL"
        case .invalidResponse: return "Invalid response from server"
        case .httpError(let code, let msg): return "HTTP \(code): \(msg ?? "Unknown error")"
        case .decodingError(let err): return "Decoding error: \(err.localizedDescription)"
        case .networkError(let err): return "Network error: \(err.localizedDescription)"
        case .unauthorized: return "Unauthorized"
        case .phoneRequired(let msg),
             .paymentRequired(let msg),
             .verificationRequired(let msg):
            return msg
        }
    }

    /// 返回该错误是否属于“前置条件未满足”的哪种机器可读码，供 UI 分发。
    var guardCode: String? {
        switch self {
        case .phoneRequired: return BackendErrorCode.phoneRequired
        case .paymentRequired: return BackendErrorCode.paymentRequired
        case .verificationRequired: return BackendErrorCode.verificationRequired
        default: return nil
        }
    }
}

struct EmptyBody: Encodable {}

/// Backend error payload. Accepts two shapes:
/// - legacy: `{"detail": "..."}`
/// - with error code: `{"detail": {"error_code": "PHONE_REQUIRED", "message": "..."}}`
struct ErrorResponse: Decodable {
    let detail: String?
    let errorCode: String?
    let message: String?

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        // Try decoding detail as a plain string first
        if let s = try? container.decode(String.self, forKey: .detail) {
            self.detail = s
            self.errorCode = nil
            self.message = nil
            return
        }
        // Fallback: detail is a dict
        if let nested = try? container.nestedContainer(keyedBy: DetailKeys.self, forKey: .detail) {
            self.errorCode = try? nested.decode(String.self, forKey: .errorCode)
            self.message = try? nested.decode(String.self, forKey: .message)
            self.detail = self.message
            return
        }
        self.detail = nil
        self.errorCode = nil
        self.message = nil
    }

    private enum CodingKeys: String, CodingKey { case detail }
    private enum DetailKeys: String, CodingKey {
        case errorCode = "error_code"
        case message
    }
}

/// Backend machine-readable error codes. Mirrors `backend/app/core/error_codes.py`.
enum BackendErrorCode {
    static let phoneRequired = "PHONE_REQUIRED"
    static let paymentRequired = "PAYMENT_REQUIRED"
    static let verificationRequired = "VERIFICATION_REQUIRED"
}

/// Compatibility alias used by older call sites and unit tests.
/// New code should reference ``BackendErrorCode`` directly.
typealias APIErrorCode = BackendErrorCode

actor APIClient {
    static let shared = APIClient()

    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder
    private var isRefreshing = false

    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        config.timeoutIntervalForResource = 60
        self.session = URLSession(configuration: config)

        self.decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601

        self.encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.dateEncodingStrategy = .iso8601
    }

    // MARK: - Public API

    func request<T: Decodable>(
        _ endpoint: APIEndpoint,
        body: (some Encodable)? = nil as EmptyBody?,
        queryItems: [URLQueryItem]? = nil
    ) async throws -> T {
        let request = try buildRequest(endpoint, body: body, queryItems: queryItems)
        return try await execute(request, endpoint: endpoint)
    }

    func requestVoid(
        _ endpoint: APIEndpoint,
        body: (some Encodable)? = nil as EmptyBody?
    ) async throws {
        let request = try buildRequest(endpoint, body: body)
        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        if httpResponse.statusCode == 401 && endpoint.requiresAuth {
            try await refreshTokenIfNeeded()
            let retryRequest = try buildRequest(endpoint, body: body)
            let (retryData, retryResponse) = try await session.data(for: retryRequest)
            guard let retryHttp = retryResponse as? HTTPURLResponse,
                  (200...299).contains(retryHttp.statusCode) else {
                try self.throwForFailedResponse(retryData, statusCode: (retryResponse as? HTTPURLResponse)?.statusCode ?? 0)
                throw APIError.unauthorized
            }
            return
        }
        guard (200...299).contains(httpResponse.statusCode) else {
            try self.throwForFailedResponse(data, statusCode: httpResponse.statusCode)
            throw APIError.httpError(statusCode: httpResponse.statusCode, message: nil)
        }
    }

    /// Shared decoder for non-2xx responses. Throws typed guard-errors
    /// (`.phoneRequired` / `.paymentRequired` / `.verificationRequired`) when the
    /// backend returned a recognized error code; otherwise throws `.httpError`
    /// with the backend-provided message (if parsable).
    private nonisolated func throwForFailedResponse(_ data: Data, statusCode: Int) throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let errorMsg = try? decoder.decode(ErrorResponse.self, from: data)
        if statusCode == 400, let code = errorMsg?.errorCode {
            switch code {
            case BackendErrorCode.phoneRequired:
                throw APIError.phoneRequired(message: errorMsg?.message ?? "请先绑定手机号")
            case BackendErrorCode.paymentRequired:
                throw APIError.paymentRequired(message: errorMsg?.message ?? "订单尚未支付")
            case BackendErrorCode.verificationRequired:
                throw APIError.verificationRequired(message: errorMsg?.message ?? "陪诊师资质未审核通过")
            default:
                break
            }
        }
        throw APIError.httpError(statusCode: statusCode, message: errorMsg?.detail)
    }

    func uploadImage(
        _ endpoint: APIEndpoint,
        imageData: Data,
        filename: String = "avatar.jpg"
    ) async throws -> AvatarUploadResponse {
        let boundary = UUID().uuidString
        var request = URLRequest(url: endpoint.url)
        request.httpMethod = endpoint.method.rawValue
        request.setValue(
            "multipart/form-data; boundary=\(boundary)",
            forHTTPHeaderField: "Content-Type"
        )

        if endpoint.requiresAuth, let token = KeychainManager.accessToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        var body = Data()
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"\(filename)\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: image/jpeg\r\n\r\n".data(using: .utf8)!)
        body.append(imageData)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        request.httpBody = body

        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }

        if httpResponse.statusCode == 401 && endpoint.requiresAuth {
            try await refreshTokenIfNeeded()
            if let token = KeychainManager.accessToken {
                request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
            }
            let (retryData, retryResponse) = try await session.data(for: request)
            guard let retryHttp = retryResponse as? HTTPURLResponse,
                  (200...299).contains(retryHttp.statusCode) else {
                throw APIError.unauthorized
            }
            return try decoder.decode(AvatarUploadResponse.self, from: retryData)
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            let errorMsg = try? decoder.decode(ErrorResponse.self, from: data)
            throw APIError.httpError(
                statusCode: httpResponse.statusCode,
                message: errorMsg?.detail
            )
        }

        return try decoder.decode(AvatarUploadResponse.self, from: data)
    }

    // MARK: - Private

    private func buildRequest(
        _ endpoint: APIEndpoint,
        body: (some Encodable)? = nil as EmptyBody?,
        queryItems: [URLQueryItem]? = nil
    ) throws -> URLRequest {
        var components = URLComponents(url: endpoint.url, resolvingAgainstBaseURL: false)
        if let queryItems {
            components?.queryItems = queryItems
        }
        guard let url = components?.url else {
            throw APIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = endpoint.method.rawValue
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        if endpoint.requiresAuth, let token = KeychainManager.accessToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        if let body, !(body is EmptyBody) {
            request.httpBody = try encoder.encode(body)
        }

        return request
    }

    private func execute<T: Decodable>(
        _ request: URLRequest,
        endpoint: APIEndpoint
    ) async throws -> T {
        do {
            let (data, response) = try await session.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else {
                throw APIError.invalidResponse
            }

            if httpResponse.statusCode == 401 && endpoint.requiresAuth {
                try await refreshTokenIfNeeded()
                let retryRequest = try buildRequest(endpoint)
                let (retryData, retryResponse) = try await session.data(for: retryRequest)
                guard let retryHttp = retryResponse as? HTTPURLResponse else {
                    throw APIError.invalidResponse
                }
                guard (200...299).contains(retryHttp.statusCode) else {
                    throw APIError.unauthorized
                }
                return try decoder.decode(T.self, from: retryData)
            }

            guard (200...299).contains(httpResponse.statusCode) else {
                try self.throwForFailedResponse(data, statusCode: httpResponse.statusCode)
                throw APIError.httpError(
                    statusCode: httpResponse.statusCode,
                    message: nil
                )
            }

            return try decoder.decode(T.self, from: data)
        } catch let error as APIError {
            throw error
        } catch let error as DecodingError {
            throw APIError.decodingError(error)
        } catch {
            throw APIError.networkError(error)
        }
    }

    private func refreshTokenIfNeeded() async throws {
        guard !isRefreshing else { return }
        isRefreshing = true
        defer { isRefreshing = false }

        guard let refreshToken = KeychainManager.refreshToken else {
            KeychainManager.clearTokens()
            throw APIError.unauthorized
        }

        let request = try buildRequest(
            .refreshToken,
            body: RefreshTokenRequest(refreshToken: refreshToken)
        )
        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            KeychainManager.clearTokens()
            throw APIError.unauthorized
        }

        let tokens = try decoder.decode(RefreshTokenResponse.self, from: data)
        KeychainManager.accessToken = tokens.accessToken
        KeychainManager.refreshToken = tokens.refreshToken
    }
}
