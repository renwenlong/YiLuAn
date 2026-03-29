import Foundation

enum APIError: Error, LocalizedError {
    case invalidURL
    case invalidResponse
    case httpError(statusCode: Int, message: String?)
    case decodingError(Error)
    case networkError(Error)
    case unauthorized

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Invalid URL"
        case .invalidResponse: return "Invalid response from server"
        case .httpError(let code, let msg): return "HTTP \(code): \(msg ?? "Unknown error")"
        case .decodingError(let err): return "Decoding error: \(err.localizedDescription)"
        case .networkError(let err): return "Network error: \(err.localizedDescription)"
        case .unauthorized: return "Unauthorized"
        }
    }
}

struct EmptyBody: Encodable {}

struct ErrorResponse: Decodable {
    let detail: String?
}

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
        let (_, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        if httpResponse.statusCode == 401 && endpoint.requiresAuth {
            try await refreshTokenIfNeeded()
            let retryRequest = try buildRequest(endpoint, body: body)
            let (_, retryResponse) = try await session.data(for: retryRequest)
            guard let retryHttp = retryResponse as? HTTPURLResponse,
                  (200...299).contains(retryHttp.statusCode) else {
                throw APIError.unauthorized
            }
            return
        }
        guard (200...299).contains(httpResponse.statusCode) else {
            throw APIError.httpError(statusCode: httpResponse.statusCode, message: nil)
        }
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
                let errorMsg = try? decoder.decode(ErrorResponse.self, from: data)
                throw APIError.httpError(
                    statusCode: httpResponse.statusCode,
                    message: errorMsg?.detail
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
