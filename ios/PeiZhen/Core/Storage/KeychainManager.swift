import Foundation
import Security

enum KeychainManager {
    enum KeychainError: Error {
        case duplicateEntry
        case itemNotFound
        case unexpectedStatus(OSStatus)
        case dataConversionError
    }

    static func save(key: String, value: String) throws {
        guard let data = value.data(using: .utf8) else {
            throw KeychainError.dataConversionError
        }

        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key,
            kSecValueData as String: data
        ]

        // Delete existing item first
        SecItemDelete(query as CFDictionary)

        let status = SecItemAdd(query as CFDictionary, nil)
        guard status == errSecSuccess else {
            throw KeychainError.unexpectedStatus(status)
        }
    }

    static func get(key: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]

        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)

        guard status == errSecSuccess,
              let data = result as? Data,
              let string = String(data: data, encoding: .utf8) else {
            return nil
        }
        return string
    }

    static func delete(key: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key
        ]
        SecItemDelete(query as CFDictionary)
    }

    // MARK: - Convenience for tokens

    static var accessToken: String? {
        get { get(key: AppConfig.accessTokenKey) }
        set {
            if let value = newValue {
                try? save(key: AppConfig.accessTokenKey, value: value)
            } else {
                delete(key: AppConfig.accessTokenKey)
            }
        }
    }

    static var refreshToken: String? {
        get { get(key: AppConfig.refreshTokenKey) }
        set {
            if let value = newValue {
                try? save(key: AppConfig.refreshTokenKey, value: value)
            } else {
                delete(key: AppConfig.refreshTokenKey)
            }
        }
    }

    static func clearTokens() {
        delete(key: AppConfig.accessTokenKey)
        delete(key: AppConfig.refreshTokenKey)
    }
}
